# examples/ - Recipe Examples

Example YAML recipes for benchmarking various services.

## Available Recipes

### Database Services
- `recipe_redis.yaml` / `recipe_redis_stress.yaml` - Redis key-value store
- `recipe_postgres.yaml` / `recipe_postgres_stress.yaml` - PostgreSQL database

### LLM Inference
- `recipe_ollama.yaml` / `recipe_ollama_gemma.yaml` - Ollama LLM server
- `recipe_vllm.yaml` / `recipe_vllm_opt350.yaml` / `recipe_vllm_stress.yaml` - vLLM inference

### Vector Databases
- `recipe_chroma.yaml` / `recipe_chroma_stress.yaml` - ChromaDB
- `recipe_qdrant.yaml` / `recipe_qdrant_stress.yaml` - Qdrant

### Object Storage
- `recipe_minio.yaml` / `recipe_minio_stress.yaml` - MinIO S3-compatible storage

## Subdirectories

| Directory | Description |
|-----------|-------------|
| `sweeps/` | Parameterized sweep recipes for scaling studies |
| `Can/`, `Giuseppe/`, `Mario/`, `Thies/` | Team member experiment directories |

## Usage

```bash
python src/frontend.py examples/recipe_redis.yaml
```
