#!/usr/bin/env python3
"""
Benchmark Campaign Automation
=============================

Automates the execution of the scaling benchmark campaign for:
1. Redis (01_redis_scaling)
2. Ollama (02_ollama_sizing)
3. vLLM (03_vllm_scaling)
4. Postgres (04_postgres_scaling)

Generates recipes into specific directories and launches them.
"""

import os
import yaml
import subprocess
import time
import argparse
from pathlib import Path
from typing import List, Dict, Any

# Import shared configuration
from config import TARGET, ACCOUNT, generate_recipe

# Configuration
MEASUREMENTS_DIR = Path("measurements")

# Service Output Directories
DIRS = {
    "redis": MEASUREMENTS_DIR / "01_redis_scaling",
    "ollama": MEASUREMENTS_DIR / "02_ollama_sizing",
    "vllm": MEASUREMENTS_DIR / "03_vllm_scaling",
    "postgres": MEASUREMENTS_DIR / "04_postgres_scaling",
}

# Ensure directories exist
for d in DIRS.values():
    d.mkdir(parents=True, exist_ok=True)

# =============================================================================
# Scenario Definitions
# =============================================================================

def generate_redis_scenarios() -> List[Dict[str, Any]]:
    """Generate Redis scaling scenarios."""
    scenarios = []
    # 1 to 256 clients
    client_counts = [1, 2, 4, 8, 16, 32, 64, 128, 256]
    
    for clients in client_counts:
        scenarios.append({
            "name": f"redis-scale-{clients}c",
            "type": "redis",
            "service": {
                "type": "redis", "image": "redis:alpine", "port": 6379, 
                "partition": "cpu", "time": "00:20:00"
            },
            "client": {
                "type": "redis_stress", "partition": "cpu", "time": "00:10:00"
            },
            "benchmark": {
                "clients": clients, "metrics": ["throughput", "latency"]
            }
        })
    return scenarios

def generate_ollama_scenarios() -> List[Dict[str, Any]]:
    """Generate Ollama model sizing scenarios."""
    scenarios = []
    models = [
        ("small", "llama3.2:1b"),
        ("medium", "llama3.2:3b"),
        ("large", "llama3.1:8b"),
    ]
    client_counts = [1, 4, 8, 16, 32]
    
    for size_name, model_tag in models:
        for clients in client_counts:
            scenarios.append({
                "name": f"ollama-{size_name}-{clients}c",
                "type": "ollama",
                "service": {
                    "type": "ollama", "image": "ollama/ollama:latest", "port": 11434, 
                    "partition": "gpu", "time": "00:45:00",
                    "settings": {"model": model_tag, "warmup_seconds": 15}
                },
                "client": {
                    "type": "ollama_smoke", "partition": "cpu", "time": "00:20:00",
                    "settings": {"model": model_tag, "num_requests": 20}
                },
                "benchmark": {
                    "clients": clients, "metrics": ["latency", "throughput"]
                }
            })
    return scenarios

def generate_vllm_scenarios() -> List[Dict[str, Any]]:
    """Generate vLLM scaling scenarios."""
    scenarios = []
    # Use opt-125m as baseline, or larger if compatible
    model = "facebook/opt-125m"
    client_counts = [1, 4, 16, 64, 128]
    
    for clients in client_counts:
        scenarios.append({
            "name": f"vllm-opt125m-{clients}c",
            "type": "vllm",
            "service": {
                "type": "vllm", "image": "vllm/vllm-openai:latest", "port": 8000,
                "partition": "gpu", "time": "00:30:00", "memory": "64G",
                "settings": {"model": model, "tensor_parallel_size": 1}
            },
            "client": {
                "type": "vllm_smoke", "partition": "cpu", "time": "00:15:00",
                "settings": {"model": model, "prompt": "Hello AI", "max_tokens": 50}
            },
            "benchmark": {
                "clients": clients, "metrics": ["latency", "throughput"]
            }
        })
    return scenarios

def generate_postgres_scenarios() -> List[Dict[str, Any]]:
    """Generate Postgres scaling scenarios."""
    scenarios = []
    client_counts = [1, 10, 50, 100, 200]
    
    for clients in client_counts:
        scenarios.append({
            "name": f"postgres-pgbench-{clients}c",
            "type": "postgres",
            "service": {
                "type": "postgres", "image": "postgres:15-alpine", "port": 5432,
                "partition": "cpu", "time": "00:20:00",
                "settings": {"POSTGRES_PASSWORD": "benchmarkpass"}
            },
            "client": {
                "type": "pgbench", "partition": "cpu", "time": "00:10:00",
                "settings": {"transactions": 200 * clients, "threads": min(clients, 4)} 
                # Scaling txs with clients to keep duration somewhat helpful
            },
            "benchmark": {
                "clients": clients, "metrics": ["tps", "latency"]
            }
        })
    return scenarios

# =============================================================================
def launch_campaign():
    parser = argparse.ArgumentParser(description="Benchmark Campaign Automation")
    parser.add_argument("--dry-run", action="store_true", help="Generate recipes but do not submit jobs")
    parser.add_argument("--service", choices=["redis", "ollama", "vllm", "postgres"], help="Run only specific service")
    args = parser.parse_args()

    print("===================================================")
    print("       Benchmark Campaign Launch Sequence      ")
    print("===================================================")
    if args.dry_run:
        print("   [DRY RUN MODE]: Jobs will NOT be submitted.")
    
    all_scenarios = []
    
    if not args.service or args.service == "redis":
        all_scenarios.extend(generate_redis_scenarios())
    if not args.service or args.service == "ollama":
        all_scenarios.extend(generate_ollama_scenarios())
    if not args.service or args.service == "vllm":
        all_scenarios.extend(generate_vllm_scenarios())
    if not args.service or args.service == "postgres":
        all_scenarios.extend(generate_postgres_scenarios())
    
    print(f"Total Scenarios to Launch: {len(all_scenarios)}")
    
    launched_stats = {k: 0 for k in DIRS.keys()}
    
    for i, app in enumerate(all_scenarios, 1):
        print(f"[{i}/{len(all_scenarios)}] Preparing {app['name']}...")
        
        # Determine output directory
        service_type = app.get("type", "unknown")
        dest_dir = DIRS.get(service_type, MEASUREMENTS_DIR)
        
        # 1. Generate Recipe
        recipe_content = generate_recipe(app)
        recipe_path = dest_dir / f"{app['name']}.yaml"
        
        with open(recipe_path, "w") as f:
            yaml.dump(recipe_content, f, sort_keys=False)
            
        # 2. Launch (or Skip)
        if args.dry_run:
            print(f"  [Dry Run] Recipe created at {recipe_path}")
            if service_type in launched_stats:
                launched_stats[service_type] += 1
            continue

        print(f"  Submitting to MeluXina...")
        try:
            cmd = ["python3", "src/frontend.py", str(recipe_path)]
            result = subprocess.run(
                cmd, 
                check=True, 
                capture_output=True, 
                text=True,
                cwd=os.getcwd()
            )
            
            # Extract ID
            bm_id = "UNKNOWN"
            for line in result.stdout.splitlines():
                if "Benchmark ID: BM-" in line:
                    bm_id = line.split("Benchmark ID: ")[1].strip()
                    break
            
            print(f"   Launched! ID: {bm_id}")
            if service_type in launched_stats:
                launched_stats[service_type] += 1
                
        except subprocess.CalledProcessError as e:
            print(f"   Failed to launch {app['name']}")
            print(f"  Error output: {e.stderr}")
            print(f"  StdOut: {e.stdout}")
        
        # Rate limit submission
        time.sleep(2)
        print("-" * 40)

    print("\n===================================================")
    print("           Campaign Launch Complete!              ")
    print("===================================================")
    for svc, count in launched_stats.items():
        if count > 0:
            print(f"Launched {count} {svc} benchmarks")
    print("\nRun 'python3 scripts/analyze_benchmarks.py' once jobs complete.")

if __name__ == "__main__":
    launch_campaign()
