# scripts/ - Campaign Automation

Scripts for automated benchmark campaign execution.

## Files

| File | Description |
|------|-------------|
| `config.py` | Shared configuration (TARGET, ACCOUNT) with environment variable support |
| `run_campaign.py` | Launch scaling benchmarks for Redis, Ollama, vLLM, Postgres |
| `analyze_benchmarks.py` | Generate analysis plots from completed benchmarks |

## Configuration

Override defaults via environment variables:
```bash
export BENCHMARK_TARGET="meluxina"    # SSH target
export BENCHMARK_ACCOUNT="p200981"    # Slurm account
```

## Usage

```bash
# Dry-run (generate recipes only)
python scripts/run_campaign.py --dry-run --service redis

# Full campaign
python scripts/run_campaign.py --service ollama

# Analysis
python scripts/analyze_benchmarks.py
```
