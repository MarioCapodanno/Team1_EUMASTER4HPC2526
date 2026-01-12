"""
Analysis module for aggregating and analyzing benchmark results.

This module provides utilities to:
- Load benchmark data from the results directory
- Parse configuration parameters from run.json
- Group and aggregate benchmarks for comparative analysis
- Generate summary statistics across benchmark runs
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict


@dataclass
class BenchmarkResult:
    """Represents a single benchmark result with its configuration and metrics."""
    
    benchmark_id: str
    service_type: str
    service_name: str
    
    # Configuration parameters extracted from run.json
    num_clients: int = 1
    num_requests: int = 0
    payload_size: Optional[int] = None
    pipeline_depth: int = 1
    
    # Metrics from summary.json
    throughput_rps: float = 0.0
    latency_avg_ms: float = 0.0
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    latency_p99_ms: float = 0.0
    latency_max_ms: float = 0.0
    success_rate: float = 0.0
    total_requests: int = 0
    duration_s: float = 0.0
    
    # LLM-specific metrics
    tokens_per_second: float = 0.0
    avg_output_tokens: float = 0.0
    avg_input_tokens: float = 0.0
    
    # New metrics
    error_rate: float = 0.0
    
    # Database-specific metrics
    operations: Dict[str, Dict] = field(default_factory=dict)
    
    # Raw data for custom analysis
    raw_summary: Dict[str, Any] = field(default_factory=dict)
    raw_run: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def config_str(self) -> str:
        """Generate a human-readable configuration string."""
        parts = []
        if self.num_clients > 0:
            parts.append(f"{self.num_clients} client{'s' if self.num_clients > 1 else ''}")
        
        if self.payload_size:
            # Format size nicely (KB, MB)
            if self.payload_size >= 1024 * 1024:
                parts.append(f"{self.payload_size / (1024 * 1024):.1f}MB")
            elif self.payload_size >= 1024:
                parts.append(f"{self.payload_size / 1024:.0f}KB")
            else:
                parts.append(f"{self.payload_size}B")
                
        if self.pipeline_depth > 1:
            parts.append(f"pipe={self.pipeline_depth}")
            
        return ", ".join(parts) if parts else self.benchmark_id


class BenchmarkLoader:
    """
    Loads benchmark results from the results directory.
    
    Parses both summary.json (metrics) and run.json (configuration).
    """
    
    def __init__(self, results_dir: str = "results"):
        self.results_dir = Path(results_dir)
    
    def list_benchmarks(self) -> List[str]:
        """List all benchmark IDs in the results directory."""
        if not self.results_dir.exists():
            return []
        
        return [
            d.name for d in self.results_dir.iterdir() 
            if d.is_dir() and d.name.startswith("BM-")
        ]
    
    def load_benchmark(self, benchmark_id: str) -> Optional[BenchmarkResult]:
        """
        Load a single benchmark result.
        
        Args:
            benchmark_id: The benchmark ID (e.g., "BM-20260111-001")
            
        Returns:
            BenchmarkResult or None if not found
        """
        bm_dir = self.results_dir / benchmark_id
        
        if not bm_dir.exists():
            return None
        
        # Load run.json for configuration
        run_json_path = bm_dir / "run.json"
        run_data = {}
        if run_json_path.exists():
            try:
                run_data = json.loads(run_json_path.read_text())
            except (json.JSONDecodeError, IOError):
                pass
        
        # Load summary.json for metrics
        summary_json_path = bm_dir / "summary.json"
        summary_data = {}
        if summary_json_path.exists():
            try:
                summary_data = json.loads(summary_json_path.read_text())
            except (json.JSONDecodeError, IOError):
                pass
        
        # Parse configuration from run.json
        config = self._parse_config(run_data)
        
        # Extract service info
        service_type = summary_data.get("service_type", config.get("service_type", "unknown"))
        service_name = run_data.get("service", {}).get("name", "unknown")
        
        # Extract latency metrics (convert from seconds to milliseconds)
        latency = summary_data.get("latency_s", {})
        
        # Calculate error rate
        total_reqs = summary_data.get("total_requests", 0)
        failed_reqs = summary_data.get("failed_requests", 0)
        error_rate = (failed_reqs / total_reqs * 100) if total_reqs > 0 else 0.0
        
        result = BenchmarkResult(
            benchmark_id=benchmark_id,
            service_type=service_type,
            service_name=service_name,
            num_clients=config.get("num_clients", 1),
            num_requests=config.get("num_requests", 0),
            payload_size=config.get("payload_size"),
            pipeline_depth=config.get("pipeline_depth", 1),
            throughput_rps=summary_data.get("requests_per_second", 0.0),
            latency_avg_ms=latency.get("avg", 0) * 1000,
            latency_p50_ms=latency.get("p50", 0) * 1000,
            latency_p95_ms=latency.get("p95", 0) * 1000,
            latency_p99_ms=latency.get("p99", 0) * 1000,
            latency_max_ms=latency.get("max", 0) * 1000,
            success_rate=summary_data.get("success_rate", 0.0),
            total_requests=total_reqs,
            duration_s=summary_data.get("test_duration_s", 0.0),
            tokens_per_second=summary_data.get("tokens_per_second", 0.0),
            avg_output_tokens=summary_data.get("avg_output_tokens", 0.0),
            avg_input_tokens=summary_data.get("avg_input_tokens", 0.0),
            operations=summary_data.get("operations", {}),
            error_rate=error_rate,
            raw_summary=summary_data,
            raw_run=run_data,
        )
        
        return result
    
    def load_all(self) -> List[BenchmarkResult]:
        """Load all benchmarks from the results directory."""
        results = []
        for benchmark_id in self.list_benchmarks():
            result = self.load_benchmark(benchmark_id)
            if result:
                results.append(result)
        return results
    
    def load_by_service(self, service_type: str) -> List[BenchmarkResult]:
        """Load benchmarks for a specific service type."""
        return [r for r in self.load_all() if r.service_type == service_type]
    
    def _parse_config(self, run_data: Dict) -> Dict[str, Any]:
        """
        Parse configuration parameters from run.json.
        """
        config = {
            "num_clients": 1,
            "num_requests": 0,
            "payload_size": None,
            "pipeline_depth": 1,
            "service_type": "unknown",
        }
        
        clients = run_data.get("clients", [])
        config["num_clients"] = len(clients) if clients else 1
        
        # Try to parse service type from service config
        service = run_data.get("service", {})
        service_name = service.get("name", "")
        
        if "redis" in service_name.lower():
            config["service_type"] = "redis"
        elif "vllm" in service_name.lower():
            config["service_type"] = "vllm"
        elif "ollama" in service_name.lower():
            config["service_type"] = "ollama"
        elif "postgres" in service_name.lower():
            config["service_type"] = "postgres"
        
        # Try to extract parameters from client commands
        # We look at all clients to be robust
        for client in clients:
            command = client.get("command", "")
            
            # Extract number of requests
            requests_match = re.search(r'Requests:\s*(\d+)', command)
            if requests_match:
                config["num_requests"] = int(requests_match.group(1))
            
            # Extract payload/value size
            # Match "Value size: 256 bytes" or similar
            payload_match = re.search(r'Value size:\s*(\d+)\s*bytes?', command, re.I)
            if payload_match:
                config["payload_size"] = int(payload_match.group(1))
            
            # Extract pipeline depth
            pipeline_match = re.search(r'pipeline[=:\s]+(\d+)', command, re.I)
            if pipeline_match:
                config["pipeline_depth"] = int(pipeline_match.group(1))
                
        return config


class BenchmarkAnalyzer:
    """
    Analyzes and groups benchmarks for comparative analysis.
    """
    
    def __init__(self, results: List[BenchmarkResult]):
        self.results = results
    
    def group_by_service(self) -> Dict[str, List[BenchmarkResult]]:
        """Group benchmarks by service type."""
        groups = defaultdict(list)
        for r in self.results:
            groups[r.service_type].append(r)
        return dict(groups)
    
    def detect_varying_parameter(self) -> Optional[str]:
        """
        Detect which parameter varies across the loaded benchmarks.
        
        Returns:
            Name of varying parameter (num_clients, payload_size, pipeline_depth) 
            or None if multiple/none.
        """
        if not self.results:
            return None
            
        params = {
            "num_clients": set(),
            "payload_size": set(),
            "pipeline_depth": set()
        }
        
        for r in self.results:
            params["num_clients"].add(r.num_clients)
            params["payload_size"].add(r.payload_size)
            params["pipeline_depth"].add(r.pipeline_depth)
            
        varying = [k for k, v in params.items() if len(v) > 1]
        
        if len(varying) == 1:
            return varying[0]
        return None
    
    def get_scaling_data(
        self, 
        x_param: str = "num_clients",
        y_metric: str = "throughput_rps",
        filter_service: Optional[str] = None,
    ) -> Tuple[List[float], List[float], List[str]]:
        """
        Extract data for scaling plots.
        
        Args:
            x_param: Attribute to use for X axis
            y_metric: Attribute to use for Y axis
            filter_service: Optional service type filter
            
        Returns:
            Tuple of (x_values, y_values, labels)
        """
        filtered = self.results
        if filter_service:
            filtered = [r for r in self.results if r.service_type == filter_service]
        
        x_values = []
        y_values = []
        labels = []
        
        for r in filtered:
            x_val = getattr(r, x_param, None)
            y_val = getattr(r, y_metric, None)
            
            if x_val is not None and y_val is not None:
                x_values.append(x_val)
                y_values.append(y_val)
                # Use config string as label
                labels.append(r.config_str)
        
        return x_values, y_values, labels
    
    def get_latency_breakdown(
        self, 
        filter_service: Optional[str] = None
    ) -> Dict[str, Dict[str, float]]:
        """
        Get latency breakdown per benchmark.
        
        Returns:
            Dict mapping config_str to latency metrics dict
        """
        filtered = self.results
        if filter_service:
            filtered = [r for r in self.results if r.service_type == filter_service]
        
        breakdown = {}
        for r in filtered:
            # Use short ID if config string is duplicate or empty
            label = r.config_str or r.benchmark_id[-7:]
            
            # Start with base key
            key = label
            counter = 2
            while key in breakdown:
                key = f"{label} ({counter})"
                counter += 1
                
            breakdown[key] = {
                "avg": r.latency_avg_ms,
                "p50": r.latency_p50_ms,
                "p95": r.latency_p95_ms,
                "p99": r.latency_p99_ms,
                "max": r.latency_max_ms,
            }
        return breakdown
    
    def get_summary_stats(self) -> Dict[str, Any]:
        """Get overall summary statistics across all benchmarks."""
        if not self.results:
            return {}
        
        by_service = self.group_by_service()
        
        stats = {
            "total_benchmarks": len(self.results),
            "services": {},
        }
        
        for service_type, benchmarks in by_service.items():
            throughputs = [b.throughput_rps for b in benchmarks if b.throughput_rps > 0]
            latencies = [b.latency_avg_ms for b in benchmarks if b.latency_avg_ms > 0]
            
            stats["services"][service_type] = {
                "count": len(benchmarks),
                "avg_throughput": sum(throughputs) / len(throughputs) if throughputs else 0,
                "max_throughput": max(throughputs) if throughputs else 0,
                "avg_latency_ms": sum(latencies) / len(latencies) if latencies else 0,
                "min_latency_ms": min(latencies) if latencies else 0,
            }
        
        return stats


def analyze_benchmarks(
    results_dir: str = "results",
    filter_service: Optional[str] = None,
) -> Tuple[BenchmarkLoader, BenchmarkAnalyzer]:
    """
    Convenience function to load and analyze benchmarks.
    """
    loader = BenchmarkLoader(results_dir)
    
    if filter_service:
        results = loader.load_by_service(filter_service)
    else:
        results = loader.load_all()
    
    analyzer = BenchmarkAnalyzer(results)
    
    return loader, analyzer
