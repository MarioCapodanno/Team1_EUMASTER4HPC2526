#!/usr/bin/env python3
"""
Client module for the AI Factory Benchmarking Framework.

This module defines the Client class that represents a benchmark client running on the
cluster. The Client is a data container that holds information obtained from
the cluster via the Manager class.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List
from infra.storage import get_storage_manager, StorageManager


@dataclass
class Client:
    """
    Represents a benchmark client running on the cluster.

    This is a simple data container that holds all information about a client
    that is obtained from the cluster by the Manager class. Clients are used
    to benchmark services by generating load and collecting metrics.

    The Manager class is responsible for:
    - Creating Client instances
    - Populating client information from the cluster (via SSH)
    - Updating client status and execution information
    """

    # Basic identification
    name: str  # Client name/identifier
    service_name: str  # Name of the service being benchmarked
    benchmark_command: str  # Command to run for benchmarking

    # Slurm job information (populated by Manager from cluster)
    job_id: Optional[str] = None  # Slurm job ID

    # Network information (obtained from cluster by Manager)
    hostname: Optional[str] = None  # Hostname/IP where client is running

    # Timestamps (set by Manager based on cluster information)
    submit_time: Optional[datetime] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    # Additional information
    node_name: Optional[str] = None  # Compute node name
    working_dir: Optional[str] = None  # Working directory on cluster
    log_file: Optional[str] = None  # Path to log file on cluster
    metrics_file: Optional[str] = None  # Path to metrics output file

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert client to dictionary.

        Returns:
            Dictionary representation of the client
        """
        return {
            "name": self.name,
            "service_name": self.service_name,
            "benchmark_command": self.benchmark_command,
            "job_id": self.job_id,
            "hostname": self.hostname,
            "submit_time": self.submit_time.isoformat() if self.submit_time else None,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "node_name": self.node_name,
            "working_dir": self.working_dir,
            "log_file": self.log_file,
            "metrics_file": self.metrics_file,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Client":
        """
        Create a Client instance from a dictionary.

        Args:
            data: Dictionary containing client data

        Returns:
            Client instance
        """
        # Handle datetime fields
        for field_name in ["submit_time", "start_time", "end_time"]:
            if field_name in data and data[field_name]:
                if isinstance(data[field_name], str):
                    data[field_name] = datetime.fromisoformat(data[field_name])

        # Handle metadata (ensure it's a dict)
        if "metadata" in data:
            if isinstance(data["metadata"], str):
                import json

                data["metadata"] = json.loads(data["metadata"])
            elif data["metadata"] is None:
                data["metadata"] = {}

        return cls(**data)

    def save(
        self, benchmark_id: str, storage_manager: Optional[StorageManager] = None
    ) -> bool:
        """
        Save this client to storage.

        Args:
            benchmark_id: Unique benchmark identifier/token
            storage_manager: Optional storage manager (uses default if not provided)

        Returns:
            True if save was successful, False otherwise
        """
        if storage_manager is None:
            storage_manager = get_storage_manager()

        return storage_manager.save_entity(
            benchmark_id=benchmark_id,
            entity_type="client",
            entity_id=self.name,
            data=self.to_dict(),
        )

    @classmethod
    def load(
        cls,
        benchmark_id: str,
        client_name: str,
        storage_manager: Optional[StorageManager] = None,
    ) -> Optional["Client"]:
        """
        Load a client from storage.

        Args:
            benchmark_id: Unique benchmark identifier/token
            client_name: Name of the client to load
            storage_manager: Optional storage manager (uses default if not provided)

        Returns:
            Client instance or None if not found
        """
        if storage_manager is None:
            storage_manager = get_storage_manager()

        data = storage_manager.load_entity(
            benchmark_id=benchmark_id, entity_type="client", entity_id=client_name
        )

        if data:
            return cls.from_dict(data)
        return None

    @classmethod
    def load_all(
        cls, benchmark_id: str, storage_manager: Optional[StorageManager] = None
    ) -> List["Client"]:
        """
        Load all clients for a benchmark.

        Args:
            benchmark_id: Unique benchmark identifier/token
            storage_manager: Optional storage manager (uses default if not provided)

        Returns:
            List of Client instances
        """
        if storage_manager is None:
            storage_manager = get_storage_manager()

        all_data = storage_manager.load_all_entities(
            benchmark_id=benchmark_id, entity_type="client"
        )

        clients = []
        for data in all_data:
            # Remove _id field added by storage
            data.pop("_id", None)
            try:
                clients.append(cls.from_dict(data))
            except Exception as e:
                print(f"Error loading client: {e}")

        return clients

    def __str__(self) -> str:
        """String representation of the client."""
        return f"Client({self.name} -> {self.service_name})"
