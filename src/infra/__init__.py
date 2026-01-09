"""
Infrastructure and I/O for the benchmarking framework.

Contains:
- communicator: SSH communication
- storage: Persistence layer
- health: Health checks
- logs: Log retrieval
"""

from .communicator import SSHCommunicator
from .storage import (
    get_storage_manager,
    StorageManager,
    format_benchmark_summary,
    format_benchmark_table,
    get_benchmark_summary,
    list_all_benchmarks,
)
from .health import check_http_health, wait_for_service_healthy
from .logs import LogManager, LogEntry, LogFile
