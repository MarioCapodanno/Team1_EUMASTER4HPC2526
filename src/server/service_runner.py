#!/usr/bin/env python3

import subprocess
import time
import os

def service_runner():
    print("SERVICE RUNNER")
    
    # Start Ollama service using bootstrap.sh
    print("Starting Ollama service...")
    script_path = "../../scripts/bootstrap.sh"
    
    if not os.path.exists(script_path):
        print(f"Error: {script_path} not found!")
        return [], []
    
    try:
        result = subprocess.run(["sbatch", script_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        job_id = result.stdout.decode('utf-8').strip().split()[-1]
        print(f"Ollama service started with job ID: {job_id}")
        
        time.sleep(5)  # Wait for job to start
        try:
            result = subprocess.run(["squeue", "-j", job_id, "--format=%N", "--noheader"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            service_node = result.stdout.decode('utf-8').strip()
            print(f"Service running on node: {service_node}")
            return [service_node], [job_id]
        except:
            print("Could not determine service node")
            return [None], [job_id]
            
    except Exception as e:
        print(f"Failed to start Ollama: {e}")
        return [], []
