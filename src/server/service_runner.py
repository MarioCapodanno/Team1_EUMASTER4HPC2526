#!/usr/bin/env python3

import subprocess
import os
from utils import get_job_node, wait_for_job_state, wait_for_http

def service_runner(model: str = "mistral"):
    print("SERVICE RUNNER")
    
    # Start Ollama service using bootstrap.sh
    print("Starting Ollama service...")
    script_path = "../../scripts/bootstrap.sh"
    
    if not os.path.exists(script_path):
        print(f"Error: {script_path} not found!")
        return [], []
    
    try:
        env = os.environ.copy()
        env["OLLAMA_MODEL"] = model
        result = subprocess.run(["sbatch", "--export=ALL,OLLAMA_MODEL=%s" % model, script_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        job_id = result.stdout.decode('utf-8').strip().split()[-1]
        print(f"Ollama service submitted with job ID: {job_id}")

        # Wait until the job is RUNNING
        reached, state = wait_for_job_state(job_id, {"RUNNING"}, timeout=900, poll=3)
        if not reached:
            print(f"Service job did not reach RUNNING state (last state: {state}).")
            return [], []

        # Determine the node where the service is running
        service_node = get_job_node(job_id)
        if not service_node:
            print("Could not determine service node")
            return [], [job_id]
        print(f"Service reported running on node: {service_node}")

        # Wait for Ollama HTTP endpoint to be ready on default port
        print(f"Waiting for Ollama to be ready at http://{service_node}:11434 ...")
        if not wait_for_http(service_node, port=11434, path="/api/version", timeout=900, poll=3):
            print("Service HTTP endpoint did not become ready in time.")
            return [], [job_id]

        print("Service is ready.")
        return [service_node], [job_id]
            
    except Exception as e:
        print(f"Failed to start Ollama: {e}")
        return [], []
