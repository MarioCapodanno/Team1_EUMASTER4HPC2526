#!/usr/bin/env python3

import subprocess
import os
from utils import wait_for_jobs_completion

# TODO: decide what type of information the monitor should collect and display
# Currently the monitor is already configured to collect the following information:
# - List all running jobs
# - Wait for client jobs to finish
# - Clean up - stop all remaining jobs
# (Right now is just a placeholder to show something)

def monitor_runner(ip_addresses, client_job_ids, service_job_ids):
    """Start monitor instances"""
    print("MONITOR RUNNER")
    print(f"Monitoring services at: {ip_addresses}")
    print(f"Monitoring client job IDs: {client_job_ids}")
    print(f"Monitoring service job IDs: {service_job_ids}")
    
    # List all running jobs
    print("\nCurrent job status:")
    try:
        user = os.getenv("USER", "")
        result = subprocess.run(["squeue", "-u", user], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output = result.stdout.decode('utf-8')
        print(output)
    except Exception as e:
        print(f"Error listing jobs: {e}")
    
    # Wait for client jobs to finish. Assume job_ids includes both service and client job IDs.
    # We will wait for all non-service jobs (heuristic: any job that is not named like bootstrap.sh).
    print("\nWaiting for client jobs to finish...")
    wait_for_jobs_completion(client_job_ids, poll=10.0)
    
    # Check job status again
    print("\nJob status after waiting:")
    try:
        user = os.getenv("USER", "")
        result = subprocess.run(["squeue", "-u", user], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output = result.stdout.decode('utf-8')
        print(output)
    except Exception as e:
        print(f"Error listing jobs: {e}")
    
    # Clean up - stop all remaining jobs (best-effort)
    print("\nCleaning up - stopping remaining jobs (services)...")
    for job_id in service_job_ids:
        try:
            subprocess.run(["scancel", job_id])
            print(f"Stopped job {job_id}")
        except Exception as e:
            print(f"Failed to stop job {job_id}: {e}")
    
    print("Monitor completed!")
