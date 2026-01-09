# Dataset Index

This document tracks all benchmark experiments run on MeluXina for the AI Factory Benchmarking Framework evaluation.

## Experiment Categories

### Inference Benchmarks
| Benchmark ID | Service | Configuration | Date | Purpose | Status |
|--------------|---------|---------------|------|---------|--------|
| 30 | Ollama | 2 clients | 2026-01-08 | Baseline inference | Completed |
| 31 | Ollama | 2 clients | 2026-01-08 | Baseline inference | Completed |

### Storage Benchmarks
| Benchmark ID | Service | Configuration | Date | Purpose | Status |
|--------------|---------|---------------|------|---------|--------|
| 29 | PostgreSQL | 4 clients, stress test | 2026-01-08 | Baseline storage | Completed |
| 32 | ChromaDB | 4 clients, stress test | 2026-01-08 | Baseline retrieval | Completed |

### PostgreSQL Concurrency Sweep
| Benchmark ID | Service | Clients | Throughput | P99 Latency | Status |
|--------------|---------|---------|------------|-------------|--------|
| BM-20260108-008 | PostgreSQL | 1 | 50.00 RPS | 17ms | Completed |
| BM-20260108-009 | PostgreSQL | 2 | 54.85 RPS | 17ms | Completed |
| 29 | PostgreSQL | 4 | 50.00 RPS | 15ms | Completed (Baseline) |
| BM-20260108-010 | PostgreSQL | 8 | 74.88 RPS | 106ms | Completed |

### ChromaDB Concurrency Sweep
| Benchmark ID | Service | Clients | Throughput | P95 Latency | Status |
|--------------|---------|---------|------------|-------------|--------|
| BM-20260108-017 | ChromaDB | 1 | 5.56 RPS | 304ms | Completed |
| BM-20260108-018 | ChromaDB | 2 | 2.50 RPS | 2321ms | Completed |
| BM-20260108-019 | ChromaDB | 8 | 4.29 RPS | 4010ms | Completed |

### Ollama Concurrency Sweep
| Benchmark ID | Service | Clients | Throughput | P95 Latency | Avg Latency | Status |
|--------------|---------|---------|------------|-------------|-------------|--------|
| BM-20260108-020 | Ollama | 1 | 1.11 RPS | 1014ms | 797ms | Completed |
| BM-20260108-021 | Ollama | 2 | 3.00 RPS | 545ms | 495ms | Completed |
| BM-20260108-022 | Ollama | 4 | 2.60 RPS | 540ms | 445ms | Completed |

## Baseline Benchmarks

These benchmarks serve as reference points for regression detection:

| Category | Baseline ID | Service | Configuration | Notes |
|----------|-------------|---------|---------------|-------|
| Storage | 29 | PostgreSQL | 4 clients | First validated run |
| Retrieval | BM-20260108-017 | ChromaDB | 1 client | Lowest latency baseline |
| Inference | 30 | Ollama | 2 clients | First validated run |

## Experiment Design Rationale

### Concurrency Sweeps
We vary the number of concurrent clients (1, 2, 4, 8, 16) to:
- Identify the saturation point where throughput stops scaling
- Measure tail latency (P99) growth under load
- Determine the optimal operating point for SLO compliance

### Prompt Size Sweeps (LLM)
For LLM services, we vary prompt sizes to understand:
- Impact of context length on latency
- Memory pressure effects
- Token throughput variations

### Connection Sweeps (Database)
For database services, we vary connections to measure:
- Transaction throughput scaling
- Query latency under concurrent load
- Connection pool efficiency

## Reproducibility

Each benchmark can be reproduced using:
```bash
# View the exact configuration used
cat results/<benchmark_id>/run.json

# Re-run with same recipe
python src/frontend.py examples/<recipe>.yaml
```

## Results Location

- Raw data: `results/<benchmark_id>/requests.jsonl`
- Summary metrics: `results/<benchmark_id>/summary.json`
- Reports: `reports/<benchmark_id>/report.md`
- Plots: `reports/<benchmark_id>/plots/`
