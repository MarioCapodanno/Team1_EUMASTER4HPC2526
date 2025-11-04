#!/usr/bin/env python3

import sys
import os
import subprocess
import datetime
from io import StringIO

# Add local directory to path to import parser
current_dir = os.path.dirname(os.path.abspath(__file__))
local_dir = os.path.join(current_dir, '..', 'local')
sys.path.insert(0, local_dir)
from parser import parse
from service_runner import service_runner
from client_runner import client_runner
from monitor_runner import monitor_runner

# Use recipe.yml from current directory (on cluster) or local folder (for local testing)
if os.path.exists("recipe.yml"):
    recipe_path = "recipe.yml"
else:
    # Fallback for local testing
    local_dir = os.path.join(current_dir, '..', 'local')
    recipe_path = os.path.join(local_dir, 'recipe.yml')

if __name__ == "__main__":
    # Create organized directory structure
    os.makedirs("logs", exist_ok=True)
    os.makedirs("scripts", exist_ok=True)
    os.makedirs("outputs", exist_ok=True)
    
    # Generate session ID for tracking current run
    session_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"Session ID: {session_id}")
    
    # Create session file to track job IDs
    session_file = f"session_{session_id}.txt"
    with open(session_file, "w") as f:
        f.write(f"Session started: {datetime.datetime.now()}\n")
    
    def log_and_print(message, step_name=""):
        """Print message to terminal and log to session file"""
        if step_name:
            # Create clean, formatted output with ASCII separators
            if step_name.startswith("STEP"):
                separator = "═══════════════════════════════════════════════════════════════"
                print(separator, flush=True)
                print(f"  {step_name}: {message}", flush=True)
                print(separator, flush=True)
            elif step_name in ["SERVICE", "CLIENT", "MONITOR"]:
                formatted_msg = f"  [{step_name:^8}] {message}"
                print(formatted_msg, flush=True)
            elif step_name == "ERROR":
                formatted_msg = f"  ✗ {message}"
                print(formatted_msg, flush=True)
            else:
                formatted_msg = f"  {step_name}: {message}"
                print(formatted_msg, flush=True)
        else:
            formatted_msg = f"  {message}"
            print(formatted_msg, flush=True)
        
        # Log to session file (without formatting)
        log_entry = f"{step_name}: {message}" if step_name else message
        with open(session_file, "a") as f:
            f.write(f"{datetime.datetime.now()}: {log_entry}\n")
    
    # REQUIREMENTS:
    #  PRIMARY THING TO DO:
    #  1. Parse recipe.yml
    log_and_print("Step 1: Parsing recipe.yml...", "STEP 1")
    log_and_print(f"Using recipe from: {recipe_path}")
    
    if not os.path.exists(recipe_path):
        log_and_print(f"Error: {recipe_path} not found!")
        log_and_print("Make sure the local folder structure is correct")
        # TODO: report this to the user
        sys.exit(1)
    
    try:
        recipe = parse(recipe_path)
        log_and_print(f" Recipe parsed successfully: {recipe}")
    except Exception as e:
        log_and_print(f"Error: Failed to parse recipe: {e}")
        # TODO: report this to the user
        sys.exit(1)
    
    #  1. Start one or more service instances on compute nodes
    #      (The ones specified in the recipe.yml)
    #    1. Waits for the services to actually start
    #    1. Gather ip addresses of the services
    #    1. Gather jobids of the services
    log_and_print("Step 2: Starting service instances...", "STEP 2")
    model = (recipe.get("bootstrap") or {}).get("model", "mistral")
    
    # Redirect service_runner output to our log_and_print function
    import sys
    from io import StringIO
    old_stdout = sys.stdout
    sys.stdout = captured_output = StringIO()
    
    try:
        ip_addresses, job_ids = service_runner(model=model)
        service_output = captured_output.getvalue()
        sys.stdout = old_stdout
        
        # Print all service_runner output through our logging system in real-time
        if service_output.strip():
            for line in service_output.strip().split('\n'):
                if line.strip():
                    log_and_print(line.strip(), "SERVICE")
        else:
            log_and_print("Service runner completed without output", "SERVICE")
    except Exception as e:
        sys.stdout = old_stdout
        log_and_print(f"Error in service_runner: {e}", "ERROR")
        ip_addresses, job_ids = [], []
    
    if not ip_addresses:
        log_and_print("Failed to start services. Exiting.")
        # TODO: report this to the user
        sys.exit(1)
    
    log_and_print(f"Services started on nodes: {ip_addresses}")
    log_and_print(f"Service job IDs: {job_ids}")
    
    # Store service job IDs in session file
    with open(session_file, "a") as f:
        f.write(f"SERVICE_JOB_IDS:{','.join(job_ids)}\n")

    #  1. Start one or more client instances on compute nodes
    #    1. Waits for the clients to actually start
    #    1. Send ip addresses to these clients
    log_and_print("Step 3: Starting client instances...", "STEP 3")
    # TODO: decide the recipe.yaml format for the benchmark and test it.
    
    # Redirect client_runner output to our log_and_print function
    old_stdout = sys.stdout
    sys.stdout = captured_output = StringIO()
    
    try:
        client_job_ids = client_runner(ip_addresses, template_dir="templates", model=model)
        client_output = captured_output.getvalue()
        sys.stdout = old_stdout
        
        # Print all client_runner output through our logging system in real-time
        if client_output.strip():
            for line in client_output.strip().split('\n'):
                if line.strip():
                    log_and_print(line.strip(), "CLIENT")
        else:
            log_and_print("Client runner completed without output", "CLIENT")
    except Exception as e:
        sys.stdout = old_stdout
        log_and_print(f"Error in client_runner: {e}", "ERROR")
        client_job_ids = []
    
    if not client_job_ids:
        log_and_print("Failed to start clients. Cleaning up services and exiting.")
        # Best-effort cleanup of services if clients can't start
        try:
            import subprocess
            for jid in job_ids:
                subprocess.run(["scancel", jid])
                log_and_print(f"Stopped service job {jid}")
        except Exception as e:
            log_and_print(f"Warning: Failed to cancel some service jobs: {e}")
        sys.exit(1)
    
    log_and_print(f"Client job IDs: {client_job_ids}")
    
    # Store client job IDs in session file
    with open(session_file, "a") as f:
        f.write(f"CLIENT_JOB_IDS:{','.join(client_job_ids)}\n")

    #  1. Start one or more monitor instances on compute nodes
    #    1. Waits for the monitors to actually start
    #    1. Send ip addresses to these monitors
    log_and_print("Step 4: Starting monitor instances...", "STEP 4")
    
    # Redirect monitor_runner output to our log_and_print function
    old_stdout = sys.stdout
    sys.stdout = captured_output = StringIO()
    
    try:
        monitor_runner(ip_addresses, client_job_ids, job_ids, session_file=session_file)
        monitor_output = captured_output.getvalue()
        sys.stdout = old_stdout
        
        # Print all monitor_runner output through our logging system in real-time
        if monitor_output.strip():
            for line in monitor_output.strip().split('\n'):
                if line.strip():
                    log_and_print(line.strip(), "MONITOR")
        else:
            log_and_print("Monitor runner completed without output", "MONITOR")
    except Exception as e:
        sys.stdout = old_stdout
        log_and_print(f"Error in monitor_runner: {e}", "ERROR")

    #  SECONDARY THINGS:
    #  1. List currently active services
    #  1. Stop running services
    log_and_print("Step 5: Final status...", "STEP 5")
    log_and_print("All jobs have been stopped and cleaned up.")
    
    # Mark session as completed
    with open(session_file, "a") as f:
        f.write(f"Session completed: {datetime.datetime.now()}\n")
