# AI Factory Benchmarking Framework - Results Summary

**Date:** January 8, 2026  
**Platform:** MeluXina HPC Cluster  
**Framework Version:** Month 3 Implementation

---

## Executive Summary

This document presents the results of systematic benchmarking experiments conducted on the MeluXina HPC cluster to evaluate the AI Factory Benchmarking Framework's capabilities for performance analysis of AI/ML infrastructure services.

### Key Findings

1. **PostgreSQL Concurrency Scaling**: Throughput scales from 50 RPS (1 client) to 74.88 RPS (8 clients) with acceptable latency degradation up to 4 clients.

2. **ChromaDB Vector Database**: Single-client performance shows 5.56 RPS with 304ms P95 latency. Concurrency increases cause significant latency growth, indicating saturation.

3. **Framework Capabilities Validated**:
   - Automated benchmark deployment on HPC
   - JSONL metrics collection
   - Report generation with plots
   - Regression detection via `--compare`

---

## PostgreSQL Concurrency Sweep Results

| Clients | Throughput (RPS) | Avg Latency | P95 Latency | P99 Latency | Success Rate |
|---------|------------------|-------------|-------------|-------------|--------------|
| 1       | 50.00            | 12ms        | 13ms        | 17ms        | 100%         |
| 2       | 54.85            | 13ms        | 13ms        | 17ms        | 100%         |
| 4       | 50.00            | 12ms        | 12ms        | 15ms        | 100%         |
| 8       | 74.88            | 14ms        | 14ms        | 106ms       | 100%         |

### Analysis
- **Optimal Operating Point**: 4 clients provides best latency with acceptable throughput
- **Saturation Indicator**: P99 latency spike at 8 clients (106ms vs 15ms baseline)
- **Throughput Scaling**: ~50% improvement from 1→8 clients

---

## ChromaDB Vector Database Results

| Clients | Throughput (RPS) | Avg Latency | P95 Latency | Success Rate |
|---------|------------------|-------------|-------------|--------------|
| 1       | 5.56             | 152ms       | 304ms       | 100%         |
| 2       | 2.50             | 720ms       | 2321ms      | 100%         |
| 8       | 4.29             | 1750ms      | 4010ms      | 100%         |

### Analysis
- **Single-Client Baseline**: Best performance at 1 client (5.56 RPS, 304ms P95)
- **Concurrency Impact**: Significant latency degradation with concurrent clients
- **Recommendation**: ChromaDB performs best with limited concurrency; consider connection pooling

---

## Ollama LLM Inference Results

| Clients | Throughput (RPS) | Avg Latency | P95 Latency | Success Rate |
|---------|------------------|-------------|-------------|--------------|
| 1       | 1.11             | 797ms       | 1014ms      | 100%         |
| 2       | 3.00             | 495ms       | 545ms       | 100%         |
| 4       | 2.60             | 445ms       | 540ms       | 100%         |

### Analysis
- **Optimal Concurrency**: 2 clients provides best throughput (3.00 RPS)
- **Latency Improvement**: Average latency decreases with concurrency (batching effect)
- **Saturation Point**: Throughput drops at 4 clients, indicating GPU saturation

---

## Benchmark IDs Reference

### PostgreSQL Sweep
- `BM-20260108-008`: 1 client
- `BM-20260108-009`: 2 clients  
- `29`: 4 clients (baseline)
- `BM-20260108-010`: 8 clients

### ChromaDB Sweep
- `BM-20260108-017`: 1 client (baseline)
- `BM-20260108-018`: 2 clients
- `BM-20260108-019`: 8 clients

### Ollama Sweep
- `BM-20260108-020`: 1 client
- `BM-20260108-021`: 2 clients (optimal)
- `BM-20260108-022`: 4 clients

---

## CLI Commands for Result Access

```bash
# List all benchmarks
python src/frontend.py --list

# View specific benchmark summary
python src/frontend.py --summary <benchmark_id>

# Generate detailed report
python src/frontend.py --report <benchmark_id>

# Compare two benchmarks (regression detection)
python src/frontend.py --compare <baseline_id> <current_id>

# View logs
python src/frontend.py --logs <benchmark_id>
```

---

## Web UI Access

The Web UI provides interactive access to all benchmark results:

```bash
# Start the Web UI
python src/frontend.py --web

# Access at http://localhost:5000
```

Features available:
- Dashboard with all benchmarks
- Interactive plots (latency, throughput)
- Comparison views
- Report downloads

---

## Framework Capabilities Demonstrated

### KF1: Saturation Finder
- Identified PostgreSQL saturation point at 8 clients (P99 spike)
- ChromaDB shows immediate saturation with concurrent clients

### KF4: Regression Detection
- `--compare` command validates performance changes
- Automatic flagging of latency regressions >5%

### Reproducibility
All benchmarks can be reproduced using:
```bash
# PostgreSQL sweep
python src/frontend.py examples/sweeps/recipe_postgres_1client.yaml
python src/frontend.py examples/sweeps/recipe_postgres_2client.yaml
python src/frontend.py examples/sweeps/recipe_postgres_8client.yaml

# ChromaDB sweep
python src/frontend.py examples/sweeps/recipe_chroma_1client.yaml
python src/frontend.py examples/sweeps/recipe_chroma_2client.yaml
python src/frontend.py examples/sweeps/recipe_chroma_8client.yaml
```

---

## Artifacts Location

| Artifact Type | Location |
|---------------|----------|
| Raw metrics | `results/<benchmark_id>/requests.jsonl` |
| Summary | `results/<benchmark_id>/summary.json` |
| Reports | `reports/<benchmark_id>/report.md` |
| Plots | `reports/<benchmark_id>/plots/` |
| Recipes | `examples/sweeps/` |

---

## Conclusions

1. **Framework Validation**: Successfully demonstrated end-to-end benchmarking workflow on HPC
2. **Saturation Analysis**: Clear identification of performance saturation points
3. **Regression Detection**: Automated comparison enables CI/CD integration
4. **Reproducibility**: All experiments documented and reproducible via recipes

---

*Generated by AI Factory Benchmarking Framework*
