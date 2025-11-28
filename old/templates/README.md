# Jinja2 Templates

## Variables



| Variable | Type | Example | Description |
|----------|------|---------|-------------|
| `client_id` | int | 1 | Client identifier |
| `service_node` | str | "node001" | Target service node |
| `service_port` | int | 11434 | Service port |
| `num_requests` | int | 10 | Requests per client |
| `model` | str | "mistral" | Model name |
| `prompt_prefix` | str | "Hello from" | Prompt prefix |
| `request_timeout` | int | 60 | Request timeout (seconds) |
| `request_interval` | int | 1 | Delay between requests (seconds) |
| `slurm.*` | dict | See below | SLURM parameters |
| `load_modules` | list | ["Apptainer"] | Modules to load |

### SLURM Configuration

```python
slurm_config = {
    "time_limit": "00:30:00",      # Job time limit
    "qos": "default",               # Quality of service
    "partition": "gpu",             # Partition/queue
    "account": "p200981",           # Account/project
    "num_nodes": 1,                 # Number of nodes
    "num_tasks": 1,                 # Number of tasks
    "tasks_per_node": 1             # Tasks per node
}
```

## Examples

###  Basic Deployment

```python
from src.server.client_runner import ClientRunner

runner = ClientRunner()

# Generate script
script = runner.render_client_script(
    client_id=1,
    service_node="node001"
)

# Or submit directly
job_id = runner.submit_client_job(
    client_id=1,
    service_node="node001"
)
```

### Custom SLURM 

```python
custom_slurm = {
    "time_limit": "01:00:00",
    "partition": "gpu",
    "num_nodes": 2
}

job_id = runner.submit_client_job(
    client_id=1,
    service_node="node001",
    slurm_config=custom_slurm,
    num_requests=50
)
```

### Load Modules

```python
job_id = runner.submit_client_job(
    client_id=1,
    service_node="node001",
    load_modules=["Apptainer", "CUDA/11.8", "Python/3.10"]
)
```

### Multiple Clients

```python
from src.server.client_runner import client_runner

job_ids = client_runner(
    ip_addresses=["192.168.1.10"],  # Service node
    num_clients=5,                   # 5 client instances
    template_dir="templates"
)

print(f"Submitted {len(job_ids)} clients: {job_ids}")
```

## Generated Script Example

The template generates sbatch scripts like:

```bash
#!/bin/bash -l

#SBATCH --time=00:30:00
#SBATCH --qos=default
#SBATCH --partition=gpu
#SBATCH --account=p200981
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --ntasks-per-node=1

echo "Starting load test client 1..."
echo "Date: $(date)"
echo "Hostname: $(hostname -s)"
echo "Target service node: node001"
echo "Service port: 11434"

for j in {1..10}; do
    echo "Client 1 sending request $j to node001:11434..."
    curl -X POST http://node001:11434/api/generate \
        -H "Content-Type: application/json" \
        -d '{"model": "mistral", "prompt": "Hello from client 1, request $j"}' \
        --max-time 60 \
        --verbose \
        --show-error \
        --write-out "HTTP Status: %{http_code}, Time: %{time_total}s\n"
    
    sleep 1
done

echo "Client 1 finished load test"
```


## TODO

- Apply same pattern to `service_runner.py` and `monitor_runner.py`
- Create templates for each service type
- Add template validation and error handling

