import os
import requests
from pathlib import Path

# Configuration from environment (falls back to defaults)
SSH_TARGET = os.environ.get("BENCHMARK_TARGET", "meluxina")
SLURM_PROJECT = os.environ.get("SLURM_PROJECT", None)  # No default - must be set by user

# Port configuration (useful when defaults are already in use)
PROMETHEUS_PORT = int(os.environ.get("PROMETHEUS_PORT", "9090"))
GRAFANA_PORT = int(os.environ.get("GRAFANA_PORT", "3000"))
SCRAPER_PORT = int(os.environ.get("SCRAPER_PORT", "8010"))


def _check_slurm_project_configured():
    """Check if SLURM_PROJECT is set, prompt user if not."""
    if SLURM_PROJECT is None:
        print("\n" + "="*60)
        print("ERROR: SLURM_PROJECT environment variable is not set!")
        print("="*60)
        print("\nPlease set your MeluXina Slurm project ID (NOT your username):")
        print("  export SLURM_PROJECT=p200XXX")
        print("\nTo find your project ID, run:")
        print("  ssh meluxina 'sacctmgr show assoc where user=$USER format=Account -P'")
        print("\nTo make this permanent, add to ~/.bashrc:")
        print("  echo 'export SLURM_PROJECT=p200XXX' >> ~/.bashrc")
        print("="*60 + "\n")
        return False
    return True


class MonitorManager:
    """
    Manages the Prometheus + Grafana monitoring stack job.
    Handles dynamic updating of Prometheus targets.
    """
    
    def __init__(self, repo_root=None, ssh_target=None):
        self.repo_root = Path(repo_root) if repo_root else Path(os.getcwd())
        self.ssh_target = ssh_target or SSH_TARGET
        self.prometheus_config_path = self.repo_root / "utils/monitoring/prometheus_dir/prometheus.yaml"
        self.job_name = "monitors"
        self.script_path = self.repo_root / "batch_scripts/start_monitors.sh"
        self.sif_dir = self.repo_root / "utils/sif-images"
        self._remote_repo_root = None  # Cached remote repo path

    def _get_remote_repo_root(self):
        """Dynamically detect remote repository root via SSH."""
        if self._remote_repo_root:
            return self._remote_repo_root
        
        import subprocess
        try:
            # Try to detect the repo path on the remote by checking common locations
            cmd = ["ssh", self.ssh_target, "echo $HOME"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                home = res.stdout.strip()
                # Assume repo is at ~/repos/Team1_EUMASTER4HPC2526
                self._remote_repo_root = f"{home}/repos/Team1_EUMASTER4HPC2526"
            else:
                # Fallback to a reasonable default
                self._remote_repo_root = "/home/users/$USER/repos/Team1_EUMASTER4HPC2526"
        except Exception:
            self._remote_repo_root = "/home/users/$USER/repos/Team1_EUMASTER4HPC2526"
        
        return self._remote_repo_root

    def setup_stack(self):
        """
        Performs initial setup:
        1. Checks if images exist.
        2. If not, submits a setup job to pull images and install dependencies.
        3. Waits for setup to complete.
        """
        required_images = [
            "grafana_latest.sif",
            "prometheus_latest.sif",
            "opentelemetry-collector_0.118.0.sif"
        ]
        
        # Determine paths
        if self._is_local():
             sif_dir = self.sif_dir
             repo_root = self.repo_root
        else:
             repo_root = self._get_remote_repo_root()
             sif_dir = f"{repo_root}/utils/sif-images"

        # Check for missing images
        missing = []
        if self._is_local():
            missing = [img for img in required_images if not (self.sif_dir / img).exists()]
        else:
            # Remote check via SSH
            cmd = ["ssh", self.ssh_target, f"ls {sif_dir}"]
            import subprocess
            res = subprocess.run(cmd, capture_output=True, text=True)
            existing_files = res.stdout.split()
            missing = [img for img in required_images if img not in existing_files]
        
        if not missing:
            print("✓ All monitoring images verified.")
            return True
            
        print(f"⚠ Missing images: {missing}")
        print("Submitting setup job to pull images (this may take 2-3 minutes)...")
        
        # Create setup script content
        setup_script_content = f"""#!/bin/bash -l
#SBATCH --qos=default
#SBATCH --partition=cpu
#SBATCH --account={SLURM_ACCOUNT}
#SBATCH --time=00:30:00
#SBATCH --job-name=monitor-setup
#SBATCH --output={repo_root}/logs/monitor_setup.out
#SBATCH --error={repo_root}/logs/monitor_setup.err

module load Apptainer 2>/dev/null || true

mkdir -p {sif_dir}
cd {sif_dir}

# Pull images
apptainer pull --force grafana_latest.sif docker://grafana/grafana:latest
apptainer pull --force prometheus_latest.sif docker://prom/prometheus:latest
apptainer pull --force opentelemetry-collector_0.118.0.sif docker://otel/opentelemetry-collector:0.118.0

# Install Python dependencies for scraper (user-level)
pip install --user prometheus_client psutil

echo "Setup Complete"
"""
        
        # Write script
        if self._is_local():
            setup_script_path = self.repo_root / "logs/setup_monitors.sh"
            setup_script_path.parent.mkdir(exist_ok=True)
            with open(setup_script_path, "w") as f:
                f.write(setup_script_content)
        else:
            setup_script_path = f"{repo_root}/logs/setup_monitors.sh"
            self._write_remote_file(setup_script_path, [setup_script_content])
            
        # Submit job
        import subprocess
        try:
            cmd = ["sbatch", str(setup_script_path)]
            if not self._is_local():
                cmd = ["ssh", self.ssh_target, f"sbatch {setup_script_path}"]

            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                 raise subprocess.CalledProcessError(res.returncode, cmd, output=res.stdout, stderr=res.stderr)

            # Parse Job ID
            # sbatch output: "Submitted batch job 12345"
            job_id_line = res.stdout.strip()
            job_id = job_id_line.split()[-1]
            print(f"✓ Setup job submitted: {job_id}")
            
            # Wait loop
            print("Waiting for setup to complete...")
            import time
            while True:
                time.sleep(10)
                # Check status
                q_cmd = ["squeue", "-j", job_id, "--noheader"]
                if not self._is_local():
                    q_cmd = ["ssh", self.ssh_target, f"squeue -j {job_id} --noheader"]
                
                q_res = subprocess.run(q_cmd, capture_output=True, text=True)
                if not q_res.stdout.strip():
                    break
                    
            # Verify result (re-check missing)
            if self._is_local():
                 still_missing = [img for img in required_images if not (self.sif_dir / img).exists()]
            else:
                 cmd = ["ssh", self.ssh_target, f"ls {sif_dir}"]
                 res = subprocess.run(cmd, capture_output=True, text=True)
                 existing_files = res.stdout.split()
                 still_missing = [img for img in required_images if img not in existing_files]

            if still_missing:
                print(f"❌ Setup failed. Missing images: {still_missing}")
                return False
                
            print("✓ Setup finished successfully!")
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"Error submitting setup job: {e}")
            if e.stderr:
                print(f"Stderr: {e.stderr}")
            return False

    def _sync_monitoring_code(self):
        """Sync local monitoring code to remote before starting stack."""
        if self._is_local():
            return True  # No sync needed for local runs
        
        import subprocess
        
        print("Syncing monitoring code to remote...")
        
        remote_repo = self._get_remote_repo_root()
        local_repo = self.repo_root
        
        # Files/directories to sync
        sync_items = [
            ("src/monitoring/", f"{remote_repo}/src/monitoring/"),
            ("batch_scripts/start_monitors.sh", f"{remote_repo}/batch_scripts/"),
            ("config/grafana/", f"{remote_repo}/config/grafana/"),
        ]
        
        for local_path, remote_path in sync_items:
            local_full = local_repo / local_path
            if not local_full.exists():
                continue
            
            # Use rsync via SSH
            rsync_cmd = [
                "rsync", "-avz", "--delete",
                "-e", f"ssh",
                str(local_full),
                f"{self.ssh_target}:{remote_path}"
            ]
            
            try:
                subprocess.run(rsync_cmd, capture_output=True, text=True, check=True, timeout=60)
            except subprocess.CalledProcessError as e:
                print(f"  Warning: Failed to sync {local_path}: {e}")
            except subprocess.TimeoutExpired:
                print(f"  Warning: Sync timeout for {local_path}")
        
        print("✓ Code sync complete")
        return True

    def start_stack(self):
        """Start the monitoring stack via sbatch (supports remote)."""
        import subprocess
        
        # Check if project is configured
        if not _check_slurm_project_configured():
            return False
        
        # Sync code to remote first
        if not self._is_local():
            self._sync_monitoring_code()
        
        script = self.script_path
        account = SLURM_PROJECT  # From environment (project ID)
        
        cmd = ["sbatch", f"--account={account}", str(script)]
        if not self._is_local():
            remote_repo = self._get_remote_repo_root()
            remote_script = f"{remote_repo}/batch_scripts/start_monitors.sh"
            # cd into repo first so SLURM_SUBMIT_DIR is correct
            # Pass account via command line since SBATCH header vars don't expand
            cmd = ["ssh", self.ssh_target, f"cd {remote_repo} && sbatch --account={account} {remote_script}"]
            
        try:
             res = subprocess.run(cmd, capture_output=True, text=True, check=True)
             print(f"✓ Stack job submitted: {res.stdout.strip()}")
             return True
        except subprocess.CalledProcessError as e:
             print(f"Error starting stack: {e}")
             if e.stderr:
                 print(f"Stderr: {e.stderr}")
             return False

    def stop_stack(self):
        """Stop the monitoring stack (supports remote)."""
        job_id, _, _ = self.check_status()
        if job_id:
            import subprocess
            cmd = ["scancel", job_id]
            if not self._is_local():
                cmd = ["ssh", self.ssh_target, f"scancel {job_id}"]
            
            subprocess.run(cmd, check=True)
            print(f"✓ Stack job {job_id} cancelled.")
        else:
            print("Stack not running.")

    def check_status(self):
        """
        Check if the monitoring job is running and get its IP address.
        Supports both local execution (on login node) and remote execution (via SSH).
        Returns: (job_id, ip_address, is_ready)
        """
        import shutil
        import subprocess

        # Detect mode
        use_ssh = False
        if not shutil.which("squeue"):
            use_ssh = True
            
        job_id = None
        
        # 1. Get Job ID
        cmd = ["squeue", "--name", self.job_name, "--noheader", "--format=%i"]
        if use_ssh:
            # Assumes 'meluxina' host is configured in SSH config or accessible
            cmd = ["ssh", self.ssh_target, "squeue", "--name", self.job_name, "--noheader", "--format=%i"]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                job_id = result.stdout.strip()
        except Exception:
            pass

        if not job_id:
            return None, None, False

        # 2. Get IP Address from log file
        # IMPORTANT: When using SSH, we must use the REMOTE repository path, not local.
        # We'll validly assume the structure is standard on the remote side.
        # Ideally this comes from configuration, but for now we hardcode the known remote root
        # or derive it if possible. Let's rely on the relative path from where sbatch usually runs? 
        # No, sbatch output paths are absolute in our script generation.
        
        if use_ssh:
             # Use dynamically detected remote repo path
             repo_path = self._get_remote_repo_root()
             remote_log_path = f"{repo_path}/logs/monitors/monitors.out"
        else:
             remote_log_path = self.repo_root / "logs/monitors/monitors.out"
        
        ip_address = None
        try:
            if use_ssh:
                cat_cmd = ["ssh", self.ssh_target, "cat", remote_log_path]
                res = subprocess.run(cat_cmd, capture_output=True, text=True)
                content = res.stdout
            else:
                if Path(remote_log_path).exists():
                    with open(remote_log_path, "r") as f:
                        content = f.read()
                else:
                    content = ""

            for line in content.splitlines():
                if "IP ADDRESS:" in line:
                    ip_address = line.split(":")[-1].strip()
        except Exception:
            pass
        
        return job_id, ip_address, True

    def _is_local(self):
        """Check if we are running on the cluster (has squeue) or local."""
        import shutil
        return shutil.which("squeue") is not None

    def _read_remote_file(self, path):
        import subprocess
        cmd = ["ssh", self.ssh_target, "cat", str(path)]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise Exception(f"Failed to read remote file {path}")
        return res.stdout.splitlines(keepends=True)

    def _write_remote_file(self, path, content_lines):
        import subprocess
        import tempfile
        import os
        
        # Write to local temp file first
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp:
            tmp.writelines(content_lines)
            tmp_path = tmp.name
            
        try:
            # SCP to remote
            cmd = ["scp", tmp_path, f"{self.ssh_target}:{path}"]
            subprocess.run(cmd, check=True)
        finally:
            os.unlink(tmp_path)

    def _reload_prometheus(self, monitor_ip):
        """Send reload signal to Prometheus."""
        if self._is_local():
            try:
                reload_url = f"http://{monitor_ip}:{PROMETHEUS_PORT}/-/reload"
                print(f"Triggering reload at {reload_url}...")
                response = requests.post(reload_url, timeout=5)
                if response.status_code == 200:
                    print("✓ Prometheus reloaded successfully")
                else:
                    print(f"⚠ Prometheus reload returned status {response.status_code}")
            except Exception as e:
                print(f"⚠ Could not reload Prometheus locally: {e}")
        else:
            # Remote (Local laptop) -> SSH -> Curl on cluster
            print(f"Triggering remote reload via SSH...")
            # Use curl with --max-time to prevent hanging
            cmd = ["ssh", self.ssh_target, f"curl --max-time 5 -X POST http://{monitor_ip}:{PROMETHEUS_PORT}/-/reload"]
            try:
                import subprocess
                subprocess.run(cmd, check=True, timeout=10, capture_output=True)
                print("✓ Prometheus reloaded successfully (via SSH)")
            except Exception as e:
                print(f"⚠ Could not reload Prometheus remotely: {e}")

    def update_prometheus_target(self, job_name, ip_address, port):
        """
        Update the Prometheus config file with a new target and reload Prometheus.
        """
        if not ip_address:
            print(f"Error: IP address for {job_name} is empty.")
            return

        # Get monitor IP to reload
        _, monitor_ip, _ = self.check_status()
        if not monitor_ip:
            print("Error: Monitor server IP is unknown. Cannot reload Prometheus.")
            return

        # Determine path
        if self._is_local():
            config_path = self.prometheus_config_path
            if not config_path.exists():
                 print(f"Error: Prometheus config not found at {config_path}")
                 return
        else:
            # Use dynamically detected remote repo path
            repo_path = self._get_remote_repo_root()
            config_path = f"{repo_path}/utils/monitoring/prometheus_dir/prometheus.yaml"

        print(f"Updating Prometheus config for {job_name} at {ip_address}:{port}...")

        try:
            if self._is_local():
                with open(config_path, 'r') as f:
                    lines = f.readlines()
            else:
                lines = self._read_remote_file(config_path)

            updated_lines = []
            updated = False
            job_found = False
            in_job_section = False
            
            i = 0
            while i < len(lines):
                line = lines[i]
                if f"- job_name: '{job_name}'" in line or f'- job_name: {job_name}' in line:
                    job_found = True
                    in_job_section = True
                    updated_lines.append(line)
                    # Skip until we find targets
                elif in_job_section and "targets:" in line:
                    updated_lines.append(line)
                    # Skip next line (the existing target)
                    i += 1 
                    # Add new target
                    updated_lines.append(f"          - '{ip_address}:{port}'\n")
                    updated = True
                    in_job_section = False # Done with this section
                else:
                    if in_job_section and line.strip().startswith("- job_name"): 
                         in_job_section = False
                    updated_lines.append(line)
                i += 1
            
            if not job_found:
                # Append new job
                updated_lines.append(f"\n")
                updated_lines.append(f"  - job_name: '{job_name}'\n")
                updated_lines.append(f"    static_configs:\n")
                updated_lines.append(f"      - targets:\n")
                updated_lines.append(f"          - '{ip_address}:{port}'\n")
                updated = True

            if self._is_local():
                with open(config_path, 'w') as f:
                    f.writelines(updated_lines)
            else:
                self._write_remote_file(config_path, updated_lines)

            print(f"✓ Prometheus config updated.")
            self._reload_prometheus(monitor_ip)
            
        except Exception as e:
            print(f"Error updating Prometheus config: {e}")
