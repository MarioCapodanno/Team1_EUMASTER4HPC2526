# AI Factory Benchmarking Framework

> A modular Python framework for benchmarking AI services on the MeluXina supercomputer.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Overview

This framework enables reproducible, end-to-end benchmarking of AI Factory workloads on HPC clusters. It orchestrates the deployment of containerized services (inference engines, databases, vector stores) via Slurm, generates configurable client load, and collects performance metrics.

**Target Platform**: [MeluXina Supercomputer](https://luxprovide.lu/) (Luxembourg)

### Key Features

- **Recipe-driven benchmarks**: Define experiments in simple YAML files
- **Service orchestration**: Deploy any containerized service via Slurm + Apptainer
- **Scalable load generation**: Spawn multiple benchmark clients in parallel
- **Persistent state**: Track all benchmark runs with unique IDs
- **Extensible design**: Pluggable backends for storage, communication, and metrics

---

## Table of Contents

- [Quick Start](#quick-start)
- [Installation](#installation)
- [Usage](#usage)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Recipe Format](#recipe-format)
- [Supported Services](#supported-services)
- [Development Status](#development-status)
- [Contributing](#contributing)
- [Team](#team)
- [License](#license)

---

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/YOUR_ORG/Team1_EUMASTER4HPC2526.git
cd Team1_EUMASTER4HPC2526

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure SSH access to MeluXina (add to ~/.ssh/config)
#    Host meluxina
#        HostName login.lxp.lu
#        User YOUR_USERNAME

# 4. Run a benchmark
python src/frontend.py examples/recipe_test.yaml

# 5. Check benchmark status
python src/frontend.py --summary 1

# 6. Launch Web UI
python src/frontend.py --web  # Launches Flask-based Web UI
```

---

## Installation

### Prerequisites

- Python 3.10+
- SSH access to MeluXina cluster
- Valid Slurm account on MeluXina (e.g., `p200981`)

### Dependencies

```bash
pip install fabric paramiko pyyaml
```

Or install all dependencies:

```bash
pip install -r requirements.txt
```

### SSH Configuration

Add your MeluXina connection to `~/.ssh/config`:

```
Host meluxina
    HostName login.lxp.lu
    User YOUR_USERNAME
    IdentityFile ~/.ssh/id_rsa
```

---

## Usage

### Running a Benchmark

```bash
# Deploy a service and run benchmark clients
python src/frontend.py examples/recipe_ollama.yaml

# With verbose output
python src/frontend.py examples/recipe_vllm.yaml -v

# Interactive mode
python src/frontend.py --ui
```

### Managing Benchmarks

```bash
# List all benchmarks
python src/frontend.py --list

# Show benchmark summary
python src/frontend.py --summary <benchmark_id>

# Watch live status
python src/frontend.py --watch <benchmark_id>

# Stop a benchmark
python src/frontend.py --stop <benchmark_id>

# View logs
python src/frontend.py --logs <benchmark_id>

# Collect metrics
python src/frontend.py --metrics <benchmark_id>
```

### Web UI

```bash
# Launch Flask-based Web UI
python src/frontend.py --web

# Then open http://localhost:5000 in your browser
```

### Example Recipe

```yaml
configuration:
  target: "meluxina"

service:
  name: "ollama-benchmark"
  image: "ollama/ollama:latest"
  command: "ollama serve"
  partition: "gpu"
  num_gpus: 1
  time_limit: "01:00:00"
  account: "p200981"

client:
  command: "curl http://$SERVICE_HOSTNAME:11434/api/generate -d '{\"model\":\"llama2\",\"prompt\":\"Hello\"}'"
  partition: "cpu"
  time_limit: "00:30:00"

benchmarks:
  num_clients: 4
  metrics: ["response_time", "throughput"]
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Interface                          │
│                      (CLI / Web UI)                             │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                         Frontend                                 │
│              Recipe parsing, session management                  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                         Manager                                  │
│           Service & client orchestration, job lifecycle          │
└───────┬──────────────┬──────────────┬──────────────┬────────────┘
        │              │              │              │
        ▼              ▼              ▼              ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│Communicator │ │  Service    │ │   Client    │ │   Storage   │
│   (SSH)     │ │  (Model)    │ │   (Model)   │ │   (CSV)     │
└──────┬──────┘ └─────────────┘ └─────────────┘ └─────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│                    MeluXina Cluster                              │
│                  (Slurm + Apptainer)                            │
└─────────────────────────────────────────────────────────────────┘
```

For detailed architecture documentation, see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Project Structure

```
Team1_EUMASTER4HPC2526/
├── src/                      # Source code
│   ├── frontend.py           # CLI entry point, recipe parsing
│   ├── manager.py            # Service/client orchestration
│   ├── communicator.py       # SSH communication with cluster
│   ├── service.py            # Service data model
│   ├── client.py             # Client data model
│   ├── storage.py            # Persistence layer (CSV backend)
│   └── monitor.py            # Metrics collection (WIP)
│
├── examples/                 # Example recipes and logs
│   ├── recipe_test.yaml      # Basic test recipe
│   ├── recipe_ollama.yaml    # Ollama inference benchmark
│   ├── recipe_vllm.yaml      # vLLM inference benchmark
│   ├── recipe_postgres.yaml  # PostgreSQL benchmark
│   └── recipe_chroma.yaml    # ChromaDB vector search benchmark
│
├── test/                     # Test scripts
│   └── test_manager.py       # Manager integration tests
│
├── ARCHITECTURE.md           # Detailed architecture documentation
├── DEVELOPMENT_PLAN.md       # Development roadmap and requirements
├── requirements.txt          # Python dependencies
└── README.md                 # This file
```

---

## Recipe Format

Recipes are YAML files that define a complete benchmark experiment.

### Sections

| Section | Description |
|---------|-------------|
| `configuration` | Cluster target (SSH alias) |
| `service` | Container image, command, Slurm resources |
| `client` | Benchmark command, Slurm resources |
| `benchmarks` | Number of clients, metrics to collect |

### Service Configuration

```yaml
service:
  name: "my-service"          # Service identifier
  image: "nginx:latest"       # Container image (Docker Hub)
  command: "nginx -g 'daemon off;'"  # Command to run
  partition: "gpu"            # Slurm partition (gpu/cpu)
  num_gpus: 1                 # Number of GPUs
  time_limit: "01:00:00"      # Job time limit (HH:MM:SS)
  account: "p200981"          # Slurm account/project
```

### Client Configuration

```yaml
client:
  command: "benchmark-tool --url $SERVICE_URL"
  partition: "cpu"
  num_gpus: 0
  time_limit: "00:30:00"
```

**Environment Variables Available to Clients**:
- `$SERVICE_NAME` - Service identifier
- `$SERVICE_HOSTNAME` - Node where service is running
- `$SERVICE_PORT` - Service port (if configured)
- `$SERVICE_URL` - Full HTTP URL to service

---

## Supported Services

The framework is designed to benchmark any containerized service. Example configurations are provided for:

### Inference Engines
- **Ollama** - Local LLM inference
- **vLLM** - High-throughput LLM serving

### Databases
- **PostgreSQL** - Relational database
- **MinIO** - S3-compatible object storage

### Vector Databases
- **ChromaDB** - Embedding database
- **Milvus** - Scalable vector search
- **Faiss** - Facebook AI similarity search

---

## Development Status

See [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md) for the full roadmap.

### Current Status (Phase 2)

| Module | Status | Description |
|--------|--------|-------------|
| Frontend (CLI) | ✅ Done | Recipe parsing, basic deployment |
| Manager | ✅ Done | Service/client orchestration |
| Communicator | ✅ Done | SSH/Slurm integration |
| Service Model | ✅ Done | Data model with persistence |
| Client Model | ✅ Done | Data model with persistence |
| Storage | ✅ Done | CSV backend |
| Monitor | 🚧 WIP | Metrics collection |
| Logs | 📋 Planned | Log aggregation |
| Reporting | 📋 Planned | Report generation |
| Prometheus Export | 📋 Planned | Optional metrics export |
| Grafana Dashboards | 📋 Planned | Optional pre-built dashboards |
| Web UI | 📋 Planned | Optional Flask-based UI |

### Requirements Coverage

| Requirement | Status |
|-------------|--------|
| REQ-IF-01: Recipe Management | ✅ |
| REQ-IF-02: Session Control | ⚠️ Partial |
| REQ-IF-03: Status Monitoring | 📋 Planned |
| REQ-IF-04: Data Retrieval | 📋 Planned |
| REQ-IF-05: Reporting | 📋 Planned |
| REQ-SV-01: Service Deployment | ✅ |
| REQ-SV-02: Service Lifecycle | 📋 Planned |
| REQ-SV-03: Health Checks | 📋 Planned |
| REQ-SV-04: Supported Services | ✅ |
| REQ-CL-01: Client Deployment | ✅ |
| REQ-CL-02: Workload Generation | 📋 Planned |
| REQ-CL-03: Client Lifecycle | 📋 Planned |
| REQ-MO-01: Metric Collection | 📋 Planned |
| REQ-MO-02: Live Monitoring | 📋 Planned |
| REQ-MO-03: Data Persistence | 📋 Planned |
| REQ-LG-01: Log Aggregation | 📋 Planned |
| REQ-LG-02: Log Access | 📋 Planned |
| REQ-LG-03: Log Storage | 📋 Planned |

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes (`git commit -am 'Add new feature'`)
4. Push to the branch (`git push origin feature/my-feature`)
5. Open a Pull Request

### Code Style

- Follow PEP 8
- Add docstrings to all public functions
- Write type hints for function signatures

---

## Team

**Team 1 - EUMASTER4HPC 2025-2026**

| Name | Role |
|------|------|
| Mario | Developer |
| Giuseppe | Developer |
| Can | Developer |
| Thies | Developer |

**Supervisor**: Dr. Farouk Mansouri (LuxProvide)

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- [LuxProvide](https://luxprovide.lu/) for access to MeluXina
- EUMASTER4HPC program for the opportunity
- Dr. Farouk Mansouri for mentorship and guidance