#!/usr/bin/env python3

import subprocess
import os
import glob
from utils import wait_for_jobs_completion

# TODO: decide what type of information the monitor should collect and display
# Currently the monitor is already configured to collect the following information:
# - List all running jobs
# - Wait for client jobs to finish
# - Clean up - stop all remaining jobs
# (Right now is just a placeholder to show something)

def monitor_runner(ip_addresses, client_job_ids, service_job_ids, session_file=None):
    """Start monitor instances"""
    print("MONITOR RUNNER")
    print(f"Monitoring services at: {ip_addresses}")
    print(f"Monitoring client job IDs: {client_job_ids}")
    print(f"Monitoring service job IDs: {service_job_ids}")
    
    def log_and_print(message, step_name="MONITOR"):
        """Print message to terminal and optionally log to session file"""
        if step_name == "MONITOR":
            formatted_msg = f"  [{step_name:^8}] {message}"
        elif step_name == "ERROR":
            formatted_msg = f"  ✗ {message}"
        else:
            formatted_msg = f"  {step_name}: {message}"
        print(formatted_msg, flush=True)
        
        if session_file:
            try:
                with open(session_file, "a") as f:
                    import datetime
                    log_entry = f"{step_name}: {message}" if step_name else message
                    f.write(f"{datetime.datetime.now()}: {log_entry}\n")
            except Exception:
                pass  # Don't fail if we can't write to session file
    
    # List all running jobs
    log_and_print("Current job status:")
    try:
        user = os.getenv("USER", "")
        result = subprocess.run(["squeue", "-u", user], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output = result.stdout.decode('utf-8')
        print(output)
    except Exception as e:
        print(f"Error listing jobs: {e}")
    
    # Wait for client jobs to finish with real-time updates
    log_and_print("Waiting for client jobs to finish...")
    
    import time
    all_job_ids = set(client_job_ids + service_job_ids)
    start_time = time.time()
    
    while True:
        # Check current job status
        try:
            user = os.getenv("USER", "")
            result = subprocess.run(["squeue", "-u", user, "--format=\"%10j %9P %8T %10M %6D %20N\""], 
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            output = result.stdout.decode('utf-8')
            
            # Filter to show only our jobs
            our_jobs = []
            for line in output.strip().split('\n'):
                if line.strip():
                    # Extract job ID from the line
                    parts = line.strip().split()
                    if parts and parts[0].isdigit():
                        job_id = parts[0]
                        if job_id in all_job_ids:
                            our_jobs.append(line.strip())
            
            if our_jobs:
                elapsed = int(time.time() - start_time)
                log_and_print(f"Active jobs (elapsed: {elapsed}s):")
                for job_line in our_jobs:
                    log_and_print(f"  {job_line}")
            else:
                log_and_print("All jobs completed!")
                break
                
        except Exception as e:
            log_and_print(f"Error checking job status: {e}")
        
        # Check if all client jobs are done
        client_jobs_still_running = []
        for job_id in client_job_ids:
            try:
                result = subprocess.run(["squeue", "-j", job_id, "-h", "-o", "%T"], 
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if result.returncode == 0 and result.stdout.strip():
                    client_jobs_still_running.append(job_id)
            except Exception:
                pass
        
        if not client_jobs_still_running:
            log_and_print("All client jobs completed!")
            break
        
        # Wait before next check
        time.sleep(5.0)
    
    # Check job status again
    log_and_print("Job status after waiting:")
    try:
        user = os.getenv("USER", "")
        result = subprocess.run(["squeue", "-u", user], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output = result.stdout.decode('utf-8')
        print(output)
    except Exception as e:
        print(f"Error listing jobs: {e}")
    
    # Collect output files for current session jobs
    log_and_print("Collecting output files for current session...")
    log_and_print("Scanning for output files...")
    collect_session_output_files(client_job_ids, service_job_ids, session_file)
    
    # Clean up - stop all remaining jobs (best-effort)
    log_and_print("Cleaning up - stopping remaining jobs (services)...")
    for job_id in service_job_ids:
        try:
            log_and_print(f"Attempting to stop service job {job_id}...")
            subprocess.run(["scancel", job_id])
            log_and_print(f"✓ Successfully stopped job {job_id}")
        except Exception as e:
            log_and_print(f"✗ Failed to stop job {job_id}: {e}")
    
    log_and_print("Monitor completed successfully!")


def collect_session_output_files(client_job_ids, service_job_ids, session_file=None):
    """Collect output files only for jobs in the current session"""
    all_job_ids = set(client_job_ids + service_job_ids)
    collected_files = []
    
    # Find all .out files in current directory
    out_files = glob.glob("slurm-*.out")
    
    print(f"  [MONITOR ] Found {len(out_files)} total .out files")
    print(f"  [MONITOR ] Checking {len(all_job_ids)} session jobs: {sorted(all_job_ids)}")
    
    for out_file in out_files:
        # Extract job ID from filename (slurm-12345.out -> 12345)
        try:
            job_id = out_file.replace("slurm-", "").replace(".out", "")
            if job_id in all_job_ids:
                print(f"  [MONITOR ] → Collecting {out_file} (job {job_id})")
                collected_files.append(out_file)
                # Move to session-specific directory
                session_dir = "session_outputs"
                os.makedirs(session_dir, exist_ok=True)
                import shutil
                shutil.move(out_file, os.path.join(session_dir, out_file))
                print(f"  [MONITOR ] ✓ Moved to session_outputs/")
            # Skip silently - don't print skipping messages
        except Exception as e:
            print(f"  [MONITOR ] ✗ Error processing {out_file}: {e}")
    
    # Also collect any files in outputs/ directory created by this session
    if os.path.exists("outputs"):
        output_files = glob.glob("outputs/*")
        print(f"  [MONITOR ] Found {len(output_files)} files in outputs/ directory")
        session_dir = "session_outputs"
        os.makedirs(session_dir, exist_ok=True)
        
        for output_file in output_files:
            try:
                filename = os.path.basename(output_file)
                print(f"  [MONITOR ] → Collecting {filename}")
                import shutil
                shutil.move(output_file, os.path.join(session_dir, filename))
                print(f"  [MONITOR ] ✓ Moved to session_outputs/")
                collected_files.append(filename)
            except Exception as e:
                print(f"  [MONITOR ] ✗ Error processing {output_file}: {e}")
    
    # Store list of collected files in session file
    if session_file and collected_files:
        try:
            with open(session_file, "a") as f:
                import datetime
                f.write(f"COLLECTED_FILES:{','.join(collected_files)}\n")
        except Exception:
            pass
    
    print(f"  [MONITOR ] ✓ Session output collection completed. Files collected: {len(collected_files)}")
