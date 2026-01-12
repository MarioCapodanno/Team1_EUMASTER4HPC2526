"""
Hardware Metric Collector for Prometheus.

A simple sidecar script that exposes CPU and memory metrics via an HTTP server
for Prometheus to scrape. Runs on port 8010 by default.
"""

import argparse
import time
import os
import socket
import glob

try:
    from prometheus_client import Gauge, start_http_server
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    print("Warning: prometheus_client not available. Install with: pip install prometheus_client")

try:
    import psutil
except ImportError:
    psutil = None
    print("Warning: psutil not available. Memory metrics will be empty.")


parser = argparse.ArgumentParser(description='Hardware Metric Collector')
parser.add_argument('--service-name', type=str, default='unknown', help='Name of the service to monitor')
parser.add_argument('--interval', type=int, default=5, help='Scrape interval in seconds')
parser.add_argument('--port', type=int, default=8010, help='Port to expose metrics on')


def get_cpu_load():
    """Returns 1, 5, 15 min load average."""
    try:
        return os.getloadavg()
    except OSError:
        return (0.0, 0.0, 0.0)


def get_memory_usage():
    """Returns memory statistics."""
    if psutil:
        mem = psutil.virtual_memory()
        return mem.total, mem.used, mem.available, mem.percent
    return 0, 0, 0, 0.0


def main():
    if not PROMETHEUS_AVAILABLE:
        print("Error: prometheus_client is required. Exiting.")
        return
        
    args = parser.parse_args()
    hostname = socket.gethostname()
    job_title = args.service_name
    job_id = os.environ.get('SLURM_JOB_ID', 'unknown')

    # Define Prometheus gauges for hardware metrics
    gauges = {
        'cpu_load_1m': Gauge('cpu_load_1m', 'CPU load average (1m)', ['hostname', 'job_title', 'job_id']),
        'cpu_load_5m': Gauge('cpu_load_5m', 'CPU load average (5m)', ['hostname', 'job_title', 'job_id']),
        'cpu_load_15m': Gauge('cpu_load_15m', 'CPU load average (15m)', ['hostname', 'job_title', 'job_id']),
        'mem_total': Gauge('system_memory_total_bytes', 'Total system memory', ['hostname', 'job_title', 'job_id']),
        'mem_used': Gauge('system_memory_used_bytes', 'Used system memory', ['hostname', 'job_title', 'job_id']),
        'mem_available': Gauge('system_memory_available_bytes', 'Available system memory', ['hostname', 'job_title', 'job_id']),
        'mem_percent': Gauge('system_memory_percent', 'System memory usage percent', ['hostname', 'job_title', 'job_id'])
    }
    
    # Define Prometheus gauges for benchmark metrics (read from summary.json)
    benchmark_gauges = {
        'requests_total': Gauge('benchmark_requests_total', 'Total requests in benchmark', ['benchmark_id', 'service']),
        'success_rate': Gauge('benchmark_success_rate', 'Success rate (0-100)', ['benchmark_id', 'service']),
        'requests_per_second': Gauge('benchmark_requests_per_second', 'Throughput RPS', ['benchmark_id', 'service']),
        'latency_avg': Gauge('benchmark_latency_avg_seconds', 'Average latency', ['benchmark_id', 'service']),
        'latency_p50': Gauge('benchmark_latency_p50_seconds', 'P50 latency', ['benchmark_id', 'service']),
        'latency_p95': Gauge('benchmark_latency_p95_seconds', 'P95 latency', ['benchmark_id', 'service']),
        'latency_p99': Gauge('benchmark_latency_p99_seconds', 'P99 latency', ['benchmark_id', 'service']),
        'tokens_per_second': Gauge('benchmark_tokens_per_second', 'LLM tokens/sec', ['benchmark_id', 'service']),
    }

    # Define Prometheus gauges for real-time monitoring
    realtime_gauges = {
        'active_clients': Gauge('active_benchmark_clients', 'Number of active benchmark client processes', ['hostname', 'job_title']),
        'estimated_throughput': Gauge('estimated_requests_per_second', 'Estimated throughput based on active clients', ['hostname', 'job_title'])
    }
    
    # Start HTTP server for Prometheus to scrape
    try:
        start_http_server(args.port)
        print(f"Prometheus metrics server started on port {args.port}")
    except Exception as e:
        print(f"Failed to start Prometheus metrics server: {e}")
        return

    print(f"Collecting metrics for service '{job_title}' on host '{hostname}'...")

    # Find results directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    results_dir = os.path.join(script_dir, '..', '..', 'results')
    if not os.path.exists(results_dir):
        results_dir = '/p/project1/EUMASTER4HPC01/teams/team1/Team1_EUMASTER4HPC2526/results'
    
    last_update_time = {}  # Track when we last read each summary.json

    while True:
        # === Hardware Metrics ===
        load1, load5, load15 = get_cpu_load()
        total, used, available, percent = get_memory_usage()

        labels = {'hostname': hostname, 'job_title': job_title, 'job_id': job_id}
        
        gauges['cpu_load_1m'].labels(**labels).set(load1)
        gauges['cpu_load_5m'].labels(**labels).set(load5)
        gauges['cpu_load_15m'].labels(**labels).set(load15)
        gauges['mem_total'].labels(**labels).set(total)
        gauges['mem_used'].labels(**labels).set(used)
        gauges['mem_available'].labels(**labels).set(available)
        gauges['mem_percent'].labels(**labels).set(percent)

        # === Real-Time Benchmark Metrics (Heartbeat Counting) ===
        client_count = 0
        try:
            if os.path.exists(results_dir):
                # Check for heartbeat files in all benchmark directories
                # Pattern 1: Global results (results/BM-*/heartbeat_*)
                heartbeats = glob.glob(os.path.join(results_dir, 'BM-*', 'heartbeat_*'))
                
                # Pattern 2: Local benchmark directory (../heartbeat_*)
                # When running as a sidecar in benchmark_dir/scripts/scraper.py
                local_heartbeats = glob.glob(os.path.join(script_dir, '..', 'heartbeat_*'))
                heartbeats.extend(local_heartbeats)
                
                current_time = time.time()
                for hb_path in heartbeats:
                    try:
                        # Check if file was modified in the last 15 seconds
                        mtime = os.path.getmtime(hb_path)
                        if current_time - mtime < 15:
                            client_count += 1
                    except OSError:
                        pass  # File might have been deleted (benchmark finished)
        except Exception as e:
            print(f"Error checking heartbeats: {e}")
        
        # Estimate throughput: ~5000 RPS per client for Redis (conservative estimate)
        # This gives immediate visual feedback before the final report
        estimated_rps = client_count * 5000
        
        realtime_labels = {'hostname': hostname, 'job_title': job_title}
        realtime_gauges['active_clients'].labels(**realtime_labels).set(client_count)
        realtime_gauges['estimated_throughput'].labels(**realtime_labels).set(estimated_rps)

        # === Benchmark Metrics (from summary.json files) ===
        try:
            if os.path.exists(results_dir):
                import json
                import glob
                
                # Find all summary.json files in results
                summaries = glob.glob(os.path.join(results_dir, 'BM-*', 'summary.json'))
                
                for summary_path in summaries[-10:]:  # Only last 10 benchmarks
                    try:
                        mtime = os.path.getmtime(summary_path)
                        # Skip if not updated since last read
                        if summary_path in last_update_time and mtime <= last_update_time[summary_path]:
                            continue
                        
                        with open(summary_path, 'r') as f:
                            summary = json.load(f)
                        
                        benchmark_id = os.path.basename(os.path.dirname(summary_path))
                        service = summary.get('service_type', 'unknown')
                        labels = {'benchmark_id': benchmark_id, 'service': service}
                        
                        # Export metrics
                        benchmark_gauges['requests_total'].labels(**labels).set(summary.get('total_requests', 0))
                        benchmark_gauges['success_rate'].labels(**labels).set(summary.get('success_rate', 0))
                        benchmark_gauges['requests_per_second'].labels(**labels).set(summary.get('requests_per_second', 0))
                        
                        latency = summary.get('latency_s', {})
                        benchmark_gauges['latency_avg'].labels(**labels).set(latency.get('avg', 0))
                        benchmark_gauges['latency_p50'].labels(**labels).set(latency.get('p50', 0))
                        benchmark_gauges['latency_p95'].labels(**labels).set(latency.get('p95', 0))
                        benchmark_gauges['latency_p99'].labels(**labels).set(latency.get('p99', 0))
                        
                        if 'tokens_per_second' in summary:
                            benchmark_gauges['tokens_per_second'].labels(**labels).set(summary.get('tokens_per_second', 0))
                        
                        last_update_time[summary_path] = mtime
                        
                    except Exception as e:
                        pass  # Skip invalid files silently
        except Exception as e:
            pass  # Ignore errors in benchmark metric collection

        time.sleep(args.interval)


if __name__ == "__main__":
    main()
