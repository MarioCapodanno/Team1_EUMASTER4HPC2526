#!/usr/bin/env python3
"""
Benchmark Analysis Script

Generates comparative analysis plots and metrics from benchmark results.
Supports all services: Redis, vLLM, Ollama, Postgres.

Usage:
    python scripts/analyze_benchmarks.py                    # Analyze all benchmarks
    python scripts/analyze_benchmarks.py --service redis    # Analyze only Redis
    python scripts/analyze_benchmarks.py BM-20260111-001 BM-20260111-002  # Specific benchmarks
"""

import argparse
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from reporting.analysis import BenchmarkLoader, BenchmarkAnalyzer, BenchmarkResult
from reporting.plotting import (
    plot_throughput_scaling,
    plot_latency_heatmap,
    plot_throughput_comparison,
    plot_latency_breakdown_comparison,
    plot_multi_series_scaling,
)


def create_output_dir(base_dir: str = "analysis") -> Path:
    """Create and return the output directory for plots."""
    output_dir = Path(base_dir) / "plots"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def generate_service_plots(
    results: list[BenchmarkResult],
    service_type: str,
    output_dir: Path,
) -> list[Path]:
    """Generate plots specific to a service type."""
    plots = []
    
    if not results:
        print(f"  No results for {service_type}")
        return plots
    
    analyzer = BenchmarkAnalyzer(results)
    
    # 1. Throughput Comparison Bar Chart
    # Use config_str for labels to make them meaningful
    labels = [r.config_str for r in results]
    throughputs = [r.throughput_rps for r in results]
    
    if any(t > 0 for t in throughputs):
        out_path = output_dir / f"{service_type}_throughput_comparison.png"
        plot_throughput_comparison(
            labels=labels,
            values=throughputs,
            output_path=out_path,
            title=f"{service_type.title()} Throughput Comparison",
        )
        plots.append(out_path)
        print(f"  ✓ {out_path.name}")
    
    # 2. Latency Heatmap
    latency_data = {}
    for r in results:
        if r.latency_avg_ms > 0:
            # Use label with some uniquifier if needed
            label = r.config_str or r.benchmark_id[-7:]
            latency_data[label] = {
                "avg": r.latency_avg_ms,
                "p50": r.latency_p50_ms,
                "p95": r.latency_p95_ms,
                "p99": r.latency_p99_ms,
            }
    
    if latency_data:
        out_path = output_dir / f"{service_type}_latency_heatmap.png"
        plot_latency_heatmap(
            data=latency_data,
            output_path=out_path,
            title=f"{service_type.title()} Latency Heatmap (ms)",
        )
        plots.append(out_path)
        print(f"  ✓ {out_path.name}")
    
    # 3. Latency Breakdown (Avg vs Tail)
    breakdown_data = analyzer.get_latency_breakdown(filter_service=service_type)
    
    if breakdown_data:
        out_path = output_dir / f"{service_type}_latency_breakdown.png"
        plot_latency_breakdown_comparison(
            data=breakdown_data,
            output_path=out_path,
            title=f"{service_type.title()} Avg vs Tail Latency",
        )
        plots.append(out_path)
        print(f"  ✓ {out_path.name}")
    
    # 4. Dynamic Scaling Plots
    # Detect what parameter is varying (clients, payload, etc.)
    varying_param = analyzer.detect_varying_parameter()
    
    if varying_param:
        print(f"  -> Detected varying parameter: {varying_param}")
        
        # Determine X-axis label
        x_label_map = {
            "num_clients": "Number of Clients",
            "payload_size": "Payload Size (bytes)",
            "pipeline_depth": "Pipeline Depth"
        }
        x_label = x_label_map.get(varying_param, varying_param)
        
        # Scaling Plot 1: Throughput
        x_vals, y_vals, _ = analyzer.get_scaling_data(
            x_param=varying_param,
            y_metric="throughput_rps",
        )
        
        # Sort data for plotting
        if x_vals and y_vals:
            out_path = output_dir / f"{service_type}_throughput_vs_{varying_param}.png"
            plot_throughput_scaling(
                x_values=x_vals,
                y_values=y_vals,
                x_label=x_label,
                title=f"{service_type.title()} Throughput vs {x_label}",
                output_path=out_path,
                log_x=(varying_param == "payload_size"),  # Log scale for payload
            )
            plots.append(out_path)
            print(f"  ✓ {out_path.name}")
            
        # Scaling Plot 2: P99 Latency
        x_vals, y_vals, _ = analyzer.get_scaling_data(
            x_param=varying_param,
            y_metric="latency_p99_ms",
        )
        if x_vals and y_vals:
            out_path = output_dir / f"{service_type}_latency_vs_{varying_param}.png"
            plot_throughput_scaling(
                x_values=x_vals,
                y_values=y_vals,
                x_label=x_label,
                title=f"{service_type.title()} P99 Latency vs {x_label}",
                output_path=out_path,
                log_x=(varying_param == "payload_size"),
            )
            plots.append(out_path)
            print(f"  ✓ {out_path.name}")
    else:
        # Fallback if multiple things vary or nothing varies perfectly
        # Attempt to plot against Clients as default if multiple clients exist
        client_counts = set(r.num_clients for r in results)
        if len(client_counts) > 1:
            print("  -> Multiple client counts detected, generating client scaling plots.")
            x_vals, y_vals, labels = analyzer.get_scaling_data(
                x_param="num_clients",
                y_metric="throughput_rps",
            )
            out_path = output_dir / f"{service_type}_throughput_vs_clients.png"
            # We don't have separate series here yet, just scatter/line
            plot_throughput_scaling(
                x_values=x_vals,
                y_values=y_vals,
                x_label="Number of Clients",
                title=f"{service_type.title()} Throughput Scaling",
                output_path=out_path,
            )
            plots.append(out_path)
            print(f"  ✓ {out_path.name}")
    
    return plots


def main():
    parser = argparse.ArgumentParser(
        description="Analyze benchmark results and generate plots."
    )
    parser.add_argument(
        "benchmark_ids",
        nargs="*",
        help="Specific benchmark IDs to analyze (default: all)",
    )
    parser.add_argument(
        "--service",
        type=str,
        choices=["redis", "vllm", "ollama", "postgres"],
        help="Filter by service type",
    )
    parser.add_argument(
        "--results-dir",
        type=str,
        default="results",
        help="Path to results directory",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="analysis",
        help="Output directory for plots",
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Benchmark Analysis")
    print("=" * 60)
    
    # Load benchmarks
    loader = BenchmarkLoader(args.results_dir)
    
    if args.benchmark_ids:
        results = []
        for bid in args.benchmark_ids:
            result = loader.load_benchmark(bid)
            if result:
                results.append(result)
            else:
                print(f"Warning: Could not load benchmark {bid}")
    elif args.service:
        results = loader.load_by_service(args.service)
    else:
        results = loader.load_all()
    
    if not results:
        print("No benchmark results found.")
        return 1
    
    print(f"\nLoaded {len(results)} benchmark(s)")
    
    # Create output directory
    output_dir = create_output_dir(args.output_dir)
    print(f"Output directory: {output_dir}")
    
    # Generate plots
    all_plots = []
    
    # Group by service and generate per-service plots
    analyzer = BenchmarkAnalyzer(results)
    by_service = analyzer.group_by_service()
    
    for service_type, service_results in by_service.items():
        print(f"\n[{service_type.upper()}] Generating plots...")
        plots = generate_service_plots(service_results, service_type, output_dir)
        all_plots.extend(plots)
    
    # Summary
    print("\n" + "=" * 60)
    print(f"Generated {len(all_plots)} plot(s)")
    print(f"Results saved to: {output_dir.absolute()}")
    print("=" * 60)
    
    # Print stats
    stats = analyzer.get_summary_stats()
    print(f"\nSummary Statistics:")
    print(f"  Total benchmarks: {stats['total_benchmarks']}")
    for service, s in stats.get("services", {}).items():
        print(f"  {service}:")
        print(f"    Count: {s['count']}")
        print(f"    Max throughput: {s['max_throughput']:.2f} req/s")
        print(f"    Avg latency: {s['avg_latency_ms']:.2f} ms")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
