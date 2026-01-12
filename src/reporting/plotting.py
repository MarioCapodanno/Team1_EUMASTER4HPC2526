"""
Plotting module for generating benchmark visualizations.

This module creates PNG plots for benchmark reports including:
- Latency percentiles bar chart
- Throughput over time (if available)
- Error distribution
- Service-specific plots
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np


# Configure matplotlib for non-interactive backend
plt.switch_backend("Agg")


def setup_plot_style():
    """Set up consistent plot styling."""
    plt.style.use("default")
    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.labelsize": 10,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "legend.fontsize": 9,
            "figure.titlesize": 14,
            "figure.dpi": 100,
            "savefig.dpi": 150,
            "savefig.bbox": "tight",
        }
    )


def plot_latency_percentiles(summary: Dict[str, Any], output_path: Path) -> None:
    """
    Create a bar chart of latency percentiles.

    Args:
        summary: Summary metrics dictionary
        output_path: Path to save the plot
    """
    setup_plot_style()

    latency_data = summary.get("latency_s", {})
    percentiles = ["p50", "p90", "p95", "p99"]
    values = [latency_data.get(p, 0) * 1000 for p in percentiles]  # Convert to ms
    labels = ["P50", "P90", "P95", "P99"]

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(labels, values, color=["#2ecc71", "#3498db", "#e74c3c", "#9b59b6"])

    # Add value labels on bars
    for bar, value in zip(bars, values):
        height = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            height,
            f"{value:.1f}ms",
            ha="center",
            va="bottom",
        )

    ax.set_title("Latency Percentiles")
    ax.set_ylabel("Latency (milliseconds)")
    ax.set_xlabel("Percentile")
    ax.grid(True, axis="y", alpha=0.3)

    # Set y-axis to start from 0
    ax.set_ylim(bottom=0)

    plt.savefig(output_path)
    plt.close()


def plot_throughput_summary(summary: Dict[str, Any], output_path: Path) -> None:
    """
    Create a throughput summary visualization.

    Args:
        summary: Summary metrics dictionary
        output_path: Path to save the plot
    """
    setup_plot_style()

    throughput = summary.get("requests_per_second", 0)
    service_type = summary.get("service_type", "unknown")

    fig, ax = plt.subplots(figsize=(6, 4))

    # Create a single bar for throughput
    bars = ax.bar(["Throughput"], [throughput], color="#3498db", width=0.5)

    # Add value label
    for bar in bars:
        height = bar.get_height()
        unit = "RPS" if service_type in ["vllm", "ollama"] else "TPS"
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            height,
            f"{throughput:.2f} {unit}",
            ha="center",
            va="bottom",
            fontsize=12,
        )

    ax.set_title(f"Throughput ({service_type.title()})")
    ax.set_ylabel(
        "Requests per Second"
        if service_type in ["vllm", "ollama"]
        else "Transactions per Second"
    )
    ax.grid(True, axis="y", alpha=0.3)

    # Set y-axis to start from 0
    ax.set_ylim(bottom=0)

    plt.savefig(output_path)
    plt.close()


def plot_error_distribution(summary: Dict[str, Any], output_path: Path) -> None:
    """
    Create a pie chart of error types.

    Args:
        summary: Summary metrics dictionary
        output_path: Path to save the plot
    """
    setup_plot_style()

    error_summary = summary.get("error_summary", {})
    total_requests = summary.get("total_requests", 0)
    successful = summary.get("successful_requests", 0)

    if not error_summary and successful == total_requests:
        # No errors, show success
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.pie(
            [successful], labels=["Successful"], colors=["#2ecc71"], autopct="%1.1f%%"
        )
        ax.set_title("Request Success Rate (100%)")
        plt.savefig(output_path)
        plt.close()
        return

    # Prepare data
    labels = ["Successful"] + list(error_summary.keys())
    sizes = [successful] + list(error_summary.values())
    # Generate colors for error types
    error_colors = plt.cm.Set3(np.linspace(0, 1, len(error_summary)))
    colors = ["#2ecc71"] + list(error_colors)

    # Filter out very small slices for readability
    filtered_data = [(l, s, c) for l, s, c in zip(labels, sizes, colors) if s > 0]
    if not filtered_data:
        return

    labels, sizes, colors = zip(*filtered_data)

    fig, ax = plt.subplots(figsize=(8, 6))
    wedges, texts, autotexts = ax.pie(
        sizes, labels=labels, colors=colors, autopct="%1.1f%%"
    )

    # Make percentage text bold
    for autotext in autotexts:
        autotext.set_weight("bold")

    ax.set_title(f"Request Distribution (Total: {total_requests})")

    plt.savefig(output_path)
    plt.close()


def plot_latency_distribution(
    requests: List[Dict[str, Any]], output_path: Path
) -> None:
    """
    Create a histogram of latency distribution.

    Args:
        requests: List of request dictionaries
        output_path: Path to save the plot
    """
    setup_plot_style()

    # Extract latencies from successful requests
    latencies = [
        r.get("latency_s", 0) * 1000
        for r in requests
        if r.get("success", False) and r.get("latency_s", 0) > 0
    ]

    if not latencies:
        return

    fig, ax = plt.subplots(figsize=(8, 5))

    # Create histogram
    n, bins, patches = ax.hist(
        latencies, bins=30, color="#3498db", alpha=0.7, edgecolor="black"
    )

    # Color code by latency ranges
    for i, patch in enumerate(patches):
        if bins[i] > 1000:  # > 1 second
            patch.set_facecolor("#e74c3c")
        elif bins[i] > 500:  # > 500ms
            patch.set_facecolor("#f39c12")
        else:
            patch.set_facecolor("#2ecc71")

    # Add vertical lines for percentiles
    p50 = np.percentile(latencies, 50)
    p95 = np.percentile(latencies, 95)
    p99 = np.percentile(latencies, 99)

    ax.axvline(
        p50, color="orange", linestyle="--", alpha=0.8, label=f"P50: {p50:.1f}ms"
    )
    ax.axvline(p95, color="red", linestyle="--", alpha=0.8, label=f"P95: {p95:.1f}ms")
    ax.axvline(
        p99, color="purple", linestyle="--", alpha=0.8, label=f"P99: {p99:.1f}ms"
    )

    ax.set_title("Latency Distribution")
    ax.set_xlabel("Latency (milliseconds)")
    ax.set_ylabel("Number of Requests")
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.savefig(output_path)
    plt.close()


def plot_service_metrics(summary: Dict[str, Any], output_path: Path) -> None:
    """
    Create service-specific metric plots.

    Args:
        summary: Summary metrics dictionary
        output_path: Path to save the plot
    """
    setup_plot_style()

    service_type = summary.get("service_type", "unknown")

    if service_type in ["vllm", "ollama"]:
        # LLM metrics
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))

        # Tokens per request
        output_tokens = summary.get("avg_output_tokens", 0)
        input_tokens = summary.get("avg_input_tokens", 0)

        ax1.bar(
            ["Input", "Output"],
            [input_tokens, output_tokens],
            color=["#3498db", "#2ecc71"],
        )
        ax1.set_title("Average Tokens per Request")
        ax1.set_ylabel("Tokens")
        ax1.grid(True, axis="y", alpha=0.3)

        # Throughput metrics
        rps = summary.get("requests_per_second", 0)
        tps = summary.get("tokens_per_second", 0)

        ax2.bar(["RPS", "Tokens/sec"], [rps, tps], color=["#9b59b6", "#e67e22"])
        ax2.set_title("Throughput Metrics")
        ax2.set_ylabel("Per Second")
        ax2.grid(True, axis="y", alpha=0.3)

    elif service_type == "postgres":
        # Database operations
        operations = summary.get("operations", {})
        if not operations:
            return

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))

        # Operation counts
        op_names = list(operations.keys())
        op_counts = [operations[op].get("count", 0) for op in op_names]

        ax1.bar(op_names, op_counts, color="#3498db")
        ax1.set_title("Operation Counts")
        ax1.set_ylabel("Count")
        ax1.tick_params(axis="x", rotation=45)
        ax1.grid(True, axis="y", alpha=0.3)

        # Operation latencies
        op_lats = [operations[op].get("avg_latency", 0) * 1000 for op in op_names]

        bars = ax2.bar(op_names, op_lats, color="#e74c3c")
        ax2.set_title("Average Latency by Operation")
        ax2.set_ylabel("Latency (ms)")
        ax2.tick_params(axis="x", rotation=45)
        ax2.grid(True, axis="y", alpha=0.3)

        # Add value labels
        for bar, value in zip(bars, op_lats):
            height = bar.get_height()
            ax2.text(
                bar.get_x() + bar.get_width() / 2.0,
                height,
                f"{value:.1f}ms",
                ha="center",
                va="bottom",
            )
    else:
        # Unknown service type, skip
        return

    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()


# =============================================================================
# Comparative Analysis Plots (inspired by Team10's approach)
# =============================================================================


def plot_throughput_scaling(
    x_values: List[float],
    y_values: List[float],
    x_label: str,
    title: str,
    output_path: Path,
    series_labels: Optional[List[str]] = None,
    log_x: bool = False,
    log_y: bool = False,
) -> None:
    """
    Create a scaling plot showing how throughput changes with a parameter.
    
    Useful for: Throughput vs Clients, Throughput vs Payload Size, etc.
    
    Args:
        x_values: X-axis values (e.g., number of clients)
        y_values: Y-axis values (e.g., throughput in RPS)
        x_label: Label for X-axis
        title: Plot title
        output_path: Path to save the plot
        series_labels: Optional labels for each data point
        log_x: Use logarithmic X-axis
        log_y: Use logarithmic Y-axis
    """
    setup_plot_style()
    
    if not x_values or not y_values:
        return
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Sort by x value for proper line plotting
    sorted_data = sorted(zip(x_values, y_values))
    x_sorted, y_sorted = zip(*sorted_data) if sorted_data else ([], [])
    
    ax.plot(x_sorted, y_sorted, marker='o', linewidth=2, markersize=8, color='#3498db')
    ax.fill_between(x_sorted, 0, y_sorted, alpha=0.2, color='#3498db')
    
    ax.set_xlabel(x_label, fontsize=12)
    ax.set_ylabel("Throughput (requests/sec)", fontsize=12)
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3)
    
    if log_x:
        ax.set_xscale('log')
    if log_y:
        ax.set_yscale('log')
    
    ax.set_ylim(bottom=0)
    
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()


def plot_latency_heatmap(
    data: Dict[str, Dict[str, float]],
    output_path: Path,
    title: str = "Latency Heatmap",
) -> None:
    """
    Create a heatmap showing latency percentiles across benchmarks/operations.
    
    Args:
        data: Dict mapping row labels to {column: value} dicts
              e.g., {"SET": {"p50": 1.2, "p95": 2.5, ...}, "GET": {...}}
        output_path: Path to save the plot
        title: Plot title
    """
    setup_plot_style()
    
    if not data:
        return
    
    # Extract labels and values
    row_labels = list(data.keys())
    col_labels = list(next(iter(data.values())).keys()) if data else []
    
    # Create matrix
    matrix = []
    for row in row_labels:
        row_data = [data[row].get(col, 0) for col in col_labels]
        matrix.append(row_data)
    
    matrix = np.array(matrix)
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Create heatmap
    im = ax.imshow(matrix, cmap='RdYlGn_r', aspect='auto')
    
    # Add colorbar
    cbar = ax.figure.colorbar(im, ax=ax)
    cbar.ax.set_ylabel("Latency (ms)", rotation=-90, va="bottom")
    
    # Set ticks
    ax.set_xticks(np.arange(len(col_labels)))
    ax.set_yticks(np.arange(len(row_labels)))
    ax.set_xticklabels([c.upper() for c in col_labels])
    ax.set_yticklabels(row_labels)
    
    # Rotate x labels
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right", rotation_mode="anchor")
    
    # Add text annotations
    for i in range(len(row_labels)):
        for j in range(len(col_labels)):
            value = matrix[i, j]
            text_color = "white" if value > matrix.max() * 0.5 else "black"
            ax.text(j, i, f"{value:.2f}", ha="center", va="center", color=text_color, fontsize=9)
    
    ax.set_title(title, fontsize=14, fontweight='bold')
    
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()


def plot_throughput_heatmap(
    data: Dict[str, Dict[str, float]],
    output_path: Path,
    title: str = "Throughput Heatmap",
    value_format: str = ".0f",
    cmap: str = "YlGnBu",
) -> None:
    """
    Create a heatmap showing throughput across two parameters (Team10-style).
    
    Args:
        data: Dict mapping row labels to {column_label: throughput_value} dicts
              e.g., {"256B": {"1 client": 1000, "10 clients": 5000}, ...}
        output_path: Path to save the plot
        title: Plot title
        value_format: Format string for value annotations (e.g., ".0f", ".1f")
        cmap: Colormap name
    """
    setup_plot_style()
    
    if not data:
        return
    
    # Extract labels and values
    row_labels = list(data.keys())
    col_labels = list(next(iter(data.values())).keys()) if data else []
    
    # Create matrix
    matrix = []
    for row in row_labels:
        row_data = [data[row].get(col, 0) for col in col_labels]
        matrix.append(row_data)
    
    matrix = np.array(matrix)
    
    fig, ax = plt.subplots(figsize=(max(8, len(col_labels)), max(6, len(row_labels) * 0.5)))
    
    # Create heatmap
    im = ax.imshow(matrix, cmap=cmap, aspect='auto')
    
    # Add colorbar
    cbar = ax.figure.colorbar(im, ax=ax)
    cbar.ax.set_ylabel("Throughput (req/s)", rotation=-90, va="bottom")
    
    # Set ticks
    ax.set_xticks(np.arange(len(col_labels)))
    ax.set_yticks(np.arange(len(row_labels)))
    ax.set_xticklabels(col_labels)
    ax.set_yticklabels(row_labels)
    
    # Rotate x labels
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right", rotation_mode="anchor")
    
    # Add text annotations
    for i in range(len(row_labels)):
        for j in range(len(col_labels)):
            value = matrix[i, j]
            # Use white text on dark cells, black on light cells
            text_color = "white" if value > matrix.max() * 0.5 else "black"
            ax.text(j, i, f"{value:{value_format}}", ha="center", va="center", 
                   color=text_color, fontsize=9, fontweight='bold')
    
    ax.set_title(title, fontsize=14, fontweight='bold')
    
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()


def plot_throughput_comparison(
    labels: List[str],
    values: List[float],
    output_path: Path,
    title: str = "Throughput Comparison",
    color_by_value: bool = True,
) -> None:
    """
    Create a horizontal bar chart comparing throughput across benchmarks/operations.
    
    Args:
        labels: Bar labels (operation names, benchmark IDs, etc.)
        values: Throughput values
        output_path: Path to save the plot
        title: Plot title
        color_by_value: If True, color bars by relative value
    """
    setup_plot_style()
    
    if not labels or not values:
        return
    
    # Sort by value descending
    sorted_data = sorted(zip(labels, values), key=lambda x: x[1], reverse=True)
    sorted_labels, sorted_values = zip(*sorted_data) if sorted_data else ([], [])
    
    fig, ax = plt.subplots(figsize=(10, max(4, len(labels) * 0.5)))
    
    # Generate colors
    if color_by_value:
        colors = plt.cm.viridis(np.linspace(0.2, 0.8, len(sorted_values)))
    else:
        colors = ['#3498db'] * len(sorted_values)
    
    bars = ax.barh(sorted_labels, sorted_values, color=colors)
    
    # Add value labels
    for bar, value in zip(bars, sorted_values):
        width = bar.get_width()
        label_x = width + max(sorted_values) * 0.01
        ax.text(label_x, bar.get_y() + bar.get_height()/2,
                f'{value:.1f}', va='center', fontsize=9)
    
    ax.set_xlabel("Throughput (requests/sec)", fontsize=12)
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.grid(True, axis='x', alpha=0.3)
    ax.set_xlim(right=max(sorted_values) * 1.15)
    
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()


def plot_latency_breakdown_comparison(
    data: Dict[str, Dict[str, float]],
    output_path: Path,
    title: str = "Latency Breakdown",
) -> None:
    """
    Create a stacked bar chart showing avg vs tail latency.
    
    Args:
        data: Dict mapping labels to {"avg": x, "tail": y} (tail = p99 - avg)
        output_path: Path to save the plot
        title: Plot title
    """
    setup_plot_style()
    
    if not data:
        return
    
    labels = list(data.keys())
    avg_values = [data[l].get("avg", 0) for l in labels]
    tail_values = [data[l].get("tail", 0) for l in labels]
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    x = np.arange(len(labels))
    width = 0.6
    
    bars1 = ax.bar(x, avg_values, width, label='Average Latency', color='#3498db')
    bars2 = ax.bar(x, tail_values, width, bottom=avg_values, label='Tail Latency (P99 - Avg)', color='#e74c3c')
    
    # Add total labels
    for i, (avg, tail) in enumerate(zip(avg_values, tail_values)):
        total = avg + tail
        ax.text(i, total + 0.01 * max(v1 + v2 for v1, v2 in zip(avg_values, tail_values)),
                f'{total:.2f}ms', ha='center', va='bottom', fontsize=9)
    
    ax.set_ylabel("Latency (ms)", fontsize=12)
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha='right')
    ax.legend()
    ax.grid(True, axis='y', alpha=0.3)
    ax.set_ylim(bottom=0)
    
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()


def plot_multi_series_scaling(
    series_data: Dict[str, Tuple[List[float], List[float]]],
    x_label: str,
    y_label: str,
    title: str,
    output_path: Path,
    log_x: bool = False,
    log_y: bool = False,
) -> None:
    """
    Create a multi-series line plot for comparing scaling across configurations.
    
    Args:
        series_data: Dict mapping series name to (x_values, y_values) tuples
        x_label: Label for X-axis
        y_label: Label for Y-axis
        title: Plot title
        output_path: Path to save the plot
        log_x: Use logarithmic X-axis
        log_y: Use logarithmic Y-axis
    """
    setup_plot_style()
    
    if not series_data:
        return
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    colors = plt.cm.tab10(np.linspace(0, 1, len(series_data)))
    markers = ['o', 's', '^', 'D', 'v', '<', '>', 'p', '*', 'h']
    
    for i, (name, (x_vals, y_vals)) in enumerate(series_data.items()):
        if not x_vals or not y_vals:
            continue
        
        # Sort by x value
        sorted_data = sorted(zip(x_vals, y_vals))
        x_sorted, y_sorted = zip(*sorted_data) if sorted_data else ([], [])
        
        marker = markers[i % len(markers)]
        ax.plot(x_sorted, y_sorted, marker=marker, linewidth=2, markersize=8,
                color=colors[i], label=name)
    
    ax.set_xlabel(x_label, fontsize=12)
    ax.set_ylabel(y_label, fontsize=12)
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.legend(loc='best')
    
    if log_x:
        ax.set_xscale('log')
    if log_y:
        ax.set_yscale('log')
    
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()


def generate_plots(
    benchmark_id: str,
    summary: Dict[str, Any],
    requests: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Path]:
    """
    Generate all plots for a benchmark.

    Args:
        benchmark_id: Unique benchmark identifier
        summary: Summary metrics dictionary
        requests: Optional list of request dictionaries

    Returns:
        Dictionary mapping plot names to file paths
    """
    from reporting.artifacts import ensure_reports_dir

    reports_dir = ensure_reports_dir(benchmark_id)
    plots_dir = reports_dir / "plots"
    plots_dir.mkdir(exist_ok=True)

    plot_files = {}

    # Generate standard plots
    plot_files["latency_percentiles"] = plots_dir / "latency_percentiles.png"
    plot_latency_percentiles(summary, plot_files["latency_percentiles"])

    plot_files["throughput"] = plots_dir / "throughput.png"
    plot_throughput_summary(summary, plot_files["throughput"])

    plot_files["error_distribution"] = plots_dir / "error_distribution.png"
    plot_error_distribution(summary, plot_files["error_distribution"])

    # Generate latency histogram if requests are available
    if requests:
        plot_files["latency_histogram"] = plots_dir / "latency_histogram.png"
        plot_latency_distribution(requests, plot_files["latency_histogram"])

    # Generate service-specific plots
    plot_files["service_metrics"] = plots_dir / "service_metrics.png"
    plot_service_metrics(summary, plot_files["service_metrics"])

    return plot_files
