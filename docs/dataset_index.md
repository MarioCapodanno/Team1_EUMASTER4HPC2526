# AI Factory Benchmarking Dataset Index

This document tracks all benchmark runs with their artifacts for reproducibility and analysis.

## Dataset Structure

Each benchmark produces:
- `results/<id>/run.json` - Full recipe, parameters, job IDs, git commit
- `results/<id>/requests.jsonl` - Per-request timing data
- `results/<id>/summary.json` - Aggregated metrics
- `reports/<id>/report.md` - Human-readable analysis
- `reports/<id>/report.json` - Machine-readable analysis
- `reports/<id>/plots/*.png` - Visualization artifacts

---

## Benchmark Categories

### Category 1: Inference (LLM)
Services: vLLM, Ollama

| Benchmark ID | Recipe | Date | Purpose | Status | Concurrency | Notes |
|--------------|--------|------|---------|--------|-------------|-------|
| BM-20260109-004 | recipe_ollama_1client.yaml | 2026-01-09 | Sweep baseline | ✅ Complete | 1 | 1.11 RPS, P99=0.98s |
| BM-20260109-006 | recipe_ollama_2client.yaml | 2026-01-09 | Sweep 2x | ✅ Complete | 2 | 1.90 RPS, P99=0.75s |
| BM-20260109-008 | recipe_ollama_4client.yaml | 2026-01-09 | Sweep 4x | ✅ Complete | 4 | 2.29 RPS, P99=1.13s |

### Category 2: Storage (Database/Object Store)
Services: PostgreSQL, MinIO, Redis

| Benchmark ID | Recipe | Date | Purpose | Status | Concurrency | Notes |
|--------------|--------|------|---------|--------|-------------|-------|
| BM-20260109-001 | recipe_redis_1client.yaml | 2026-01-09 | Sweep baseline | ✅ Complete | 1 | 3.37 RPS, P95=0.35s |
| BM-20260109-002 | recipe_redis_2client.yaml | 2026-01-09 | Sweep 2x | ✅ Complete | 2 | 6.51 RPS, P95=0.37s |
| BM-20260109-003 | recipe_redis_4client.yaml | 2026-01-09 | Sweep 4x | ✅ Complete | 4 | 12.80 RPS, P95=0.37s |

### Category 3: Retrieval (Vector DB)
Services: ChromaDB, Qdrant

| Benchmark ID | Recipe | Date | Purpose | Status | Concurrency | Notes |
|--------------|--------|------|---------|--------|-------------|-------|
| BM-20260109-005 | recipe_chroma_1client.yaml | 2026-01-09 | Sweep baseline | ✅ Complete | 1 | 6.52 RPS, P95=0.26s |
| BM-20260109-007 | recipe_chroma_2client.yaml | 2026-01-09 | Sweep 2x | ✅ Complete | 2 | 9.09 RPS, P95=0.43s |
| BM-20260109-009 | recipe_chroma_8client.yaml | 2026-01-09 | Sweep 8x | ✅ Complete | 8 | 6.97 RPS, P95=1.62s |

---

## Concurrency Sweeps

### Inference Sweep
**Purpose**: Find optimal concurrency for LLM inference under SLO
**SLO**: P99 < 1.0s

| Sweep Name | Service | Concurrency Levels | Sweep Report | Status |
|------------|---------|-------------------|--------------|--------|
| ollama_sweep | Ollama (llama2) | 1, 2, 4 | `reports/sweep_BM-20260109-004_BM-20260109-008/` | ✅ Complete |

### Storage Sweep
**Purpose**: Find optimal concurrency for database operations under SLO
**SLO**: P99 < 100ms

| Sweep Name | Service | Concurrency Levels | Sweep Report | Status |
|------------|---------|-------------------|--------------|--------|
| redis_sweep | Redis | 1, 2, 4 | `reports/sweep_BM-20260109-001_BM-20260109-003/` | ✅ Complete |

### Retrieval Sweep
**Purpose**: Find optimal concurrency for vector search under SLO
**SLO**: P99 < 500ms

| Sweep Name | Service | Concurrency Levels | Sweep Report | Status |
|------------|---------|-------------------|--------------|--------|
| chroma_sweep | ChromaDB | 1, 2, 8 | `reports/sweep_BM-20260109-005_BM-20260109-009/` | ✅ Complete |

---

## Reproducibility Guide

### Re-running a Benchmark

Each benchmark can be reproduced from its `run.json`:

```bash
# Option 1: Use --rerun command (if available)
python src/frontend.py --rerun <benchmark_id>

# Option 2: Manual reproduction from run.json
# 1. Extract recipe from run.json
cat results/<id>/run.json | jq '.recipe' > recipe.yaml

# 2. Verify git commit matches
git checkout $(cat results/<id>/run.json | jq -r '.git_commit')

# 3. Run the recipe
python src/frontend.py recipe.yaml
```

### Verifying Reproducibility Bundle

Each `run.json` must contain:
- ✅ `benchmark_id` - Unique identifier
- ✅ `created_at` - Timestamp
- ✅ `git_commit` - Code version
- ✅ `recipe_hash` - Recipe fingerprint
- ✅ `recipe` - Full recipe embedded
- ✅ `target` - Cluster name
- ✅ `service` - Service deployment details (name, job_id, image, port, etc.)
- ✅ `clients` - Client deployment details (job_id, command, etc.)
- ✅ `environment` - Framework version

---

## Notes

- All benchmarks use `BM-YYYYMMDD-NNN` format for IDs
- Sweep reports are in `reports/sweep_<first>_<last>/`
- Dataset is continuously updated during Phase 3

---

*Last updated: 2026-01-09*
