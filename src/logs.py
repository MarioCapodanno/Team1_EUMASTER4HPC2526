#!/usr/bin/env python3
"""
Logs module for the AI Factory Benchmarking Framework.

Provides log management capabilities:
- Download logs from cluster
- Aggregate and search logs
- Store logs locally for offline access
"""

import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from communicator import SSHCommunicator
from storage import get_storage_manager, get_benchmark_summary


@dataclass
class LogEntry:
    """A single log entry."""
    timestamp: Optional[datetime]
    level: str
    message: str
    source: str  # e.g., "service:postgres-db" or "client:client-postgres-db-1"


@dataclass
class LogFile:
    """Represents a log file."""
    name: str
    path: str
    size: int
    job_id: str
    job_type: str  # "service" or "client"
    content: Optional[str] = None


class LogManager:
    """Manages benchmark logs."""
    
    def __init__(self, communicator: Optional[SSHCommunicator] = None, local_log_dir: str = "logs"):
        self.communicator = communicator
        self.local_log_dir = Path(local_log_dir)
        self.local_log_dir.mkdir(parents=True, exist_ok=True)
    
    def list_remote_logs(self, benchmark_id: str, working_dir: str = "~") -> List[LogFile]:
        """
        List all log files for a benchmark on the cluster.
        
        Args:
            benchmark_id: Benchmark ID
            working_dir: Base working directory on cluster
            
        Returns:
            List of LogFile objects
        """
        if not self.communicator:
            return []
        
        log_dir = f"{working_dir}/benchmark_{benchmark_id}/logs"
        
        # List files with size
        cmd = f"ls -la {log_dir}/*.out {log_dir}/*.err 2>/dev/null | awk '{{print $5, $9}}'"
        result = self.communicator.execute_command(cmd)
        
        if not result.success:
            return []
        
        logs = []
        for line in result.stdout.strip().split('\n'):
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 2:
                try:
                    size = int(parts[0])
                    path = parts[1]
                    name = os.path.basename(path)
                    
                    # Extract job ID and type from filename
                    # Format: {name}_{jobid}.out or {name}_{jobid}.err
                    match = re.match(r'(.+)_(\d+)\.(out|err)', name)
                    if match:
                        job_name = match.group(1)
                        job_id = match.group(2)
                        job_type = "service" if not job_name.startswith("client-") else "client"
                        
                        logs.append(LogFile(
                            name=name,
                            path=path,
                            size=size,
                            job_id=job_id,
                            job_type=job_type
                        ))
                except (ValueError, IndexError):
                    continue
        
        return logs
    
    def download_logs(self, benchmark_id: str, working_dir: str = "~") -> Path:
        """
        Download all logs for a benchmark to local storage.
        
        Args:
            benchmark_id: Benchmark ID
            working_dir: Base working directory on cluster
            
        Returns:
            Path to local log directory
        """
        if not self.communicator:
            raise RuntimeError("No communicator available")
        
        local_dir = self.local_log_dir / benchmark_id
        local_dir.mkdir(parents=True, exist_ok=True)
        
        remote_log_dir = f"{working_dir}/benchmark_{benchmark_id}/logs"
        
        # Use rsync or scp to download
        # For now, download each file individually
        logs = self.list_remote_logs(benchmark_id, working_dir)
        
        for log in logs:
            local_path = local_dir / log.name
            # Read content and save locally
            result = self.communicator.execute_command(f"cat {log.path}")
            if result.success:
                local_path.write_text(result.stdout)
        
        return local_dir
    
    def get_log_content(self, benchmark_id: str, log_name: str, 
                        num_lines: Optional[int] = None, 
                        from_local: bool = False) -> Optional[str]:
        """
        Get content of a specific log file.
        
        Args:
            benchmark_id: Benchmark ID
            log_name: Name of the log file
            num_lines: If specified, only return last N lines
            from_local: If True, read from local storage
            
        Returns:
            Log content or None
        """
        if from_local:
            local_path = self.local_log_dir / benchmark_id / log_name
            if local_path.exists():
                content = local_path.read_text()
                if num_lines:
                    lines = content.split('\n')
                    content = '\n'.join(lines[-num_lines:])
                return content
            return None
        
        if not self.communicator:
            return None
        
        # Get from remote
        summary = get_benchmark_summary(benchmark_id)
        if not summary or not summary.log_dir:
            return None
        
        log_path = f"{summary.log_dir}/{log_name}"
        
        if num_lines:
            cmd = f"tail -n {num_lines} {log_path}"
        else:
            cmd = f"cat {log_path}"
        
        result = self.communicator.execute_command(cmd)
        return result.stdout if result.success else None
    
    def search_logs(self, benchmark_id: str, pattern: str, 
                    case_insensitive: bool = True) -> List[Tuple[str, str]]:
        """
        Search for a pattern in logs.
        
        Args:
            benchmark_id: Benchmark ID
            pattern: Search pattern (regex)
            case_insensitive: Whether to ignore case
            
        Returns:
            List of (log_name, matching_line) tuples
        """
        results = []
        local_dir = self.local_log_dir / benchmark_id
        
        if not local_dir.exists():
            return results
        
        flags = re.IGNORECASE if case_insensitive else 0
        regex = re.compile(pattern, flags)
        
        for log_file in local_dir.glob("*.out"):
            content = log_file.read_text()
            for line in content.split('\n'):
                if regex.search(line):
                    results.append((log_file.name, line.strip()))
        
        return results
    
    def aggregate_logs(self, benchmark_id: str) -> str:
        """
        Aggregate all logs for a benchmark into a single timeline.
        
        Args:
            benchmark_id: Benchmark ID
            
        Returns:
            Aggregated log content
        """
        local_dir = self.local_log_dir / benchmark_id
        
        if not local_dir.exists():
            return "No local logs found. Run download_logs first."
        
        entries = []
        
        for log_file in sorted(local_dir.glob("*.out")):
            source = log_file.stem  # e.g., "postgres-db_12345"
            content = log_file.read_text()
            
            for line in content.split('\n'):
                if line.strip():
                    entries.append(f"[{source}] {line}")
        
        return '\n'.join(entries)


def format_log_list(logs: List[LogFile]) -> str:
    """Format a list of log files as a table."""
    if not logs:
        return "No log files found."
    
    lines = [
        f"{'Name':<45} {'Size':<10} {'Type':<10} {'Job ID'}",
        "-" * 80
    ]
    
    for log in sorted(logs, key=lambda x: (x.job_type, x.name)):
        size_str = f"{log.size:,}" if log.size < 1024 else f"{log.size/1024:.1f}K"
        lines.append(f"{log.name:<45} {size_str:<10} {log.job_type:<10} {log.job_id}")
    
    return '\n'.join(lines)
