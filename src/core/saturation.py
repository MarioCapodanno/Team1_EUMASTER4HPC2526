"""
Saturation Finder module (KF1) for detecting optimal operating points.

This module analyzes benchmark results from concurrency sweeps to find:
- The "knee" where tail latency (P95/P99) grows sharply
- The point where throughput stops scaling linearly
- Recommended max concurrency under a user-defined SLO

The saturation point is critical for capacity planning and SLO compliance.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np


def find_knee_point(x_values: List[float], y_values: List[float]) -> Optional[int]:
    """
    Find the knee/elbow point in a curve using the maximum curvature method.

    The knee point is where the curve transitions from linear to saturated behavior.

    Args:
        x_values: X-axis values (e.g., concurrency levels)
        y_values: Y-axis values (e.g., latency or throughput)

    Returns:
        Index of the knee point, or None if not found
    """
    if len(x_values) < 3:
        return None

    # Normalize values to [0, 1] range for consistent analysis
    x_norm = np.array(x_values, dtype=float)
    y_norm = np.array(y_values, dtype=float)

    x_norm = (x_norm - x_norm.min()) / (x_norm.max() - x_norm.min() + 1e-10)
    y_norm = (y_norm - y_norm.min()) / (y_norm.max() - y_norm.min() + 1e-10)

    # Calculate curvature at each point
    # Curvature = |x'y'' - y'x''| / (x'^2 + y'^2)^(3/2)
    dx = np.gradient(x_norm)
    dy = np.gradient(y_norm)
    ddx = np.gradient(dx)
    ddy = np.gradient(dy)

    curvature = np.abs(dx * ddy - dy * ddx) / (dx**2 + dy**2 + 1e-10) ** 1.5

    # Find the point with maximum curvature (excluding endpoints)
    if len(curvature) > 2:
        knee_idx = np.argmax(curvature[1:-1]) + 1
        return int(knee_idx)

    return None


def find_latency_knee(
    concurrency_levels: List[int], p99_latencies: List[float]
) -> Optional[Dict[str, Any]]:
    """
    Find the concurrency level where P99 latency starts growing sharply.

    Args:
        concurrency_levels: List of concurrency levels tested
        p99_latencies: P99 latency at each concurrency level

    Returns:
        Dictionary with knee point info, or None if not found
    """
    if len(concurrency_levels) < 3:
        return None

    knee_idx = find_knee_point(concurrency_levels, p99_latencies)

    if knee_idx is None:
        return None

    return {
        "concurrency": concurrency_levels[knee_idx],
        "p99_latency": p99_latencies[knee_idx],
        "index": knee_idx,
        "type": "latency_knee",
    }


def find_throughput_saturation(
    concurrency_levels: List[int], throughputs: List[float]
) -> Optional[Dict[str, Any]]:
    """
    Find the concurrency level where throughput stops scaling linearly.

    Args:
        concurrency_levels: List of concurrency levels tested
        throughputs: Throughput (RPS/TPS) at each concurrency level

    Returns:
        Dictionary with saturation point info, or None if not found
    """
    if len(concurrency_levels) < 3:
        return None

    # For throughput, we look for where the curve flattens
    # This is the inverse of the latency knee
    knee_idx = find_knee_point(concurrency_levels, throughputs)

    if knee_idx is None:
        return None

    # Calculate efficiency at each point
    efficiencies = [
        t / c if c > 0 else 0 for t, c in zip(throughputs, concurrency_levels)
    ]

    return {
        "concurrency": concurrency_levels[knee_idx],
        "throughput": throughputs[knee_idx],
        "efficiency": efficiencies[knee_idx],
        "index": knee_idx,
        "type": "throughput_saturation",
    }


def find_slo_limit(
    concurrency_levels: List[int], p99_latencies: List[float], slo_threshold: float
) -> Optional[Dict[str, Any]]:
    """
    Find the maximum concurrency that meets the SLO threshold.

    Args:
        concurrency_levels: List of concurrency levels tested
        p99_latencies: P99 latency at each concurrency level
        slo_threshold: Maximum acceptable P99 latency (in seconds)

    Returns:
        Dictionary with SLO limit info, or None if all points exceed SLO
    """
    # Find the highest concurrency that still meets SLO
    valid_indices = [i for i, lat in enumerate(p99_latencies) if lat <= slo_threshold]

    if not valid_indices:
        return None

    max_valid_idx = max(valid_indices)

    return {
        "max_concurrency": concurrency_levels[max_valid_idx],
        "p99_latency": p99_latencies[max_valid_idx],
        "slo_threshold": slo_threshold,
        "headroom_percent": (slo_threshold - p99_latencies[max_valid_idx])
        / slo_threshold
        * 100,
        "index": max_valid_idx,
        "type": "slo_limit",
    }


def analyze_saturation(
    sweep_results: List[Dict[str, Any]], slo_threshold: Optional[float] = None
) -> Dict[str, Any]:
    """
    Analyze a concurrency sweep to find saturation points.

    Args:
        sweep_results: List of benchmark summaries at different concurrency levels
                      Each should have 'concurrency', 'requests_per_second',
                      and 'latency_s' with percentiles
        slo_threshold: Optional SLO threshold for P99 latency (in seconds)

    Returns:
        Analysis results including knee points and recommendations
    """
    if not sweep_results:
        return {"error": "No sweep results provided"}

    # Extract data points
    concurrency_levels = []
    throughputs = []
    p99_latencies = []
    p95_latencies = []

    for result in sweep_results:
        conc = result.get("concurrency") or result.get("num_clients", 1)
        concurrency_levels.append(conc)
        throughputs.append(result.get("requests_per_second", 0))
        p99_latencies.append(result.get("latency_s", {}).get("p99", 0))
        p95_latencies.append(result.get("latency_s", {}).get("p95", 0))

    # Sort by concurrency
    sorted_data = sorted(
        zip(concurrency_levels, throughputs, p99_latencies, p95_latencies)
    )
    concurrency_levels = [d[0] for d in sorted_data]
    throughputs = [d[1] for d in sorted_data]
    p99_latencies = [d[2] for d in sorted_data]
    p95_latencies = [d[3] for d in sorted_data]

    analysis = {
        "data_points": len(concurrency_levels),
        "concurrency_range": [min(concurrency_levels), max(concurrency_levels)],
        "throughput_range": [min(throughputs), max(throughputs)],
        "p99_latency_range": [min(p99_latencies), max(p99_latencies)],
    }

    # Find latency knee
    latency_knee = find_latency_knee(concurrency_levels, p99_latencies)
    if latency_knee:
        analysis["latency_knee"] = latency_knee

    # Find throughput saturation
    throughput_sat = find_throughput_saturation(concurrency_levels, throughputs)
    if throughput_sat:
        analysis["throughput_saturation"] = throughput_sat

    # Find SLO limit if threshold provided
    if slo_threshold:
        slo_limit = find_slo_limit(concurrency_levels, p99_latencies, slo_threshold)
        if slo_limit:
            analysis["slo_limit"] = slo_limit
        else:
            analysis["slo_limit"] = {
                "error": f"No concurrency level meets SLO threshold of {slo_threshold}s"
            }

    # Generate recommendation
    analysis["recommendation"] = generate_saturation_recommendation(
        analysis, slo_threshold
    )

    return analysis


def generate_saturation_recommendation(
    analysis: Dict[str, Any], slo_threshold: Optional[float] = None
) -> Dict[str, Any]:
    """
    Generate a recommendation based on saturation analysis.

    Args:
        analysis: Saturation analysis results
        slo_threshold: Optional SLO threshold

    Returns:
        Recommendation dictionary
    """
    rec = {"summary": "", "max_recommended_concurrency": None, "reasoning": []}

    # Determine recommended concurrency
    candidates = []

    if "slo_limit" in analysis and "max_concurrency" in analysis["slo_limit"]:
        candidates.append(("slo", analysis["slo_limit"]["max_concurrency"]))
        rec["reasoning"].append(
            f"SLO limit: concurrency {analysis['slo_limit']['max_concurrency']} "
            f"(P99={analysis['slo_limit']['p99_latency'] * 1000:.1f}ms, "
            f"headroom={analysis['slo_limit']['headroom_percent']:.1f}%)"
        )

    if "latency_knee" in analysis:
        candidates.append(("knee", analysis["latency_knee"]["concurrency"]))
        rec["reasoning"].append(
            f"Latency knee: concurrency {analysis['latency_knee']['concurrency']} "
            f"(P99={analysis['latency_knee']['p99_latency'] * 1000:.1f}ms)"
        )

    if "throughput_saturation" in analysis:
        candidates.append(
            ("saturation", analysis["throughput_saturation"]["concurrency"])
        )
        rec["reasoning"].append(
            f"Throughput saturation: concurrency {analysis['throughput_saturation']['concurrency']} "
            f"({analysis['throughput_saturation']['throughput']:.1f} RPS)"
        )

    # Choose the most conservative recommendation
    if candidates:
        # Prefer SLO limit if available, otherwise use the minimum
        slo_candidates = [c for c in candidates if c[0] == "slo"]
        if slo_candidates:
            rec["max_recommended_concurrency"] = slo_candidates[0][1]
            rec["summary"] = (
                f"Recommended max concurrency: {rec['max_recommended_concurrency']} "
                f"(based on SLO compliance)"
            )
        else:
            rec["max_recommended_concurrency"] = min(c[1] for c in candidates)
            rec["summary"] = (
                f"Recommended max concurrency: {rec['max_recommended_concurrency']} "
                f"(based on saturation analysis)"
            )
    else:
        rec["summary"] = (
            "Insufficient data for recommendation. Run more concurrency levels."
        )

    return rec


def format_saturation_report(analysis: Dict[str, Any]) -> str:
    """
    Format saturation analysis as a Markdown report section.

    Args:
        analysis: Saturation analysis results

    Returns:
        Markdown formatted string
    """
    lines = [
        "## Saturation Analysis (KF1)",
        "",
        "*Automated detection of optimal operating point*",
        "",
    ]

    # Data summary
    lines.extend(
        [
            "### Data Points Analyzed",
            "",
            f"- **Concurrency Range:** {analysis['concurrency_range'][0]} - {analysis['concurrency_range'][1]}",
            f"- **Throughput Range:** {analysis['throughput_range'][0]:.1f} - {analysis['throughput_range'][1]:.1f} RPS",
            f"- **P99 Latency Range:** {analysis['p99_latency_range'][0] * 1000:.1f} - {analysis['p99_latency_range'][1] * 1000:.1f} ms",
            "",
        ]
    )

    # Key findings
    lines.extend(
        [
            "### Key Findings",
            "",
        ]
    )

    if "latency_knee" in analysis:
        knee = analysis["latency_knee"]
        lines.append(
            f"- **Latency Knee Point:** Concurrency {knee['concurrency']} "
            f"(P99 = {knee['p99_latency'] * 1000:.1f}ms)"
        )

    if "throughput_saturation" in analysis:
        sat = analysis["throughput_saturation"]
        lines.append(
            f"- **Throughput Saturation:** Concurrency {sat['concurrency']} "
            f"({sat['throughput']:.1f} RPS, efficiency = {sat['efficiency']:.2f} RPS/client)"
        )

    if "slo_limit" in analysis:
        slo = analysis["slo_limit"]
        if "max_concurrency" in slo:
            lines.append(
                f"- **SLO Limit (P99 < {slo['slo_threshold'] * 1000:.0f}ms):** "
                f"Max concurrency {slo['max_concurrency']} "
                f"(headroom = {slo['headroom_percent']:.1f}%)"
            )
        else:
            lines.append(f"- **SLO Limit:** {slo.get('error', 'Not determined')}")

    lines.append("")

    # Recommendation
    rec = analysis.get("recommendation", {})
    lines.extend(
        [
            "### Recommendation",
            "",
            f"**{rec.get('summary', 'No recommendation available')}**",
            "",
        ]
    )

    if rec.get("reasoning"):
        lines.append("Reasoning:")
        for reason in rec["reasoning"]:
            lines.append(f"- {reason}")
        lines.append("")

    return "\n".join(lines)


def load_sweep_results(benchmark_ids: List[str]) -> List[Dict[str, Any]]:
    """
    Load summary.json files for multiple benchmark IDs.

    Args:
        benchmark_ids: List of benchmark IDs to load

    Returns:
        List of summary dictionaries with concurrency info
    """
    results = []

    for bid in benchmark_ids:
        summary_path = Path(f"results/{bid}/summary.json")
        if summary_path.exists():
            with open(summary_path) as f:
                summary = json.load(f)
                summary["benchmark_id"] = bid
                
                # Try to get concurrency from run.json if not in summary
                if "concurrency" not in summary and "num_clients" not in summary:
                    run_path = Path(f"results/{bid}/run.json")
                    if run_path.exists():
                        try:
                            with open(run_path) as rf:
                                run_data = json.load(rf)
                                # Get num_clients from run.json
                                clients = run_data.get("clients", [])
                                if clients:
                                    summary["num_clients"] = len(clients)
                                    summary["concurrency"] = len(clients)
                                # Also try to get from recipe
                                recipe = run_data.get("recipe", {})
                                if "num_clients" in recipe:
                                    summary["num_clients"] = recipe["num_clients"]
                                    summary["concurrency"] = recipe["num_clients"]
                        except (json.JSONDecodeError, IOError):
                            pass
                
                results.append(summary)

    return results
