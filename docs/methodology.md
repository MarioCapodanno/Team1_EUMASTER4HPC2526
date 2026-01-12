# Methodology

This document explains the metrics collected by the AI Factory Benchmarking Framework and how to interpret them.

## Overview

The framework collects performance metrics from benchmark runs and aggregates them into standardized artifacts. This methodology ensures reproducible, comparable results across different services and configurations.

## Metrics Collected

### Universal Metrics (All Services)

| Metric | Unit | Description | How Computed |
|--------|------|-------------|--------------|
| **Total Requests** | count | Number of operations executed | Count of JSONL entries |
| **Success Rate** | % | Percentage of successful operations | `successful / total * 100` |
| **Latency (avg)** | seconds | Mean response time | Arithmetic mean of all latencies |
| **Latency (P50)** | seconds | Median response time | 50th percentile |
| **Latency (P90)** | seconds | 90th percentile latency | 90th percentile |
| **Latency (P95)** | seconds | 95th percentile latency | 95th percentile |
| **Latency (P99)** | seconds | 99th percentile (tail) latency | 99th percentile |
| **Throughput** | RPS/TPS | Operations per second | `total_requests / duration` |

### LLM-Specific Metrics (vLLM, Ollama)

| Metric | Unit | Description |
|--------|------|-------------|
| **Tokens/Second** | TPS | Output token throughput |
| **TTFT** | seconds | Time to First Token (streaming only) |
| **Output Tokens** | count | Average tokens generated per request |
| **Input Tokens** | count | Average prompt tokens per request |

### Database-Specific Metrics (PostgreSQL)

| Metric | Unit | Description |
|--------|------|-------------|
| **Insert TPS** | TPS | Insert transactions per second |
| **Select QPS** | QPS | Select queries per second |
| **Operation Breakdown** | - | Per-operation latency statistics |

## Percentile Calculation

Percentiles are calculated using linear interpolation:

```python
def percentile(values, p):
    sorted_values = sorted(values)
    k = (len(sorted_values) - 1) * (p / 100)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_values[int(k)]
    return sorted_values[f] * (c - k) + sorted_values[c] * (k - f)
```

## Throughput Calculation

Throughput is calculated as:

```
throughput = total_requests / (max_timestamp - min_timestamp)
```

Where timestamps are extracted from the first and last request in the JSONL file.

## Latency Measurement

Latency is measured per-request as:

```
latency_s = timestamp_end - timestamp_start
```

Both timestamps are captured using high-resolution timers (`date +%s.%N` on Linux).

## SLO Compliance

The framework uses default SLO thresholds for assessment:

| Service Type | SLO Threshold | Metric |
|--------------|---------------|--------|
| LLM (vLLM, Ollama) | P99 < 1000ms | Response latency |
| Database (PostgreSQL) | P99 < 100ms | Query latency |
| Vector DB (ChromaDB) | P99 < 200ms | Query latency |

These thresholds can be customized in the recipe or via CLI flags.

## Saturation Analysis (KF1)

The Saturation Finder analyzes concurrency sweeps to detect:

1. **Latency Knee**: Point where P99 latency starts growing sharply
2. **Throughput Saturation**: Point where throughput stops scaling linearly
3. **SLO Limit**: Maximum concurrency that meets the SLO threshold

### Knee Detection Algorithm

Uses maximum curvature method:
1. Normalize x and y values to [0, 1]
2. Calculate curvature at each point
3. Find point with maximum curvature (excluding endpoints)

## Regression Detection (KF4)

Compares two benchmark runs and flags regressions:

| Metric | Regression Threshold |
|--------|---------------------|
| P99 Latency | > 10% increase |
| Throughput | > 10% decrease |
| Success Rate | > 1% decrease |
| Error Count | Any increase |

## Artifact Schema

### run.json
Contains benchmark metadata:
- Benchmark ID
- Timestamps
- Service configuration
- Client configuration
- Slurm job IDs
- Git commit (if available)

### requests.jsonl
One JSON object per request:
```json
{
  "timestamp_start": 1704672000.123,
  "timestamp_end": 1704672000.456,
  "latency_s": 0.333,
  "success": true,
  "service_type": "postgres",
  "request_id": "insert_1",
  "operation_type": "insert"
}
```

### summary.json
Aggregated metrics:
```json
{
  "total_requests": 1000,
  "successful_requests": 998,
  "failed_requests": 2,
  "success_rate": 99.8,
  "latency_s": {
    "avg": 0.012,
    "min": 0.008,
    "max": 0.150,
    "p50": 0.011,
    "p90": 0.015,
    "p95": 0.018,
    "p99": 0.025
  },
  "requests_per_second": 50.0
}
```

## Interpreting Results

### Good Performance Indicators
- ✅ Success rate ≥ 99%
- ✅ P99 latency within SLO
- ✅ Linear throughput scaling with concurrency
- ✅ Low latency variance (P99/P50 ratio < 3)

### Warning Signs
- ⚠️ P99 latency > 2x P50 (high variance)
- ⚠️ Throughput plateaus while latency increases
- ⚠️ Success rate < 99%
- ⚠️ Error patterns in logs

### Bottleneck Indicators
- **CPU-bound**: High CPU utilization, stable GPU, rising latency
- **GPU-bound**: High GPU utilization, stable CPU, TTFT increases
- **Memory-bound**: High RSS, OOM errors, latency spikes
- **I/O-bound**: Latency spikes without compute saturation

## Best Practices

1. **Warmup**: Always include warmup period (default: 5-30 seconds)
2. **Duration**: Run tests long enough for stable metrics (≥30 seconds)
3. **Repetition**: Run multiple times for statistical significance
4. **Isolation**: Avoid running other workloads during benchmarks
5. **Documentation**: Record all configuration parameters
