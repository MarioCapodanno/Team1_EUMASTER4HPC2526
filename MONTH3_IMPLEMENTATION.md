# Month 3 Implementation Plan (February 2026)

## Goal: Benchmarking Experiments & Dataset

This month focuses on running systematic benchmark experiments and building a validated dataset for analysis.

---

## Week 1-2: Run Systematic Benchmark Suite

### LLM Suite (vLLM/Ollama)
Run concurrency sweeps to find saturation points:

```bash
# Concurrency sweep: 1, 2, 4, 8 clients
python src/frontend.py examples/recipe_vllm_stress.yaml  # 1 client
# Modify recipe for 2, 4, 8 clients and run each
```

**Configurations to test:**
| Clients | Purpose |
|---------|---------|
| 1 | Baseline latency |
| 2 | Light load |
| 4 | Medium load |
| 8 | Heavy load |

### PostgreSQL Suite
Run connection sweeps:

```bash
# Already have baseline: benchmark 29 (4 clients)
# Run additional sweeps
python src/frontend.py examples/recipe_postgres_stress.yaml
```

**Configurations to test:**
| Clients | Purpose |
|---------|---------|
| 1 | Single connection baseline |
| 4 | Current baseline (benchmark 29) |
| 8 | High concurrency |
| 16 | Saturation test |

### ChromaDB Suite
Run vector database sweeps:

```bash
# Already have baseline: benchmark 32 (4 clients)
python src/frontend.py examples/recipe_chroma_stress.yaml
```

---

## Week 3-4: Validation & Comparisons

### Establish Baselines
Define reference benchmarks for regression detection:

| Category | Baseline ID | Service | Notes |
|----------|-------------|---------|-------|
| Storage | 29 | PostgreSQL | 4 clients, validated |
| Retrieval | 32 | ChromaDB | 4 clients, validated |
| Inference | TBD | vLLM | Pending |

### Run Comparisons (KF4)
Use the `--compare` command to detect regressions:

```bash
# Compare new run against baseline
python src/frontend.py --compare 29 <new_postgres_id>
python src/frontend.py --compare 32 <new_chroma_id>
```

**Expected output:**
```
============================================================
Comparison: 29 (baseline) vs 35 (current)
============================================================

Metric                    Baseline     Current      Delta        Change     Status  
--------------------------------------------------------------------------------
Success Rate              100.0%       99.5%        -0.5%        -0.5%      OK      
Throughput (RPS)          50.00        52.30        +2.30        +4.6%      OK      
P99 Latency               0.015s       0.018s       +0.003s      +20.0%     REGRESS 

============================================================
⚠ RESULT: REGRESSIONS DETECTED
```

### Generate Saturation Reports (KF1)
For concurrency sweeps, analyze saturation points:

```bash
# After running sweep with multiple concurrency levels
python src/frontend.py --report <sweep_id>
```

The report will include:
- Latency knee detection
- Throughput saturation point
- Recommended operating range under SLO

---

## Deliverables

### 1. Dataset Index (`docs/dataset_index.md`)
✅ Created - tracks all experiments with:
- Benchmark IDs
- Configurations
- Purpose
- Status

### 2. Raw Results (`results/<id>/`)
For each benchmark:
- `run.json` - metadata
- `requests.jsonl` - raw request data
- `summary.json` - aggregated metrics

### 3. Reports (`reports/<id>/`)
For each benchmark:
- `report.md` - human-readable analysis
- `plots/` - visualization PNGs

### 4. Comparison Results
- Baseline vs current comparisons
- Regression detection output
- PASS/FAIL gates for CI integration

---

## Commands Reference

### Running Benchmarks
```bash
# Interactive UI
python src/frontend.py --ui

# Direct recipe execution
python src/frontend.py examples/recipe_<service>_stress.yaml

# Watch status
python src/frontend.py --watch <benchmark_id>
```

### Analyzing Results
```bash
# View summary with metrics
python src/frontend.py --summary <benchmark_id>

# Generate report
python src/frontend.py --report <benchmark_id>

# Compare two runs
python src/frontend.py --compare <baseline_id> <current_id>

# View logs
python src/frontend.py --logs <benchmark_id>
```

### Web UI
```bash
# Launch web interface
python src/frontend.py --web
# Open http://localhost:5000
```

---

## Operational Rules

1. **Warmup**: Always enabled (5-30 seconds depending on service)
2. **Repetitions**: At least 3 runs per configuration when possible
3. **Metadata**: All recipes and environment details recorded in `run.json`
4. **Validation**: Check for outliers and rerun if needed

---

## Success Criteria

By end of Month 3:
- [ ] At least 10 benchmark runs completed
- [ ] Concurrency sweep for at least 2 services
- [ ] Baseline benchmarks established
- [ ] Comparison reports generated
- [ ] Dataset index complete
- [ ] All results reproducible via stored recipes

---

## Current Status

### Completed Benchmarks
| ID | Service | Clients | Status | Notes |
|----|---------|---------|--------|-------|
| 29 | PostgreSQL | 4 | ✅ Complete | Baseline storage |
| 32 | ChromaDB | 4 | ✅ Complete | Baseline retrieval |

### Pending Benchmarks
| Service | Clients | Priority | Notes |
|---------|---------|----------|-------|
| PostgreSQL | 1,8,16 | High | Complete sweep |
| ChromaDB | 1,2,8 | High | Complete sweep |
| vLLM | 1,2,4,8 | High | Inference baseline |
| Ollama | 1,2,4 | Medium | Alternative inference |

---

## Next Steps

1. **Immediate**: Run PostgreSQL sweep (1, 8, 16 clients)
2. **This week**: Run ChromaDB sweep (1, 2, 8 clients)
3. **Next week**: Run vLLM baseline and sweep
4. **End of month**: Generate all comparison reports
