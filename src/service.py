#!/usr/bin/env python3
"""
Service module for the AI Factory Benchmarking Framework.

This module defines the Service class that represents a service running on the
cluster. The Service is a data container that holds information obtained from
the cluster via the Manager class.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any
from storage import get_storage_manager, StorageManager


@dataclass
class Service:
    """
    Represents a service running on the cluster.

    This is a simple data container that holds all information about a service
    that is obtained from the cluster by the Manager class. It contains
    everything needed by clients to connect to the service and by monitors
    to track it.

    The Manager class is responsible for:
    - Creating Service instances
    - Populating service information from the cluster (via SSH)
    - Updating service status and network information
    """

    # Basic identification
    name: str  # Service name/identifier
    container_image: str  # Container image for this service

    # Slurm job information (populated by Manager from cluster)
    job_id: Optional[str] = None  # Slurm job ID

    # Network information (obtained from cluster by Manager)
    hostname: Optional[str] = None  # Hostname/IP where service is running
    port: Optional[int] = None  # Service port

    # Timestamps (set by Manager based on cluster information)
    submit_time: Optional[datetime] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    # Additional information
    node_name: Optional[str] = None  # Compute node name
    working_dir: Optional[str] = None  # Working directory on cluster
    log_file: Optional[str] = None  # Path to log file on cluster

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_url(self) -> Optional[str]:
        """
        Get the service URL if hostname and port are available.

        Returns:
            URL string or None if information not available
        """
        if self.hostname and self.port:
            return f"http://{self.hostname}:{self.port}"
        return None

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert service to dictionary.

        Returns:
            Dictionary representation of the service
        """
        return {
            "name": self.name,
            "container_image": self.container_image,
            "job_id": self.job_id,
            "hostname": self.hostname,
            "port": self.port,
            "submit_time": self.submit_time.isoformat() if self.submit_time else None,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "node_name": self.node_name,
            "working_dir": self.working_dir,
            "log_file": self.log_file,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Service":
        """
        Create a Service instance from a dictionary.

        Args:
            data: Dictionary containing service data

        Returns:
            Service instance
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
        Save this service to storage.

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
            entity_type="service",
            entity_id=self.name,
            data=self.to_dict(),
        )

    @classmethod
    def load(
        cls,
        benchmark_id: str,
        service_name: str,
        storage_manager: Optional[StorageManager] = None,
    ) -> Optional["Service"]:
        """
        Load a service from storage.

        Args:
            benchmark_id: Unique benchmark identifier/token
            service_name: Name of the service to load
            storage_manager: Optional storage manager (uses default if not provided)

        Returns:
            Service instance or None if not found
        """
        if storage_manager is None:
            storage_manager = get_storage_manager()

        data = storage_manager.load_entity(
            benchmark_id=benchmark_id, entity_type="service", entity_id=service_name
        )

        if data:
            return cls.from_dict(data)
        return None

    @classmethod
    def load_all(
        cls, benchmark_id: str, storage_manager: Optional[StorageManager] = None
    ) -> list["Service"]:
        """
        Load all services for a benchmark.

        Args:
            benchmark_id: Unique benchmark identifier/token
            storage_manager: Optional storage manager (uses default if not provided)

        Returns:
            List of Service instances
        """
        if storage_manager is None:
            storage_manager = get_storage_manager()

        all_data = storage_manager.load_all_entities(
            benchmark_id=benchmark_id, entity_type="service"
        )

        services = []
        for data in all_data:
            # Remove _id field added by storage
            data.pop("_id", None)
            try:
                services.append(cls.from_dict(data))
            except Exception as e:
                print(f"Error loading service: {e}")

        return services

    def __str__(self) -> str:
        """String representation of the service."""
        url = self.get_url() or "N/A"
        return f"Service({self.name} @ {url})"
