"""
Monitoring stack manager for Prometheus + Grafana.

Supports multiple backends:
1. Docker (preferred for local development)
2. Apptainer (for HPC environments)
3. External (user manages their own Prometheus pointing at /metrics)

The Flask app always exposes /metrics endpoint for Prometheus scraping,
so the monitoring stack is OPTIONAL - users can point any Prometheus at it.
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Optional

class StackManager:
    """
    Manages the Prometheus + Grafana monitoring stack.
    
    Supports Docker (local) and Apptainer (HPC) backends.
    Falls back gracefully when neither is available.
    """

    def __init__(self, base_dir: str = ".monitoring"):
        self.base_dir = Path(os.getcwd()) / base_dir
        self.config_dir = self.base_dir / "config"
        self.data_dir = self.base_dir / "data"
        self.images_dir = self.base_dir / "images"
        
        self.prometheus_port = 9090
        self.grafana_port = 3000
        self.api_port = 5000  # Flask app port
        
        # Detect available backend
        self._backend = self._detect_backend()

    def _detect_backend(self) -> Optional[str]:
        """Detect which container runtime is available."""
        # Check Docker first (preferred for local dev)
        if shutil.which("docker"):
            try:
                result = subprocess.run(
                    ["docker", "info"], 
                    capture_output=True, 
                    timeout=5
                )
                if result.returncode == 0:
                    return "docker"
            except (subprocess.TimeoutExpired, Exception):
                pass
        
        # Check Apptainer (HPC)
        if shutil.which("apptainer"):
            return "apptainer"
        
        # Try loading Apptainer module (HPC)
        try:
            result = subprocess.run(
                "module load Apptainer 2>/dev/null && which apptainer",
                shell=True,
                capture_output=True,
                executable="/bin/bash",
                timeout=10
            )
            if result.returncode == 0:
                return "apptainer"
        except Exception:
            pass
        
        return None

    def _ensure_dirs(self):
        """Create necessary directories."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        
        # Subdirs
        (self.data_dir / "prometheus").mkdir(exist_ok=True)
        (self.data_dir / "grafana").mkdir(exist_ok=True)

    def _run_docker_cmd(self, cmd: list) -> bool:
        """Run a Docker command."""
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            return True
        except subprocess.CalledProcessError as e:
            print(f"Docker command failed: {e.stderr.decode() if e.stderr else e}")
            return False

    def _run_apptainer_cmd(self, cmd: str) -> bool:
        """Run an Apptainer command with module loading."""
        full_cmd = f"module load Apptainer 2>/dev/null || true && {cmd}"
        try:
            subprocess.run(full_cmd, shell=True, check=True, executable="/bin/bash")
            return True
        except subprocess.CalledProcessError as e:
            print(f"Apptainer command failed: {e}")
            return False

    def configure(self, api_host: str = "localhost", api_port: int = 5000):
        """Generate configuration files."""
        self._ensure_dirs()
        self.api_port = api_port
        
        # Prometheus config template
        prom_config = f"""
global:
  scrape_interval: 5s
  
scrape_configs:
  - job_name: 'benchmark-framework'
    static_configs:
      - targets: ['{api_host}:{api_port}']
    metrics_path: /metrics
"""
        (self.config_dir / "prometheus.yml").write_text(prom_config)
        
        # Grafana datasources
        ds_config = f"""
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://localhost:{self.prometheus_port}
    isDefault: true
"""
        prov_dir = self.config_dir / "grafana" / "provisioning" / "datasources"
        prov_dir.mkdir(parents=True, exist_ok=True)
        (prov_dir / "datasources.yml").write_text(ds_config)

    def start(self) -> Dict[str, str]:
        """Start the monitoring stack."""
        if not self._backend:
            raise RuntimeError(
                "No container runtime available. "
                "The monitoring stack is OPTIONAL - you can point any external Prometheus "
                "at http://localhost:5000/metrics to scrape benchmark metrics."
            )
        
        self.configure(api_port=self.api_port)
        
        if self._backend == "docker":
            return self._start_docker()
        else:
            return self._start_apptainer()

    def _start_docker(self) -> Dict[str, str]:
        """Start with Docker."""
        print("Starting monitoring stack with Docker...")
        
        # Stop any existing containers first
        subprocess.run(
            ["docker", "rm", "-f", "prometheus-benchmark", "grafana-benchmark"],
            capture_output=True
        )
        
        # Start Prometheus
        print("  Starting Prometheus...")
        prom_cmd = [
            "docker", "run", "-d",
            "--name", "prometheus-benchmark",
            "-p", f"{self.prometheus_port}:9090",
            "-v", f"{self.config_dir}/prometheus.yml:/etc/prometheus/prometheus.yml",
            "-v", f"{self.data_dir}/prometheus:/prometheus",
            "--add-host", "host.docker.internal:host-gateway",
            "prom/prometheus:latest",
            "--config.file=/etc/prometheus/prometheus.yml",
            "--storage.tsdb.path=/prometheus",
            "--web.enable-lifecycle"
        ]
        
        if not self._run_docker_cmd(prom_cmd):
            raise RuntimeError("Failed to start Prometheus container")
        
        # Start Grafana
        print("  Starting Grafana...")
        graf_cmd = [
            "docker", "run", "-d",
            "--name", "grafana-benchmark",
            "-p", f"{self.grafana_port}:3000",
            "-v", f"{self.config_dir}/grafana/provisioning:/etc/grafana/provisioning",
            "-v", f"{self.data_dir}/grafana:/var/lib/grafana",
            "-e", "GF_AUTH_ANONYMOUS_ENABLED=true",
            "-e", "GF_AUTH_ANONYMOUS_ORG_ROLE=Admin",
            "grafana/grafana:latest"
        ]
        
        if not self._run_docker_cmd(graf_cmd):
            raise RuntimeError("Failed to start Grafana container")
        
        print("  ✓ Stack started!")
        return {
            "prometheus": f"http://localhost:{self.prometheus_port}",
            "grafana": f"http://localhost:{self.grafana_port}"
        }

    def _start_apptainer(self) -> Dict[str, str]:
        """Start with Apptainer (HPC)."""
        print("Starting monitoring stack with Apptainer...")
        
        prom_img = self.images_dir / "prometheus.sif"
        graf_img = self.images_dir / "grafana.sif"
        
        # Pull images if needed
        if not prom_img.exists():
            print("  Pulling Prometheus image...")
            self._run_apptainer_cmd(f"apptainer pull --force {prom_img} docker://prom/prometheus:latest")
        
        if not graf_img.exists():
            print("  Pulling Grafana image...")
            self._run_apptainer_cmd(f"apptainer pull --force {graf_img} docker://grafana/grafana:latest")
        
        # Start Prometheus
        print("  Starting Prometheus...")
        prom_cmd = (
            f"apptainer instance start "
            f"--bind {self.config_dir}/prometheus.yml:/etc/prometheus/prometheus.yml "
            f"--bind {self.data_dir}/prometheus:/prometheus "
            f"{prom_img} prometheus-instance "
            f"--config.file=/etc/prometheus/prometheus.yml "
            f"--storage.tsdb.path=/prometheus "
            f"--web.listen-address=:{self.prometheus_port}"
        )
        self._run_apptainer_cmd(prom_cmd)
        
        # Start Grafana
        print("  Starting Grafana...")
        graf_cmd = (
            f"apptainer instance start "
            f"--bind {self.config_dir}/grafana/provisioning:/etc/grafana/provisioning "
            f"--bind {self.data_dir}/grafana:/var/lib/grafana "
            f"--env GF_SERVER_HTTP_PORT={self.grafana_port} "
            f"--env GF_AUTH_ANONYMOUS_ENABLED=true "
            f"--env GF_AUTH_ANONYMOUS_ORG_ROLE=Admin "
            f"{graf_img} grafana-instance"
        )
        self._run_apptainer_cmd(graf_cmd)
        
        print("  ✓ Stack started!")
        return {
            "prometheus": f"http://localhost:{self.prometheus_port}",
            "grafana": f"http://localhost:{self.grafana_port}"
        }

    def stop(self):
        """Stop the monitoring stack."""
        print("Stopping monitoring stack...")
        
        if self._backend == "docker":
            subprocess.run(
                ["docker", "rm", "-f", "prometheus-benchmark", "grafana-benchmark"],
                capture_output=True
            )
        elif self._backend == "apptainer":
            self._run_apptainer_cmd("apptainer instance stop prometheus-instance 2>/dev/null || true")
            self._run_apptainer_cmd("apptainer instance stop grafana-instance 2>/dev/null || true")
        
        print("  ✓ Stack stopped")

    def status(self) -> Dict[str, bool]:
        """Check status of monitoring services."""
        prom_ok = False
        graf_ok = False
        
        try:
            result = subprocess.run(
                ["curl", "-sf", f"http://localhost:{self.prometheus_port}/-/healthy"],
                capture_output=True,
                timeout=3
            )
            prom_ok = result.returncode == 0
        except Exception:
            pass
            
        try:
            result = subprocess.run(
                ["curl", "-sf", f"http://localhost:{self.grafana_port}/api/health"],
                capture_output=True,
                timeout=3
            )
            graf_ok = result.returncode == 0
        except Exception:
            pass
        
        return {
            "prometheus": prom_ok, 
            "grafana": graf_ok,
            "backend": self._backend or "none"
        }
    
    def get_setup_instructions(self) -> str:
        """Get instructions for manual setup if no container runtime available."""
        return f"""
=== Manual Prometheus Setup ===

The monitoring stack is OPTIONAL. The Flask app always exposes metrics at:
  http://localhost:5000/metrics

To set up Prometheus manually:

1. Download Prometheus from https://prometheus.io/download/
2. Create prometheus.yml:

   global:
     scrape_interval: 5s
   scrape_configs:
     - job_name: 'benchmark-framework'
       static_configs:
         - targets: ['localhost:5000']
       metrics_path: /metrics

3. Run: ./prometheus --config.file=prometheus.yml

Then view metrics at: http://localhost:{self.prometheus_port}
"""
