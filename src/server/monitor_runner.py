#!/usr/bin/env python3

import subprocess
import time
import os

def monitor_runner(ip_addresses, job_ids):
    """Start monitor instances"""
    print("MONITOR RUNNER")
    print(f"Monitoring services at: {ip_addresses}")
    print(f"Monitoring job IDs: {job_ids}")
    
    # List all running jobs
    print("\nCurrent job status:")
    try:
        result = subprocess.run(["squeue", "-u", os.getenv("USER")], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output = result.stdout.decode('utf-8')
        print(output)
    except Exception as e:
        print(f"Error listing jobs: {e}")
    
    # Wait for clients to finish (30 seconds)
    print("\nWaiting for clients to finish (30 seconds)...")
    time.sleep(30)
    
    # Check job status again
    print("\nJob status after waiting:")
    try:
        result = subprocess.run(["squeue", "-u", os.getenv("USER")], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output = result.stdout.decode('utf-8')
        print(output)
    except Exception as e:
        print(f"Error listing jobs: {e}")
    
    # Clean up - stop all jobs
    print("\nCleaning up - stopping all jobs...")
    for job_id in job_ids:
        try:
            subprocess.run(["scancel", job_id])
            print(f"Stopped job {job_id}")
        except Exception as e:
            print(f"Failed to stop job {job_id}: {e}")
    
    print("Monitor completed!")
