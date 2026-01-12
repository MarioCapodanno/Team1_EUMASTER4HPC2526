# AI Factory Benchmarking Framework

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MeluXina](https://img.shields.io/badge/HPC-MeluXina-orange.svg)](https://luxprovide.lu/)

DEMO VIDEO: https://jumpshare.com/s/cIjAgHpFNb3LU72oAiBg
---

##  Overview

This framework automates the complete benchmarking lifecycle for containerized AI services:

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Recipe    │───▶│   Deploy    │───▶│  Load Gen   │───▶│   Analyze   │───▶│   Report    │
│   (YAML)    │    │  (Slurm)    │    │  (Clients)  │    │  (Metrics)  │    │  (MD/JSON)  │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
```

-  **One-command execution** from declarative YAML recipes
-  **Automated analysis** including saturation detection and bottleneck attribution
- **Full reproducibility** with embedded metadata and rerun support
-  **Dual interface** with CLI and web UI feature parity
-  **Real-time monitoring** via Prometheus/Grafana integration

---

##  Installation

### Prerequisites
- Python 3.10+
- SSH access to MeluXina (or compatible HPC cluster)
- SSH key authentication configured

### Setup

```bash
# Clone the repository
git clone https://github.com/EUMASTER4HPC/Team1_EUMASTER4HPC2526.git
cd Team1_EUMASTER4HPC2526

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Verify installation
python src/frontend.py --help
```

### Configuration

Create `~/.melussh` or configure SSH with host alias `meluxina`:

```bash
# ~/.ssh/config
Host meluxina
    HostName login.lxp.lu
    User your_username
    IdentityFile ~/.ssh/id_meluxina
```

---

##  Quick Start

### Run Your First Benchmark

```bash
# 1. Run a Redis benchmark
python src/frontend.py examples/recipe_redis.yaml

# 2. Monitor execution
python src/frontend.py --watch BM-20260112-001

# 3. Generate analysis report
python src/frontend.py --report BM-20260112-001

# 4. View results in web interface
python src/frontend.py --web
# Open http://localhost:5000
```

### Interactive Mode

```bash
python src/frontend.py --ui
```

Provides a guided menu for benchmark operations.

---

##  Supported Services

| Category | Service | Port | Use Case |
|----------|---------|------|----------|
| **Inference** | vLLM | 8000 | High-performance LLM serving with PagedAttention |
| | Ollama | 11434 | Lightweight local LLM deployment |
| **Database** | PostgreSQL | 5432 | OLTP transactional workloads |
| | Redis | 6379 | In-memory caching and pub/sub |
| | MinIO | 9000 | S3-compatible object storage |
| **Vector DB** | ChromaDB | 8000 | Embedding storage for RAG |
| | Qdrant | 6333 | High-performance vector search |

---

##  Recipe Format

Recipes define complete experiments in declarative YAML:

```yaml
configuration:
  target: meluxina

service:
  type: vllm                    # Service type
  partition: gpu                # Slurm partition
  num_gpus: 1                   # GPU allocation
  time_limit: "01:00:00"        # Job time limit
  settings:
    model: facebook/opt-125m   # Model to serve

client:
  type: vllm_smoke              # Client type
  partition: cpu
  settings:
    num_requests: 100
    max_tokens: 50

benchmarks:
  num_clients: 4                # Concurrent clients
```

See [`docs/RECIPE_REFERENCE.md`](docs/RECIPE_REFERENCE.md) for complete reference.

---

##  Automated Analysis

### Saturation Detection

Identifies the optimal operating point using maximum curvature analysis:

```bash
# Run concurrency sweep
python src/frontend.py examples/recipe_redis.yaml --clients 1,2,4,8,16,32

# Generate sweep report
python src/frontend.py --sweep-report BM-001,BM-002,BM-003,BM-004,BM-005
```

**Outputs:**
- Latency knee point (where P99 grows superlinearly)
- Throughput saturation (max sustainable RPS)
- SLO compliance limit (max concurrency under latency target)

### Bottleneck Attribution

Classifies limiting factors from resource utilization:

| Bottleneck | Indicators |
|------------|------------|
| GPU-bound | GPU util >80%, stable CPU, rising TTFT |
| CPU-bound | High CPU time, low GPU, stable memory |
| Memory-bound | High RSS, OOM errors, latency spikes |
| Queueing | Throughput plateau, exploding P99 |

### Regression Detection

```bash
python src/frontend.py --compare BM-001 BM-002
```

Flags regressions when:
- P99 latency increases >10%
- Throughput decreases >10%
- Success rate drops >1%

---

##  User Interfaces

### Command-Line Interface

```bash
# Benchmark Operations
python src/frontend.py <recipe.yaml>           # Run benchmark
python src/frontend.py --ui                     # Interactive mode

# Monitoring
python src/frontend.py --list                   # List all benchmarks
python src/frontend.py --watch <id>             # Live status
python src/frontend.py --logs <id>              # View logs
python src/frontend.py --stop <id>              # Cancel jobs

# Results
python src/frontend.py --collect <id>           # Download artifacts
python src/frontend.py --metrics <id>           # View metrics
python src/frontend.py --report <id>            # Generate report

# Analysis
python src/frontend.py --compare <a> <b>        # Regression detection
python src/frontend.py --sweep-report <ids>     # Saturation analysis

# Web Interface
python src/frontend.py --web                    # Launch at :5000
```

### Web Interface

Launch with `python src/frontend.py --web` and open http://localhost:5000

**Pages:**
- **Dashboard** - Overview of all benchmarks with status
- **Run Recipe** - Deploy benchmarks from UI
- **Benchmarks** - Detailed benchmark views
- **Monitoring** - Prometheus/Grafana integration
- **Metrics** - Charts and statistics
- **Reports** - Generated analysis with plots

---

##  Project Structure

```
Team1_EUMASTER4HPC2526/
├── src/
│   ├── frontend.py              # CLI entry point, recipe parsing
│   ├── core/
│   │   ├── manager.py           # Service/client orchestration
│   │   ├── aggregator.py        # Metrics aggregation
│   │   ├── saturation.py        # KF1: Saturation detection
│   │   ├── bottleneck.py        # KF2: Bottleneck attribution
│   │   ├── lifecycle.py         # Job lifecycle management
│   │   └── collector.py         # Artifact collection
│   ├── infra/
│   │   ├── communicator.py      # SSH/Slurm abstraction
│   │   └── storage.py           # Benchmark state persistence
│   ├── models/
│   │   ├── service.py           # Service data model
│   │   └── client.py            # Client data model
│   ├── builders/
│   │   └── command_builders.py  # Sbatch script generation
│   ├── monitoring/
│   │   ├── manager.py           # Prometheus/Grafana stack
│   │   └── monitor.py           # Metrics collection
│   ├── reporting/
│   │   ├── reporter.py          # Report generation
│   │   ├── plotting.py          # Chart generation
│   │   └── artifacts.py         # Artifact I/O
│   └── web/
│       └── flask_app.py         # Web interface
├── examples/                     # Recipe templates
├── measurements/                 # Benchmark campaigns
├── results/                      # Benchmark artifacts (gitignored)
├── reports/                      # Generated reports
├── docs/                         # Documentation
│   ├── report.tex               # Academic LaTeX report
│   ├── presentation.tex         # Beamer slides
│   ├── RECIPE_REFERENCE.md      # Recipe format reference
│   └── methodology.md           # Benchmarking methodology
├── scripts/                      # Automation scripts
├── requirements.txt              # Python dependencies
└── README.md                     # This file
```

---

##  Results Structure

Each benchmark produces:

```
results/<benchmark_id>/
├── run.json           # Complete metadata + embedded recipe
├── requests.jsonl     # Per-request timing (microsecond precision)
├── summary.json       # Aggregated metrics
└── logs/              # Service and client logs

reports/<benchmark_id>/
├── report.md          # Human-readable analysis
├── report.json        # Machine-readable summary
└── plots/             # Visualization PNGs
    ├── latency_percentiles.png
    ├── throughput_timeline.png
    └── success_rate.png
```

---

##  Reproducibility

Every benchmark is fully reproducible:

```bash
# Rerun with identical configuration
python src/frontend.py --rerun BM-20260112-001
```

Captured metadata includes:
- Complete YAML recipe (embedded)
- Git commit hash
- Container image digests
- Slurm job IDs and node allocations
- Timestamps for all lifecycle events

---

##  Documentation

| Document | Description |
|----------|-------------|
| [`docs/report.tex`](docs/report.tex) | Academic LaTeX report |
| [`docs/presentation.tex`](docs/presentation.tex) | Beamer presentation slides |
| [`docs/RECIPE_REFERENCE.md`](docs/RECIPE_REFERENCE.md) | Complete recipe format reference |
| [`docs/methodology.md`](docs/methodology.md) | Benchmarking methodology |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | System architecture documentation |

---

##  Technology Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.10+ |
| Cluster Communication | Fabric, Paramiko (SSH) |
| Job Scheduling | Slurm |
| Containerization | Apptainer/Singularity |
| Web Framework | Flask |
| Visualization | Matplotlib, Chart.js |
| Monitoring | Prometheus, Grafana |
| Target Platform | MeluXina (LuxProvide) |

---

##  Team

**Team 1 — EUMASTER4HPC 2025-2026**

| Member | 
|--------|
| Mario Capodanno 
| Giuseppe | 
| Can | 
| Thies | 

---

*Developed for the EUMASTER4HPC Data Science Challenge 2025-2026*
