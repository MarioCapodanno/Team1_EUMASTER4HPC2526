#!/usr/bin/env python3

import subprocess
import time
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from jinja2 import Environment, FileSystemLoader
# Support running as a script (no package) or as a module
try:  # type: ignore
    from .utils import wait_for_http  # type: ignore
except Exception:
    from utils import wait_for_http  # type: ignore


class ClientRunner:
    """Manages client deployment using the Jinja2 templates"""
    
    def __init__(self, template_dir: str = "templates", output_dir: str = "."):
        """
        Initialize the class.
        
        Args:
            template_dir: Directory containing Jinja2 templates
            output_dir: Directory to save generated scripts
        """
        # Resolve template_dir; if not found, try repo-level templates folder
        self.template_dir = Path(template_dir)
        if not self.template_dir.is_dir():
            repo_templates = Path(__file__).resolve().parents[2] / "templates"
            if repo_templates.is_dir():
                self.template_dir = repo_templates
            else:
                print(f"Warning: templates dir '{self.template_dir}' not found; proceeding anyway")
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            self.jinja_env = Environment(loader=FileSystemLoader(str(self.template_dir)))
        except Exception as e:
            print(f"Warning: Could not initialize Jinja2 environment: {e}")
            self.jinja_env = None
    
    def render_client_script(
        self,
        client_id: int,
        service_node: str,
        service_port: int = 11434,
        num_requests: int = 10,
        model: str = "mistral", # TODO: generalize beyond Ollama
        prompt_prefix: str = "Hello from", # TODO: generalize
        request_timeout: int = 60,
        request_interval: int = 1,
        slurm_config: Optional[Dict[str, Any]] = None,
        load_modules: Optional[List[str]] = None
    ) -> str:
        """
        Render sbatch script from template.
        [Render means in the jinja2 context to fill in the template with provided parameters.]
        
        Args:
            client_id:
            service_node: Target service node IP/hostname 
            service_port: Service port (default 11434 for Ollama)
            num_requests: Number of requests per client
            model: Model name to use
            prompt_prefix: Prompt prefix text
            request_timeout: Timeout per request in seconds
            request_interval: Delay between requests in seconds
            slurm_config: Dict with SLURM parameters
            load_modules: List of modules to load
            
        Returns:
            Rendered sbatch script as string
        """
        if not self.jinja_env:
            raise RuntimeError("Jinja2 environment not initialized")
        
        # Default SLURM configs
        if slurm_config is None:
            slurm_config = {
                "time_limit": "00:30:00",
                "qos": "default",
                "partition": "gpu",
                "account": "p200981",
                "num_nodes": 1,
                "num_tasks": 1,
                "tasks_per_node": 1
            }
        
        template = self.jinja_env.get_template("client.sbatch.j2")
        
        # Context for template rendering
        context = {
            "client_id": client_id,
            "service_node": service_node,
            "service_port": service_port,
            "num_requests": num_requests,
            "model": model,
            "prompt_prefix": prompt_prefix,
            "request_timeout": request_timeout,
            "request_interval": request_interval,
            "slurm": slurm_config,
            "load_modules": load_modules or []
        }
        
        return template.render(context)
    
    def submit_client_job(
        self,
        client_id: int,
        service_node: str,
        service_port: int = 11434,
        num_requests: int = 10,
        **kwargs
    ) -> str:
        """
        Render client script and submit as sbatch job.
        
        Args:
            client_id: Client identifier
            service_node: Target service node
            service_port: Service port
            num_requests: Number of requests
            **kwargs: Additional arguments for render_client_script
            
        Returns:
            Job ID as string
            
        Raises:
            RuntimeError: If job submission fails
        """
        # Render script from template
        script_content = self.render_client_script(
            client_id=client_id,
            service_node=service_node,
            service_port=service_port,
            num_requests=num_requests,
            **kwargs
        )
        
        # Save script to file
        script_name = self.output_dir / f"client_{client_id}.sh"
        with open(script_name, "w") as f:
            f.write(script_content)
        os.chmod(script_name, 0o755)
        
        print(f"Generated client script: {script_name}")
        
        # Submit to Slurm
        try:
            result = subprocess.run(
                ["sbatch", str(script_name)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"sbatch failed: {result.stderr}")
            
            job_id = result.stdout.strip().split()[-1]
            print(f"Client {client_id} submitted with job ID: {job_id}")
            return job_id
            
        except Exception as e:
            print(f"Failed to submit client {client_id}: {e}")
            raise


def client_runner(ip_addresses, num_clients: int = 2, template_dir: str = "templates", model: str = "mistral"):
    """
    Deploy client workloads.
    
    Args:
        ip_addresses: List of service node IP addresses
        num_clients: Number of client instances to spawn
        template_dir: Directory containing Jinja2 templates
        
    Returns:
        List of job IDs
    """
    print("CLIENT RUNNER")
    
    if not ip_addresses:
        print("No service IP addresses provided")
        return []
    
    service_node = ip_addresses[0]
    print(f"Starting {num_clients} clients for service at: {service_node}")
    
    # Wait actively for the service to become ready instead of a blind sleep
    # Extended timeout to allow model pull to complete
    print("Waiting for service HTTP readiness (up to 300s for model pull)...")
    if not wait_for_http(service_node, port=11434, path="/api/version", timeout=300, poll=3):
        print("Warning: Service did not report readiness in time; will proceed anyway.")
    
    runner = ClientRunner(template_dir=template_dir)
    
    # TODO: this configuration is still dependent on Ollama specifics. Need to generalize.
    job_ids = []
    for i in range(num_clients):
        try:
            job_id = runner.submit_client_job(
                client_id=i+1,
                service_node=service_node,
                service_port=11434,
                num_requests=10,
                model=model,
                prompt_prefix="Hello from",
                request_timeout=60,
                request_interval=1
            )
            job_ids.append(job_id)
        except Exception as e:
            print(f"Error submitting client {i+1}: {e}")
    
    return job_ids
