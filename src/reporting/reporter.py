"""
Report generator module for creating benchmark reports.

This module generates human-readable reports (Markdown and JSON) from
aggregated benchmark metrics, including analysis and findings.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from reporting.artifacts import read_run_json, ensure_reports_dir

# Optional plotting support
try:
    from reporting.plotting import generate_plots

    HAS_PLOTTING = True
except ImportError:
    HAS_PLOTTING = False
    generate_plots = None

# KF2 Bottleneck Attribution
try:
    from core.bottleneck import classify_bottleneck, format_bottleneck_report

    HAS_BOTTLENECK = True
except ImportError:
    HAS_BOTTLENECK = False
    classify_bottleneck = None
    format_bottleneck_report = None

# KF1 Saturation Finder
try:
    from core.saturation import analyze_saturation, format_saturation_report, load_sweep_results

    HAS_SATURATION = True
except ImportError:
    HAS_SATURATION = False
    analyze_saturation = None
    format_saturation_report = None
    analyze_saturation = None
    format_saturation_report = None
    load_sweep_results = None

# Prometheus Metrics
try:
    from monitoring.monitor import format_prometheus_metrics
    HAS_PROMETHEUS = True
except ImportError:
    HAS_PROMETHEUS = False
    format_prometheus_metrics = None


def generate_findings(summary: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Generate findings from benchmark metrics.

    Args:
        summary: Aggregated benchmark metrics

    Returns:
        List of finding dictionaries
    """
    findings = []

    # Performance findings
    success_rate = summary.get("success_rate", 0)
    if success_rate < 95:
        findings.append(
            {
                "type": "warning",
                "title": "Low Success Rate",
                "description": f"Success rate is {success_rate:.1f}%, below the recommended 95%",
            }
        )
    elif success_rate == 100:
        findings.append(
            {
                "type": "success",
                "title": "Perfect Reliability",
                "description": f"All {summary.get('total_requests', 0)} requests completed successfully",
            }
        )

    # Latency findings
    p99_latency = summary.get("latency_s", {}).get("p99", 0)
    p95_latency = summary.get("latency_s", {}).get("p95", 0)
    avg_latency = summary.get("latency_s", {}).get("avg", 0)

    if p99_latency > 2.0:
        findings.append(
            {
                "type": "warning",
                "title": "High Tail Latency",
                "description": f"P99 latency is {p99_latency:.3f}s, which may impact user experience",
            }
        )
    elif p99_latency < 0.1:
        findings.append(
            {
                "type": "success",
                "title": "Excellent Latency",
                "description": f"P99 latency is {p99_latency:.3f}s, indicating excellent performance",
            }
        )

    # Throughput findings
    throughput = summary.get("requests_per_second", 0)
    service_type = summary.get("service_type", "unknown")

    if service_type in ["vllm", "ollama"]:
        if throughput > 10:
            findings.append(
                {
                    "type": "success",
                    "title": "High Throughput",
                    "description": f"Achieved {throughput:.2f} RPS for LLM inference",
                }
            )
        elif throughput < 1:
            findings.append(
                {
                    "type": "info",
                    "title": "Low Throughput",
                    "description": f"Only {throughput:.2f} RPS achieved - consider optimization",
                }
            )
    elif service_type == "postgres":
        if throughput > 1000:
            findings.append(
                {
                    "type": "success",
                    "title": "High Database Throughput",
                    "description": f"Achieved {throughput:.0f} TPS for database operations",
                }
            )

    # Error analysis
    error_summary = summary.get("error_summary", {})
    if error_summary:
        most_common = max(error_summary.items(), key=lambda x: x[1])
        findings.append(
            {
                "type": "error",
                "title": "Error Pattern Detected",
                "description": f"Most common error: '{most_common[0]}' ({most_common[1]} occurrences)",
            }
        )

    return findings


def generate_recommendations(summary: Dict[str, Any]) -> List[str]:
    """
    Generate recommendations based on benchmark results.

    Args:
        summary: Aggregated benchmark metrics

    Returns:
        List of recommendation strings
    """
    recommendations = []
    service_type = summary.get("service_type", "unknown")

    # General recommendations
    success_rate = summary.get("success_rate", 0)
    if success_rate < 100:
        recommendations.append("Investigate failed requests to improve reliability")

    # Service-specific recommendations
    if service_type in ["vllm", "ollama"]:
        p95_latency = summary.get("latency_s", {}).get("p95", 0)
        if p95_latency > 1.0:
            recommendations.append(
                "Consider reducing model size or increasing GPU resources"
            )
            recommendations.append("Enable request batching to improve throughput")

        throughput = summary.get("requests_per_second", 0)
        if throughput < 5:
            recommendations.append("Check GPU utilization and memory usage")
            recommendations.append(
                "Consider using tensor parallelism for larger models"
            )

    elif service_type == "postgres":
        operations = summary.get("operations", {})
        if operations:
            slow_ops = [
                op
                for op, data in operations.items()
                if data.get("avg_latency", 0) > 0.1
            ]
            if slow_ops:
                recommendations.append(
                    f"Optimize slow operations: {', '.join(slow_ops)}"
                )
                recommendations.append("Review and add appropriate indexes")

    return recommendations


def generate_one_page_summary(
    benchmark_id: str,
    summary: Dict[str, Any],
    run_data: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Generate KF5 Engineer-Friendly One Page Summary.

    This is a decision-oriented summary with the key metrics engineers need:
    - Max sustainable concurrency under SLO
    - Peak throughput achieved
    - Tail latency at peak
    - Resource efficiency
    - Top issues encountered

    Args:
        benchmark_id: Unique benchmark identifier
        summary: Aggregated benchmark metrics
        run_data: Optional run metadata

    Returns:
        One page summary as Markdown string
    """
    service_type = summary.get("service_type", "unknown")

    # Calculate key decision metrics
    throughput = summary.get("requests_per_second", 0)
    tps = summary.get("transactions_per_second", throughput)
    p99_latency = summary.get("latency_s", {}).get("p99", 0)
    p95_latency = summary.get("latency_s", {}).get("p95", 0)
    p50_latency = summary.get("latency_s", {}).get("p50", 0)
    success_rate = summary.get("success_rate", 0)
    total_requests = summary.get("total_requests", 0)
    failed_requests = summary.get("failed_requests", 0)

    # Determine throughput unit based on service type
    if service_type in ["vllm", "ollama"]:
        throughput_unit = "RPS"
        throughput_label = "Requests/Second"
    else:
        throughput_unit = "TPS"
        throughput_label = "Transactions/Second"

    # Calculate resource efficiency (if GPU info available)
    num_gpus = 1  # Default
    if run_data:
        service_info = run_data.get("service", {})
        num_gpus = service_info.get("num_gpus", 1) or 1

    efficiency = throughput / num_gpus if num_gpus > 0 else throughput

    # Determine SLO status (default SLO: p99 < 1s for LLM, p99 < 100ms for DB)
    if service_type in ["vllm", "ollama"]:
        slo_threshold = 1.0  # 1 second for LLM
        slo_name = "P99 < 1s"
    else:
        slo_threshold = 0.1  # 100ms for DB
        slo_name = "P99 < 100ms"

    meets_slo = p99_latency <= slo_threshold
    slo_status = "PASS" if meets_slo else "FAIL"

    # Determine overall health
    if success_rate >= 99.9 and meets_slo:
        health_status = "EXCELLENT"
        health_desc = "Production ready"
    elif success_rate >= 95 and p99_latency <= slo_threshold * 2:
        health_status = "GOOD"
        health_desc = "Acceptable for most workloads"
    elif success_rate >= 90:
        health_status = "FAIR"
        health_desc = "May need optimization"
    else:
        health_status = "POOR"
        health_desc = "Requires investigation"

    # Build one-page summary
    lines = [
        "# Executive Summary",
        "",
        "*Engineer-friendly decision metrics at a glance*",
        "",
        "---",
        "",
        "## Overall Assessment",
        "",
        f"| Status | {health_status} |",
        "|--------|---------------|",
        f"| Assessment | {health_desc} |",
        f"| SLO Check ({slo_name}) | {slo_status} |",
        "",
        "---",
        "",
        "## Key Decision Metrics",
        "",
        "| Metric | Value | Assessment |",
        "|--------|-------|------------|",
        f"| **Peak Throughput** | {throughput:.2f} {throughput_unit} | {'OK' if throughput > 10 else 'LOW'} |",
        f"| **P99 Latency** | {p99_latency * 1000:.1f} ms | {'OK' if meets_slo else 'HIGH'} |",
        f"| **P95 Latency** | {p95_latency * 1000:.1f} ms | - |",
        f"| **P50 Latency** | {p50_latency * 1000:.1f} ms | - |",
        f"| **Success Rate** | {success_rate:.2f}% | {'OK' if success_rate >= 99 else 'ISSUES'} |",
        f"| **Resource Efficiency** | {efficiency:.2f} {throughput_unit}/GPU | - |",
        "",
        "---",
        "",
        "## Quick Facts",
        "",
        f"- **Total Operations:** {total_requests:,}",
        f"- **Failed Operations:** {failed_requests:,}",
        f"- **Service Type:** {service_type.upper()}",
    ]

    # Add test duration if available
    duration = summary.get("test_duration_s", 0)
    if duration > 0:
        lines.append(f"- **Test Duration:** {duration:.1f} seconds")

    # Add top issues
    error_summary = summary.get("error_summary", {})
    if error_summary:
        lines.extend(
            [
                "",
                "---",
                "",
                "## Issues Detected",
                "",
            ]
        )
        sorted_errors = sorted(error_summary.items(), key=lambda x: x[1], reverse=True)[
            :3
        ]
        for error_type, count in sorted_errors:
            lines.append(f"- **{error_type}**: {count} occurrences")
    else:
        lines.extend(
            [
                "",
                "---",
                "",
                "## No Issues Detected",
                "",
                "All operations completed successfully.",
            ]
        )

    # Add recommendation box
    lines.extend(
        [
            "",
            "---",
            "",
            "## Recommendation",
            "",
        ]
    )

    if meets_slo and success_rate >= 99:
        lines.append(
            f"**Ready for production** at current load ({throughput:.1f} {throughput_unit})."
        )
        lines.append("Consider testing higher concurrency to find saturation point.")
    elif meets_slo:
        lines.append(
            f"**Acceptable performance** but {100 - success_rate:.1f}% failure rate needs investigation."
        )
    else:
        lines.append(
            f"**Not recommended for production** - P99 latency ({p99_latency * 1000:.0f}ms) exceeds SLO ({slo_threshold * 1000:.0f}ms)."
        )
        lines.append(
            "Consider: reducing concurrency, adding resources, or optimizing service configuration."
        )

    lines.extend(
        [
            "",
            "---",
            "",
        ]
    )

    return "\n".join(lines)


def generate_markdown_report(
    benchmark_id: str,
    summary: Dict[str, Any],
    run_data: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Generate a professional academic-style Markdown report for a benchmark.

    Args:
        benchmark_id: Unique benchmark identifier
        summary: Aggregated benchmark metrics
        run_data: Optional run metadata

    Returns:
        Markdown report as string
    """
    # Load run data if not provided
    if not run_data:
        run_data = read_run_json(benchmark_id) or {}

    # Get service info
    service_info = run_data.get("service", {})
    service_type = service_info.get("type", "unknown")
    service_name = service_info.get("name", "Unknown Service")

    # Extract key metrics
    total_requests = summary.get("total_requests", 0)
    success_rate = summary.get("success_rate", 0)
    latency = summary.get("latency_s", {})
    p50 = latency.get("p50", 0)
    p95 = latency.get("p95", 0)
    p99 = latency.get("p99", 0)
    avg_latency = latency.get("avg", 0)
    throughput = summary.get("requests_per_second", 0)
    
    # Generate findings and recommendations
    findings = generate_findings(summary)
    recommendations = generate_recommendations(summary)

    # Build report
    lines = [
        f"# Performance Report: {service_name}",
        "",
        f"**Benchmark ID:** `{benchmark_id}`  ",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC  ",
        f"**Service Type:** {service_type.title()}",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
        f"This report presents the performance analysis of **{service_name}** under benchmark conditions. ",
        f"A total of **{total_requests:,}** requests were processed with a success rate of **{success_rate:.1f}%**.",
        "",
    ]
    
    # Verdict
    if success_rate >= 99 and p99 < 2.0:
        verdict = "PASS - Ready for production"
        verdict_color = "green"
    elif success_rate >= 95:
        verdict = "ACCEPTABLE - Minor issues detected"
        verdict_color = "yellow"
    else:
        verdict = "FAIL - Requires optimization"
        verdict_color = "red"
    
    lines.extend([
        f"**Verdict:** {verdict}",
        "",
        "---",
        "",
        "## Performance Metrics",
        "",
        "### Latency Distribution",
        "",
        "| Percentile | Latency (ms) |",
        "|------------|-------------|",
        f"| P50 (Median) | {p50 * 1000:.1f} |",
        f"| P95 | {p95 * 1000:.1f} |",
        f"| P99 | {p99 * 1000:.1f} |",
        f"| Average | {avg_latency * 1000:.1f} |",
        "",
        "### Throughput",
        "",
        f"| Metric | Value |",
        "|--------|-------|",
        f"| Requests per Second | {throughput:.2f} |",
        f"| Total Requests | {total_requests:,} |",
        f"| Success Rate | {success_rate:.1f}% |",
        "",
    ])

    # Service-specific metrics
    if service_type in ["vllm", "ollama"]:
        tps = summary.get("tokens_per_second", 0)
        if tps > 0:
            lines.extend([
                "### LLM Performance",
                "",
                "| Metric | Value |",
                "|--------|-------|",
                f"| Tokens per Second | {tps:.2f} |",
                f"| Avg Output Tokens | {summary.get('avg_output_tokens', 0):.1f} |",
                f"| Avg Input Tokens | {summary.get('avg_input_tokens', 0):.1f} |",
                "",
            ])

    # Analysis section
    lines.extend([
        "---",
        "",
        "## Analysis",
        "",
    ])
    
    # Findings
    if findings:
        lines.append("### Key Findings")
        lines.append("")
        for i, finding in enumerate(findings, 1):
            severity = finding["type"].upper()
            lines.append(f"{i}. **[{severity}]** {finding['title']}: {finding['description']}")
        lines.append("")
    
    # Recommendations
    if recommendations:
        lines.append("### Recommendations")
        lines.append("")
        for i, rec in enumerate(recommendations, 1):
            lines.append(f"{i}. {rec}")
        lines.append("")

    # KF2 Bottleneck Attribution
    if HAS_BOTTLENECK and classify_bottleneck:
        try:
            bottleneck_analysis = classify_bottleneck(summary)
            bottleneck_report = format_bottleneck_report(bottleneck_analysis)
            lines.extend([
                "---",
                "",
                bottleneck_report,
            ])
        except Exception:
            pass

    # Log Analysis
    try:
        from reporting.log_analyzer import generate_log_summary_for_report
        _, log_markdown = generate_log_summary_for_report(benchmark_id)
        if log_markdown:
            lines.extend([
                "---",
                "",
                log_markdown,
            ])
    except Exception:
        pass

    # Methodology
    lines.extend([
        "---",
        "",
        "## Methodology",
        "",
        "### Test Environment",
        "",
        "| Parameter | Value |",
        "|-----------|-------|",
        f"| Target Cluster | {run_data.get('target', 'N/A')} |",
        f"| Service Image | `{service_info.get('image', 'N/A')}` |",
        f"| Run Date | {run_data.get('created_at', 'N/A')[:19] if run_data.get('created_at') else 'N/A'} |",
        "",
        "### Reproducibility",
        "",
        "To reproduce this benchmark:",
        "",
        "```bash",
        f"python src/frontend.py examples/recipe_{service_type}.yaml",
        "```",
        "",
        "---",
        "",
        "*Report generated by AI Factory Benchmarking Framework*",
        "",
    ])

    return "\n".join(lines)


def write_report_files(
    benchmark_id: str,
    summary: Dict[str, Any],
    requests: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Path]:
    """
    Write both Markdown and JSON report files.

    Args:
        benchmark_id: Unique benchmark identifier
        summary: Aggregated benchmark metrics

    Returns:
        Dictionary with paths to generated files
    """
    reports_dir = ensure_reports_dir(benchmark_id)

    # Load run data
    run_data = read_run_json(benchmark_id) or {}

    # Generate Markdown report
    md_content = generate_markdown_report(benchmark_id, summary, run_data)
    md_file = reports_dir / "report.md"
    with open(md_file, "w") as f:
        f.write(md_content)

    # Generate JSON report
    json_report = {
        "benchmark_id": benchmark_id,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "summary": summary,
        "findings": generate_findings(summary),
        "recommendations": generate_recommendations(summary),
        "run_metadata": run_data,
    }

    json_file = reports_dir / "report.json"
    with open(json_file, "w") as f:
        json.dump(json_report, f, indent=2)

    # Generate plots if available
    if HAS_PLOTTING and generate_plots:
        print("  Generating plots...")
        plot_files = generate_plots(benchmark_id, summary, requests)
    else:
        print("  Skipping plots (matplotlib not installed)")
        plot_files = {}

    # Generate Prometheus metrics file
    if HAS_PROMETHEUS and format_prometheus_metrics:
        print("  Generating Prometheus metrics file...")
        service_type = summary.get("service_type", "unknown")
        prom_content = format_prometheus_metrics(
            summary, 
            benchmark_id, 
            service_type, 
            run_data=run_data
        )
        prom_file = reports_dir / "metrics.txt"
        with open(prom_file, "w") as f:
            f.write(prom_content)
    else:
        prom_file = None

    return {"markdown": md_file, "json": json_file, "plots": plot_files, "prometheus": prom_file}


def generate_benchmark_report(
    benchmark_id: str, summary: Optional[Dict[str, Any]] = None
) -> Dict[str, Path]:
    """
    Generate complete benchmark report.

    Args:
        benchmark_id: Unique benchmark identifier
        summary: Optional pre-computed summary metrics

    Returns:
        Dictionary with paths to generated files
    """
    # Load summary if not provided
    if not summary:
        from reporting.artifacts import read_requests_jsonl
        from core.aggregator import aggregate_requests

        print("  Loading request data...")
        requests = read_requests_jsonl(benchmark_id)
        if not requests:
            raise ValueError(f"No request data found for benchmark {benchmark_id}")

        print("  Aggregating metrics...")
        summary = aggregate_requests(requests)

        # Write summary.json
        from core.aggregator import write_summary_json

        write_summary_json(benchmark_id, summary)
    else:
        # Load requests for plotting if needed
        from reporting.artifacts import read_requests_jsonl

        requests = read_requests_jsonl(benchmark_id)

    # Generate reports
    print("  Generating report files...")
    return write_report_files(benchmark_id, summary, requests)


def generate_sweep_report(
    benchmark_ids: List[str],
    slo_threshold: Optional[float] = None,
    output_name: Optional[str] = None,
) -> Dict[str, Path]:
    """
    Generate a sweep report with KF1 saturation analysis from multiple benchmark runs.

    Args:
        benchmark_ids: List of benchmark IDs from a concurrency sweep
        slo_threshold: Optional SLO threshold for P99 latency (seconds)
        output_name: Optional custom name for the report

    Returns:
        Dictionary with paths to generated files
    """
    if not HAS_SATURATION:
        raise ImportError("Saturation analysis module not available")

    if len(benchmark_ids) < 2:
        raise ValueError("Sweep report requires at least 2 benchmark IDs")

    print(f"Generating sweep report for {len(benchmark_ids)} benchmarks...")

    # Load sweep results
    sweep_results = load_sweep_results(benchmark_ids)
    if not sweep_results:
        raise ValueError("No valid summaries found for provided benchmark IDs")

    # Analyze saturation
    print("  Analyzing saturation points...")
    analysis = analyze_saturation(sweep_results, slo_threshold)

    # Create output directory
    report_name = output_name or f"sweep_{benchmark_ids[0]}_{benchmark_ids[-1]}"
    reports_dir = Path(f"reports/{report_name}")
    reports_dir.mkdir(parents=True, exist_ok=True)

    # Generate saturation report section
    saturation_md = format_saturation_report(analysis)

    # Build full report
    lines = [
        "# Concurrency Sweep Analysis Report",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC",
        f"**Benchmarks Analyzed:** {len(benchmark_ids)}",
        f"**Benchmark IDs:** {', '.join(benchmark_ids)}",
        "",
        "---",
        "",
        saturation_md,
        "",
        "## Individual Benchmark Summaries",
        "",
        "| Benchmark ID | Concurrency | Throughput (RPS) | P99 Latency (ms) | Success Rate |",
        "|--------------|-------------|------------------|------------------|--------------|",
    ]

    for result in sorted(sweep_results, key=lambda x: x.get("concurrency", x.get("num_clients", 0))):
        bid = result.get("benchmark_id", "?")
        conc = result.get("concurrency", result.get("num_clients", "?"))
        rps = result.get("requests_per_second", 0)
        p99 = result.get("latency_s", {}).get("p99", 0) * 1000
        success = result.get("success_rate", 0)
        lines.append(f"| {bid} | {conc} | {rps:.2f} | {p99:.1f} | {success:.1f}% |")

    lines.extend([
        "",
        "---",
        "*Report generated by AI Factory Benchmarking Framework - Saturation Finder (KF1)*",
    ])

    # Write report
    md_file = reports_dir / "sweep_report.md"
    with open(md_file, "w") as f:
        f.write("\n".join(lines))

    # Write JSON
    json_file = reports_dir / "sweep_analysis.json"
    with open(json_file, "w") as f:
        json.dump({
            "benchmark_ids": benchmark_ids,
            "analysis": analysis,
            "sweep_results": sweep_results,
            "generated_at": datetime.utcnow().isoformat() + "Z",
        }, f, indent=2)

    print(f"✓ Sweep report generated: {md_file}")
    return {"markdown": md_file, "json": json_file}
