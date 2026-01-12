#!/usr/bin/env python3
"""
Overnight Benchmark Launch Script
=================================

This script generates and launches a suite of benchmarks to gather meaningful data
on MeluXina's performance and Model serving characteristics.

Insights targeted:
1. **Network/Service Scalability**: Stress testing Redis with increasing client counts (up to 32).
2. **LLM Inference Scaling**: Analyzing latency/throughput vs Model Size (OPT family on vLLM).
3. **Model Variety**: Baseline performance for popular models (Gemma, Llama2) on Ollama.

Usage:
    python scripts/launch_overnight.py
"""

import os
import yaml
import subprocess
import time
from pathlib import Path

# Import shared configuration
from config import TARGET, ACCOUNT, generate_recipe

# Configuration
RECIPE_DIR = Path("measurements/overnight_recipes")
RECIPE_DIR.mkdir(parents=True, exist_ok=True)

APP_DEFINITIONS = [
    # -------------------------------------------------------------------------
    # 1. Redis Scalability Study
    # Insight: How does the interconnect handle concurrent connections?
    # -------------------------------------------------------------------------
    {
        "name": "redis-scale-1",
        "service": {"type": "redis", "image": "redis:alpine", "port": 6379, "partition": "cpu", "time": "00:30:00"},
        "client": {"type": "redis_stress", "partition": "cpu", "time": "00:10:00"},
        "benchmark": {"clients": 1, "metrics": ["throughput", "latency"]}
    },
    {
        "name": "redis-scale-8",
        "service": {"type": "redis", "image": "redis:alpine", "port": 6379, "partition": "cpu", "time": "00:30:00"},
        "client": {"type": "redis_stress", "partition": "cpu", "time": "00:10:00"},
        "benchmark": {"clients": 8, "metrics": ["throughput", "latency"]}
    },
    {
        "name": "redis-scale-32",
        "service": {"type": "redis", "image": "redis:alpine", "port": 6379, "partition": "cpu", "time": "00:45:00"},
        "client": {"type": "redis_stress", "partition": "cpu", "time": "00:15:00"},
        "benchmark": {"clients": 32, "metrics": ["throughput", "latency"]}
    },

    # -------------------------------------------------------------------------
    # 2. vLLM Model Size Scaling
    # Insight: Latency/Throughput trade-offs as model size increases.
    # -------------------------------------------------------------------------
    {
        "name": "vllm-opt-125m",
        "service": {
            "type": "vllm", 
            "image": "vllm/vllm-openai:latest", 
            "port": 8000, 
            "partition": "gpu", 
            "time": "01:00:00",
            "memory": "64G",
            "settings": {"model": "facebook/opt-125m", "tensor_parallel_size": 1}
        },
        "client": {
            "type": "vllm_smoke", 
            "partition": "cpu", 
            "time": "00:20:00",
            "settings": {
                "model": "facebook/opt-125m", 
                "prompt": "Write a short poem about coding.", 
                "max_tokens": 100,
                "warmup_delay": 60
            }
        },
        "benchmark": {"clients": 4, "metrics": ["latency", "throughput"]}
    },
    {
        "name": "vllm-opt-350m",
        "service": {
            "type": "vllm", 
            "image": "vllm/vllm-openai:latest", 
            "port": 8000, 
            "partition": "gpu", 
            "time": "01:00:00",
            "memory": "64G",
            "settings": {"model": "facebook/opt-350m", "tensor_parallel_size": 1}
        },
        "client": {
            "type": "vllm_smoke", 
            "partition": "cpu", 
            "time": "00:20:00",
            "settings": {
                "model": "facebook/opt-350m", 
                "prompt": "Write a short poem about AI.", 
                "max_tokens": 100,
                "warmup_delay": 60
            }
        },
        "benchmark": {"clients": 4, "metrics": ["latency", "throughput"]}
    },
    
    # -------------------------------------------------------------------------
    # 3. Ollama Model Variety
    # Insight: Baseline performance for popular open models.
    # -------------------------------------------------------------------------
    {
        "name": "ollama-gemma2-2b",
        "service": {
            "type": "ollama", 
            "image": "ollama/ollama:latest", 
            "port": 11434, 
            "partition": "gpu", 
            "time": "01:00:00",
            "settings": {"model": "gemma2:2b", "warmup_seconds": 10}
        },
        "client": {
            "type": "ollama_smoke", 
            "partition": "cpu", 
            "time": "00:20:00",
            "settings": {"model": "gemma2:2b", "num_requests": 10}
        },
        "benchmark": {"clients": 2, "metrics": ["latency"]}
    }
]

def main():
    print("===================================================")
    print("      🚀 Overnight Benchmark Launch Sequence      ")
    print("===================================================")
    print(f"Generating recipes in: {RECIPE_DIR}\n")
    
    launched_benchmarks = []
    
    for app in APP_DEFINITIONS:
        # 1. Generate Recipe
        recipe_content = generate_recipe(app)
        recipe_path = RECIPE_DIR / f"recipe_{app['name']}.yaml"
        
        with open(recipe_path, "w") as f:
            yaml.dump(recipe_content, f, sort_keys=False)
            
        print(f"[{app['name']}] Recipe generated: {recipe_path}")
        
        # 2. Launch Benchmark
        print(f"[{app['name']}] Submitting to MeluXina...")
        try:
            cmd = ["python", "src/frontend.py", str(recipe_path)]
            # Run using subprocess, capture output
            result = subprocess.run(
                cmd, 
                check=True, 
                capture_output=True, 
                text=True,
                cwd=os.getcwd()  # Ensure running from repo root
            )
            
            # Extract Benchmark ID from output (simple parsing)
            for line in result.stdout.splitlines():
                if "Benchmark ID: BM-" in line:
                    bm_id = line.split("Benchmark ID: ")[1].strip()
                    launched_benchmarks.append((app['name'], bm_id))
                    print(f"[{app['name']}] ✅ Launched successfully! ID: {bm_id}")
                    break
            else:
                 print(f"[{app['name']}] ⚠ Launched but ID not found in output.")
                 
        except subprocess.CalledProcessError as e:
            print(f"[{app['name']}] ❌ Failed to launch!")
            print(f"Error: {e.stderr}")
        
        # Small sleep between submissions to avoid overwhelming the scheduler/connection
        time.sleep(2)
        print("-" * 50)

    print("\n===================================================")
    print("           Launch Sequence Complete! 💤           ")
    print("===================================================")
    print("Summary of Launched Benchmarks:")
    for name, bm_id in launched_benchmarks:
        print(f"  * {name:<20} -> {bm_id}")
    print("\nUse the --watch or --summary commands to check progress tomorrow.")

if __name__ == "__main__":
    main()
