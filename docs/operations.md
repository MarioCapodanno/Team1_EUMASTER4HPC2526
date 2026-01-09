# Operations Guide

This guide explains how to run the AI Factory Benchmarking Framework on MeluXina HPC cluster.

## Prerequisites

### Local Machine
- Python 3.10+
- SSH access to MeluXina configured (SSH alias `meluxina`)
- Conda environment with dependencies installed

### MeluXina
- Active account with compute allocation
- Access to CPU and GPU partitions

## Quick Start

### 1. Setup Environment

```bash
# Clone repository
git clone <repo-url>
cd Team1_EUMASTER4HPC2526

# Create conda environment
conda create -n ds2025 python=3.14
conda activate ds2025

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure SSH

Ensure your `~/.ssh/config` has MeluXina configured:

```
Host meluxina
    HostName login.lxp.lu
    User your_username
    IdentityFile ~/.ssh/your_key
```

### 3. Run a Benchmark

```bash
# Run PostgreSQL stress test
python src/frontend.py examples/recipe_postgres_stress.yaml

# Run vLLM inference benchmark
python src/frontend.py examples/recipe_vllm.yaml

# Run Ollama benchmark
python src/frontend.py examples/recipe_ollama.yaml
```

## CLI Commands

### Running Benchmarks

```bash
# Run a benchmark from recipe
python src/frontend.py <recipe.yaml>

# Run with verbose output
python src/frontend.py <recipe.yaml> -v
```

### Managing Benchmarks

```bash
# List all benchmarks
python src/frontend.py --list

# Show benchmark summary
python src/frontend.py --summary <BENCHMARK_ID>

# Watch live status
python src/frontend.py --watch <BENCHMARK_ID>

# Stop a benchmark
python src/frontend.py --stop <BENCHMARK_ID>
```

### Viewing Results

```bash
# Show logs
python src/frontend.py --logs <BENCHMARK_ID>

# Collect metrics
python src/frontend.py --metrics <BENCHMARK_ID>

# Generate report
python src/frontend.py --report <BENCHMARK_ID>

# Compare two benchmarks
python src/frontend.py --compare <BASELINE_ID> <CURRENT_ID>
```

### Web UI

```bash
# Launch Flask web UI
python src/frontend.py --web

# Or directly
python src/web/flask_app.py
```

Then open http://localhost:5000 in your browser.

## Directory Structure

```
Team1_EUMASTER4HPC2526/
├── results/                    # Benchmark results
│   └── <benchmark_id>/
│       ├── run.json           # Metadata
│       ├── requests.jsonl     # Per-request data
│       └── summary.json       # Aggregated metrics
├── reports/                    # Generated reports
│   └── <benchmark_id>/
│       ├── report.md          # Markdown report
│       ├── report.json        # JSON report
│       └── plots/             # Visualization PNGs
├── examples/                   # Recipe examples
└── logs/                       # Downloaded logs
```

## Recipe Configuration

### Basic Structure

```yaml
configuration:
  target: "meluxina"

service:
  type: "postgres"           # Service type
  name: "my-benchmark"       # Service name
  partition: "cpu"           # Slurm partition
  time_limit: "01:00:00"     # Job time limit

client:
  type: "postgres_stress"    # Client type
  partition: "cpu"
  time_limit: "00:30:00"
  settings:
    num_inserts: 1000
    num_selects: 500

benchmarks:
  num_clients: 4             # Concurrent clients
```

### Supported Services

| Service | Type | Default Port |
|---------|------|--------------|
| PostgreSQL | `postgres` | 5432 |
| vLLM | `vllm` | 8000 |
| Ollama | `ollama` | 11434 |
| ChromaDB | `chroma` | 8000 |

## Accessing Results on MeluXina

### SSH Tunnel for Web UI

If running Flask on MeluXina:

```bash
# From your local machine
ssh -L 5000:localhost:5000 meluxina

# Then open http://localhost:5000
```

### Downloading Artifacts

```bash
# Download results
scp -r meluxina:~/benchmark_results/results/<id> ./results/

# Download reports
scp -r meluxina:~/benchmark_results/reports/<id> ./reports/
```

## Troubleshooting

### Common Issues

#### "Service health check failed"
- Check if the service container started correctly
- Verify port is not blocked
- Check Slurm job logs: `python src/frontend.py --logs <id>`

#### "No JSONL files found"
- Benchmark may not have completed
- Check client job status: `python src/frontend.py --watch <id>`
- Verify working directory on cluster

#### "Connection refused"
- SSH tunnel may have closed
- Verify SSH config is correct
- Check if MeluXina login nodes are accessible

### Checking Job Status

```bash
# On MeluXina
squeue -u $USER

# View job output
cat ~/benchmark_<id>/logs/*.out
```

### Cleaning Up

```bash
# Stop all jobs for a benchmark
python src/frontend.py --stop <BENCHMARK_ID>

# On MeluXina, cancel jobs manually
scancel <JOB_ID>
```

## Best Practices

1. **Start Small**: Test with small workloads first
2. **Monitor Resources**: Check GPU/CPU utilization
3. **Save Results**: Download artifacts after each run
4. **Document Changes**: Note any configuration changes
5. **Use Version Control**: Commit recipes and results

## Optional: Prometheus/Grafana Monitoring

The framework supports optional real-time monitoring:

```bash
# Enable monitoring (future feature)
python src/frontend.py <recipe.yaml> --with-monitoring

# Get monitoring access info
python src/frontend.py --monitoring-info <BENCHMARK_ID>
```

Container definitions are available in `containers/`:
- `prometheus.def` - Prometheus server
- `grafana.def` - Grafana dashboards
- `pushgateway.def` - Metrics push gateway

Pre-built dashboards in `config/grafana/dashboards/`:
- `llm-inference.json` - LLM metrics
- `database-benchmark.json` - Database metrics

## Support

For issues:
1. Check logs: `python src/frontend.py --logs <id>`
2. Review this guide
3. Check `docs/methodology.md` for metric interpretation
4. Contact the team
