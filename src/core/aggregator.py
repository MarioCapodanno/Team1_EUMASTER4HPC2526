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
    timestamps = [
        r.get("timestamp_start", 0) for r in actual_requests if r.get("timestamp_start")
    ]
    if timestamps:
        summary["test_duration_s"] = max(timestamps) - min(timestamps)
        summary["test_start_time"] = min(timestamps)
        summary["test_end_time"] = max(timestamps)

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
    from artifacts import read_requests_jsonl

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


def compare_summaries(
    summary1: Dict[str, Any], summary2: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Compare two benchmark summaries and highlight differences.

    Args:
        summary1: First (baseline) summary
        summary2: Second (current) summary

    Returns:
        Comparison results
    """
    comparison = {
        "baseline": summary1.get("service_type", "unknown"),
        "current": summary2.get("service_type", "unknown"),
        "metrics": {},
    }

    # Compare key metrics
    metrics_to_compare = [
        ("success_rate", "Success Rate (%)"),
        ("latency_s.avg", "Avg Latency (s)"),
        ("latency_s.p95", "P95 Latency (s)"),
        ("latency_s.p99", "P99 Latency (s)"),
        ("requests_per_second", "Throughput (RPS)"),
    ]

    for metric_path, label in metrics_to_compare:
        keys = metric_path.split(".")
        val1 = summary1
        val2 = summary2

        for key in keys:
            val1 = val1.get(key, 0) if isinstance(val1, dict) else 0
            val2 = val2.get(key, 0) if isinstance(val2, dict) else 0

        delta = val2 - val1
        pct_change = (delta / val1 * 100) if val1 != 0 else 0

        comparison["metrics"][metric_path] = {
            "label": label,
            "baseline": val1,
            "current": val2,
            "delta": delta,
            "percent_change": pct_change,
            "regression": False,
        }

        # Mark regressions
        if "latency" in label.lower() and delta > 0:
            comparison["metrics"][metric_path]["regression"] = True
        elif "Success Rate" in label and delta < 0:
            comparison["metrics"][metric_path]["regression"] = True
        elif "Throughput" in label and delta < 0:
            comparison["metrics"][metric_path]["regression"] = True

    return comparison
