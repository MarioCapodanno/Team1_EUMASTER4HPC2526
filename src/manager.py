#!/usr/bin/env python3
"""
Manager module for the AI Factory Benchmarking Framework.

The Manager class is responsible for:
- Deploying services to the cluster
- Creating and submitting sbatch scripts
- Monitoring job status
- Creating Service objects with cluster information
- Persisting service state to storage
"""

import time
from pathlib import Path
from datetime import datetime
from typing import Optional, List

#TODO: maybe here we should import and use the create_communicator factory method
# but it works so leave it for now
from communicator import SSHCommunicator
from service import Service
from storage import get_storage_manager, StorageManager


class Manager:
    """
    Manager class for deploying and managing services on the cluster.
    
    This class handles the lifecycle of services:
    1. Parse recipe configuration
    2. Generate sbatch scripts from templates
    3. Connect to cluster via SSH
    4. Submit jobs
    5. Wait for jobs to start
    6. Create Service objects with cluster information
    7. Save service state to storage
    """
    
    def __init__(
        self,
        target: str,
        benchmark_id: str,
        working_dir: Optional[str] = None,
        storage_manager: Optional[StorageManager] = None
    ):
        """
        Initialize the Manager.
        
        Args:
            target: SSH target (alias or hostname) for the cluster
            benchmark_id: Unique identifier for this benchmark run
            working_dir: Working directory on cluster (default: ~/benchmark_{benchmark_id})
            storage_manager: Storage manager for persisting state
        """
        self.target = target
        self.benchmark_id = benchmark_id
        self.working_dir = working_dir or f"~/benchmark_{benchmark_id}"
        self.abs_working_dir: Optional[str] = None  # Will be set after connection
        self.storage_manager = storage_manager or get_storage_manager()
        self.communicator: Optional[SSHCommunicator] = None
    
    def connect(self) -> bool:
        """
        Establish connection to the cluster.
        
        Returns:
            True if connection successful, False otherwise
        """
        self.communicator = SSHCommunicator(target=self.target)
        connected = self.communicator.connect()
        
        if connected:
            # Resolve absolute working directory
            self._resolve_working_dir()
        
        return connected
    
    def _resolve_working_dir(self) -> None:
        """Resolve the absolute working directory path on the cluster."""
        if self.working_dir.startswith("~"):
            result = self.communicator.execute_command("echo $HOME")
            if result.success:
                home_dir = result.stdout.strip()
                self.abs_working_dir = self.working_dir.replace("~", home_dir)
            else:
                # Fallback to using ~ as-is
                self.abs_working_dir = self.working_dir
        else:
            self.abs_working_dir = self.working_dir
    
    def disconnect(self) -> None:
        """Close connection to the cluster."""
        if self.communicator:
            self.communicator.disconnect()
    
    def _ensure_connected(self) -> None:
        """Ensure we have an active connection."""
        if not self.communicator or not self.communicator._connection:
            raise RuntimeError("Not connected to cluster. Call connect() first.")
    
    def _create_sbatch_script(
        self,
        service_name: str,
        container_image: str,
        service_command: str,
        time_limit: str = "01:00:00",
        partition: str = "gpu",
        account: str = "p200981",
        num_nodes: int = 1,
        num_gpus: int = 1
    ) -> str:
        """
        Create an sbatch script for deploying a service.
        
        Args:
            service_name: Name of the service
            container_image: Container image to run (e.g., "postgres:latest", "ollama/ollama:latest")
            service_command: Command to run in the container (e.g., "postgres", "ollama serve")
            time_limit: Time limit for the job
            partition: Slurm partition
            account: Slurm account/project ID
            num_nodes: Number of nodes
            num_gpus: Number of GPUs
            
        Returns:
            Content of the sbatch script
        """
        # Simple f-string template for now (can be replaced with Jinja2 later)
        script = f"""#!/bin/bash -l
#SBATCH --job-name={service_name}
#SBATCH --time={time_limit}
#SBATCH --qos=default
#SBATCH --partition={partition}
#SBATCH --account={account}
#SBATCH --nodes={num_nodes}
#SBATCH --ntasks={num_nodes}
#SBATCH --ntasks-per-node=1
#SBATCH --gpus={num_gpus}
#SBATCH --output={self.abs_working_dir}/logs/{service_name}_%j.out
#SBATCH --error={self.abs_working_dir}/logs/{service_name}_%j.err

echo "==============================================="
echo "Service: {service_name}"
echo "Date: $(date)"
echo "Hostname: $(hostname -s)"
echo "Working Directory: $(pwd)"
echo "==============================================="

# Load required modules
module add Apptainer

# Pull container image if not already present
echo "Pulling container image: {container_image}"
apptainer pull docker://{container_image}

# Extract image name for the .sif file
IMAGE_NAME=$(echo {container_image} | sed 's|.*/||' | sed 's|:.*||')
SIF_FILE="${{IMAGE_NAME}}_latest.sif"

echo "Running container: $SIF_FILE"

# Write service information to a file that can be read later
echo "$(hostname)" > {self.working_dir}/{service_name}.hostname
echo "$SLURM_JOB_ID" > {self.working_dir}/{service_name}.jobid

# Run the service
apptainer exec --nv "$SIF_FILE" {service_command}
"""
        return script
    
    def deploy_service(
        self,
        service_name: str,
        container_image: str,
        service_command: str,
        wait_for_start: bool = True,
        max_wait_time: int = 300,
        **sbatch_kwargs
    ) -> Optional[Service]:
        """
        Deploy a service to the cluster.
        
        This method:
        1. Creates an sbatch script
        2. Uploads it to the cluster
        3. Submits the job
        4. Waits for the job to start (optional)
        5. Retrieves hostname and other info
        6. Creates a Service object
        7. Saves the service to storage
        
        Args:
            service_name: Name of the service
            container_image: Container image to run (e.g., "postgres:latest", "redis:latest")
            service_command: Command to run in container (e.g., "postgres", "redis-server")
            wait_for_start: Whether to wait for job to start running
            max_wait_time: Maximum time to wait for job to start (seconds)
            **sbatch_kwargs: Additional sbatch parameters (partition, num_gpus, time_limit, etc.)
            
        Returns:
            Service object if successful, None otherwise
        """
        self._ensure_connected()
        
        print(f"Deploying service: {service_name}")
        print(f"  Container image: {container_image}")
        print(f"  Benchmark ID: {self.benchmark_id}")
        
        # Create working directory structure on cluster
        print(f"Creating working directory: {self.abs_working_dir}")
        
        # Create directories
        result = self.communicator.execute_command(f"mkdir -p {self.abs_working_dir}/logs")
        if not result.success:
            print(f"Error: Failed to create logs directory: {result.stderr}")
            return None
        
        result = self.communicator.execute_command(f"mkdir -p {self.abs_working_dir}/scripts")
        if not result.success:
            print(f"Error: Failed to create scripts directory: {result.stderr}")
            return None
        
        # Generate sbatch script
        script_content = self._create_sbatch_script(
            service_name=service_name,
            container_image=container_image,
            service_command=service_command,
            **sbatch_kwargs
        )
        
        # Write script locally first
        local_script_path = Path(f"/tmp/{service_name}_{self.benchmark_id}.sh")
        local_script_path.write_text(script_content)
        
        # Upload script to cluster (use absolute path)
        remote_script_path = f"{self.abs_working_dir}/scripts/{service_name}.sh"
        print(f"Uploading sbatch script to: {remote_script_path}")
        
        if not self.communicator.upload_file(local_script_path, remote_script_path):
            print(f"Error: Failed to upload script")
            return None
        
        # Submit job
        print(f"Submitting job...")
        job_id = self.communicator.submit_job(remote_script_path)
        
        if not job_id:
            print(f"Error: Failed to submit job")
            return None
        
        print(f"✓ Job submitted with ID: {job_id}")
        
        # Create initial service object
        service = Service(
            name=service_name,
            container_image=container_image,
            job_id=job_id,
            working_dir=self.working_dir,
            submit_time=datetime.now(),
            log_file=f"{self.working_dir}/logs/{service_name}_{job_id}.out"
        )
        
        # Save initial state
        service.save(self.benchmark_id, self.storage_manager)
        print(f"✓ Service state saved to storage")
        
        # Wait for job to start if requested
        if wait_for_start:
            print(f"Waiting for job to start (max {max_wait_time}s)...")
            if self._wait_for_job_to_start(job_id, max_wait_time):
                print(f"✓ Job is running")
                
                # Update service with runtime information
                service.start_time = datetime.now()
                
                # Try to get hostname
                hostname = self._get_service_hostname(service_name)
                if hostname:
                    service.hostname = hostname
                    service.node_name = hostname
                    print(f"✓ Service running on: {hostname}")
                
                # Save updated state
                service.save(self.benchmark_id, self.storage_manager)
            else:
                print(f"Warning: Job did not start within {max_wait_time}s")
        
        return service
    
    def _wait_for_job_to_start(self, job_id: str, max_wait_time: int) -> bool:
        """
        Wait for a job to transition from PENDING to RUNNING.
        
        Args:
            job_id: Slurm job ID
            max_wait_time: Maximum time to wait in seconds
            
        Returns:
            True if job started, False if timeout
        """
        start_time = time.time()
        
        while time.time() - start_time < max_wait_time:
            status = self.communicator.get_job_status(job_id)
            
            if status == "RUNNING":
                return True
            elif status in ["COMPLETED", "FAILED", "CANCELLED"]:
                print(f"Job ended with status: {status}")
                return False
            
            # Wait a bit before checking again
            time.sleep(5)
        
        return False
    
    def _get_service_hostname(self, service_name: str) -> Optional[str]:
        """
        Get the hostname where a service is running.
        
        Reads from the hostname file written by the sbatch script.
        
        Args:
            service_name: Name of the service
            
        Returns:
            Hostname or None if not available
        """
        hostname_file = f"{self.abs_working_dir}/{service_name}.hostname"
        
        # Check if file exists
        result = self.communicator.execute_command(f"test -e {hostname_file}")
        if not result.success:
            return None
        
        try:
            result = self.communicator.execute_command(f"cat {hostname_file}")
            if result.success and result.stdout:
                return result.stdout.strip()
        except Exception as e:
            print(f"Error reading hostname file: {e}")
        
        return None
    
    def get_job_status(self, job_id: str) -> Optional[str]:
        """
        Get the status of a Slurm job.
        
        Args:
            job_id: Slurm job ID
            
        Returns:
            Job status string or None
        """
        self._ensure_connected()
        return self.communicator.get_job_status(job_id)
    
    def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a Slurm job.
        
        Args:
            job_id: Slurm job ID
            
        Returns:
            True if successful
        """
        self._ensure_connected()
        return self.communicator.cancel_job(job_id)
    
    def load_service(self, service_name: str) -> Optional[Service]:
        """
        Load a service from storage.
        
        Args:
            service_name: Name of the service to load
            
        Returns:
            Service object or None if not found
        """
        return Service.load(self.benchmark_id, service_name, self.storage_manager)
    
    def load_all_services(self) -> List[Service]:
        """
        Load all services for this benchmark.
        
        Returns:
            List of Service objects
        """
        return Service.load_all(self.benchmark_id, self.storage_manager)
    
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
        return False
