#!/usr/bin/env python3
"""
Monitor module for the AI Factory Benchmarking Framework.

Collects and stores performance metrics from benchmark runs including:
- Slurm job metrics (CPU time, memory usage)
- GPU metrics (utilization, memory)
- Custom application metrics
"""

import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from communicator import SSHCommunicator
from storage import get_storage_manager


@dataclass
class JobMetrics:
    """Metrics for a single Slurm job."""
    job_id: str
    job_name: str
    state: str = ""
    elapsed_time: str = ""
    cpu_time: str = ""
    max_memory: str = ""
    avg_memory: str = ""
    exit_code: str = ""
    node_list: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GPUMetrics:
    """GPU metrics from nvidia-smi."""
    gpu_index: int
    name: str = ""
    utilization_percent: float = 0.0
    memory_used_mb: float = 0.0
    memory_total_mb: float = 0.0
    temperature_c: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BenchmarkMetrics:
    """Complete metrics for a benchmark run."""
    benchmark_id: str
    collected_at: datetime = field(default_factory=datetime.now)
    service_metrics: Optional[JobMetrics] = None
    client_metrics: List[JobMetrics] = field(default_factory=list)
    gpu_metrics: List[GPUMetrics] = field(default_factory=list)
    custom_metrics: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'benchmark_id': self.benchmark_id,
            'collected_at': self.collected_at.isoformat(),
            'service_metrics': self.service_metrics.to_dict() if self.service_metrics else None,
            'client_metrics': [c.to_dict() for c in self.client_metrics],
            'gpu_metrics': [g.to_dict() for g in self.gpu_metrics],
            'custom_metrics': self.custom_metrics
        }
    
    def save(self, storage_dir: str = ".benchmark_storage") -> bool:
        """Save metrics to JSON file."""
        try:
            metrics_dir = Path(storage_dir) / self.benchmark_id
            metrics_dir.mkdir(parents=True, exist_ok=True)
            
            metrics_file = metrics_dir / "metrics.json"
            with open(metrics_file, 'w') as f:
                json.dump(self.to_dict(), f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving metrics: {e}")
            return False
    
    @classmethod
    def load(cls, benchmark_id: str, storage_dir: str = ".benchmark_storage") -> Optional['BenchmarkMetrics']:
        """Load metrics from JSON file."""
        try:
            metrics_file = Path(storage_dir) / benchmark_id / "metrics.json"
            if not metrics_file.exists():
                return None
            
            with open(metrics_file, 'r') as f:
                data = json.load(f)
            
            metrics = cls(benchmark_id=benchmark_id)
            metrics.collected_at = datetime.fromisoformat(data.get('collected_at', datetime.now().isoformat()))
            
            if data.get('service_metrics'):
                metrics.service_metrics = JobMetrics(**data['service_metrics'])
            
            metrics.client_metrics = [JobMetrics(**c) for c in data.get('client_metrics', [])]
            metrics.gpu_metrics = [GPUMetrics(**g) for g in data.get('gpu_metrics', [])]
            metrics.custom_metrics = data.get('custom_metrics', {})
            
            return metrics
        except Exception as e:
            print(f"Error loading metrics: {e}")
            return None


class MetricsCollector:
    """Collects metrics from the cluster."""
    
    def __init__(self, communicator: SSHCommunicator):
        self.communicator = communicator
    
    def collect_job_metrics(self, job_id: str) -> Optional[JobMetrics]:
        """
        Collect metrics for a Slurm job using sacct.
        
        Args:
            job_id: Slurm job ID
            
        Returns:
            JobMetrics object or None if collection failed
        """
        # Use sacct to get job metrics
        cmd = f"sacct -j {job_id} --format=JobID,JobName,State,Elapsed,CPUTime,MaxRSS,AveRSS,ExitCode,NodeList --noheader -P"
        result = self.communicator.execute_command(cmd)
        
        if not result.success or not result.stdout.strip():
            return None
        
        # Parse the first line (main job, not steps)
        lines = result.stdout.strip().split('\n')
        for line in lines:
            parts = line.split('|')
            if len(parts) >= 9 and not '.batch' in parts[0] and not '.extern' in parts[0]:
                return JobMetrics(
                    job_id=parts[0],
                    job_name=parts[1],
                    state=parts[2],
                    elapsed_time=parts[3],
                    cpu_time=parts[4],
                    max_memory=parts[5],
                    avg_memory=parts[6],
                    exit_code=parts[7],
                    node_list=parts[8]
                )
        
        return None
    
    def collect_gpu_metrics(self, hostname: str) -> List[GPUMetrics]:
        """
        Collect GPU metrics from a node using nvidia-smi.
        
        Args:
            hostname: Node hostname
            
        Returns:
            List of GPUMetrics objects
        """
        # Run nvidia-smi on the specific node via srun
        cmd = f"srun --nodelist={hostname} --time=00:01:00 nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv,noheader,nounits 2>/dev/null"
        result = self.communicator.execute_command(cmd)
        
        if not result.success or not result.stdout.strip():
            # Try alternative: direct nvidia-smi if already on node
            cmd = f"ssh {hostname} nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv,noheader,nounits 2>/dev/null"
            result = self.communicator.execute_command(cmd)
            
            if not result.success or not result.stdout.strip():
                return []
        
        metrics = []
        for line in result.stdout.strip().split('\n'):
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 6:
                try:
                    metrics.append(GPUMetrics(
                        gpu_index=int(parts[0]),
                        name=parts[1],
                        utilization_percent=float(parts[2]) if parts[2] else 0.0,
                        memory_used_mb=float(parts[3]) if parts[3] else 0.0,
                        memory_total_mb=float(parts[4]) if parts[4] else 0.0,
                        temperature_c=float(parts[5]) if parts[5] else 0.0
                    ))
                except (ValueError, IndexError):
                    continue
        
        return metrics
    
    def collect_benchmark_metrics(
        self,
        benchmark_id: str,
        service_job_id: Optional[str] = None,
        client_job_ids: Optional[List[str]] = None,
        service_hostname: Optional[str] = None
    ) -> BenchmarkMetrics:
        """
        Collect all metrics for a benchmark.
        
        Args:
            benchmark_id: Benchmark ID
            service_job_id: Service Slurm job ID
            client_job_ids: List of client Slurm job IDs
            service_hostname: Hostname where service is running (for GPU metrics)
            
        Returns:
            BenchmarkMetrics object
        """
        metrics = BenchmarkMetrics(benchmark_id=benchmark_id)
        
        # Collect service metrics
        if service_job_id:
            metrics.service_metrics = self.collect_job_metrics(service_job_id)
        
        # Collect client metrics
        if client_job_ids:
            for job_id in client_job_ids:
                job_metrics = self.collect_job_metrics(job_id)
                if job_metrics:
                    metrics.client_metrics.append(job_metrics)
        
        # Collect GPU metrics if hostname available
        if service_hostname:
            metrics.gpu_metrics = self.collect_gpu_metrics(service_hostname)
        
        return metrics


def format_metrics_report(metrics: BenchmarkMetrics) -> str:
    """Format metrics as a readable report."""
    lines = [
        "",
        "=" * 60,
        f"Metrics for Benchmark {metrics.benchmark_id}",
        "=" * 60,
        f"Collected: {metrics.collected_at.strftime('%Y-%m-%d %H:%M:%S')}",
        ""
    ]
    
    # Service metrics
    if metrics.service_metrics:
        sm = metrics.service_metrics
        lines.extend([
            "Service Job:",
            f"  Job ID:    {sm.job_id}",
            f"  Name:      {sm.job_name}",
            f"  State:     {sm.state}",
            f"  Elapsed:   {sm.elapsed_time}",
            f"  CPU Time:  {sm.cpu_time}",
            f"  Max Mem:   {sm.max_memory}",
            f"  Node:      {sm.node_list}",
            ""
        ])
    
    # Client metrics
    if metrics.client_metrics:
        lines.append(f"Client Jobs ({len(metrics.client_metrics)}):")
        for cm in metrics.client_metrics:
            lines.append(f"  [{cm.job_id}] {cm.job_name}: {cm.state} ({cm.elapsed_time})")
        lines.append("")
    
    # GPU metrics
    if metrics.gpu_metrics:
        lines.append("GPU Metrics:")
        for gm in metrics.gpu_metrics:
            lines.append(f"  GPU {gm.gpu_index} ({gm.name}):")
            lines.append(f"    Utilization: {gm.utilization_percent:.1f}%")
            lines.append(f"    Memory: {gm.memory_used_mb:.0f}/{gm.memory_total_mb:.0f} MB")
            lines.append(f"    Temperature: {gm.temperature_c:.0f}°C")
        lines.append("")
    
    # Custom metrics
    if metrics.custom_metrics:
        lines.append("Custom Metrics:")
        for key, value in metrics.custom_metrics.items():
            lines.append(f"  {key}: {value}")
        lines.append("")
    
    lines.append("=" * 60)
    return "\n".join(lines)
