"""
Unit tests for aggregator module using fixture requests.jsonl files per service type.
"""

import json
import tempfile
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.aggregator import aggregate_requests, aggregate_benchmark, write_summary_json
from reporting.artifacts import write_requests_jsonl, read_requests_jsonl


def create_fixture_requests(service_type: str, num_requests: int = 10) -> list:
    """Create fixture request data for a service type."""
    requests = []
    base_time = 1000000000
    
    for i in range(num_requests):
        request = {
            "timestamp_start": base_time + i,
            "timestamp_end": base_time + i + 1,
            "latency_s": 0.1 + (i * 0.01),
            "success": i < num_requests - 1,  # Last one fails
            "service_type": service_type,
            "request_id": i + 1,
        }
        
        # Add service-specific fields
        if service_type == "postgres":
            request["operation_type"] = "insert" if i % 2 == 0 else "select"
        elif service_type == "chroma":
            request["operation_type"] = "insert" if i % 2 == 0 else "query"
            request["dimension"] = 128
        elif service_type == "qdrant":
            request["operation"] = "INSERT" if i % 2 == 0 else "QUERY"
        elif service_type == "minio":
            request["operation"] = "PUT" if i % 2 == 0 else "GET"
            request["bytes"] = 1048576
        elif service_type == "redis":
            request["operation"] = "SET" if i % 2 == 0 else "GET"
        elif service_type in ["vllm", "ollama"]:
            request["http_status"] = 200 if request["success"] else None
            request["output_tokens"] = 50 if request["success"] else 0
        
        requests.append(request)
    
    return requests


def test_aggregate_postgres():
    """Test aggregation for PostgreSQL requests."""
    requests = create_fixture_requests("postgres", 10)
    summary = aggregate_requests(requests)
    
    assert summary["total_requests"] == 10
    assert summary["successful_requests"] == 9
    assert summary["failed_requests"] == 1
    assert summary["success_rate"] == 90.0
    assert summary["service_type"] == "postgres"
    assert "latency_s" in summary
    assert summary["latency_s"]["p50"] > 0
    assert summary["latency_s"]["p99"] > summary["latency_s"]["p50"]


def test_aggregate_chroma():
    """Test aggregation for ChromaDB requests."""
    requests = create_fixture_requests("chroma", 10)
    summary = aggregate_requests(requests)
    
    assert summary["total_requests"] == 10
    assert summary["success_rate"] == 90.0
    assert summary["service_type"] == "chroma"


def test_aggregate_qdrant():
    """Test aggregation for Qdrant requests."""
    requests = create_fixture_requests("qdrant", 10)
    summary = aggregate_requests(requests)
    
    assert summary["total_requests"] == 10
    assert summary["success_rate"] == 90.0
    assert summary["service_type"] == "qdrant"


def test_aggregate_minio():
    """Test aggregation for MinIO requests."""
    requests = create_fixture_requests("minio", 10)
    summary = aggregate_requests(requests)
    
    assert summary["total_requests"] == 10
    assert summary["success_rate"] == 90.0
    assert summary["service_type"] == "minio"


def test_aggregate_redis():
    """Test aggregation for Redis requests."""
    requests = create_fixture_requests("redis", 10)
    summary = aggregate_requests(requests)
    
    assert summary["total_requests"] == 10
    assert summary["success_rate"] == 90.0
    assert summary["service_type"] == "redis"


def test_aggregate_vllm():
    """Test aggregation for vLLM requests."""
    requests = create_fixture_requests("vllm", 10)
    summary = aggregate_requests(requests)
    
    assert summary["total_requests"] == 10
    assert summary["success_rate"] == 90.0
    assert summary["service_type"] == "vllm"


def test_aggregate_ollama():
    """Test aggregation for Ollama requests."""
    requests = create_fixture_requests("ollama", 10)
    summary = aggregate_requests(requests)
    
    assert summary["total_requests"] == 10
    assert summary["success_rate"] == 90.0
    assert summary["service_type"] == "ollama"


def test_aggregate_empty():
    """Test aggregation with empty requests."""
    summary = aggregate_requests([])
    
    assert summary["total_requests"] == 0
    assert summary["success_rate"] == 0.0
    assert summary["latency_s"]["p50"] == 0.0


def test_aggregate_benchmark_integration():
    """Test full aggregation pipeline with temporary files."""
    benchmark_id = "test-aggregator-001"
    
    # Create temporary results directory
    with tempfile.TemporaryDirectory() as tmpdir:
        results_dir = Path(tmpdir) / "results" / benchmark_id
        results_dir.mkdir(parents=True)
        
        # Write fixture requests
        requests = create_fixture_requests("postgres", 20)
        requests_file = results_dir / "requests.jsonl"
        with open(requests_file, "w") as f:
            for req in requests:
                f.write(json.dumps(req) + "\n")
        
        # Change to temp directory and run aggregation
        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            
            # Aggregate
            summary = aggregate_benchmark(benchmark_id)
            
            assert summary is not None
            assert summary["total_requests"] == 20
            assert summary["success_rate"] == 95.0  # 19/20
            
            # Check summary.json was written
            summary_file = results_dir / "summary.json"
            assert summary_file.exists()
            
            with open(summary_file) as f:
                saved_summary = json.load(f)
            
            assert saved_summary["total_requests"] == 20
        finally:
            os.chdir(old_cwd)


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])

