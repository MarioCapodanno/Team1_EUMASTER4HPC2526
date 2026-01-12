"""
Integration tests: generate dummy results → run --report → verify artifacts.
"""

import json
import tempfile
import shutil
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from reporting.artifacts import (
    write_run_json,
    write_requests_jsonl,
    read_run_json,
    read_requests_jsonl,
    read_summary_json,
)
from core.aggregator import aggregate_benchmark
from reporting.reporter import generate_benchmark_report


def create_dummy_benchmark(benchmark_id: str, service_type: str = "postgres", num_requests: int = 50):
    """Create a dummy benchmark with all artifacts."""
    results_dir = Path("results") / benchmark_id
    results_dir.mkdir(parents=True, exist_ok=True)
    
    # Create run.json
    run_data = {
        "benchmark_id": benchmark_id,
        "created_at": "2026-01-09T12:00:00Z",
        "service_type": service_type,
        "service": {
            "type": service_type,
            "hostname": "test-node",
            "job_id": "12345",
        },
        "clients": [
            {"job_id": "12346", "name": "client-1"}
        ],
        "recipe": {
            "service": {"type": service_type},
            "client": {"type": f"{service_type}_stress"},
        },
    }
    
    with open(results_dir / "run.json", "w") as f:
        json.dump(run_data, f, indent=2)
    
    # Create requests.jsonl
    requests = []
    base_time = 1000000000
    
    for i in range(num_requests):
        request = {
            "timestamp_start": base_time + i,
            "timestamp_end": base_time + i + 1,
            "latency_s": 0.1 + (i * 0.01),
            "success": i < num_requests - 2,  # Last 2 fail
            "service_type": service_type,
            "request_id": i + 1,
        }
        
        # Add service-specific fields
        if service_type == "postgres":
            request["operation_type"] = "insert" if i % 2 == 0 else "select"
        elif service_type == "minio":
            request["operation"] = "PUT" if i % 2 == 0 else "GET"
            request["bytes"] = 1048576
        
        requests.append(request)
    
    write_requests_jsonl(benchmark_id, requests)
    
    return benchmark_id


def test_e2e_postgres():
    """Test end-to-end flow for PostgreSQL."""
    benchmark_id = create_dummy_benchmark("test-e2e-postgres", "postgres", 50)
    
    # Aggregate
    summary = aggregate_benchmark(benchmark_id)
    assert summary is not None
    assert summary["total_requests"] == 50
    
    # Generate report
    report_files = generate_benchmark_report(benchmark_id)
    assert "markdown" in report_files
    assert "json" in report_files
    assert "plots" in report_files
    
    # Verify files exist
    assert Path(f"reports/{benchmark_id}/report.md").exists()
    assert Path(f"reports/{benchmark_id}/report.json").exists()
    assert len(report_files["plots"]) > 0
    
    # Cleanup
    shutil.rmtree(f"results/{benchmark_id}", ignore_errors=True)
    shutil.rmtree(f"reports/{benchmark_id}", ignore_errors=True)


def test_e2e_minio():
    """Test end-to-end flow for MinIO."""
    benchmark_id = create_dummy_benchmark("test-e2e-minio", "minio", 30)
    
    # Aggregate
    summary = aggregate_benchmark(benchmark_id)
    assert summary is not None
    
    # Generate report
    report_files = generate_benchmark_report(benchmark_id)
    assert "markdown" in report_files
    
    # Cleanup
    shutil.rmtree(f"results/{benchmark_id}", ignore_errors=True)
    shutil.rmtree(f"reports/{benchmark_id}", ignore_errors=True)


def test_e2e_redis():
    """Test end-to-end flow for Redis."""
    benchmark_id = create_dummy_benchmark("test-e2e-redis", "redis", 40)
    
    # Aggregate
    summary = aggregate_benchmark(benchmark_id)
    assert summary is not None
    
    # Generate report
    report_files = generate_benchmark_report(benchmark_id)
    assert "markdown" in report_files
    
    # Cleanup
    shutil.rmtree(f"results/{benchmark_id}", ignore_errors=True)
    shutil.rmtree(f"reports/{benchmark_id}", ignore_errors=True)


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])

