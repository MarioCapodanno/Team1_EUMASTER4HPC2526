#!/usr/bin/env python3
"""
Storage module for the AI Factory Benchmarking Framework.

This module provides an abstraction layer for persisting benchmark state
(Services, Clients, Monitors) to various storage backends. Currently implements
CSV-based storage, but can be extended to support databases.

The storage is organized by benchmark_id (token) to allow multiple benchmarks
to run concurrently or access historical benchmark data.
"""

import csv
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List, Optional, Type
from datetime import datetime


class StorageBackend(ABC):
    """
    Abstract base class for storage backends.
    
    Provides a generic interface for storing and retrieving benchmark entities
    (Services, Clients, Monitors) organized by benchmark_id.
    """
    
    @abstractmethod
    def save(self, benchmark_id: str, entity_type: str, entity_id: str, data: Dict[str, Any]) -> bool:
        """
        Save an entity to storage.
        
        Args:
            benchmark_id: Unique identifier for the benchmark run
            entity_type: Type of entity (e.g., "service", "client", "monitor")
            entity_id: Unique identifier for this entity (e.g., service name)
            data: Dictionary containing entity data
            
        Returns:
            True if save was successful, False otherwise
        """
        pass
    
    @abstractmethod
    def load(self, benchmark_id: str, entity_type: str, entity_id: str) -> Optional[Dict[str, Any]]:
        """
        Load an entity from storage.
        
        Args:
            benchmark_id: Unique identifier for the benchmark run
            entity_type: Type of entity (e.g., "service", "client", "monitor")
            entity_id: Unique identifier for this entity
            
        Returns:
            Dictionary containing entity data, or None if not found
        """
        pass
    
    @abstractmethod
    def load_all(self, benchmark_id: str, entity_type: str) -> List[Dict[str, Any]]:
        """
        Load all entities of a given type for a benchmark.
        
        Args:
            benchmark_id: Unique identifier for the benchmark run
            entity_type: Type of entity (e.g., "service", "client", "monitor")
            
        Returns:
            List of dictionaries containing entity data
        """
        pass
    
    @abstractmethod
    def delete(self, benchmark_id: str, entity_type: str, entity_id: str) -> bool:
        """
        Delete an entity from storage.
        
        Args:
            benchmark_id: Unique identifier for the benchmark run
            entity_type: Type of entity
            entity_id: Unique identifier for this entity
            
        Returns:
            True if deletion was successful, False otherwise
        """
        pass
    
    @abstractmethod
    def list_benchmarks(self) -> List[str]:
        """
        List all benchmark IDs in storage.
        
        Returns:
            List of benchmark IDs
        """
        pass


class CSVStorageBackend(StorageBackend):
    """
    CSV-based storage backend.
    
    Stores entities in CSV files organized by benchmark_id and entity_type.
    Structure: {storage_dir}/{benchmark_id}/{entity_type}.csv
    
    Each CSV file contains all entities of that type for a specific benchmark.
    Complex fields (metadata, dicts) are stored as JSON strings.
    """
    
    def __init__(self, storage_dir: str = ".benchmark_storage"):
        """
        Initialize CSV storage backend.
        
        Args:
            storage_dir: Directory to store benchmark data
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_csv_path(self, benchmark_id: str, entity_type: str) -> Path:
        """Get path to CSV file for a specific benchmark and entity type."""
        benchmark_dir = self.storage_dir / benchmark_id
        benchmark_dir.mkdir(parents=True, exist_ok=True)
        return benchmark_dir / f"{entity_type}.csv"
    
    def _serialize_value(self, value: Any) -> str:
        """Serialize a value for CSV storage."""
        if value is None:
            return ""
        elif isinstance(value, (dict, list)):
            return json.dumps(value)
        elif isinstance(value, datetime):
            return value.isoformat()
        else:
            return str(value)
    
    def _deserialize_value(self, value: str, hint: Optional[type] = None) -> Any:
        """Deserialize a value from CSV storage."""
        if value == "":
            return None
        
        # Try to parse as JSON (for dicts/lists)
        if value.startswith('{') or value.startswith('['):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                pass
        
        # Try to parse as datetime
        if hint == datetime or 'T' in value:
            try:
                return datetime.fromisoformat(value)
            except (ValueError, AttributeError):
                pass
        
        # Try to parse as int
        try:
            return int(value)
        except ValueError:
            pass
        
        # Return as string
        return value
    
    def save(self, benchmark_id: str, entity_type: str, entity_id: str, data: Dict[str, Any]) -> bool:
        """
        Save an entity to CSV storage.
        
        Args:
            benchmark_id: Unique identifier for the benchmark run
            entity_type: Type of entity (e.g., "service", "client", "monitor")
            entity_id: Unique identifier for this entity
            data: Dictionary containing entity data
            
        Returns:
            True if save was successful, False otherwise
        """
        try:
            csv_path = self._get_csv_path(benchmark_id, entity_type)
            
            # Add entity_id to data
            data_with_id = {"_id": entity_id, **data}
            
            # Read existing data
            existing_data = []
            if csv_path.exists():
                with open(csv_path, 'r', newline='') as f:
                    reader = csv.DictReader(f)
                    existing_data = [row for row in reader if row.get('_id') != entity_id]
            
            # Add new/updated data
            existing_data.append(data_with_id)
            
            # Get all fieldnames
            all_fields = set()
            for row in existing_data:
                all_fields.update(row.keys())
            fieldnames = ['_id'] + sorted([f for f in all_fields if f != '_id'])
            
            # Write CSV
            with open(csv_path, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for row in existing_data:
                    # Serialize complex values
                    serialized_row = {k: self._serialize_value(v) for k, v in row.items()}
                    writer.writerow(serialized_row)
            
            return True
        except Exception as e:
            print(f"Error saving to CSV: {e}")
            return False
    
    def load(self, benchmark_id: str, entity_type: str, entity_id: str) -> Optional[Dict[str, Any]]:
        """
        Load an entity from CSV storage.
        
        Args:
            benchmark_id: Unique identifier for the benchmark run
            entity_type: Type of entity
            entity_id: Unique identifier for this entity
            
        Returns:
            Dictionary containing entity data, or None if not found
        """
        try:
            csv_path = self._get_csv_path(benchmark_id, entity_type)
            
            if not csv_path.exists():
                return None
            
            with open(csv_path, 'r', newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('_id') == entity_id:
                        # Remove _id and deserialize values
                        data = {k: self._deserialize_value(v) for k, v in row.items() if k != '_id'}
                        return data
            
            return None
        except Exception as e:
            print(f"Error loading from CSV: {e}")
            return None
    
    def load_all(self, benchmark_id: str, entity_type: str) -> List[Dict[str, Any]]:
        """
        Load all entities of a given type for a benchmark.
        
        Args:
            benchmark_id: Unique identifier for the benchmark run
            entity_type: Type of entity
            
        Returns:
            List of dictionaries containing entity data
        """
        try:
            csv_path = self._get_csv_path(benchmark_id, entity_type)
            
            if not csv_path.exists():
                return []
            
            result = []
            with open(csv_path, 'r', newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Keep _id in the result for identification
                    data = {k: self._deserialize_value(v) for k, v in row.items()}
                    result.append(data)
            
            return result
        except Exception as e:
            print(f"Error loading all from CSV: {e}")
            return []
    
    def delete(self, benchmark_id: str, entity_type: str, entity_id: str) -> bool:
        """
        Delete an entity from CSV storage.
        
        Args:
            benchmark_id: Unique identifier for the benchmark run
            entity_type: Type of entity
            entity_id: Unique identifier for this entity
            
        Returns:
            True if deletion was successful, False otherwise
        """
        try:
            csv_path = self._get_csv_path(benchmark_id, entity_type)
            
            if not csv_path.exists():
                return False
            
            # Read existing data, excluding the entity to delete
            remaining_data = []
            with open(csv_path, 'r', newline='') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                remaining_data = [row for row in reader if row.get('_id') != entity_id]
            
            # Rewrite CSV without deleted entity
            with open(csv_path, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(remaining_data)
            
            return True
        except Exception as e:
            print(f"Error deleting from CSV: {e}")
            return False
    
    def list_benchmarks(self) -> List[str]:
        """
        List all benchmark IDs in storage.
        
        Returns:
            List of benchmark IDs
        """
        try:
            return [d.name for d in self.storage_dir.iterdir() if d.is_dir()]
        except Exception as e:
            print(f"Error listing benchmarks: {e}")
            return []


class StorageManager:
    """
    High-level storage manager that provides a simple interface for entities
    to save/load their state.
    
    This class acts as a facade to the storage backend and can be shared
    across Services, Clients, and Monitors.
    """
    
    def __init__(self, backend: StorageBackend):
        """
        Initialize storage manager with a backend.
        
        Args:
            backend: Storage backend to use
        """
        self.backend = backend
    
    def save_entity(self, benchmark_id: str, entity_type: str, entity_id: str, data: Dict[str, Any]) -> bool:
        """
        Save an entity.
        
        Args:
            benchmark_id: Benchmark identifier
            entity_type: Entity type (e.g., "service", "client", "monitor")
            entity_id: Entity identifier
            data: Entity data as dictionary
            
        Returns:
            True if successful
        """
        return self.backend.save(benchmark_id, entity_type, entity_id, data)
    
    def load_entity(self, benchmark_id: str, entity_type: str, entity_id: str) -> Optional[Dict[str, Any]]:
        """
        Load an entity.
        
        Args:
            benchmark_id: Benchmark identifier
            entity_type: Entity type
            entity_id: Entity identifier
            
        Returns:
            Entity data or None if not found
        """
        return self.backend.load(benchmark_id, entity_type, entity_id)
    
    def load_all_entities(self, benchmark_id: str, entity_type: str) -> List[Dict[str, Any]]:
        """
        Load all entities of a type for a benchmark.
        
        Args:
            benchmark_id: Benchmark identifier
            entity_type: Entity type
            
        Returns:
            List of entity data dictionaries
        """
        return self.backend.load_all(benchmark_id, entity_type)
    
    def delete_entity(self, benchmark_id: str, entity_type: str, entity_id: str) -> bool:
        """
        Delete an entity.
        
        Args:
            benchmark_id: Benchmark identifier
            entity_type: Entity type
            entity_id: Entity identifier
            
        Returns:
            True if successful
        """
        return self.backend.delete(benchmark_id, entity_type, entity_id)
    
    def list_benchmarks(self) -> List[str]:
        """
        List all benchmark IDs.
        
        Returns:
            List of benchmark IDs
        """
        return self.backend.list_benchmarks()


# Global storage manager instance (can be configured)
_default_storage_manager: Optional[StorageManager] = None


def get_storage_manager() -> StorageManager:
    """
    Get the default storage manager instance.
    
    Creates a CSV-based storage manager if none exists.
    
    Returns:
        StorageManager instance
    """
    global _default_storage_manager
    if _default_storage_manager is None:
        backend = CSVStorageBackend()
        _default_storage_manager = StorageManager(backend)
    return _default_storage_manager


def set_storage_manager(manager: StorageManager) -> None:
    """
    Set the default storage manager.
    
    Args:
        manager: StorageManager instance to use as default
    """
    global _default_storage_manager
    _default_storage_manager = manager


# =============================================================================
# BENCHMARK INFO HELPERS
# =============================================================================

@dataclass
class BenchmarkInfo:
    """Summary information about a benchmark."""
    benchmark_id: str
    service_name: Optional[str] = None
    service_job_id: Optional[str] = None
    num_clients: int = 0
    created_at: Optional[datetime] = None


@dataclass
class BenchmarkSummary:
    """Detailed summary of a benchmark run."""
    benchmark_id: str
    service_name: Optional[str] = None
    service_job_id: Optional[str] = None
    service_hostname: Optional[str] = None
    service_image: Optional[str] = None
    clients: List[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    log_dir: Optional[str] = None
    
    def __post_init__(self):
        if self.clients is None:
            self.clients = []


def list_all_benchmarks() -> List[BenchmarkInfo]:
    """
    List all benchmarks in storage with basic info.
    
    Returns:
        List of BenchmarkInfo objects sorted by ID (newest first)
    """
    storage = get_storage_manager()
    benchmark_ids = storage.list_benchmarks()
    
    benchmarks = []
    for bid in benchmark_ids:
        try:
            # Try to parse as int for sorting
            int_id = int(bid)
        except ValueError:
            int_id = 0
        
        info = BenchmarkInfo(benchmark_id=bid)
        
        # Try to load service info
        services = storage.load_all_entities(bid, "service")
        if services:
            svc = services[0]  # Usually one service per benchmark
            info.service_name = svc.get('name')
            info.service_job_id = svc.get('job_id')
            # Try to get creation time
            submit_time = svc.get('submit_time')
            if submit_time and isinstance(submit_time, datetime):
                info.created_at = submit_time
        
        # Count clients
        clients = storage.load_all_entities(bid, "client")
        info.num_clients = len(clients)
        
        benchmarks.append((int_id, info))
    
    # Sort by ID descending (newest first)
    benchmarks.sort(key=lambda x: x[0], reverse=True)
    return [b[1] for b in benchmarks]


def get_benchmark_summary(benchmark_id: str) -> Optional[BenchmarkSummary]:
    """
    Get detailed summary of a benchmark.
    
    Args:
        benchmark_id: Benchmark ID to get summary for
        
    Returns:
        BenchmarkSummary object or None if not found
    """
    storage = get_storage_manager()
    
    # Check if benchmark exists
    all_ids = storage.list_benchmarks()
    if benchmark_id not in all_ids:
        return None
    
    summary = BenchmarkSummary(benchmark_id=benchmark_id)
    
    # Load service info
    services = storage.load_all_entities(benchmark_id, "service")
    if services:
        svc = services[0]
        summary.service_name = svc.get('name')
        summary.service_job_id = svc.get('job_id')
        summary.service_hostname = svc.get('hostname')
        summary.service_image = svc.get('container_image')
        submit_time = svc.get('submit_time')
        if submit_time and isinstance(submit_time, datetime):
            summary.created_at = submit_time
        
        # Construct log directory path
        working_dir = svc.get('working_dir', f'~/benchmark_{benchmark_id}')
        summary.log_dir = f"{working_dir}/logs"
    
    # Load client info
    clients = storage.load_all_entities(benchmark_id, "client")
    for client in clients:
        summary.clients.append({
            'name': client.get('name'),
            'job_id': client.get('job_id'),
            'hostname': client.get('hostname'),
            'service_name': client.get('service_name')
        })
    
    return summary


def format_benchmark_table(benchmarks: List[BenchmarkInfo]) -> str:
    """
    Format a list of benchmarks as a nice ASCII table.
    
    Args:
        benchmarks: List of BenchmarkInfo objects
        
    Returns:
        Formatted table string
    """
    if not benchmarks:
        return "No benchmarks found."
    
    # Header
    lines = [
        f"{'ID':<6} {'Service':<25} {'Job ID':<12} {'Clients':<8} {'Created'}",
        "-" * 75
    ]
    
    for b in benchmarks:
        created = b.created_at.strftime("%Y-%m-%d %H:%M") if b.created_at else "?"
        service = (b.service_name or "?")[:24]
        job_id = str(b.service_job_id or "?")[:11]
        lines.append(f"{b.benchmark_id:<6} {service:<25} {job_id:<12} {b.num_clients:<8} {created}")
    
    return "\n".join(lines)


def format_benchmark_summary(summary: BenchmarkSummary) -> str:
    """
    Format a benchmark summary as a nice text report.
    
    Args:
        summary: BenchmarkSummary object
        
    Returns:
        Formatted summary string
    """
    lines = [
        f"",
        f"{'='*60}",
        f"Benchmark {summary.benchmark_id} - {summary.service_name or 'Unknown Service'}",
        f"{'='*60}",
        f"",
        f"Service:",
        f"  Name:      {summary.service_name or '?'}",
        f"  Job ID:    {summary.service_job_id or '?'}",
        f"  Hostname:  {summary.service_hostname or '?'}",
        f"  Image:     {summary.service_image or '?'}",
        f"",
    ]
    
    if summary.clients:
        lines.append(f"Clients ({len(summary.clients)}):")
        for c in summary.clients:
            lines.append(f"  - {c.get('name', '?')} (Job {c.get('job_id', '?')}) on {c.get('hostname', '?')}")
    else:
        lines.append("Clients: None")
    
    lines.extend([
        f"",
        f"Created: {summary.created_at.strftime('%Y-%m-%d %H:%M:%S') if summary.created_at else '?'}",
        f"",
        f"Logs: {summary.log_dir or '?'}",
        f"{'='*60}",
    ])
    
    return "\n".join(lines)
