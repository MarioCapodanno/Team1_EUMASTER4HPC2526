# src/ - Source Code

Main source code for the AI Factory Benchmarking Framework.

## Structure

| Directory | Description |
|-----------|-------------|
| `core/` | Core benchmark management (manager, aggregator, collector, lifecycle) |
| `infra/` | Infrastructure layer (SSH communicator, storage, health checks, logs) |
| `monitoring/` | Metrics collection and monitoring stack (Prometheus/Grafana integration) |
| `reporting/` | Report generation, analysis, plotting, and artifact management |
| `models/` | Data models for Service, Client entities |
| `builders/` | Recipe and configuration builders |
| `cli/` | Command-line interface utilities |
| `web/` | Flask web application for browser-based UI |

## Key Files

- `frontend.py` - Main CLI entry point with all commands (--run, --watch, --report, etc.)
- `__init__.py` - Package initialization with version info

## Usage

```bash
# Run a benchmark from recipe
python src/frontend.py examples/recipe_redis.yaml

# Interactive UI
python src/frontend.py --ui

# Web interface  
python src/frontend.py --web
```
