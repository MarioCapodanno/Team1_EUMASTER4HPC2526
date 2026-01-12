"""
Aggregator module for processing benchmark request data into summary metrics.

This module processes requests.jsonl files to generate summary.json with
aggregated metrics like latency percentiles, throughput, and success rates.
"""

import json
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np


def calculate_percentiles(
    values: List[float], percentiles: List[float]
) -> Dict[str, float]:
    """
    Calculate percentiles for a list of values.

    Args:
        values: List of numeric values
        percentiles: List of percentiles to calculate (e.g., [50, 90, 95, 99])

    Returns:
        Dictionary mapping percentile to value
    """
    if not values:
        return {f"p{p}": 0.0 for p in percentiles}

    sorted_values = sorted(values)
    result = {}

    for p in percentiles:
        # Use numpy for accurate percentile calculation
        result[f"p{p}"] = float(np.percentile(sorted_values, p))

    return result


def aggregate_requests(requests: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Aggregate a list of request dictionaries into summary metrics.

    Args:
        requests: List of request dictionaries from requests.jsonl

    Returns:
        Summary metrics dictionary
    """
    if not requests:
        return {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "success_rate": 0.0,
            "latency_s": {
                "avg": 0.0,
                "min": 0.0,
                "max": 0.0,
                "p50": 0.0,
                "p90": 0.0,
                "p95": 0.0,
                "p99": 0.0,
            },
            "requests_per_second": 0.0,
            "errors": [],
        }

    # Filter out test start entries and get actual requests
    # Also filter out entries with literal $BENCHMARK_ID (malformed)
    actual_requests = [
        r
        for r in requests
        if ("request_id" in r or "operation_type" in r)
        and r.get("benchmark_id") != "$BENCHMARK_ID"
    ]

    if not actual_requests:
        return aggregate_empty_summary()

    # Separate successful and failed requests
    successful = [r for r in actual_requests if r.get("success", False)]
    failed = [r for r in actual_requests if not r.get("success", False)]

    # Extract latencies from successful requests
    latencies = [r.get("latency_s", 0) for r in successful if r.get("latency_s", 0) > 0]

    # Calculate basic metrics
    total_requests = len(actual_requests)
    successful_requests = len(successful)
    failed_requests = len(failed)
    success_rate = (
        (successful_requests / total_requests * 100) if total_requests > 0 else 0
    )

    # Calculate latency statistics
    latency_stats = {}
    if latencies:
        latency_stats = {
            "avg": statistics.mean(latencies),
            "min": min(latencies),
            "max": max(latencies),
            "std": statistics.stdev(latencies) if len(latencies) > 1 else 0.0,
        }
        # Add percentiles
        latency_stats.update(calculate_percentiles(latencies, [50, 90, 95, 99]))
    else:
        latency_stats = {
            "avg": 0.0,
            "min": 0.0,
            "max": 0.0,
            "std": 0.0,
            "p50": 0.0,
            "p90": 0.0,
            "p95": 0.0,
            "p99": 0.0,
        }

    # Calculate throughput (requests per second)
    requests_per_second = 0.0
    duration = 0.0
    start_times = []
    end_times = []

    if actual_requests:
        start_times = [
            r.get("timestamp_start", 0)
            for r in actual_requests
            if r.get("timestamp_start")
        ]
        end_times = [
            (r.get("timestamp_end") or r.get("timestamp_start") or 0)
            for r in actual_requests
            if (r.get("timestamp_end") or r.get("timestamp_start"))
        ]

        if start_times and end_times:
            duration = max(end_times) - min(start_times)
            
            # Fix for sub-second tests where integer timestamps result in 0 duration
            # Ensure duration is at least the maximum latency of any single request
            if latency_stats and "max" in latency_stats:
                duration = max(duration, latency_stats["max"])
            else:
                # Fallback epsilon if no latency stats
                duration = max(duration, 0.000001)

            if duration > 0:
                requests_per_second = total_requests / duration

    # Calculate service-specific metrics
    service_type = actual_requests[0].get("service_type", "unknown")
    service_metrics = {}

    if service_type in ["vllm", "ollama"]:
        # LLM-specific metrics
        output_tokens = [r.get("output_tokens", 0) for r in successful]
        input_tokens = [r.get("input_tokens", 0) for r in successful]

        if output_tokens:
            service_metrics = {
                "tokens_per_second": sum(output_tokens) / duration
                if duration > 0
                else 0.0,
                "avg_output_tokens": statistics.mean(output_tokens),
                "avg_input_tokens": statistics.mean(input_tokens)
                if input_tokens
                else 0.0,
            }

    elif service_type == "postgres":
        # Database-specific metrics
        operations = {}
        for req in successful:
            op = req.get("operation_type", "unknown")
            if op not in operations:
                operations[op] = {"count": 0, "latencies": []}
            operations[op]["count"] += 1
            if req.get("latency_s", 0) > 0:
                operations[op]["latencies"].append(req.get("latency_s", 0))

        # Calculate per-operation metrics
        for op, data in operations.items():
            if data["latencies"]:
                data["avg_latency"] = statistics.mean(data["latencies"])
                data["p95_latency"] = calculate_percentiles(data["latencies"], [95])[
                    "p95"
                ]

        service_metrics = {
            "operations": operations,
            "transactions_per_second": requests_per_second,  # Alias for DB
        }

    elif service_type == "redis":
        # Redis-specific metrics with per-operation breakdown (Team10-style)
        operations = {}
        payload_sizes = []
        
        for req in successful:
            op = req.get("operation_type", "unknown").upper()
            if op not in operations:
                operations[op] = {"count": 0, "latencies": [], "throughput": 0}
            operations[op]["count"] += 1
            if req.get("latency_s", 0) > 0:
                operations[op]["latencies"].append(req.get("latency_s", 0))
            
            # Collect payload sizes if available
            if req.get("payload_size_bytes"):
                payload_sizes.append(req.get("payload_size_bytes"))

        # Calculate per-operation metrics
        for op, data in operations.items():
            if data["latencies"]:
                data["avg_latency"] = statistics.mean(data["latencies"])
                data["min_latency"] = min(data["latencies"])
                data["max_latency"] = max(data["latencies"])
                percentiles = calculate_percentiles(data["latencies"], [50, 95, 99])
                data["p50_latency"] = percentiles["p50"]
                data["p95_latency"] = percentiles["p95"]
                data["p99_latency"] = percentiles["p99"]
                if duration > 0:
                    data["throughput"] = data["count"] / duration
                # Clean up raw latencies to save space
                del data["latencies"]

        service_metrics = {
            "operations": operations,
            "transactions_per_second": requests_per_second,
        }
        
        # Add payload size info if collected
        if payload_sizes:
            service_metrics["avg_payload_size_bytes"] = statistics.mean(payload_sizes)
            service_metrics["payload_sizes_used"] = list(set(payload_sizes))

    # Collect error information
    error_types = {}
    for req in failed:
        error = req.get("error", "unknown")
        error_types[error] = error_types.get(error, 0) + 1

    # Build summary
    summary = {
        "total_requests": total_requests,
        "successful_requests": successful_requests,
        "failed_requests": failed_requests,
        "success_rate": success_rate,
        "service_type": service_type,
        "latency_s": latency_stats,
        "requests_per_second": requests_per_second,
        "error_summary": error_types,
        **service_metrics,
    }

    # Add timestamp range
    if start_times and end_times:
        summary["test_duration_s"] = duration
        summary["test_start_time"] = min(start_times)
        summary["test_end_time"] = max(end_times)

    # Extract parametric configuration (for scaling analysis)
    # These fields enable Team10-style plots: throughput vs clients, vs payload, etc.
    parametric_fields = {}
    
    # Get configuration from first request (should be consistent across all)
    first_req = actual_requests[0] if actual_requests else {}
    
    # Concurrency / client count
    if first_req.get("concurrent_requests"):
        parametric_fields["concurrent_requests"] = first_req.get("concurrent_requests")
    elif first_req.get("num_clients"):
        parametric_fields["concurrent_requests"] = first_req.get("num_clients")
    
    # Payload size (for Redis, DB benchmarks)
    if first_req.get("payload_size_bytes"):
        parametric_fields["payload_size_bytes"] = first_req.get("payload_size_bytes")
    elif first_req.get("data_size"):
        parametric_fields["payload_size_bytes"] = first_req.get("data_size")
    
    # LLM-specific parameters
    if first_req.get("prompt_length"):
        parametric_fields["prompt_length"] = first_req.get("prompt_length")
    if first_req.get("max_tokens"):
        parametric_fields["max_tokens"] = first_req.get("max_tokens")
    if first_req.get("model"):
        parametric_fields["model"] = first_req.get("model")
    
    # Pipeline depth (for Redis)
    if first_req.get("pipeline"):
        parametric_fields["pipeline"] = first_req.get("pipeline")
    
    if parametric_fields:
        summary["parametric"] = parametric_fields

    return summary


def aggregate_empty_summary() -> Dict[str, Any]:
    """Return an empty summary structure for benchmarks with no requests."""
    return {
        "total_requests": 0,
        "successful_requests": 0,
        "failed_requests": 0,
        "success_rate": 0.0,
        "service_type": "unknown",
        "latency_s": {
            "avg": 0.0,
            "min": 0.0,
            "max": 0.0,
            "std": 0.0,
            "p50": 0.0,
            "p90": 0.0,
            "p95": 0.0,
            "p99": 0.0,
        },
        "requests_per_second": 0.0,
        "error_summary": {},
        "test_duration_s": 0.0,
    }


def write_summary_json(benchmark_id: str, summary: Dict[str, Any]) -> Path:
    """
    Write summary metrics to summary.json file.

    Args:
        benchmark_id: Unique benchmark identifier
        summary: Summary metrics dictionary

    Returns:
        Path to the written summary.json file
    """
    results_dir = Path("results") / benchmark_id
    results_dir.mkdir(parents=True, exist_ok=True)

    summary_file = results_dir / "summary.json"
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)

    return summary_file


def aggregate_benchmark(benchmark_id: str) -> Optional[Dict[str, Any]]:
    """
    Load requests from a benchmark and aggregate them into a summary.

    Args:
        benchmark_id: Unique benchmark identifier

    Returns:
        Summary metrics dictionary, or None if requests file not found
    """
    from reporting.artifacts import read_requests_jsonl

    # Load requests
    requests = read_requests_jsonl(benchmark_id)

    if not requests:
        print(f"Warning: No requests found for benchmark {benchmark_id}")
        return None

    # Aggregate
    summary = aggregate_requests(requests)

    # Write summary
    write_summary_json(benchmark_id, summary)

    return summary


# Default regression thresholds (configurable)
DEFAULT_REGRESSION_THRESHOLDS = {
    "latency_pct": 10.0,       # Latency increase > 10% is a regression
    "throughput_pct": 10.0,    # Throughput decrease > 10% is a regression
    "success_rate_pct": 1.0,   # Success rate decrease > 1% is a regression
}


def compare_summaries(
    summary1: Dict[str, Any], 
    summary2: Dict[str, Any],
    thresholds: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    Compare two benchmark summaries and highlight differences (KF4 Regression Detection).

    Uses configurable thresholds to determine if a change is a significant regression.
    Default thresholds:
    - Latency: > 10% increase is a regression
    - Throughput: > 10% decrease is a regression  
    - Success rate: > 1% decrease is a regression

    Args:
        summary1: First (baseline) summary
        summary2: Second (current) summary
        thresholds: Optional dict with custom thresholds:
            - latency_pct: max allowed latency increase (%)
            - throughput_pct: max allowed throughput decrease (%)
            - success_rate_pct: max allowed success rate decrease (%)

    Returns:
        Comparison results with PASS/FAIL verdict
    """
    # Merge custom thresholds with defaults
    config = DEFAULT_REGRESSION_THRESHOLDS.copy()
    if thresholds:
        config.update(thresholds)
    
    comparison = {
        "baseline": summary1.get("service_type", "unknown"),
        "current": summary2.get("service_type", "unknown"),
        "thresholds": config,
        "metrics": {},
        "regressions": [],
        "improvements": [],
        "verdict": "PASS",
    }

    # Compare key metrics
    metrics_to_compare = [
        ("success_rate", "Success Rate (%)", "success_rate"),
        ("latency_s.avg", "Avg Latency (s)", "latency"),
        ("latency_s.p95", "P95 Latency (s)", "latency"),
        ("latency_s.p99", "P99 Latency (s)", "latency"),
        ("requests_per_second", "Throughput (RPS)", "throughput"),
    ]

    for metric_path, label, metric_type in metrics_to_compare:
        keys = metric_path.split(".")
        val1 = summary1
        val2 = summary2

        for key in keys:
            val1 = val1.get(key, 0) if isinstance(val1, dict) else 0
            val2 = val2.get(key, 0) if isinstance(val2, dict) else 0

        delta = val2 - val1
        pct_change = (delta / val1 * 100) if val1 != 0 else 0

        # Determine if this is a regression based on thresholds
        is_regression = False
        is_improvement = False
        threshold_used = None
        
        if metric_type == "latency":
            threshold_used = config["latency_pct"]
            if pct_change > threshold_used:  # Latency increased beyond threshold
                is_regression = True
            elif pct_change < -threshold_used:  # Latency decreased (improvement)
                is_improvement = True
        elif metric_type == "throughput":
            threshold_used = config["throughput_pct"]
            if pct_change < -threshold_used:  # Throughput decreased beyond threshold
                is_regression = True
            elif pct_change > threshold_used:  # Throughput increased (improvement)
                is_improvement = True
        elif metric_type == "success_rate":
            threshold_used = config["success_rate_pct"]
            if pct_change < -threshold_used:  # Success rate decreased beyond threshold
                is_regression = True
            elif pct_change > threshold_used:  # Success rate increased (improvement)
                is_improvement = True

        comparison["metrics"][metric_path] = {
            "label": label,
            "baseline": val1,
            "current": val2,
            "delta": delta,
            "percent_change": pct_change,
            "regression": is_regression,
            "improvement": is_improvement,
            "threshold": threshold_used,
        }

        if is_regression:
            comparison["regressions"].append({
                "metric": label,
                "change": f"{pct_change:+.1f}%",
                "threshold": f"{threshold_used}%",
            })
        elif is_improvement:
            comparison["improvements"].append({
                "metric": label,
                "change": f"{pct_change:+.1f}%",
            })

    # Set verdict
    if comparison["regressions"]:
        comparison["verdict"] = "FAIL"
    
    return comparison
