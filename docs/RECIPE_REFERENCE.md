# Recipe Reference Guide

This document explains how to create and customize benchmark recipes using the simplified `type` + `settings` approach.

## Overview

Recipes are YAML files that define:
- **Service**: The containerized application to benchmark (e.g., database, LLM server)
- **Client**: The benchmark workload to run against the service
- **Benchmarks**: Configuration like number of concurrent clients

## Basic Structure

```yaml
configuration:
  target: "meluxina"          # SSH alias for the cluster

service:
  type: "postgres"            # Service type (auto-generates startup command)
  name: "my-service"          # Unique name for this service
  partition: "cpu"            # Slurm partition (cpu or gpu)
  num_gpus: 0                 # Number of GPUs needed
  time_limit: "02:00:00"      # Max runtime (HH:MM:SS)
  settings:                   # Type-specific configuration
    db_name: "benchmark"

client:
  type: "postgres_smoke"      # Client type (auto-generates benchmark command)
  partition: "cpu"
  num_gpus: 0
  time_limit: "00:30:00"
  settings:                   # Type-specific configuration
    warmup_delay: 5

benchmarks:
  num_clients: 4              # Number of concurrent clients
  metrics: ["latency"]        # Metrics to track (informational)
```

---

## Supported Service Types

### `postgres`

PostgreSQL database server.

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `db_name` | string | `"benchmark"` | Database name to create |
| `auth` | string | `"trust"` | Authentication method |
| `data_dir` | string | `"/tmp/pgdata"` | Data directory path |
| `tuning.shared_buffers` | string | `"128MB"` | Shared buffer size |
| `tuning.effective_cache_size` | string | `"512MB"` | Effective cache size |

**Default image:** `postgres:latest`  
**Default port:** `5432`

---

### `chroma`

ChromaDB vector database server.

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `host` | string | `"0.0.0.0"` | Listen address |
| `port` | int | `8000` | Listen port |

**Default image:** `chromadb/chroma:latest`  
**Default port:** `8000`

---

### `vllm`

vLLM OpenAI-compatible inference server.

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `model` | string | `"facebook/opt-125m"` | Model to serve |
| `tensor_parallel_size` | int | `1` | Number of GPUs for parallelism |

**Default image:** `vllm/vllm-openai:latest`  
**Default port:** `8000`

---

### `ollama`

Ollama local LLM server.

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `model` | string | `"llama2"` | Model to pull and serve |
| `warmup_seconds` | int | `5` | Wait time before pulling model |

**Default image:** `ollama/ollama:latest`  
**Default port:** `11434`

---

### `nginx`

Nginx web server (useful for testing connectivity).

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| (none) | - | - | No settings needed |

**Default image:** `nginx:latest`  
**Default port:** `80`

---

## Supported Client Types

### `postgres_smoke`

Simple PostgreSQL connectivity test.

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `query` | string | `"SELECT version();"` | SQL query to execute |
| `warmup_delay` | int | `5` | Seconds to wait before connecting |
| `db_name` | string | `"benchmark"` | Database to connect to |

---

### `postgres_stress`

PostgreSQL stress test with inserts and selects.

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `num_inserts` | int | `10000` | Number of INSERT operations |
| `num_selects` | int | `5000` | Number of SELECT operations |
| `table_name` | string | `"stress_test"` | Table name to use |
| `warmup_delay` | int | `5` | Seconds to wait before starting |
| `db_name` | string | `"benchmark"` | Database to use |

---

### `chroma_healthcheck`

Simple ChromaDB connectivity test.

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| (none) | - | - | No settings needed |

---

### `chroma_stress`

ChromaDB vector insert and query stress test.

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `num_vectors` | int | `10000` | Number of vectors to insert |
| `dim` | int | `128` | Vector dimension |
| `num_queries` | int | `1000` | Number of similarity queries |
| `top_k` | int | `10` | Results per query |
| `warmup_delay` | int | `5` | Seconds to wait before starting |

---

### `vllm_smoke`

Simple vLLM inference test.

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `model` | string | `"facebook/opt-125m"` | Model name |
| `prompt` | string | `"Hello"` | Prompt to send |
| `max_tokens` | int | `50` | Max tokens to generate |
| `warmup_delay` | int | `5` | Seconds to wait for model load |

---

### `vllm_stress`

vLLM stress test with multiple requests.

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `model` | string | `"facebook/opt-125m"` | Model name |
| `num_requests` | int | `50` | Requests per client |
| `max_tokens` | int | `64` | Max tokens per response |
| `warmup_delay` | int | `10` | Seconds to wait for model load |

---

### `ollama_smoke`

Ollama inference test with retry logic.

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `model` | string | `"llama2"` | Model name |
| `num_requests` | int | `5` | Number of inference requests |
| `max_retries` | int | `30` | Max retries waiting for service |

---

### `nginx_healthcheck`

Simple nginx connectivity test.

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| (none) | - | - | No settings needed |

---

## Examples

### Minimal Postgres Benchmark

```yaml
configuration:
  target: "meluxina"

service:
  type: "postgres"
  name: "postgres-db"
  partition: "cpu"
  num_gpus: 0
  time_limit: "02:00:00"
  settings:
    db_name: "benchmark"

client:
  type: "postgres_smoke"
  partition: "cpu"
  num_gpus: 0
  time_limit: "00:30:00"

benchmarks:
  num_clients: 1
```

### ChromaDB Stress Test

```yaml
configuration:
  target: "meluxina"

service:
  type: "chroma"
  name: "chroma-stress"
  partition: "cpu"
  num_gpus: 0
  time_limit: "04:00:00"

client:
  type: "chroma_stress"
  partition: "cpu"
  num_gpus: 0
  time_limit: "02:00:00"
  settings:
    num_vectors: 50000
    dim: 768
    num_queries: 5000
    top_k: 10

benchmarks:
  num_clients: 4
```

### vLLM Inference Benchmark

```yaml
configuration:
  target: "meluxina"

service:
  type: "vllm"
  name: "vllm-bench"
  partition: "gpu"
  num_gpus: 1
  time_limit: "04:00:00"
  settings:
    model: "facebook/opt-125m"

client:
  type: "vllm_stress"
  partition: "cpu"
  num_gpus: 0
  time_limit: "01:00:00"
  settings:
    model: "facebook/opt-125m"
    num_requests: 100
    max_tokens: 128
    warmup_delay: 60

benchmarks:
  num_clients: 4
```

---

## Advanced: Raw Commands

If you need custom behavior not covered by the built-in types, you can specify raw commands:

```yaml
service:
  name: "custom-service"
  image: "my-custom-image:latest"
  command: "my-custom-startup-command --flag value"
  port: 9000

client:
  command: |
    echo "Running custom benchmark"
    curl $SERVICE_URL/api/test
```

The raw `command` field takes precedence over `type` if both are specified.

---

## Environment Variables Available to Clients

| Variable | Description |
|----------|-------------|
| `SERVICE_URL` | Full URL to the service (e.g., `http://node123:8000`) |
| `SERVICE_HOSTNAME` | Hostname where service is running |
| `SERVICE_PORT` | Port the service is listening on |
| `SERVICE_NAME` | Name of the service |

---

## Running a Recipe

```bash
python src/frontend.py examples/recipe_postgres.yaml
```

The framework will:
1. Deploy the service container on the cluster
2. Wait for it to start
3. Deploy the specified number of client jobs
4. Clients will connect to the service and run benchmarks

Check logs in `~/benchmark_<ID>/logs/` on the cluster.
