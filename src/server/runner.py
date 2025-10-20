#!/usr/bin/env python3

import sys
import os

# Add local directory to path to import parser
current_dir = os.path.dirname(os.path.abspath(__file__))
local_dir = os.path.join(current_dir, '..', 'local')
sys.path.insert(0, local_dir)
from parser import parse
from service_runner import service_runner
from client_runner import client_runner
from monitor_runner import monitor_runner

# Use recipe.yml from local folder
recipe_path = os.path.join(local_dir, 'recipe.yml')

if __name__ == "__main__":
    # REQUIREMENTS:
    #  PRIMARY THING TO DO:
    #  1. Parse recipe.yml
    print("Step 1: Parsing recipe.yml...")
    print(f"Using recipe from: {recipe_path}")
    
    if not os.path.exists(recipe_path):
        print(f"Error: {recipe_path} not found!")
        print("Make sure the local folder structure is correct")
        sys.exit(1)
    
    try:
        recipe = parse(recipe_path)
        print(f" Recipe parsed successfully: {recipe}")
    except Exception as e:
        print(f"Error: Failed to parse recipe: {e}")
        sys.exit(1)
    
    #  1. Start one or more service instances on compute nodes
    #      (The ones specified in the recipe.yml)
    #    1. Waits for the services to actually start
    #    1. Gather ip addresses of the services
    #    1. Gather jobids of the services
    print("\nStep 2: Starting service instances...")
    model = (recipe.get("bootstrap") or {}).get("model", "mistral")
    ip_addresses, job_ids = service_runner(model=model)
    
    if not ip_addresses:
        print("Failed to start services. Exiting.")
        sys.exit(1)
    
    print(f"Services started on nodes: {ip_addresses}")
    print(f"Service job IDs: {job_ids}")

    #  1. Start one or more client instances on compute nodes
    #    1. Waits for the clients to actually start
    #    1. Send ip addresses to these clients
    print("\nStep 3: Starting client instances...")
    client_job_ids = client_runner(ip_addresses, model=model)
    
    if not client_job_ids:
        print("Failed to start clients. Cleaning up services and exiting.")
        # Best-effort cleanup of services if clients can't start
        try:
            import subprocess
            for jid in job_ids:
                subprocess.run(["scancel", jid])
                print(f"Stopped service job {jid}")
        except Exception as e:
            print(f"Warning: Failed to cancel some service jobs: {e}")
        sys.exit(1)
    
    print(f"Client job IDs: {client_job_ids}")

    #  1. Start one or more monitor instances on compute nodes
    #    1. Waits for the monitors to actually start
    #    1. Send ip addresses to these monitors
    print("\nStep 4: Starting monitor instances...")
    monitor_runner(ip_addresses, client_job_ids, job_ids)

    #  SECONDARY THINGS:
    #  1. List currently active services
    #  1. Stop running services
    print("\nStep 5: Final status...")
    print("All jobs have been stopped and cleaned up.")
