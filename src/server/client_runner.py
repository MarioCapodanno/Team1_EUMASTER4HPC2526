#!/usr/bin/env python3

import subprocess
import time
import os

def client_runner(ip_addresses):
    print("CLIENT RUNNER")
    
    if not ip_addresses:
        print("No service IP addresses provided")
        return []
    
    service_node = ip_addresses[0]
    print(f"Starting clients for service at: {service_node}")
    
    print("Waiting for service to be ready (60 seconds)...")
    time.sleep(60)
    
    # Start load test clients
    job_ids = []
    num_clients = 2
    
    for i in range(num_clients):
        script_content = f"""#!/bin/bash -l

#SBATCH --time=00:30:00
#SBATCH --qos=default
#SBATCH --partition=gpu
#SBATCH --account=p200981
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --ntasks-per-node=1

echo "Starting load test client {i+1}..."
echo "Date: $(date)"
echo "Hostname: $(hostname -s)"
echo "Target service node: {service_node}"

# Simple load test - connect to service node
for j in {{1..10}}; do
    echo "Client {i+1} sending request $j to {service_node}..."
    echo "Request details:"
    echo "  - Model: mistral"
    echo "  - Prompt: Hello from client {i+1}, request $j"
    echo "  - Timeout: 60 seconds"
    
    curl -X POST http://{service_node}:11434/api/generate \\
        -H "Content-Type: application/json" \\
        -d '{{"model": "mistral", "prompt": "Hello from client {i+1}, request $j"}}' \\
        --max-time 60 \\
        --verbose \\
        --show-error \\
        --write-out "HTTP Status: %{{http_code}}, Time: %{{time_total}}s\\n"
    
    echo "Request $j completed"
    sleep 1
done

echo "Client {i+1} finished load test"
"""
        
        script_name = f"client_{i+1}.sh"
        with open(script_name, "w") as f:
            f.write(script_content)
        os.chmod(script_name, 0o755)
        
        try:
            result = subprocess.run(["sbatch", script_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            job_id = result.stdout.decode('utf-8').strip().split()[-1]
            job_ids.append(job_id)
            print(f"Client {i+1} started with job ID: {job_id}")
        except Exception as e:
            print(f"Failed to start client {i+1}: {e}")
    
    return job_ids
