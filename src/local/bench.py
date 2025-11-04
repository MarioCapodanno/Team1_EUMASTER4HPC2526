#!/usr/bin/env python3
"""
Production-ready AI Benchmark Orchestrator for EU HPC Challenge
Features:
- Real-time monitoring of cluster jobs
- Optional debug output (-d flag)
- Automatic results synchronization
- Clean progress reporting
"""

import sys
import os
import argparse
import time
from bootstrap import bootstrap
from parser import parse

def parse_arguments():
    parser = argparse.ArgumentParser(description='AI Benchmark Orchestrator for HPC Clusters')
    parser.add_argument('recipe', help='Recipe YAML file')
    parser.add_argument('-d', '--debug', action='store_true', help='Enable debug output')
    parser.add_argument('--watch', action='store_true', help='Watch real-time job progress')
    return parser.parse_args()

def print_banner():
    print(r"""
    ╔═══════════════════════════════════════════════════════════════════╗
    ║                                                                   ║
    ║     _    ___   _____ _    ____ _____ ___  ____  ___ _____  __     ║
    ║    / \  |_ _| |  ___/ \  / ___|_   _/ _ \|  _ \|_ _| ____ / ___|  ║
    ║   / _ \  | |  | |_ / _ \| |     | || | | | |_) || ||  _|  \___ \  ║
    ║  / ___ \ | |  |  _/ ___ \ |___  | || |_| |  _ < | || |___  ___) | ║
    ║ /_/   \_\___|_|_|/_/___\_\____|_|_|_\___/|_| \_\___|_____||____/  ║
    ║                                                                   ║
    ║     | __ )| ____| \ | |/ ___| | | |  \/  |  / \  |  _ \| |/ /     ║
    ║     |  _ \|  _| |  \| | |   | |_| | |\/| | / _ \ | |_) | ' /      ║
    ║     | |_) | |___| |\  | |___|  _  | |  | |/ ___ \|  _ <| . \      ║
    ║     |____/|_____|_| \_|\____|_| |_|_|  |_/_/   \_\_| \_\_|\_\     ║
    ║                                                                   ║
    ║                  EUMasterHPC Challenge 2025/2026                  ║
    ║                                                                   ║
    ╚═══════════════════════════════════════════════════════════════════╝
    """)

def monitor_cluster_jobs(host, working_dir, debug=False):
    """Monitor real-time job progress on cluster"""
    try:
        from fabric import Connection
        with Connection(host) as c:
            print("\n[MONITOR] Real-time Cluster Job Status:")
            print("─" * 60)
            
            while True:
                try:
                    result = c.run(f"squeue -u $USER --format=\"%10j %9P %8T %10M %6D %20N\"", hide=True)
                    if result.stdout.strip():
                        lines = result.stdout.strip().split('\n')
                        if len(lines) > 1:  # Skip header
                            print("\r" + " " * 60, end="", flush=True)  # Clear line
                            for line in lines[1:]:  # Skip header
                                if line.strip():
                                    print(f"\r[JOB] {line.strip()}")
                    else:
                        print("\r[COMPLETE] No active jobs - Benchmark completed", flush=True)
                        break
                        
                    time.sleep(3)
                except KeyboardInterrupt:
                    print("\n[STOPPED] Monitoring stopped by user")
                    break
                except Exception as e:
                    if debug:
                        print(f"\n[WARNING] Monitor error: {e}")
                    time.sleep(5)
                    
    except ImportError:
        print("[WARNING] Fabric not available - cannot monitor cluster jobs")
    except Exception as e:
        if debug:
            print(f"[WARNING] Monitor connection error: {e}")

def sync_results(host, working_dir, debug=False):
    """Synchronize results from cluster to local with proper organization"""
    print("\n[SYNC] Synchronizing results from cluster...")
    
    try:
        from fabric import Connection
        import datetime
        
        # Create timestamped results directory
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        results_dir = f"benchmark_results_{timestamp}"
        os.makedirs(results_dir, exist_ok=True)
        
        with Connection(host) as c:
            # Check what files are available
            print(f"[SYNC] Discovering remote files in {working_dir}/server...")
            
            # First, try to find session files to determine current session
            session_files = c.run(f"find {working_dir}/server -name 'session_*.txt' 2>/dev/null || true", hide=True)
            
            if session_files.stdout.strip():
                # Get the most recent session file
                session_file_list = session_files.stdout.strip().split()
                latest_session = max(session_file_list, key=lambda x: x.split('_')[-1].replace('.txt', ''))
                print(f"[SYNC] Found session file: {os.path.basename(latest_session)}")
                
                # Read session file to get collected files list
                session_content = c.run(f"cat {latest_session}", hide=True)
                collected_files = []
                
                for line in session_content.stdout.split('\n'):
                    if line.startswith('COLLECTED_FILES:'):
                        files_str = line.replace('COLLECTED_FILES:', '')
                        collected_files = files_str.split(',')
                        break
                
                if collected_files:
                    print(f"[SYNC] Collecting {len(collected_files)} session-specific files...")
                    
                    # Try to get files from session_outputs directory first
                    session_output_files = c.run(f"find {working_dir}/server/session_outputs -type f 2>/dev/null || true", hide=True)
                    
                    if session_output_files.stdout.strip():
                        for output_file in session_output_files.stdout.strip().split():
                            filename = os.path.basename(output_file)
                            local_path = os.path.join(results_dir, "session_outputs", filename)
                            os.makedirs(os.path.dirname(local_path), exist_ok=True)
                            try:
                                c.get(output_file, local_path)
                                print(f"  [OK] session_outputs/{filename}")
                            except Exception as e:
                                print(f"  [FAIL] session_outputs/{filename}: {e}")
                    
                    # Also get the session file itself
                    try:
                        c.get(latest_session, os.path.join(results_dir, "session_info.txt"))
                        print(f"  [OK] session_info.txt")
                    except Exception as e:
                        print(f"  [FAIL] session_info.txt: {e}")
                else:
                    print("[SYNC] No collected files found in session, falling back to all files...")
                    # Fallback to original behavior
                    log_files = c.run(f"find {working_dir}/server -name '*.log' -o -name '*.out' 2>/dev/null || true", hide=True)
                    output_files = c.run(f"find {working_dir}/server/outputs -type f 2>/dev/null || true", hide=True)
                    
                    if log_files.stdout.strip():
                        print(f"[SYNC] Found log files: {len(log_files.stdout.strip().split())} files")
                        for log_file in log_files.stdout.strip().split():
                            filename = os.path.basename(log_file)
                            local_path = os.path.join(results_dir, "logs", filename)
                            os.makedirs(os.path.dirname(local_path), exist_ok=True)
                            try:
                                c.get(log_file, local_path)
                                print(f"  [OK] {filename}")
                            except Exception as e:
                                print(f"  [FAIL] {filename}: {e}")
                    
                    if output_files.stdout.strip():
                        print(f"[SYNC] Found output files: {len(output_files.stdout.strip().split())} files")
                        for output_file in output_files.stdout.strip().split():
                            filename = os.path.basename(output_file)
                            local_path = os.path.join(results_dir, "outputs", filename)
                            os.makedirs(os.path.dirname(local_path), exist_ok=True)
                            try:
                                c.get(output_file, local_path)
                                print(f"  [OK] {filename}")
                            except Exception as e:
                                print(f"  [FAIL] {filename}: {e}")
            else:
                print("[SYNC] No session files found, falling back to all output files...")
                # Fallback to original behavior
                log_files = c.run(f"find {working_dir}/server -name '*.log' -o -name '*.out' 2>/dev/null || true", hide=True)
                output_files = c.run(f"find {working_dir}/server/outputs -type f 2>/dev/null || true", hide=True)
                
                if log_files.stdout.strip():
                    print(f"[SYNC] Found log files: {len(log_files.stdout.strip().split())} files")
                    for log_file in log_files.stdout.strip().split():
                        filename = os.path.basename(log_file)
                        local_path = os.path.join(results_dir, "logs", filename)
                        os.makedirs(os.path.dirname(local_path), exist_ok=True)
                        try:
                            c.get(log_file, local_path)
                            print(f"  [OK] {filename}")
                        except Exception as e:
                            print(f"  [FAIL] {filename}: {e}")
                
                if output_files.stdout.strip():
                    print(f"[SYNC] Found output files: {len(output_files.stdout.strip().split())} files")
                    for output_file in output_files.stdout.strip().split():
                        filename = os.path.basename(output_file)
                        local_path = os.path.join(results_dir, "outputs", filename)
                        os.makedirs(os.path.dirname(local_path), exist_ok=True)
                        try:
                            c.get(output_file, local_path)
                            print(f"  [OK] {filename}")
                        except Exception as e:
                            print(f"  [FAIL] {filename}: {e}")
            
            # Copy the recipe file for reference
            try:
                c.get(f"{working_dir}/recipe.yml", os.path.join(results_dir, "recipe.yml"))
                print(f"  [OK] recipe.yml")
            except Exception as e:
                print(f"  [FAIL] recipe.yml: {e}")
        
        print(f"\n[SYNC] Results synchronized to: {results_dir}/")
        return results_dir
        
    except Exception as e:
        print(f"[ERROR] Synchronization failed: {e}")
        return None

def show_results_summary(results_dir):
    """Show a summary of benchmark results"""
    if not results_dir or not os.path.exists(results_dir):
        return
        
    print("\n[RESULTS] Benchmark Summary:")
    print("─" * 50)
    
    logs_dir = os.path.join(results_dir, "logs")
    if os.path.exists(logs_dir):
        log_files = [f for f in os.listdir(logs_dir) if f.endswith('.out')]
        print(f"[INFO] Log files: {len(log_files)}")
        
        # Extract key metrics from client logs
        client_logs = [f for f in log_files if 'client' in f]
        if client_logs:
            total_requests = 0
            total_time = 0
            
            for client_log in client_logs:
                try:
                    with open(os.path.join(logs_dir, client_log), 'r') as f:
                        content = f.read()
                        requests = content.count('Request completed in')
                        total_requests += requests
                        
                        # Extract durations
                        import re
                        durations = re.findall(r'DURATION:([\d.]+)', content)
                        for dur in durations:
                            total_time += float(dur)
                except Exception:
                    pass
            
            if total_requests > 0:
                avg_time = total_time / total_requests
                print(f"[METRICS] Total requests processed: {total_requests}")
                print(f"[METRICS] Average response time: {avg_time:.3f}s")
    
    print(f"[INFO] Full results available in: {results_dir}/")

if __name__ == "__main__":
    args = parse_arguments()
    
    print_banner()
    
    # Create local directories for results
    os.makedirs("logs", exist_ok=True)
    os.makedirs("outputs", exist_ok=True)

    print(f"\n[STEP 1] Parsing recipe file: {args.recipe}")
    try:
        recipe_obj = parse(args.recipe)
        if args.debug:
            print(f"[DEBUG] Recipe parsed: {recipe_obj}")
        else:
            print(f"[OK] Recipe parsed successfully")
            print(f"   Target: {recipe_obj['bootstrap']['host']}")
            print(f"   Model: {recipe_obj['bootstrap'].get('model', 'mistral')}")
    except Exception as e:
        print(f"[ERROR] Failed to parse recipe: {e}")
        sys.exit(1)

    print(f"\n[STEP 2] Starting benchmark orchestration...")
    bootstrap_obj = {
            "host": recipe_obj["bootstrap"]["host"],
            "working_dir": recipe_obj["bootstrap"]["working_dir"],
            "recipe_path": args.recipe,
            "debug": args.debug
            }
    
    if args.debug:
        print(f"[DEBUG] Bootstrap config: {bootstrap_obj}")

    # Start monitoring if requested
    if args.watch:
        import threading
        monitor_thread = threading.Thread(
            target=monitor_cluster_jobs, 
            args=(bootstrap_obj["host"], bootstrap_obj["working_dir"], args.debug)
        )
        monitor_thread.daemon = True
        monitor_thread.start()

    print(f"[STEP 3] Executing benchmark on cluster...")
    try:
        result = bootstrap(bootstrap_obj)
    except KeyboardInterrupt:
        print("\n[STOPPED] Benchmark interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Benchmark failed: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)
    
    # Synchronize results
    results_dir = sync_results(bootstrap_obj["host"], bootstrap_obj["working_dir"], args.debug)
    
    # Show summary
    if result:
        print("\n" + "="*60)
        print("BENCHMARK COMPLETED SUCCESSFULLY!")
        print("="*60)
        
        if results_dir:
            show_results_summary(results_dir)
    else:
        print("\n" + "="*60)
        print("BENCHMARK FAILED!")
        print("="*60)
    
    print(f"\n[COMPLETE] Benchmark orchestration completed")
