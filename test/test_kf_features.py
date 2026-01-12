"""
Golden tests for Killer Features (KF1, KF2, KF4).

These tests verify deterministic behavior and expected outcomes for:
- KF1: Saturation analysis and knee detection
- KF2: Bottleneck classification
- KF4: Regression detection with configurable thresholds
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.aggregator import compare_summaries, DEFAULT_REGRESSION_THRESHOLDS
from core.saturation import (
    analyze_saturation,
    find_knee_point,
    find_latency_knee,
    find_throughput_saturation,
    find_slo_limit,
)
from core.bottleneck import classify_bottleneck


# ==============================================================================
# KF4: Regression Detection Tests
# ==============================================================================

class TestKF4RegressionDetection:
    """Golden tests for KF4 compare_summaries() regression detection."""

    def test_no_regression_identical_summaries(self):
        """Identical summaries should produce PASS verdict."""
        summary = {
            "service_type": "postgres",
            "success_rate": 100.0,
            "requests_per_second": 100.0,
            "latency_s": {"avg": 0.1, "p95": 0.2, "p99": 0.3},
        }
        result = compare_summaries(summary, summary)
        assert result["verdict"] == "PASS", "Identical summaries should PASS"
        assert len(result["regressions"]) == 0, "No regressions expected"

    def test_latency_regression_above_threshold(self):
        """Latency increase > 10% should be flagged as regression."""
        baseline = {
            "service_type": "vllm",
            "success_rate": 100.0,
            "requests_per_second": 50.0,
            "latency_s": {"avg": 1.0, "p95": 1.5, "p99": 2.0},
        }
        current = {
            "service_type": "vllm",
            "success_rate": 100.0,
            "requests_per_second": 50.0,
            "latency_s": {"avg": 1.2, "p95": 1.7, "p99": 2.5},  # 20%, 13%, 25% increase
        }
        result = compare_summaries(baseline, current)
        assert result["verdict"] == "FAIL", "Latency increase > 10% should FAIL"
        assert len(result["regressions"]) >= 1, "At least one regression expected"
        # Check that P99 is flagged
        p99_regression = any(r["metric"] == "P99 Latency (s)" for r in result["regressions"])
        assert p99_regression, "P99 latency regression should be flagged"

    def test_latency_within_threshold_passes(self):
        """Latency increase <= 10% should PASS."""
        baseline = {
            "service_type": "postgres",
            "success_rate": 100.0,
            "requests_per_second": 100.0,
            "latency_s": {"avg": 0.1, "p95": 0.2, "p99": 0.3},
        }
        current = {
            "service_type": "postgres",
            "success_rate": 100.0,
            "requests_per_second": 100.0,
            "latency_s": {"avg": 0.105, "p95": 0.21, "p99": 0.32},  # 5%, 5%, 6.7% increase
        }
        result = compare_summaries(baseline, current)
        assert result["verdict"] == "PASS", "Latency increase < 10% should PASS"

    def test_throughput_regression_above_threshold(self):
        """Throughput decrease > 10% should be flagged as regression."""
        baseline = {
            "service_type": "redis",
            "success_rate": 100.0,
            "requests_per_second": 1000.0,
            "latency_s": {"avg": 0.001, "p95": 0.002, "p99": 0.003},
        }
        current = {
            "service_type": "redis",
            "success_rate": 100.0,
            "requests_per_second": 850.0,  # 15% decrease
            "latency_s": {"avg": 0.001, "p95": 0.002, "p99": 0.003},
        }
        result = compare_summaries(baseline, current)
        assert result["verdict"] == "FAIL", "Throughput decrease > 10% should FAIL"
        throughput_regression = any(r["metric"] == "Throughput (RPS)" for r in result["regressions"])
        assert throughput_regression, "Throughput regression should be flagged"

    def test_success_rate_regression(self):
        """Success rate decrease > 1% should be flagged as regression."""
        baseline = {
            "service_type": "postgres",
            "success_rate": 99.5,
            "requests_per_second": 100.0,
            "latency_s": {"avg": 0.1, "p95": 0.2, "p99": 0.3},
        }
        current = {
            "service_type": "postgres",
            "success_rate": 97.0,  # 2.5% decrease
            "requests_per_second": 100.0,
            "latency_s": {"avg": 0.1, "p95": 0.2, "p99": 0.3},
        }
        result = compare_summaries(baseline, current)
        assert result["verdict"] == "FAIL", "Success rate decrease > 1% should FAIL"

    def test_custom_thresholds(self):
        """Custom thresholds should override defaults."""
        baseline = {
            "service_type": "postgres",
            "success_rate": 100.0,
            "requests_per_second": 100.0,
            "latency_s": {"avg": 1.0, "p95": 1.5, "p99": 2.0},
        }
        current = {
            "service_type": "postgres",
            "success_rate": 100.0,
            "requests_per_second": 100.0,
            "latency_s": {"avg": 1.15, "p95": 1.72, "p99": 2.3},  # 15% increase
        }
        # Default threshold (10%) should FAIL
        result_default = compare_summaries(baseline, current)
        assert result_default["verdict"] == "FAIL"
        
        # Custom threshold (20%) should PASS
        result_custom = compare_summaries(baseline, current, {"latency_pct": 20.0})
        assert result_custom["verdict"] == "PASS", "15% increase should pass with 20% threshold"

    def test_improvements_are_tracked(self):
        """Improvements should be tracked separately."""
        baseline = {
            "service_type": "vllm",
            "success_rate": 95.0,
            "requests_per_second": 100.0,
            "latency_s": {"avg": 2.0, "p95": 3.0, "p99": 4.0},
        }
        current = {
            "service_type": "vllm",
            "success_rate": 99.0,  # Improvement
            "requests_per_second": 150.0,  # 50% improvement
            "latency_s": {"avg": 1.5, "p95": 2.0, "p99": 2.5},  # 25% improvement
        }
        result = compare_summaries(baseline, current)
        assert result["verdict"] == "PASS", "Improvements should not cause FAIL"
        assert len(result["improvements"]) >= 1, "Improvements should be tracked"


# ==============================================================================
# KF1: Saturation Analysis Tests
# ==============================================================================

class TestKF1SaturationAnalysis:
    """Golden tests for KF1 analyze_saturation() knee/SLO behavior."""

    def test_find_knee_point_monotonic_curve(self):
        """Knee point detection on a classic saturation curve."""
        x = [1, 2, 4, 8, 16, 32]
        y = [0.1, 0.12, 0.15, 0.3, 1.0, 5.0]  # Sharp increase after x=8
        knee_idx = find_knee_point(x, y)
        assert knee_idx is not None, "Should find knee point"
        assert knee_idx >= 2, "Knee should be after initial linear region"

    def test_find_knee_point_insufficient_data(self):
        """Knee point should return None with < 3 data points."""
        assert find_knee_point([1, 2], [0.1, 0.2]) is None
        assert find_knee_point([1], [0.1]) is None
        assert find_knee_point([], []) is None

    def test_find_latency_knee(self):
        """Find latency knee point in a sweep."""
        concurrency = [1, 2, 4, 8, 16]
        p99_latencies = [0.05, 0.06, 0.08, 0.2, 0.8]
        result = find_latency_knee(concurrency, p99_latencies)
        assert result is not None, "Should find latency knee"
        assert result["type"] == "latency_knee"
        assert result["concurrency"] <= 16

    def test_find_throughput_saturation(self):
        """Find throughput saturation point."""
        concurrency = [1, 2, 4, 8, 16, 32]
        throughputs = [100, 180, 320, 500, 520, 510]  # Plateaus after 8
        result = find_throughput_saturation(concurrency, throughputs)
        assert result is not None, "Should find saturation point"
        assert result["type"] == "throughput_saturation"

    def test_find_slo_limit_all_pass(self):
        """SLO limit when all points meet threshold."""
        concurrency = [1, 2, 4, 8]
        p99_latencies = [0.05, 0.06, 0.07, 0.08]
        result = find_slo_limit(concurrency, p99_latencies, 0.1)  # SLO: 100ms
        assert result is not None
        assert result["max_concurrency"] == 8, "All points meet SLO, max is 8"
        assert result["headroom_percent"] > 0

    def test_find_slo_limit_partial_pass(self):
        """SLO limit when some points exceed threshold."""
        concurrency = [1, 2, 4, 8, 16]
        p99_latencies = [0.05, 0.06, 0.08, 0.12, 0.5]  # Exceeds 100ms at 8+
        result = find_slo_limit(concurrency, p99_latencies, 0.1)  # SLO: 100ms
        assert result is not None
        assert result["max_concurrency"] == 4, "Max SLO-compliant is 4"

    def test_find_slo_limit_none_pass(self):
        """SLO limit when no points meet threshold."""
        concurrency = [1, 2, 4]
        p99_latencies = [0.2, 0.3, 0.5]  # All exceed 100ms
        result = find_slo_limit(concurrency, p99_latencies, 0.1)
        assert result is None, "No points meet SLO"

    def test_analyze_saturation_full_sweep(self):
        """Full saturation analysis on synthetic sweep data."""
        sweep_results = [
            {"concurrency": 1, "requests_per_second": 50, "latency_s": {"p95": 0.05, "p99": 0.06}},
            {"concurrency": 2, "requests_per_second": 95, "latency_s": {"p95": 0.06, "p99": 0.07}},
            {"concurrency": 4, "requests_per_second": 180, "latency_s": {"p95": 0.07, "p99": 0.08}},
            {"concurrency": 8, "requests_per_second": 300, "latency_s": {"p95": 0.1, "p99": 0.15}},
            {"concurrency": 16, "requests_per_second": 350, "latency_s": {"p95": 0.3, "p99": 0.5}},
            {"concurrency": 32, "requests_per_second": 320, "latency_s": {"p95": 1.0, "p99": 2.0}},
        ]
        result = analyze_saturation(sweep_results, slo_threshold=0.2)
        
        assert "data_points" in result
        assert result["data_points"] == 6
        assert "recommendation" in result
        assert result["recommendation"]["max_recommended_concurrency"] is not None
        
        # With SLO=200ms, max should be <= 8 (where P99=150ms)
        assert result["recommendation"]["max_recommended_concurrency"] <= 8

    def test_analyze_saturation_with_slo_compliance(self):
        """Analysis includes SLO compliance info when threshold provided."""
        sweep_results = [
            {"concurrency": 1, "requests_per_second": 100, "latency_s": {"p95": 0.01, "p99": 0.02}},
            {"concurrency": 2, "requests_per_second": 190, "latency_s": {"p95": 0.02, "p99": 0.03}},
        ]
        result = analyze_saturation(sweep_results, slo_threshold=0.1)
        assert "slo_limit" in result
        assert "max_concurrency" in result["slo_limit"]


# ==============================================================================
# KF2: Bottleneck Classification Tests
# ==============================================================================

class TestKF2BottleneckClassification:
    """Golden tests for KF2 classify_bottleneck() classification outcomes."""

    def test_healthy_system(self):
        """Healthy system with good metrics should be classified as 'healthy'."""
        summary = {
            "success_rate": 99.5,  # >= 99%
            "requests_per_second": 500.0,
            "total_requests": 1000,
            "failed_requests": 5,
            "latency_s": {"avg": 0.3, "p50": 0.35, "p95": 0.4, "p99": 0.5},  # p99 < 1.0, spread = 0.5/0.35 = 1.43 < 2
            "error_summary": {},
        }
        result = classify_bottleneck(summary)
        assert result["classification"] == "healthy", f"Got {result['classification']} with scores {result['scores']}"
        assert result["confidence"] in ["high", "medium"]

    def test_queueing_high_latency_spread(self):
        """High P99/P50 ratio indicates queueing bottleneck."""
        summary = {
            "success_rate": 95.0,
            "requests_per_second": 100.0,
            "total_requests": 1000,
            "failed_requests": 50,
            "latency_s": {"avg": 0.5, "p50": 0.1, "p95": 1.5, "p99": 3.0},  # P99/P50 = 30x
            "error_summary": {},
        }
        result = classify_bottleneck(summary)
        assert result["classification"] == "queueing"
        assert any("spread" in e.lower() for e in result["evidence"])

    def test_queueing_with_timeouts(self):
        """Timeout errors indicate queueing/overload."""
        summary = {
            "success_rate": 90.0,
            "requests_per_second": 50.0,
            "total_requests": 1000,
            "failed_requests": 100,
            "latency_s": {"avg": 2.0, "p50": 1.0, "p95": 5.0, "p99": 10.0},
            "error_summary": {"timeout": 100},
        }
        result = classify_bottleneck(summary)
        assert result["classification"] == "queueing"

    def test_gpu_bound_with_metrics(self):
        """High GPU utilization indicates GPU-bound."""
        summary = {
            "success_rate": 100.0,
            "requests_per_second": 20.0,
            "total_requests": 200,
            "failed_requests": 0,
            "latency_s": {"avg": 0.5, "p50": 0.45, "p95": 0.6, "p99": 0.7},
            "error_summary": {},
        }
        gpu_metrics = {
            "gpu_utilization": 95.0,
            "memory_used_mb": 15000,
            "memory_total_mb": 16000,
        }
        result = classify_bottleneck(summary, gpu_metrics=gpu_metrics)
        assert result["classification"] == "gpu_bound"
        assert any("gpu" in e.lower() for e in result["evidence"])

    def test_memory_bound_high_gpu_memory(self):
        """High GPU memory usage indicates memory-bound."""
        summary = {
            "success_rate": 100.0,
            "requests_per_second": 10.0,
            "total_requests": 100,
            "failed_requests": 0,
            "latency_s": {"avg": 1.0, "p50": 0.9, "p95": 1.2, "p99": 1.5},
            "error_summary": {},
        }
        gpu_metrics = {
            "gpu_utilization": 60.0,
            "memory_used_mb": 31000,
            "memory_total_mb": 32000,  # 97% memory usage
        }
        result = classify_bottleneck(summary, gpu_metrics=gpu_metrics)
        assert result["classification"] in ["memory_bound", "gpu_bound"]

    def test_cpu_bound_with_slurm_metrics(self):
        """High CPU efficiency indicates CPU-bound."""
        summary = {
            "success_rate": 100.0,
            "requests_per_second": 200.0,
            "total_requests": 2000,
            "failed_requests": 0,
            "latency_s": {"avg": 0.05, "p50": 0.04, "p95": 0.07, "p99": 0.1},
            "error_summary": {},
        }
        slurm_metrics = {
            "cpu_time_s": 950,
            "elapsed_s": 1000,  # 95% CPU efficiency
            "max_rss_mb": 4000,
        }
        result = classify_bottleneck(summary, slurm_metrics=slurm_metrics)
        assert result["classification"] in ["cpu_bound", "healthy"]

    def test_unknown_with_minimal_evidence(self):
        """Unknown classification when no clear indicators."""
        summary = {
            "success_rate": 100.0,
            "requests_per_second": 100.0,
            "total_requests": 100,
            "failed_requests": 0,
            "latency_s": {"avg": 0.5, "p50": 0.45, "p95": 0.55, "p99": 0.6},
            "error_summary": {},
        }
        result = classify_bottleneck(summary)
        # Either healthy or unknown depending on scoring
        assert result["classification"] in ["healthy", "unknown"]

    def test_recommendations_provided(self):
        """All classifications should provide recommendations."""
        summaries = [
            {  # Healthy
                "success_rate": 100.0, "requests_per_second": 500.0,
                "total_requests": 1000, "failed_requests": 0,
                "latency_s": {"avg": 0.05, "p50": 0.04, "p95": 0.08, "p99": 0.1},
                "error_summary": {},
            },
            {  # Queueing
                "success_rate": 90.0, "requests_per_second": 50.0,
                "total_requests": 1000, "failed_requests": 100,
                "latency_s": {"avg": 2.0, "p50": 0.5, "p95": 5.0, "p99": 10.0},
                "error_summary": {"timeout": 100},
            },
        ]
        for summary in summaries:
            result = classify_bottleneck(summary)
            assert "recommendations" in result
            assert len(result["recommendations"]) > 0, f"No recommendations for {result['classification']}"


# ==============================================================================
# Run tests
# ==============================================================================

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])

