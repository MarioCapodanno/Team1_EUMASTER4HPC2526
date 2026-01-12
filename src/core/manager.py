#!/usr/bin/env python3
"""
Manager module for the AI Factory Benchmarking Framework.

The Manager class is responsible for:
- Deploying services to the cluster
- Creating and submitting sbatch scripts
- Monitoring job status
- Creating Service objects with cluster information
- Persisting service state to storage
- Writing benchmark artifacts (run.json, etc.)
"""

import time
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict

# TODO: maybe here we should import and use the create_communicator factory method
# but it works so leave it for now
from infra.communicator import SSHCommunicator
from infra.storage import get_storage_manager, StorageManager
from models.service import Service
from models.client import Client


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
        storage_manager: Optional[StorageManager] = None,
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
        num_gpus: int = 1,
        env_vars: Optional[Dict[str, str]] = None,
        gpus_per_node: Optional[int] = None,
        cpus_per_task: Optional[int] = None,
        memory: Optional[str] = None,
        constraints: Optional[str] = None,
        exclude_nodes: Optional[str] = None,
        volumes: Optional[List[str]] = None,
        modules: Optional[List[str]] = None,
        pre_run_commands: Optional[List[str]] = None,
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
        # Build environment variables setup
        env_vars_setup = ""
        apptainer_opts = ""

        if env_vars:
            env_exports = []
            for key, value in env_vars.items():
                env_exports.append(f"export {key}='{value}'")
            env_vars_setup = "\n".join(env_exports) + "\n"
            # Add environment variables to Apptainer
            apptainer_opts = " ".join(
                [f"--env {key}='{value}'" for key, value in env_vars.items()]
            )

        # Build GPU directive
        # Prefer explicit gpus_per_node if provided, else use num_gpus if > 0
        if gpus_per_node is not None:
            gpu_directive = f"#SBATCH --gpus-per-node={gpus_per_node}"
            use_gpu = True
        elif num_gpus > 0:
            gpu_directive = f"#SBATCH --gpus={num_gpus}"
            use_gpu = True
        else:
            gpu_directive = ""
            use_gpu = False

        # Use --nv flag only when GPUs are requested
        nv_flag = "--nv" if use_gpu else ""

        # Build other directives
        cpu_directive = f"#SBATCH --cpus-per-task={cpus_per_task}" if cpus_per_task else ""
        mem_directive = f"#SBATCH --mem={memory}" if memory else ""
        constraint_directive = f"#SBATCH --constraint={constraints}" if constraints else ""
        exclude_directive = f"#SBATCH --exclude={exclude_nodes}" if exclude_nodes else ""

        # Build apptainer volumes
        if volumes:
            bind_opts = " ".join([f"--bind {v}" for v in volumes])
            apptainer_opts = f"{apptainer_opts} {bind_opts}"

        # Build modules loading
        module_loads = ""
        if modules:
            module_loads = "\n".join([f"module load {m}" for m in modules])

        # Build pre-run commands
        pre_run = ""
        if pre_run_commands:
            pre_run = "\n".join(pre_run_commands)
        
        script = f"""#!/bin/bash -l
#SBATCH --job-name={service_name}
#SBATCH --time={time_limit}
#SBATCH --qos=default
#SBATCH --partition={partition}
#SBATCH --account={account}
#SBATCH --nodes={num_nodes}
#SBATCH --ntasks={num_nodes}
#SBATCH --ntasks-per-node=1
{gpu_directive}
{cpu_directive}
{mem_directive}
{constraint_directive}
{exclude_directive}
#SBATCH --output={self.abs_working_dir}/logs/{service_name}_%j.out
#SBATCH --error={self.abs_working_dir}/logs/{service_name}_%j.err

echo "==============================================="
echo "Service: {service_name}"
echo "Date: $(date)"
echo "Hostname: $(hostname -s)"
echo "Working Directory: $(pwd)"
echo "==============================================="

# Write service information EARLY so clients can discover us
# This MUST happen before container pull (which can be slow)
echo "$(hostname)" > {self.working_dir}/{service_name}.hostname
echo "$SLURM_JOB_ID" > {self.working_dir}/{service_name}.jobid

# Load required modules
module add Apptainer
{module_loads}

# Extract image name for the .sif file
IMAGE_NAME=$(echo {container_image} | sed 's|.*/||' | sed 's|:.*||')
SIF_FILE="${{IMAGE_NAME}}_latest.sif"

# Pull container image if not already present
if [ ! -f "$SIF_FILE" ]; then
  echo "Pulling container image: {container_image}"
  apptainer pull docker://{container_image}
else
  echo "Using cached container: $SIF_FILE"
fi

echo "Running container: $SIF_FILE"

# Set up environment variables for the container
{env_vars_setup}

# Pre-run commands
{pre_run}


# MONITORING SIDECAR
# ------------------
# Run hardware scraper in background (exposes metrics on port 8010)
echo "Starting hardware scraper..."
SCRAPER_SCRIPT="{self.abs_working_dir}/scripts/scraper.py"
if [ -f "$SCRAPER_SCRIPT" ]; then
    python3 "$SCRAPER_SCRIPT" --service-name "{service_name}" > {self.abs_working_dir}/logs/scraper_{service_name}.out 2>&1 &
    echo "Scraper started with PID $!"
else
    echo "Warning: Scraper script not found at $SCRAPER_SCRIPT"
fi

# Run the service
apptainer exec {nv_flag} {apptainer_opts} "$SIF_FILE" {service_command}
"""
        return script

    def _create_client_sbatch_script(
        self,
        client_name: str,
        service_name: str,
        service_hostname: Optional[str],
        service_port: Optional[int],
        service_url: str,
        benchmark_command: str,
        time_limit: str = "01:00:00",
        partition: str = "cpu",
        account: str = "p200981",
        num_nodes: int = 1,
        num_gpus: int = 0,
    ) -> str:
        """
        Create an sbatch script for deploying a benchmark client.

        Args:
            client_name: Name of the client
            service_name: Name of the service being benchmarked
            service_hostname: Hostname of the service to connect to
            service_port: Port of the service to connect to
            benchmark_command: Command to run for benchmarking
            time_limit: Time limit for the job
            partition: Slurm partition
            account: Slurm account/project ID
            num_nodes: Number of nodes
            num_gpus: Number of GPUs

        Returns:
            Content of the sbatch script
        """
        # Build service URL if hostname and port are available
        service_url = ""
        if service_hostname and service_port:
            service_url = f"http://{service_hostname}:{service_port}"

        script = f"""#!/bin/bash -l
#SBATCH --job-name={client_name}
#SBATCH --time={time_limit}
#SBATCH --qos=default
#SBATCH --partition={partition}
#SBATCH --account={account}
#SBATCH --nodes={num_nodes}
#SBATCH --ntasks={num_nodes}
#SBATCH --ntasks-per-node=1"""

        # Only add GPU directive if num_gpus > 0
        if num_gpus > 0:
            script += f"""
#SBATCH --gpus={num_gpus}"""

        script += f"""
#SBATCH --output={self.abs_working_dir}/logs/{client_name}_%j.out
#SBATCH --error={self.abs_working_dir}/logs/{client_name}_%j.err

echo "================================================"
echo "Client: {client_name}"
echo "Service: {service_name}"
echo "Date: $(date)"
echo "Hostname: $(hostname -s)"
echo "Working Directory: $(pwd)"
echo "================================================"

# Export service connection information
export SERVICE_NAME="{service_name}"
export SERVICE_HOSTNAME="{service_hostname or ""}"
export SERVICE_PORT="{service_port or ""}"
export SERVICE_URL="{service_url}"

# Export benchmark information for artifacts
export BENCHMARK_ID="{self.benchmark_id}"
export BENCHMARK_OUTPUT_DIR="{self.abs_working_dir}/metrics"
export CLIENT_NAME="{client_name}"

# Write client information to files
echo "$(hostname)" > {self.working_dir}/{client_name}.hostname
echo "$SLURM_JOB_ID" > {self.working_dir}/{client_name}.jobid

# Create metrics directory
mkdir -p {self.working_dir}/metrics

# Start Heartbeat (for real-time monitoring across nodes)
# Touch a file every 2 seconds so scraper knows we are alive
HEARTBEAT_FILE="{self.abs_working_dir}/heartbeat_{client_name}"
echo "Starting heartbeat at $HEARTBEAT_FILE"
(while true; do touch "$HEARTBEAT_FILE"; sleep 2; done) &
HEARTBEAT_PID=$!

# Run the benchmark command
echo "Running benchmark command..."
{benchmark_command}

# Stop Heartbeat
kill $HEARTBEAT_PID 2>/dev/null
rm -f "$HEARTBEAT_FILE"

echo "Benchmark completed at $(date)"
"""
        return script

    def deploy_client(
        self,
        client_name: str,
        service_name: str,
        benchmark_command: str,
        service: Optional[Service] = None,
        wait_for_start: bool = True,
        max_wait_time: int = 300,
        **sbatch_kwargs,
    ) -> Optional[Client]:
        """
        Deploy a benchmark client to the cluster.

        This method:
        1. Verifies the service is running (or uses provided service object)
        2. Creates an sbatch script for the client
        3. Uploads it to the cluster
        4. Submits the job
        5. Waits for the job to start (optional)
        6. Creates a Client object
        7. Saves the client to storage

        Args:
            client_name: Name of the client
            service_name: Name of the service to benchmark
            benchmark_command: Command to run for benchmarking
            service: Optional Service object (will be loaded if not provided)
            wait_for_start: Whether to wait for job to start running
            max_wait_time: Maximum time to wait for job to start (seconds)
            **sbatch_kwargs: Additional sbatch parameters (partition, num_gpus, time_limit, etc.)

        Returns:
            Client object if successful, None otherwise
        """
        self._ensure_connected()

        print(f"Deploying client: {client_name}")
        print(f"  Service: {service_name}")
        print(f"  Benchmark ID: {self.benchmark_id}")

        # Load service if not provided
        if service is None:
            service = self.load_service(service_name)
            if service is None:
                print(f"Error: Service '{service_name}' not found")
                return None

        # Verify service is running
        if service.job_id:
            status = self.get_job_status(service.job_id)
            if status != "RUNNING":
                print(
                    f"Error: Service '{service_name}' is not running (status: {status})"
                )
                return None
            print(f"✓ Service '{service_name}' is running (Job ID: {service.job_id})")
        else:
            print(f"Warning: Service '{service_name}' has no job_id")

        # Get fresh hostname from file (in case it wasn't saved to Service object)
        service_hostname = service.hostname
        if not service_hostname:
            # Poll for hostname with exponential backoff
            print("Waiting for service hostname to be available...")
            service_hostname = self._wait_for_service_hostname(
                service_name, max_wait_time=120  # Increased for GPU services
            )
            if service_hostname:
                print(f"✓ Retrieved service hostname: {service_hostname}")
            else:
                # FAIL-FAST: Cancel service job since we can't connect clients to it
                print("\n❌ FAIL-FAST: Hostname not available. Cancelling service job...")
                if service.job_id:
                    self.cancel_job(service.job_id)
                print("   Benchmark aborted. No resources wasted.")
                return None

        # Construct SERVICE_URL in Python to avoid None string issues
        service_url = ""
        if service_hostname and service.port:
            service_url = f"http://{service_hostname}:{service.port}"

        # Generate sbatch script
        script_content = self._create_client_sbatch_script(
            client_name=client_name,
            service_name=service_name,
            service_hostname=service_hostname,
            service_port=service.port,
            service_url=service_url,
            benchmark_command=benchmark_command,
            **sbatch_kwargs,
        )

        # Write script locally first
        local_script_path = Path(f"/tmp/{client_name}_{self.benchmark_id}.sh")
        local_script_path.write_text(script_content)

        # Upload script to cluster
        remote_script_path = f"{self.abs_working_dir}/scripts/{client_name}.sh"
        print(f"Uploading client sbatch script to: {remote_script_path}")

        if not self.communicator.upload_file(local_script_path, remote_script_path):
            print("Error: Failed to upload script")
            return None

        # Submit job
        print("Submitting client job...")
        job_id = self.communicator.submit_job(remote_script_path)

        if not job_id:
            print("Error: Failed to submit job")
            return None

        print(f"✓ Job submitted with ID: {job_id}")

        # Create initial client object
        client = Client(
            name=client_name,
            service_name=service_name,
            benchmark_command=benchmark_command,
            job_id=job_id,
            working_dir=self.working_dir,
            submit_time=datetime.now(),
            log_file=f"{self.working_dir}/logs/{client_name}_{job_id}.out",
            metrics_file=f"{self.working_dir}/metrics/{client_name}_metrics.json",
        )

        # Save initial state
        client.save(self.benchmark_id, self.storage_manager)
        print("✓ Client state saved to storage")

        # Wait for job to start if requested
        if wait_for_start:
            print(f"Waiting for client job to start (max {max_wait_time}s)...")
            job_started, final_status = self._wait_for_job_to_start(job_id, max_wait_time)
            
            if job_started:
                print("✓ Client job is running")

                # Update client with runtime information
                client.start_time = datetime.now()

                # Try to get hostname
                hostname = self._get_service_hostname(client_name)
                if hostname:
                    client.hostname = hostname
                    client.node_name = hostname
                    print(f"✓ Client running on: {hostname}")

                # Save updated state
                client.save(self.benchmark_id, self.storage_manager)
            else:
                print(f"Warning: Client job did not start within {max_wait_time}s (status: {final_status})")

        return client

    def deploy_multiple_clients(
        self,
        service_name: str,
        benchmark_command: str,
        num_clients: int,
        client_name_prefix: str = "client",
        service: Optional[Service] = None,
        service_type: Optional[str] = None,
        expected_model: Optional[str] = None,
        ready_check_timeout: int = 300,
        **sbatch_kwargs,
    ) -> List[Client]:
        """
        Deploy multiple benchmark clients to the cluster.

        Args:
            service_name: Name of the service to benchmark
            benchmark_command: Command to run for benchmarking
            num_clients: Number of clients to deploy
            client_name_prefix: Prefix for client names (will be numbered)
            service: Optional Service object (will be loaded if not provided)
            service_type: Type of service (ollama, vllm, etc.) for health checks
            expected_model: For LLM services, the model that should be loaded
            ready_check_timeout: Seconds to wait for service readiness
            **sbatch_kwargs: Additional sbatch parameters

        Returns:
            List of Client objects
        """
        clients = []

        # Load service once if not provided
        if service is None:
            service = self.load_service(service_name)
            if service is None:
                print(f"Error: Service '{service_name}' not found")
                return clients

        print(f"\nDeploying {num_clients} client(s) for service '{service_name}'...")

        # Get hostname first (needed for readiness check)
        service_hostname = service.hostname
        if not service_hostname:
            print("Waiting for service hostname to be available...")
            service_hostname = self._wait_for_service_hostname(
                service_name, max_wait_time=120
            )
            if service_hostname:
                print(f"✓ Retrieved service hostname: {service_hostname}")
                service.hostname = service_hostname
            else:
                print("❌ FAIL-FAST: Hostname not available. Cannot deploy clients.")
                if service.job_id:
                    self.cancel_job(service.job_id)
                return clients

        # Wait for service to be READY (not just running)
        # This ensures model is loaded, API is responding, etc.
        if service_type:
            print(f"\nWaiting for {service_type} service to be ready...")
            is_ready = self._wait_for_service_ready(
                service_type=service_type,
                hostname=service_hostname,
                port=service.port,
                max_wait_time=ready_check_timeout,
                expected_model=expected_model,
            )
            if not is_ready:
                print("❌ FAIL-FAST: Service not ready. Cancelling benchmark...")
                if service.job_id:
                    self.cancel_job(service.job_id)
                return clients
            print()  # Empty line after readiness check

        for i in range(num_clients):
            client_name = f"{client_name_prefix}-{i + 1}"
            client = self.deploy_client(
                client_name=client_name,
                service_name=service_name,
                benchmark_command=benchmark_command,
                service=service,
                wait_for_start=False,  # Don't wait for each client individually
                **sbatch_kwargs,
            )
            if client:
                clients.append(client)
            print()  # Empty line between clients

        return clients

    def deploy_service(
        self,
        service_name: str,
        container_image: str,
        service_command: str,
        port: Optional[int] = None,
        env_vars: Optional[Dict[str, str]] = None,
        wait_for_start: bool = True,
        max_wait_time: int = 300,
        **sbatch_kwargs,
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
        result = self.communicator.execute_command(
            f"mkdir -p {self.abs_working_dir}/logs"
        )
        if not result.success:
            print(f"Error: Failed to create logs directory: {result.stderr}")
            return None

        result = self.communicator.execute_command(
            f"mkdir -p {self.abs_working_dir}/scripts"
        )
        if not result.success:
            print(f"Error: Failed to create scripts directory: {result.stderr}")
            return None

        # Generate sbatch script
        script_content = self._create_sbatch_script(
            service_name=service_name,
            container_image=container_image,
            service_command=service_command,
            env_vars=env_vars,
            **sbatch_kwargs,
        )

        # Write script locally first
        local_script_path = Path(f"/tmp/{service_name}_{self.benchmark_id}.sh")
        local_script_path.write_text(script_content)

        # Upload script to cluster (use absolute path)
        remote_script_path = f"{self.abs_working_dir}/scripts/{service_name}.sh"
        print(f"Uploading sbatch script to: {remote_script_path}")

        if not self.communicator.upload_file(local_script_path, remote_script_path):
            print("Error: Failed to upload script")
            return None

        # Upload monitoring scraper script
        try:
            import sys
            repo_root = Path(__file__).parent.parent.parent
            local_scraper_path = repo_root / "src/monitoring/scraper.py"
            
            if local_scraper_path.exists():
                remote_scraper_path = f"{self.abs_working_dir}/scripts/scraper.py"
                print(f"Uploading scraper to: {remote_scraper_path}")
                self.communicator.upload_file(local_scraper_path, remote_scraper_path)
        except Exception as e:
            print(f"Warning: Failed to upload scraper: {e}")

        # Submit job
        print("Submitting job...")
        job_id = self.communicator.submit_job(remote_script_path)

        if not job_id:
            print("Error: Failed to submit job")
            return None

        print(f"✓ Job submitted with ID: {job_id}")

        # Create initial service object
        service = Service(
            name=service_name,
            container_image=container_image,
            job_id=job_id,
            port=port,
            working_dir=self.working_dir,
            submit_time=datetime.now(),
            log_file=f"{self.working_dir}/logs/{service_name}_{job_id}.out",
        )

        # Save initial state
        service.save(self.benchmark_id, self.storage_manager)
        print("✓ Service state saved to storage")

        # Wait for job to start if requested
        if wait_for_start:
            print(f"Waiting for job to start (max {max_wait_time}s)...")
            job_started, final_status = self._wait_for_job_to_start(job_id, max_wait_time)
            
            if job_started:
                print("✓ Job is running")

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
                # Job did not start - FAIL-FAST: cancel the job to free resources
                print(f"\n❌ FAIL-FAST: Cancelling service job {job_id}...")
                self.cancel_job(job_id)
                
                if final_status == "PENDING":
                    print(f"⚠️  TIMEOUT: Service job {job_id} still PENDING after {max_wait_time}s")
                    print("   Note: Node allocation is waiting in the SLURM queue.")
                elif final_status in ["COMPLETED", "FAILED", "CANCELLED"]:
                    print(f"❌ Service job ended with status: {final_status}")
                else:
                    print(f"⚠️  Service job did not start within {max_wait_time}s (status: {final_status})")
                
                print("   Benchmark aborted. No resources wasted.")
                return None

        return service

    def _wait_for_job_to_start(self, job_id: str, max_wait_time: int) -> tuple:
        """
        Wait for a job to transition from PENDING to RUNNING.

        Args:
            job_id: Slurm job ID
            max_wait_time: Maximum time to wait in seconds

        Returns:
            Tuple of (success: bool, final_status: str)
            - success: True if job started running, False if timeout or failure
            - final_status: Last known job status ("RUNNING", "PENDING", "FAILED", etc.)
        """
        start_time = time.time()
        last_status = "UNKNOWN"

        while time.time() - start_time < max_wait_time:
            status = self.communicator.get_job_status(job_id)
            last_status = status or "UNKNOWN"

            if status == "RUNNING":
                return (True, status)
            elif status in ["COMPLETED", "FAILED", "CANCELLED"]:
                return (False, status)

            # Wait a bit before checking again
            time.sleep(5)

        return (False, last_status)

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

    def load_client(self, client_name: str) -> Optional[Client]:
        """
        Load a client from storage.

        Args:
            client_name: Name of the client to load

        Returns:
            Client object or None if not found
        """
        return Client.load(self.benchmark_id, client_name, self.storage_manager)

    def load_all_clients(self) -> List[Client]:
        """
        Load all clients for this benchmark.

        Returns:
            List of Client objects
        """
        return Client.load_all(self.benchmark_id, self.storage_manager)

    def _wait_for_service_hostname(
        self, service_name: str, max_wait_time: int = 120
    ) -> Optional[str]:
        """
        Wait for service hostname to become available with exponential backoff.

        This method polls for the hostname file to exist and contain data,
        using exponential backoff to handle variable cluster scheduling delays.

        Args:
            service_name: Name of the service
            max_wait_time: Maximum time to wait in seconds

        Returns:
            Hostname string or None if timeout reached
        """
        hostname_file = f"{self.abs_working_dir}/{service_name}.hostname"
        start_time = time.time()
        wait_interval = 1  # Start with 1 second
        max_interval = 10  # Max 10 seconds between polls

        while time.time() - start_time < max_wait_time:
            # Check if file exists and has content
            result = self.communicator.execute_command(
                f"test -s {hostname_file} && cat {hostname_file}"
            )
            if result.success and result.stdout:
                hostname = result.stdout.strip()
                if hostname:  # Ensure hostname is not empty
                    return hostname

            # Wait with exponential backoff
            time.sleep(wait_interval)
            wait_interval = min(wait_interval * 2, max_interval)

            # Show progress
            elapsed = int(time.time() - start_time)
            print(f"  Waiting for hostname... ({elapsed}s elapsed)")

        return None

    def _wait_for_service_ready(
        self,
        service_type: Optional[str],
        hostname: str,
        port: Optional[int],
        max_wait_time: int = 300,
        expected_model: Optional[str] = None,
    ) -> bool:
        """
        Wait for service to be ready to accept requests.
        
        This method performs service-specific health checks to ensure the service
        is not just running, but actually ready (model loaded, API responding).
        
        Args:
            service_type: Type of service (ollama, vllm, redis, postgres, etc.)
            hostname: Service hostname
            port: Service port
            max_wait_time: Maximum time to wait in seconds
            expected_model: For LLM services, the model that should be loaded
            
        Returns:
            True if service is ready, False if timeout
        """
        if not hostname:
            return False
            
        start_time = time.time()
        wait_interval = 2  # Start with 2 seconds
        max_interval = 15  # Max 15 seconds between polls
        
        print(f"  Checking service readiness ({service_type or 'generic'})...")
        
        while time.time() - start_time < max_wait_time:
            elapsed = int(time.time() - start_time)
            is_ready = False
            
            try:
                if service_type == "ollama":
                    # Ollama: Check /api/tags for model availability
                    check_url = f"http://{hostname}:11434/api/tags"
                    result = self.communicator.execute_command(
                        f"curl -s --max-time 5 {check_url}"
                    )
                    if result.success and result.stdout:
                        # Check if expected model is in the response
                        if expected_model:
                            if expected_model in result.stdout:
                                is_ready = True
                                print(f"  ✓ Model '{expected_model}' is loaded")
                        else:
                            # Any successful response means service is ready
                            if "models" in result.stdout:
                                is_ready = True
                                
                elif service_type == "vllm":
                    # vLLM: Check /health or /v1/models
                    check_url = f"http://{hostname}:{port or 8000}/health"
                    result = self.communicator.execute_command(
                        f"curl -s --max-time 5 -o /dev/null -w '%{{http_code}}' {check_url}"
                    )
                    if result.success and result.stdout.strip() == "200":
                        is_ready = True
                    else:
                        # Fallback to /v1/models
                        check_url = f"http://{hostname}:{port or 8000}/v1/models"
                        result = self.communicator.execute_command(
                            f"curl -s --max-time 5 {check_url}"
                        )
                        if result.success and "data" in result.stdout:
                            is_ready = True
                            
                elif service_type in ("redis", "postgres", "chroma"):
                    # For databases: Simple TCP port check
                    check_port = port or {"redis": 6379, "postgres": 5432, "chroma": 8000}.get(service_type, port)
                    if check_port:
                        result = self.communicator.execute_command(
                            f"timeout 3 bash -c 'cat < /dev/null > /dev/tcp/{hostname}/{check_port}' 2>/dev/null && echo 'OK'"
                        )
                        if result.success and "OK" in result.stdout:
                            is_ready = True
                else:
                    # Generic check: TCP port if available
                    if port:
                        result = self.communicator.execute_command(
                            f"timeout 3 bash -c 'cat < /dev/null > /dev/tcp/{hostname}/{port}' 2>/dev/null && echo 'OK'"
                        )
                        if result.success and "OK" in result.stdout:
                            is_ready = True
                    else:
                        # No port to check, assume ready after hostname available
                        is_ready = True
                        
            except Exception as e:
                print(f"  Health check error: {e}")
                
            if is_ready:
                print(f"  ✓ Service is ready! ({elapsed}s)")
                return True
                
            # Show progress
            print(f"  Waiting for service to be ready... ({elapsed}s/{max_wait_time}s)")
            
            # Wait with exponential backoff
            time.sleep(wait_interval)
            wait_interval = min(wait_interval * 1.5, max_interval)
            
        print(f"  ❌ Service readiness timeout after {max_wait_time}s")
        return False

    def stop_benchmark(self) -> dict:
        """
        Stop all jobs (service + clients) for this benchmark.

        Returns:
            Dictionary with cancelled job info: {'services': [...], 'clients': [...], 'errors': [...]}
        """
        self._ensure_connected()

        result = {"services": [], "clients": [], "errors": []}

        # Load and cancel all services
        services = self.load_all_services()
        for service in services:
            if service.job_id:
                try:
                    if self.cancel_job(service.job_id):
                        result["services"].append(
                            {"name": service.name, "job_id": service.job_id}
                        )
                    else:
                        result["errors"].append(
                            f"Failed to cancel service {service.name} (job {service.job_id})"
                        )
                except Exception as e:
                    result["errors"].append(
                        f"Error cancelling service {service.name}: {e}"
                    )

        # Load and cancel all clients
        clients = self.load_all_clients()
        for client in clients:
            if client.job_id:
                try:
                    if self.cancel_job(client.job_id):
                        result["clients"].append(
                            {"name": client.name, "job_id": client.job_id}
                        )
                    else:
                        result["errors"].append(
                            f"Failed to cancel client {client.name} (job {client.job_id})"
                        )
                except Exception as e:
                    result["errors"].append(
                        f"Error cancelling client {client.name}: {e}"
                    )

        return result

    def get_benchmark_status(self) -> dict:
        """
        Get current status of all jobs in this benchmark.

        Returns:
            Dictionary with status info for services and clients
        """
        self._ensure_connected()

        status = {"services": [], "clients": []}

        # Get service statuses
        services = self.load_all_services()
        for service in services:
            job_status = None
            if service.job_id:
                job_status = self.get_job_status(service.job_id)
            status["services"].append(
                {
                    "name": service.name,
                    "job_id": service.job_id,
                    "status": job_status or "UNKNOWN",
                    "hostname": service.hostname,
                }
            )

        # Get client statuses
        clients = self.load_all_clients()
        for client in clients:
            if client.job_id:
                job_status = self.get_job_status(client.job_id)
            
            # Lazy-load hostname if running/completed but missing
            if (job_status in ["RUNNING", "COMPLETED"] and not client.hostname and client.job_id):
                hostname = self._get_service_hostname(client.name)
                if hostname:
                    client.hostname = hostname
                    client.node_name = hostname
                    # Persist the found hostname
                    client.save(self.benchmark_id, self.storage_manager)

            status["clients"].append(
                {
                    "name": client.name,
                    "job_id": client.job_id,
                    "status": job_status or "UNKNOWN",
                    "hostname": client.hostname,
                }
            )

        return status

    def tail_logs(self, num_lines: int = 20) -> dict:
        """
        Tail the logs for all jobs in this benchmark.

        Args:
            num_lines: Number of lines to tail

        Returns:
            Dictionary with log snippets for services and clients
        """
        self._ensure_connected()

        logs = {"services": {}, "clients": {}}

        # Get service logs
        services = self.load_all_services()
        for service in services:
            if service.job_id:
                log_path = (
                    f"{self.abs_working_dir}/logs/{service.name}_{service.job_id}.out"
                )
                result = self.communicator.execute_command(
                    f"tail -n {num_lines} {log_path} 2>/dev/null"
                )
                logs["services"][service.name] = (
                    result.stdout if result.success else "(no logs yet)"
                )

        # Get client logs
        clients = self.load_all_clients()
        for client in clients:
            if client.job_id:
                log_path = (
                    f"{self.abs_working_dir}/logs/{client.name}_{client.job_id}.out"
                )
                result = self.communicator.execute_command(
                    f"tail -n {num_lines} {log_path} 2>/dev/null"
                )
                logs["clients"][client.name] = (
                    result.stdout if result.success else "(no logs yet)"
                )

        return logs

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
        return False
