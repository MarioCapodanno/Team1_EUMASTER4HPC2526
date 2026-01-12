#!/usr/bin/env python3
"""
Monitor module for the AI Factory Benchmarking Framework.

Collects and stores performance metrics from benchmark runs including:
- Slurm job metrics (CPU time, memory usage)
- GPU metrics (utilization, memory)
- Custom application metrics
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from infra.communicator import SSHCommunicator


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
            "benchmark_id": self.benchmark_id,
            "collected_at": self.collected_at.isoformat(),
            "service_metrics": self.service_metrics.to_dict()
            if self.service_metrics
            else None,
            "client_metrics": [c.to_dict() for c in self.client_metrics],
            "gpu_metrics": [g.to_dict() for g in self.gpu_metrics],
            "custom_metrics": self.custom_metrics,
        }

    def save(self, storage_dir: str = ".benchmark_storage") -> bool:
        """Save metrics to JSON file."""
        try:
            metrics_dir = Path(storage_dir) / self.benchmark_id
            metrics_dir.mkdir(parents=True, exist_ok=True)

            metrics_file = metrics_dir / "metrics.json"
            with open(metrics_file, "w") as f:
                json.dump(self.to_dict(), f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving metrics: {e}")
            return False

    @classmethod
    def load(
        cls, benchmark_id: str, storage_dir: str = ".benchmark_storage"
    ) -> Optional["BenchmarkMetrics"]:
        """Load metrics from JSON file."""
        try:
            metrics_file = Path(storage_dir) / benchmark_id / "metrics.json"
            if not metrics_file.exists():
                return None

            with open(metrics_file, "r") as f:
                data = json.load(f)

            metrics = cls(benchmark_id=benchmark_id)
            metrics.collected_at = datetime.fromisoformat(
                data.get("collected_at", datetime.now().isoformat())
            )

            if data.get("service_metrics"):
                metrics.service_metrics = JobMetrics(**data["service_metrics"])

            metrics.client_metrics = [
                JobMetrics(**c) for c in data.get("client_metrics", [])
            ]
            metrics.gpu_metrics = [GPUMetrics(**g) for g in data.get("gpu_metrics", [])]
            metrics.custom_metrics = data.get("custom_metrics", {})

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
        lines = result.stdout.strip().split("\n")
        for line in lines:
            parts = line.split("|")
            if (
                len(parts) >= 9
                and ".batch" not in parts[0]
                and ".extern" not in parts[0]
            ):
                return JobMetrics(
                    job_id=parts[0],
                    job_name=parts[1],
                    state=parts[2],
                    elapsed_time=parts[3],
                    cpu_time=parts[4],
                    max_memory=parts[5],
                    avg_memory=parts[6],
                    exit_code=parts[7],
                    node_list=parts[8],
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
        for line in result.stdout.strip().split("\n"):
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 6:
                try:
                    metrics.append(
                        GPUMetrics(
                            gpu_index=int(parts[0]),
                            name=parts[1],
                            utilization_percent=float(parts[2]) if parts[2] else 0.0,
                            memory_used_mb=float(parts[3]) if parts[3] else 0.0,
                            memory_total_mb=float(parts[4]) if parts[4] else 0.0,
                            temperature_c=float(parts[5]) if parts[5] else 0.0,
                        )
                    )
                except (ValueError, IndexError):
                    continue

        return metrics

    def collect_benchmark_metrics(
        self,
        benchmark_id: str,
        service_job_id: Optional[str] = None,
        client_job_ids: Optional[List[str]] = None,
        service_hostname: Optional[str] = None,
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
        "",
    ]

    # Service metrics
    if metrics.service_metrics:
        sm = metrics.service_metrics
        lines.extend(
            [
                "Service Job:",
                f"  Job ID:    {sm.job_id}",
                f"  Name:      {sm.job_name}",
                f"  State:     {sm.state}",
                f"  Elapsed:   {sm.elapsed_time}",
                f"  CPU Time:  {sm.cpu_time}",
                f"  Max Mem:   {sm.max_memory}",
                f"  Node:      {sm.node_list}",
                "",
            ]
        )

    # Client metrics
    if metrics.client_metrics:
        lines.append(f"Client Jobs ({len(metrics.client_metrics)}):")
        for cm in metrics.client_metrics:
            lines.append(
                f"  [{cm.job_id}] {cm.job_name}: {cm.state} ({cm.elapsed_time})"
            )
        lines.append("")

    # GPU metrics
    if metrics.gpu_metrics:
        lines.append("GPU Metrics:")
        for gm in metrics.gpu_metrics:
            lines.append(f"  GPU {gm.gpu_index} ({gm.name}):")
            lines.append(f"    Utilization: {gm.utilization_percent:.1f}%")
            lines.append(
                f"    Memory: {gm.memory_used_mb:.0f}/{gm.memory_total_mb:.0f} MB"
            )
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


def format_prometheus_metrics(
    summary: Dict[str, Any], 
    benchmark_id: str, 
    service_type: str,
    job_metrics: Optional[JobMetrics] = None,
    gpu_metrics: Optional[List[GPUMetrics]] = None,
    run_data: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Format benchmark metrics as comprehensive Prometheus exposition format.
    
    This function provides extensive metrics for monitoring and observability:
    - Request counts and success/failure rates
    - Latency statistics (all percentiles, min, max, std, avg)
    - Throughput (RPS, tokens/s for LLM, TPS for DB)
    - Service-specific metrics
    - Cluster resource utilization (GPU, memory, CPU time)
    - Error breakdown
    - Client concurrency and test configuration
    
    Args:
        summary: Summary data from summary.json
        benchmark_id: Benchmark ID
        service_type: Type of service (e.g., "ollama", "redis", "postgres")
        job_metrics: Optional Slurm job metrics for resource utilization
        gpu_metrics: Optional GPU metrics from nvidia-smi
        run_data: Optional run metadata for configuration info
    
    Returns:
        Prometheus-formatted metrics string
    """
    lines = []
    
    # Common labels
    labels = f'benchmark_id="{benchmark_id}",service="{service_type}"'
    
    # ==========================================================================
    # REQUEST METRICS
    # ==========================================================================
    lines.extend([
        "# HELP benchmark_requests_total Total number of benchmark requests",
        "# TYPE benchmark_requests_total counter",
        f'benchmark_requests_total{{{labels}}} {summary.get("total_requests", 0)}',
        "",
        "# HELP benchmark_requests_success Number of successful requests",
        "# TYPE benchmark_requests_success counter",
        f'benchmark_requests_success{{{labels}}} {summary.get("successful_requests", 0)}',
        "",
        "# HELP benchmark_requests_failed Number of failed requests",
        "# TYPE benchmark_requests_failed counter",
        f'benchmark_requests_failed{{{labels}}} {summary.get("failed_requests", 0)}',
        "",
        "# HELP benchmark_success_rate_percent Success rate as percentage (0-100)",
        "# TYPE benchmark_success_rate_percent gauge",
        f'benchmark_success_rate_percent{{{labels}}} {summary.get("success_rate", 0)}',
        ""
    ])
    
    # ==========================================================================
    # LATENCY METRICS (comprehensive)
    # ==========================================================================
    latency = summary.get("latency_s", {})
    
    lines.extend([
        "# HELP benchmark_latency_seconds Request latency distribution in seconds",
        "# TYPE benchmark_latency_seconds summary",
        f'benchmark_latency_seconds{{{labels},quantile="0.50"}} {latency.get("p50", 0)}',
        f'benchmark_latency_seconds{{{labels},quantile="0.90"}} {latency.get("p90", 0)}',
        f'benchmark_latency_seconds{{{labels},quantile="0.95"}} {latency.get("p95", 0)}',
        f'benchmark_latency_seconds{{{labels},quantile="0.99"}} {latency.get("p99", 0)}',
        "",
        "# HELP benchmark_latency_avg_seconds Average request latency",
        "# TYPE benchmark_latency_avg_seconds gauge",
        f'benchmark_latency_avg_seconds{{{labels}}} {latency.get("avg", 0)}',
        "",
        "# HELP benchmark_latency_min_seconds Minimum request latency",
        "# TYPE benchmark_latency_min_seconds gauge",
        f'benchmark_latency_min_seconds{{{labels}}} {latency.get("min", 0)}',
        "",
        "# HELP benchmark_latency_max_seconds Maximum request latency",
        "# TYPE benchmark_latency_max_seconds gauge",
        f'benchmark_latency_max_seconds{{{labels}}} {latency.get("max", 0)}',
        "",
        "# HELP benchmark_latency_std_seconds Standard deviation of latency",
        "# TYPE benchmark_latency_std_seconds gauge",
        f'benchmark_latency_std_seconds{{{labels}}} {latency.get("std", 0)}',
        ""
    ])
    
    # ==========================================================================
    # THROUGHPUT METRICS
    # ==========================================================================
    lines.extend([
        "# HELP benchmark_throughput_rps Throughput in requests per second",
        "# TYPE benchmark_throughput_rps gauge",
        f'benchmark_throughput_rps{{{labels}}} {summary.get("requests_per_second", 0)}',
        ""
    ])
    
    # ==========================================================================
    # TEST DURATION AND TIMING
    # ==========================================================================
    lines.extend([
        "# HELP benchmark_duration_seconds Total test duration in seconds",
        "# TYPE benchmark_duration_seconds gauge",
        f'benchmark_duration_seconds{{{labels}}} {summary.get("test_duration_s", 0)}',
        "",
        "# HELP benchmark_start_timestamp Unix timestamp when test started",
        "# TYPE benchmark_start_timestamp gauge",
        f'benchmark_start_timestamp{{{labels}}} {summary.get("test_start_time", 0)}',
        "",
        "# HELP benchmark_end_timestamp Unix timestamp when test ended",
        "# TYPE benchmark_end_timestamp gauge", 
        f'benchmark_end_timestamp{{{labels}}} {summary.get("test_end_time", 0)}',
        ""
    ])
    
    # ==========================================================================
    # SERVICE-SPECIFIC METRICS
    # ==========================================================================
    
    # LLM services (vLLM, Ollama)
    if service_type in ["vllm", "ollama"] or "tokens_per_second" in summary:
        lines.extend([
            "# HELP benchmark_llm_tokens_per_second Token generation throughput",
            "# TYPE benchmark_llm_tokens_per_second gauge",
            f'benchmark_llm_tokens_per_second{{{labels}}} {summary.get("tokens_per_second", 0)}',
            "",
            "# HELP benchmark_llm_avg_output_tokens Average output tokens per request",
            "# TYPE benchmark_llm_avg_output_tokens gauge",
            f'benchmark_llm_avg_output_tokens{{{labels}}} {summary.get("avg_output_tokens", 0)}',
            "",
            "# HELP benchmark_llm_avg_input_tokens Average input tokens per request",
            "# TYPE benchmark_llm_avg_input_tokens gauge",
            f'benchmark_llm_avg_input_tokens{{{labels}}} {summary.get("avg_input_tokens", 0)}',
            ""
        ])
    
    # Database services (Postgres, Redis)
    if service_type in ["postgres", "redis"] or "transactions_per_second" in summary:
        tps = summary.get("transactions_per_second", summary.get("requests_per_second", 0))
        lines.extend([
            "# HELP benchmark_db_transactions_per_second Database transactions per second",
            "# TYPE benchmark_db_transactions_per_second gauge",
            f'benchmark_db_transactions_per_second{{{labels}}} {tps}',
            ""
        ])
        
        # Per-operation metrics (Postgres and Redis)
        operations = summary.get("operations", {})
        if operations:
            # Add HELP/TYPE headers first
            lines.extend([
                "# HELP benchmark_db_operation_count Count per operation type",
                "# TYPE benchmark_db_operation_count counter",
                "# HELP benchmark_db_operation_throughput_rps Throughput per operation type",
                "# TYPE benchmark_db_operation_throughput_rps gauge",
                "# HELP benchmark_db_operation_avg_latency_seconds Average latency per operation",
                "# TYPE benchmark_db_operation_avg_latency_seconds gauge",
                "# HELP benchmark_db_operation_p50_latency_seconds P50 latency per operation",
                "# TYPE benchmark_db_operation_p50_latency_seconds gauge",
                "# HELP benchmark_db_operation_p95_latency_seconds P95 latency per operation",
                "# TYPE benchmark_db_operation_p95_latency_seconds gauge",
                "# HELP benchmark_db_operation_p99_latency_seconds P99 latency per operation",
                "# TYPE benchmark_db_operation_p99_latency_seconds gauge",
            ])
            
            for op_name, op_data in operations.items():
                if isinstance(op_data, dict):
                    op_labels = f'{labels},operation="{op_name}"'
                    lines.append(f'benchmark_db_operation_count{{{op_labels}}} {op_data.get("count", 0)}')
                    lines.append(f'benchmark_db_operation_throughput_rps{{{op_labels}}} {op_data.get("throughput", 0)}')
                    lines.append(f'benchmark_db_operation_avg_latency_seconds{{{op_labels}}} {op_data.get("avg_latency", 0)}')
                    lines.append(f'benchmark_db_operation_p50_latency_seconds{{{op_labels}}} {op_data.get("p50_latency", 0)}')
                    lines.append(f'benchmark_db_operation_p95_latency_seconds{{{op_labels}}} {op_data.get("p95_latency", 0)}')
                    lines.append(f'benchmark_db_operation_p99_latency_seconds{{{op_labels}}} {op_data.get("p99_latency", 0)}')
            lines.append("")
        
        # Redis-specific: payload size metrics
        if service_type == "redis" and summary.get("avg_payload_size_bytes"):
            lines.extend([
                "# HELP benchmark_redis_payload_size_bytes Average payload size used",
                "# TYPE benchmark_redis_payload_size_bytes gauge",
                f'benchmark_redis_payload_size_bytes{{{labels}}} {summary.get("avg_payload_size_bytes", 0)}',
                ""
            ])
    
    # Parametric configuration metrics (for scaling analysis in Grafana)
    parametric = summary.get("parametric", {})
    if parametric:
        lines.extend([
            "# HELP benchmark_parametric_concurrent_requests Number of concurrent requests/clients",
            "# TYPE benchmark_parametric_concurrent_requests gauge",
            f'benchmark_parametric_concurrent_requests{{{labels}}} {parametric.get("concurrent_requests", 0)}',
            "",
            "# HELP benchmark_parametric_payload_size_bytes Payload/data size in bytes",
            "# TYPE benchmark_parametric_payload_size_bytes gauge",
            f'benchmark_parametric_payload_size_bytes{{{labels}}} {parametric.get("payload_size_bytes", 0)}',
            "",
            "# HELP benchmark_parametric_prompt_length LLM prompt length in tokens",
            "# TYPE benchmark_parametric_prompt_length gauge",
            f'benchmark_parametric_prompt_length{{{labels}}} {parametric.get("prompt_length", 0)}',
            "",
            "# HELP benchmark_parametric_max_tokens LLM max output tokens",
            "# TYPE benchmark_parametric_max_tokens gauge",
            f'benchmark_parametric_max_tokens{{{labels}}} {parametric.get("max_tokens", 0)}',
            "",
            "# HELP benchmark_parametric_pipeline Pipeline depth for batching",
            "# TYPE benchmark_parametric_pipeline gauge",
            f'benchmark_parametric_pipeline{{{labels}}} {parametric.get("pipeline", 1)}',
            ""
        ])

    
    # Vector DB services (Chroma, Qdrant)
    if service_type in ["chroma", "qdrant"]:
        lines.extend([
            "# HELP benchmark_vector_queries_per_second Vector query throughput",
            "# TYPE benchmark_vector_queries_per_second gauge",
            f'benchmark_vector_queries_per_second{{{labels}}} {summary.get("requests_per_second", 0)}',
            ""
        ])
    
    # ==========================================================================
    # ERROR METRICS
    # ==========================================================================
    error_summary = summary.get("error_summary", {})
    if error_summary:
        lines.append("# HELP benchmark_errors_by_type Count of errors by error type")
        lines.append("# TYPE benchmark_errors_by_type counter")
        for error_type, count in error_summary.items():
            # Sanitize error type for label
            safe_error = str(error_type).replace('"', '\\"').replace("\n", " ")[:100]
            lines.append(f'benchmark_errors_by_type{{{labels},error_type="{safe_error}"}} {count}')
        lines.append("")
    
    # ==========================================================================
    # CLIENT CONCURRENCY (from run_data if available)
    # ==========================================================================
    if run_data:
        num_clients = 0
        if "clients" in run_data:
            num_clients = len(run_data.get("clients", []))
        elif "benchmarks" in run_data:
            benchmarks_config = run_data.get("benchmarks", {})
            if isinstance(benchmarks_config, dict):
                num_clients = benchmarks_config.get("num_clients", 0)
        
        lines.extend([
            "# HELP benchmark_client_count Number of concurrent benchmark clients",
            "# TYPE benchmark_client_count gauge",
            f'benchmark_client_count{{{labels}}} {num_clients}',
            ""
        ])
    
    # ==========================================================================
    # CLUSTER RESOURCE METRICS (from job_metrics if available)
    # ==========================================================================
    if job_metrics:
        # Parse elapsed time (format: HH:MM:SS or D-HH:MM:SS)
        elapsed = job_metrics.elapsed_time
        elapsed_seconds = 0
        if elapsed:
            try:
                parts = elapsed.replace("-", ":").split(":")
                if len(parts) == 4:  # D-HH:MM:SS
                    elapsed_seconds = int(parts[0]) * 86400 + int(parts[1]) * 3600 + int(parts[2]) * 60 + int(parts[3])
                elif len(parts) == 3:  # HH:MM:SS
                    elapsed_seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            except (ValueError, IndexError):
                pass
        
        # Parse memory (format: 123456K or 123M or 1G)
        def parse_memory_mb(mem_str: str) -> float:
            if not mem_str:
                return 0.0
            mem_str = mem_str.strip().upper()
            try:
                if mem_str.endswith("K"):
                    return float(mem_str[:-1]) / 1024
                elif mem_str.endswith("M"):
                    return float(mem_str[:-1])
                elif mem_str.endswith("G"):
                    return float(mem_str[:-1]) * 1024
                return float(mem_str) / (1024 * 1024)  # Assume bytes
            except (ValueError, TypeError):
                return 0.0
        
        lines.extend([
            "# HELP benchmark_slurm_elapsed_seconds Slurm job elapsed time in seconds",
            "# TYPE benchmark_slurm_elapsed_seconds gauge",
            f'benchmark_slurm_elapsed_seconds{{{labels},job_id="{job_metrics.job_id}"}} {elapsed_seconds}',
            "",
            "# HELP benchmark_slurm_max_memory_mb Maximum memory used by job in MB",
            "# TYPE benchmark_slurm_max_memory_mb gauge",
            f'benchmark_slurm_max_memory_mb{{{labels},job_id="{job_metrics.job_id}"}} {parse_memory_mb(job_metrics.max_memory)}',
            "",
            "# HELP benchmark_slurm_job_state Current state of Slurm job",
            "# TYPE benchmark_slurm_job_state gauge",
            f'benchmark_slurm_job_state{{{labels},job_id="{job_metrics.job_id}",state="{job_metrics.state}"}} 1',
            ""
        ])
    
    # ==========================================================================
    # GPU METRICS (from gpu_metrics if available)
    # ==========================================================================
    if gpu_metrics:
        lines.append("# HELP benchmark_gpu_utilization_percent GPU utilization percentage")
        lines.append("# TYPE benchmark_gpu_utilization_percent gauge")
        lines.append("# HELP benchmark_gpu_memory_used_mb GPU memory used in MB")
        lines.append("# TYPE benchmark_gpu_memory_used_mb gauge")
        lines.append("# HELP benchmark_gpu_memory_total_mb Total GPU memory in MB")
        lines.append("# TYPE benchmark_gpu_memory_total_mb gauge")
        lines.append("# HELP benchmark_gpu_memory_utilization_percent GPU memory utilization percentage")
        lines.append("# TYPE benchmark_gpu_memory_utilization_percent gauge")
        lines.append("# HELP benchmark_gpu_temperature_celsius GPU temperature in Celsius")
        lines.append("# TYPE benchmark_gpu_temperature_celsius gauge")
        
        for gm in gpu_metrics:
            gpu_labels = f'{labels},gpu="{gm.gpu_index}",gpu_name="{gm.name}"'
            mem_util = (gm.memory_used_mb / gm.memory_total_mb * 100) if gm.memory_total_mb > 0 else 0
            
            lines.extend([
                f'benchmark_gpu_utilization_percent{{{gpu_labels}}} {gm.utilization_percent}',
                f'benchmark_gpu_memory_used_mb{{{gpu_labels}}} {gm.memory_used_mb}',
                f'benchmark_gpu_memory_total_mb{{{gpu_labels}}} {gm.memory_total_mb}',
                f'benchmark_gpu_memory_utilization_percent{{{gpu_labels}}} {mem_util:.1f}',
                f'benchmark_gpu_temperature_celsius{{{gpu_labels}}} {gm.temperature_c}',
            ])
        lines.append("")
    
    # ==========================================================================
    # INFO METRIC (for Grafana labels)
    # ==========================================================================
    info_labels = [f'{labels}']
    if run_data:
        service_info = run_data.get("service", {})
        if isinstance(service_info, dict):
            if service_info.get("image"):
                info_labels.append(f'image="{service_info.get("image")}"')
            if service_info.get("partition"):
                info_labels.append(f'partition="{service_info.get("partition")}"')
            if service_info.get("num_gpus"):
                info_labels.append(f'num_gpus="{service_info.get("num_gpus")}"')
    
    lines.extend([
        "# HELP benchmark_info Benchmark metadata (use for joining with other metrics)",
        "# TYPE benchmark_info gauge",
        f'benchmark_info{{{",".join(info_labels)}}} 1',
    ])
    
    return "\n".join(lines)
