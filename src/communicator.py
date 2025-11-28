#!/usr/bin/env python3
"""
Communicator module for the AI Factory Benchmarking Framework.

This module provides abstract and concrete implementations for communicating
with remote clusters (e.g., MeluXina) to execute commands, transfer files,
and manage benchmark jobs.

Uses Fabric for SSH communication, which provides a clean Python API
for remote command execution and file transfers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from fabric import Connection
from invoke.exceptions import UnexpectedExit
from paramiko.ssh_exception import SSHException


@dataclass
class CommandResult:
    """Result of a command execution on the remote cluster."""
    stdout: str
    stderr: str
    return_code: int
    
    @property
    def success(self) -> bool:
        """Check if the command executed successfully."""
        return self.return_code == 0
    
    def __str__(self) -> str:
        status = "SUCCESS" if self.success else f"FAILED (code: {self.return_code})"
        return f"CommandResult({status})\nstdout: {self.stdout}\nstderr: {self.stderr}"


class Communicator(ABC):
    """
    Abstract base class for cluster communication.
    
    This class defines the interface for communicating with remote clusters,
    including executing commands, transferring files, and managing jobs.
    Concrete implementations should provide the actual communication mechanism
    (e.g., SSH, API calls, etc.).
    """
    
    def __init__(self, target: str):
        """
        Initialize the communicator.
        
        Args:
            target: The target cluster identifier (e.g., SSH alias, hostname, or API endpoint)
        """
        self.target = target
    
    @abstractmethod
    def connect(self) -> bool:
        """
        Establish a connection to the remote cluster.
        
        Returns:
            True if connection was successful, False otherwise
        """
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """Close the connection to the remote cluster."""
        pass
    
    @abstractmethod
    def execute_command(self, command: str, working_dir: Optional[str] = None) -> CommandResult:
        """
        Execute a command on the remote cluster.
        
        Args:
            command: The command to execute
            working_dir: Optional working directory for command execution
            
        Returns:
            CommandResult containing stdout, stderr, and return code
        """
        pass
    
    @abstractmethod
    def upload_file(self, local_path: Path, remote_path: str) -> bool:
        """
        Upload a file to the remote cluster.
        
        Args:
            local_path: Path to the local file
            remote_path: Destination path on the remote cluster
            
        Returns:
            True if upload was successful, False otherwise
        """
        pass
    
    @abstractmethod
    def download_file(self, remote_path: str, local_path: Path) -> bool:
        """
        Download a file from the remote cluster.
        
        Args:
            remote_path: Path to the file on the remote cluster
            local_path: Destination path on the local machine
            
        Returns:
            True if download was successful, False otherwise
        """
        pass
    
    @abstractmethod
    def submit_job(self, script_path: str) -> Optional[str]:
        """
        Submit a Slurm job to the cluster.
        
        Args:
            script_path: Path to the sbatch script on the remote cluster
            
        Returns:
            Job ID if submission was successful, None otherwise
        """
        pass
    
    @abstractmethod
    def get_job_status(self, job_id: str) -> Optional[str]:
        """
        Get the status of a Slurm job.
        
        Args:
            job_id: The Slurm job ID
            
        Returns:
            Job status string (e.g., "PENDING", "RUNNING", "COMPLETED") or None if not found
        """
        pass
    
    @abstractmethod
    def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a Slurm job.
        
        Args:
            job_id: The Slurm job ID to cancel
            
        Returns:
            True if cancellation was successful, False otherwise
        """
        pass
    
    def __enter__(self) -> "Communicator":
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.disconnect()


class SSHCommunicator(Communicator):
    """
    SSH-based communicator for remote cluster communication using Fabric.
    
    This implementation uses Fabric (built on Paramiko) for SSH command execution
    and file transfers. It supports SSH config files, so you can use SSH aliases
    defined in ~/.ssh/config.
    """
    
    def __init__(
        self, 
        target: str, 
        user: Optional[str] = None, 
        port: Optional[int] = None,
        connect_timeout: int = 30,
        command_timeout: int = 300
    ):
        """
        Initialize the SSH communicator with Fabric.
        
        Args:
            target: SSH alias or hostname (e.g., "meluxina" or "login.lxp.lu")
            user: Optional username for SSH connection (if not in SSH config)
            port: SSH port (if not in SSH config, defaults to 22)
            connect_timeout: Timeout for establishing connection (seconds)
            command_timeout: Default timeout for command execution (seconds)
        """
        super().__init__(target)
        self.user = user
        self.port = port
        self.connect_timeout = connect_timeout
        self.command_timeout = command_timeout
        self._connection: Optional[Connection] = None
    
    def _create_connection(self) -> Connection:
        """Create a new Fabric connection with the configured parameters."""
        # Note: Don't pass timeout in both connect_timeout and connect_kwargs
        # to avoid ambiguity. Use connect_timeout as the primary parameter.
        return Connection(
            host=self.target,
            user=self.user,
            port=self.port,
            connect_timeout=self.connect_timeout
        )
    
    def connect(self) -> bool:
        """
        Establish an SSH connection to the remote cluster.
        
        Returns:
            True if connection was successful, False otherwise
        """
        try:
            self._connection = self._create_connection()
            self._connection.open()
            return True
        except (SSHException, Exception) as e:
            print(f"Connection failed: {e}")
            self._connection = None
            return False
    
    def disconnect(self) -> None:
        """Close the SSH connection."""
        if self._connection:
            self._connection.close()
            self._connection = None
    
    @property
    def connection(self) -> Connection:
        """Get the active connection, creating one if necessary."""
        if self._connection is None or not self._connection.is_connected:
            self._connection = self._create_connection()
        return self._connection
    
    def execute_command(
        self, 
        command: str, 
        working_dir: Optional[str] = None,
        timeout: Optional[int] = None
    ) -> CommandResult:
        """
        Execute a command on the remote cluster via SSH.
        
        Args:
            command: The command to execute
            working_dir: Optional working directory for command execution
            timeout: Optional timeout override (uses default if not specified)
            
        Returns:
            CommandResult containing stdout, stderr, and return code
        """
        if working_dir:
            command = f"cd {working_dir} && {command}"
        
        timeout = timeout or self.command_timeout
        
        try:
            result = self.connection.run(
                command,
                hide=True,  # Don't print output to console
                warn=True,  # Don't raise exception on non-zero exit
                timeout=timeout
            )
            return CommandResult(
                stdout=result.stdout.strip() if result.stdout else "",
                stderr=result.stderr.strip() if result.stderr else "",
                return_code=result.return_code
            )
        except UnexpectedExit as e:
            return CommandResult(
                stdout=e.result.stdout.strip() if e.result.stdout else "",
                stderr=e.result.stderr.strip() if e.result.stderr else "",
                return_code=e.result.return_code
            )
        except Exception as e:
            return CommandResult(
                stdout="",
                stderr=str(e),
                return_code=-1
            )
    
    def upload_file(self, local_path: Path, remote_path: str) -> bool:
        """
        Upload a file to the remote cluster using SFTP.
        
        Args:
            local_path: Path to the local file
            remote_path: Destination path on the remote cluster
            
        Returns:
            True if upload was successful, False otherwise
        """
        if not local_path.exists():
            return False
        
        try:
            self.connection.put(str(local_path), remote=remote_path)
            return True
        except Exception as e:
            print(f"Upload failed: {e}")
            return False
    
    def download_file(self, remote_path: str, local_path: Path) -> bool:
        """
        Download a file from the remote cluster using SFTP.
        
        Args:
            remote_path: Path to the file on the remote cluster
            local_path: Destination path on the local machine
            
        Returns:
            True if download was successful, False otherwise
        """
        # Ensure parent directory exists
        local_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            self.connection.get(remote_path, local=str(local_path))
            return True
        except Exception as e:
            print(f"Download failed: {e}")
            return False
    
    # def upload_directory(self, local_path: Path, remote_path: str) -> bool:
    #     """
    #     Upload a directory recursively to the remote cluster.
        
    #     Args:
    #         local_path: Path to the local directory
    #         remote_path: Destination path on the remote cluster
            
    #     Returns:
    #         True if upload was successful, False otherwise
    #     """
    #     if not local_path.is_dir():
    #         return False
        
    #     try:
    #         # Create remote directory
    #         self.execute_command(f"mkdir -p {remote_path}")
            
    #         # Upload each file
    #         for item in local_path.rglob("*"):
    #             if item.is_file():
    #                 relative = item.relative_to(local_path)
    #                 remote_file = f"{remote_path}/{relative}"
    #                 remote_dir = str(Path(remote_file).parent)
    #                 self.execute_command(f"mkdir -p {remote_dir}")
    #                 self.upload_file(item, remote_file)
            
    #         return True
    #     except Exception as e:
    #         print(f"Directory upload failed: {e}")
    #         return False
    
    def submit_job(self, script_path: str) -> Optional[str]:
        """
        Submit a Slurm job via sbatch.
        
        Args:
            script_path: Path to the sbatch script on the remote cluster
            
        Returns:
            Job ID if submission was successful, None otherwise
        """
        result = self.execute_command(f"sbatch {script_path}")
        
        #TODO: Are we sure that sbatch output format is consistent across all Slurm versions?
        if result.success:
            # Parse job ID from sbatch output (typically "Submitted batch job <job_id>")
            parts = result.stdout.split()
            if len(parts) >= 4 and parts[-1].isdigit():
                return parts[-1]
        
        return None
    
    def get_job_status(self, job_id: str) -> Optional[str]:
        """
        Get the status of a Slurm job using squeue.
        
        Args:
            job_id: The Slurm job ID
            
        Returns:
            Job status string (e.g., "PENDING", "RUNNING", "COMPLETED") or None if not found
        """
        result = self.execute_command(f"squeue -j {job_id} -h -o %T")
        
        if result.success and result.stdout:
            return result.stdout.strip()
        
        # Job might have completed - check sacct
        result = self.execute_command(f"sacct -j {job_id} -n -o State --parsable2")
        
        if result.success and result.stdout:
            # Return the first status (main job, not steps)
            statuses = result.stdout.strip().split('\n')
            if statuses:
                return statuses[0].strip()
        
        return None
    
    def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a Slurm job using scancel.
        
        Args:
            job_id: The Slurm job ID to cancel
            
        Returns:
            True if cancellation was successful, False otherwise
        """
        result = self.execute_command(f"scancel {job_id}")
        return result.success
    
    # def list_directory(self, remote_path: str) -> list[str]:
    #     """
    #     List contents of a remote directory.
        
    #     Args:
    #         remote_path: Path to the directory on the remote cluster
            
    #     Returns:
    #         List of filenames in the directory
    #     """
    #     result = self.execute_command(f"ls -1 {remote_path}")
    #     if result.success:
    #         return result.stdout.split('\n') if result.stdout else []
    #     return []
    
    # def file_exists(self, remote_path: str) -> bool:
    #     """
    #     Check if a file exists on the remote cluster.
        
    #     Args:
    #         remote_path: Path to check on the remote cluster
            
    #     Returns:
    #         True if the file exists, False otherwise
    #     """
    #     result = self.execute_command(f"test -e {remote_path}")
    #     return result.success
    
    # def read_remote_file(self, remote_path: str) -> Optional[str]:
    #     """
    #     Read the contents of a remote file.
        
    #     Args:
    #         remote_path: Path to the file on the remote cluster
            
    #     Returns:
    #         File contents as string, or None if read failed
    #     """
    #     result = self.execute_command(f"cat {remote_path}")
    #     if result.success:
    #         return result.stdout
    #     return None


def create_communicator(target: str, method: str = "ssh", **kwargs) -> Communicator:
    """
    Factory function to create a communicator instance.
    
    Args:
        target: The target cluster identifier
        method: Communication method ("ssh" for now, extensible for future methods)
        **kwargs: Additional arguments passed to the communicator constructor
        
    Returns:
        Communicator instance
        
    Raises:
        ValueError: If the specified method is not supported
    """
    if method == "ssh":
        return SSHCommunicator(target, **kwargs)
    else:
        raise ValueError(f"Unsupported communication method: {method}")
    
if __name__ == "__main__":
    # Example usage

    communicator = create_communicator("meluxina", method="ssh")

    with communicator as comm:
        result = comm.execute_command(command="pwd")
        print(result)