"""
Bottleneck Attribution module (KF2) for identifying performance bottlenecks.

This module analyzes benchmark metrics to classify the most likely bottleneck:
- GPU-bound: High GPU utilization, stable CPU, rising latency
- CPU-bound: High CPU time/RSS, low GPU utilization
- Memory-bound: High RSS, rising latency, possible OOM/evictions
- Service queueing: Throughput saturates, P99 explodes, error rate rises
- Network/IO: Latency spikes without compute saturation

Output includes:
- Most likely bottleneck classification
- Supporting evidence from metrics
- Recommended next tuning actions
"""

from typing import Any, Dict, List, Optional, Tuple


def classify_bottleneck(
    summary: Dict[str, Any],
    slurm_metrics: Optional[Dict[str, Any]] = None,
    gpu_metrics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Classify the most likely bottleneck from benchmark metrics.

    Args:
        summary: Aggregated benchmark summary (from summary.json)
        slurm_metrics: Optional Slurm job metrics (CPUTime, MaxRSS, etc.)
        gpu_metrics: Optional GPU metrics (utilization, memory)

    Returns:
        Dictionary with bottleneck classification and evidence
    """
    evidence = []
    scores = {
        "gpu_bound": 0,
        "cpu_bound": 0,
        "memory_bound": 0,
        "queueing": 0,
        "network_io": 0,
        "healthy": 0,
    }

    # Extract key metrics
    success_rate = summary.get("success_rate", 100)
    throughput = summary.get("requests_per_second", 0)
    latency = summary.get("latency_s", {})
    p50 = latency.get("p50", 0)
    p95 = latency.get("p95", 0)
    p99 = latency.get("p99", 0)
    avg_latency = latency.get("avg", 0)
    total_requests = summary.get("total_requests", 0)
    failed_requests = summary.get("failed_requests", 0)
    error_summary = summary.get("error_summary", {})

    # Calculate latency spread (tail vs median)
    latency_spread = p99 / p50 if p50 > 0 else 0

    # 1. Check for queueing/overload indicators
    if latency_spread > 5:
        scores["queueing"] += 3
        evidence.append(f"High latency spread: P99/P50 = {latency_spread:.1f}x (queueing indicator)")

    if success_rate < 95:
        scores["queueing"] += 2
        evidence.append(f"Low success rate: {success_rate:.1f}% indicates overload")

    if failed_requests > 0 and "timeout" in str(error_summary).lower():
        scores["queueing"] += 2
        evidence.append(f"Timeout errors detected ({failed_requests} failures)")

    # 2. Check GPU metrics if available
    if gpu_metrics:
        gpu_util = gpu_metrics.get("gpu_utilization", 0)
        gpu_mem_used = gpu_metrics.get("memory_used_mb", 0)
        gpu_mem_total = gpu_metrics.get("memory_total_mb", 1)
        gpu_mem_pct = (gpu_mem_used / gpu_mem_total) * 100 if gpu_mem_total > 0 else 0

        if gpu_util > 90:
            scores["gpu_bound"] += 3
            evidence.append(f"High GPU utilization: {gpu_util:.0f}%")
        elif gpu_util > 70:
            scores["gpu_bound"] += 1
            evidence.append(f"Moderate GPU utilization: {gpu_util:.0f}%")
        elif gpu_util < 30:
            scores["cpu_bound"] += 1
            scores["network_io"] += 1
            evidence.append(f"Low GPU utilization: {gpu_util:.0f}% (not GPU-bound)")

        if gpu_mem_pct > 90:
            scores["memory_bound"] += 2
            evidence.append(f"High GPU memory usage: {gpu_mem_pct:.0f}%")

    # 3. Check Slurm/CPU metrics if available
    if slurm_metrics:
        max_rss_mb = slurm_metrics.get("max_rss_mb", 0)
        cpu_time = slurm_metrics.get("cpu_time_s", 0)
        elapsed_time = slurm_metrics.get("elapsed_s", 1)

        cpu_efficiency = (cpu_time / elapsed_time) * 100 if elapsed_time > 0 else 0

        if cpu_efficiency > 90:
            scores["cpu_bound"] += 2
            evidence.append(f"High CPU efficiency: {cpu_efficiency:.0f}%")

        if max_rss_mb > 8000:  # More than 8GB RSS
            scores["memory_bound"] += 2
            evidence.append(f"High memory usage: {max_rss_mb:.0f} MB RSS")

    # 4. Latency pattern analysis (when no hardware metrics available)
    if not gpu_metrics and not slurm_metrics:
        # Use latency patterns as proxy
        if p99 > 2.0:  # More than 2 seconds P99
            scores["queueing"] += 2
            evidence.append(f"High tail latency: P99 = {p99:.2f}s")

        if latency_spread > 3:
            scores["queueing"] += 1
        elif latency_spread < 1.5 and avg_latency > 0.5:
            # Consistent but slow - likely compute bound
            scores["gpu_bound"] += 1
            scores["cpu_bound"] += 1
            evidence.append(f"Consistent latency ({latency_spread:.1f}x spread) suggests compute-bound")

    # 5. Check for healthy operation
    if success_rate >= 99 and latency_spread < 2 and p99 < 1.0:
        scores["healthy"] += 3
        evidence.append("System operating within normal parameters")

    # Determine primary bottleneck
    max_score = max(scores.values())
    if max_score == 0:
        primary = "unknown"
    else:
        primary = max(scores, key=scores.get)

    # Generate recommendations based on bottleneck type
    recommendations = _get_recommendations(primary, summary, evidence)

    return {
        "classification": primary,
        "confidence": _calculate_confidence(scores),
        "scores": scores,
        "evidence": evidence,
        "recommendations": recommendations,
        "summary": _generate_summary(primary, evidence),
    }


def _calculate_confidence(scores: Dict[str, int]) -> str:
    """Calculate confidence level based on score distribution."""
    values = list(scores.values())
    max_score = max(values)
    second_max = sorted(values, reverse=True)[1] if len(values) > 1 else 0

    if max_score == 0:
        return "low"
    elif max_score - second_max >= 2:
        return "high"
    elif max_score - second_max >= 1:
        return "medium"
    else:
        return "low"


def _get_recommendations(
    bottleneck: str, summary: Dict[str, Any], evidence: List[str]
) -> List[str]:
    """Generate actionable recommendations based on bottleneck type."""
    recommendations = []

    if bottleneck == "gpu_bound":
        recommendations.extend([
            "Consider using a smaller model or enabling quantization",
            "Increase batch size to improve GPU efficiency",
            "Enable tensor parallelism across multiple GPUs",
            "Check if model fits in GPU memory without swapping",
        ])

    elif bottleneck == "cpu_bound":
        recommendations.extend([
            "Profile CPU-intensive operations (tokenization, data loading)",
            "Consider using more CPU cores or faster processors",
            "Optimize data preprocessing pipeline",
            "Check for unnecessary CPU-GPU data transfers",
        ])

    elif bottleneck == "memory_bound":
        recommendations.extend([
            "Reduce batch size to lower memory pressure",
            "Enable gradient checkpointing for training workloads",
            "Use memory-efficient attention mechanisms",
            "Consider model quantization (INT8/FP16)",
            "Check for memory leaks in long-running services",
        ])

    elif bottleneck == "queueing":
        recommendations.extend([
            "Reduce concurrency/request rate",
            "Scale horizontally with more service replicas",
            "Implement request queuing with backpressure",
            "Increase service timeout limits",
            "Add request rate limiting at the client",
        ])

    elif bottleneck == "network_io":
        recommendations.extend([
            "Check network bandwidth between client and service",
            "Reduce payload sizes where possible",
            "Enable compression for large responses",
            "Consider co-locating client and service on same node",
        ])

    elif bottleneck == "healthy":
        recommendations.extend([
            "System is operating well - consider testing higher load",
            "Document current configuration as baseline",
            "Monitor for degradation over time",
        ])

    else:
        recommendations.extend([
            "Collect more detailed metrics (GPU utilization, CPU time)",
            "Run additional tests with varying concurrency",
            "Enable verbose logging to identify slow operations",
        ])

    return recommendations[:5]  # Return top 5 recommendations


def _generate_summary(bottleneck: str, evidence: List[str]) -> str:
    """Generate a human-readable summary of the bottleneck analysis."""
    labels = {
        "gpu_bound": "GPU Compute",
        "cpu_bound": "CPU Compute",
        "memory_bound": "Memory",
        "queueing": "Service Queueing/Overload",
        "network_io": "Network/I/O",
        "healthy": "No Significant Bottleneck",
        "unknown": "Unable to Determine",
    }

    label = labels.get(bottleneck, bottleneck.title())

    if not evidence:
        return f"Most likely bottleneck: {label} (insufficient data for detailed analysis)"

    top_evidence = evidence[0] if evidence else "No specific indicators"
    return f"Most likely bottleneck: {label}. Primary indicator: {top_evidence}"


def format_bottleneck_report(analysis: Dict[str, Any]) -> str:
    """
    Format bottleneck analysis as a Markdown report section.

    Args:
        analysis: Output from classify_bottleneck()

    Returns:
        Markdown formatted string
    """
    lines = [
        "## Bottleneck Analysis (KF2)",
        "",
        f"**Classification:** {analysis['classification'].replace('_', ' ').title()}",
        f"**Confidence:** {analysis['confidence'].title()}",
        "",
        "### Summary",
        "",
        analysis["summary"],
        "",
    ]

    # Evidence section
    if analysis["evidence"]:
        lines.extend([
            "### Supporting Evidence",
            "",
        ])
        for item in analysis["evidence"]:
            lines.append(f"- {item}")
        lines.append("")

    # Recommendations section
    if analysis["recommendations"]:
        lines.extend([
            "### Recommended Actions",
            "",
        ])
        for i, rec in enumerate(analysis["recommendations"], 1):
            lines.append(f"{i}. {rec}")
        lines.append("")

    # Score breakdown (for debugging/transparency)
    lines.extend([
        "### Analysis Scores",
        "",
        "| Category | Score |",
        "|----------|-------|",
    ])
    for category, score in sorted(analysis["scores"].items(), key=lambda x: -x[1]):
        lines.append(f"| {category.replace('_', ' ').title()} | {score} |")
    lines.append("")

    return "\n".join(lines)


def analyze_benchmark_bottleneck(
    benchmark_id: str,
) -> Dict[str, Any]:
    """
    Analyze bottleneck for a specific benchmark.

    Args:
        benchmark_id: The benchmark ID to analyze

    Returns:
        Bottleneck analysis dictionary
    """
    from pathlib import Path
    import json

    # Load summary
    summary_file = Path(f"results/{benchmark_id}/summary.json")
    if not summary_file.exists():
        return {
            "classification": "unknown",
            "confidence": "low",
            "scores": {},
            "evidence": ["No summary.json found"],
            "recommendations": ["Run --report to generate summary first"],
            "summary": "Unable to analyze - no metrics available",
        }

    with open(summary_file) as f:
        summary = json.load(f)

    # Try to load additional metrics
    slurm_metrics = None
    gpu_metrics = None

    # Check for metrics file
    metrics_file = Path(f"results/{benchmark_id}/metrics.json")
    if metrics_file.exists():
        with open(metrics_file) as f:
            metrics_data = json.load(f)
            slurm_metrics = metrics_data.get("slurm", {})
            gpu_metrics = metrics_data.get("gpu", {})

    return classify_bottleneck(summary, slurm_metrics, gpu_metrics)
