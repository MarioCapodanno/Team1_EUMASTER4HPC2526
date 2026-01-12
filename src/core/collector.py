"""
Collector module for retrieving benchmark artifacts from the cluster.

This module handles downloading JSONL files and other artifacts from
the cluster after benchmark completion.
"""

import os
from pathlib import Path
from typing import Optional

from infra.communicator import SSHCommunicator


def collect_benchmark_artifacts(benchmark_id: str, target: Optional[str] = None) -> bool:
    """
    Collect artifacts from the cluster for a completed benchmark.

    This downloads:
    - requests.jsonl files from all clients
    - Log files from services and clients
    - Updates client hostname information

    Args:
        benchmark_id: Unique benchmark identifier
        target: SSH target for the cluster (auto-resolved if None)

    Returns:
        True if collection was successful, False otherwise
    """
    # Resolve target if not provided
    if target is None:
        from core.lifecycle import get_benchmark_target
        target = get_benchmark_target(benchmark_id)
    
    print(f"Collecting artifacts for benchmark {benchmark_id}...")

    # Connect to cluster
    communicator = SSHCommunicator(target=target)
    if not communicator.connect():
        print(f"Error: Failed to connect to {target}")
        return False

    try:
        # Get working directory
        working_dir = f"~/benchmark_{benchmark_id}"

        # Resolve absolute path
        result = communicator.execute_command("echo $HOME")
        if not result.success:
            print("Error: Could not determine home directory")
            return False

        home_dir = result.stdout.strip()
        abs_working_dir = working_dir.replace("~", home_dir)

        # Create local results directory
        local_results_dir = Path("results") / benchmark_id
        local_results_dir.mkdir(parents=True, exist_ok=True)

        # Check if metrics directory exists on cluster
        metrics_dir = f"{abs_working_dir}/metrics"
        result = communicator.execute_command(
            f"ls {metrics_dir}/*.jsonl 2>/dev/null || echo 'NO_FILES'"
        )

        if result.success and "NO_FILES" not in result.stdout:
            # Download all JSONL files
            jsonl_files = [
                f.strip() for f in result.stdout.strip().split("\n") if f.strip()
            ]

            print(f"Found {len(jsonl_files)} JSONL file(s)")

            for remote_file in jsonl_files:
                filename = os.path.basename(remote_file)
                local_file = local_results_dir / filename

                print(f"  Downloading {filename}...")
                if communicator.download_file(remote_file, local_file):
                    print(f"    ✓ Downloaded to {local_file}")
                else:
                    print(f"    ✗ Failed to download {filename}")

            # Merge all requests.jsonl files into one
            merge_requests_jsonl(benchmark_id, local_results_dir)

        else:
            print("No JSONL files found on cluster")
            print(f"Checked: {metrics_dir}")
        
        # Download logs from cluster
        download_logs(benchmark_id, abs_working_dir, local_results_dir, communicator)
        
        # Update client hostnames from hostname files on cluster
        update_client_hostnames(benchmark_id, abs_working_dir, communicator)
        
        return True

    finally:
        communicator.disconnect()


def merge_requests_jsonl(benchmark_id: str, results_dir) -> Optional[Path]:
    """
    Merge multiple requests.jsonl files from different clients into one.

    Args:
        benchmark_id: Unique benchmark identifier
        results_dir: Local results directory (Path or str)

    Returns:
        Path to merged requests.jsonl file, or None if no files found
    """
    import json
    
    # Ensure results_dir is a Path object
    results_dir = (
        Path(results_dir) if not isinstance(results_dir, Path) else results_dir
    )

    merged_file = results_dir / "requests.jsonl"
    
    # Clear existing merged file to avoid contamination from old data
    if merged_file.exists():
        merged_file.unlink()

    # Find all requests_*.jsonl files (client-specific files)
    jsonl_files = list(results_dir.glob("requests_*.jsonl"))

    if not jsonl_files:
        print("No requests.jsonl files to merge")
        return None

    # Merge files
    print(f"Merging {len(jsonl_files)} JSONL files...")

    all_lines = []

    # Read all files and filter by benchmark_id
    for jsonl_file in sorted(jsonl_files):
        with open(jsonl_file, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                # Validate and filter by benchmark_id
                try:
                    data = json.loads(line)
                    # Only include lines that match this benchmark_id
                    line_bid = data.get("benchmark_id")
                    if line_bid and line_bid != benchmark_id:
                        continue  # Skip lines from other benchmarks
                    all_lines.append(line + "\n")
                except json.JSONDecodeError:
                    # Keep malformed lines but warn
                    all_lines.append(line + "\n")

        # Remove individual file after merging
        jsonl_file.unlink()

    # Write merged file
    with open(merged_file, "w") as f:
        f.writelines(all_lines)

    print(f"✓ Merged into {merged_file} ({len(all_lines)} lines)")
    return merged_file


def download_logs(benchmark_id: str, abs_working_dir: str, local_results_dir: Path, communicator) -> bool:
    """
    Download log files from the cluster for a benchmark.

    Args:
        benchmark_id: Unique benchmark identifier
        abs_working_dir: Absolute working directory on cluster
        local_results_dir: Local results directory
        communicator: Connected SSHCommunicator

    Returns:
        True if logs were downloaded successfully
    """
    logs_dir = f"{abs_working_dir}/logs"
    local_logs_dir = local_results_dir / "logs"
    local_logs_dir.mkdir(parents=True, exist_ok=True)

    # Find all log files on cluster
    result = communicator.execute_command(
        f"ls {logs_dir}/*.out {logs_dir}/*.err 2>/dev/null || echo 'NO_FILES'"
    )

    if result.success and "NO_FILES" not in result.stdout:
        log_files = [
            f.strip() for f in result.stdout.strip().split("\n") if f.strip()
        ]
        print(f"Found {len(log_files)} log file(s)")

        for remote_file in log_files:
            filename = os.path.basename(remote_file)
            # Simplify log filename for easier viewing (remove job ID from filename)
            # e.g., redis-cache_3940121.out -> redis-cache_service.out
            if "_" in filename:
                parts = filename.rsplit("_", 1)
                name_part = parts[0]
                ext = "." + filename.split(".")[-1] if "." in filename else ""
                # Determine if this is a service or client log
                if "client" in name_part.lower():
                    simple_name = f"{name_part}_client{ext}"
                else:
                    simple_name = f"{name_part}_service{ext}"
            else:
                simple_name = filename

            local_file = local_logs_dir / simple_name

            print(f"  Downloading {filename} -> {simple_name}...")
            if communicator.download_file(remote_file, local_file):
                print(f"    ✓ Downloaded to {local_file}")
            else:
                print(f"    ✗ Failed to download {filename}")

        return True
    else:
        print("No log files found on cluster")
        return False


def update_client_hostnames(benchmark_id: str, abs_working_dir: str, communicator) -> None:
    """
    Update client hostnames in storage by reading hostname files from cluster.
    
    Also updates run.json if it exists.

    Args:
        benchmark_id: Unique benchmark identifier
        abs_working_dir: Absolute working directory on cluster
        communicator: Connected SSHCommunicator
    """
    import json
    from infra.storage import get_storage_manager
    
    storage = get_storage_manager()
    
    # Load all clients from storage
    clients = storage.load_all_entities(benchmark_id, "client")
    
    updated_clients = []
    for client in clients:
        client_name = client.get("name") or client.get("_id")
        if not client_name:
            continue
            
        # Try to read hostname file from cluster
        hostname_file = f"{abs_working_dir}/{client_name}.hostname"
        result = communicator.execute_command(f"cat {hostname_file} 2>/dev/null")
        
        if result.success and result.stdout.strip():
            hostname = result.stdout.strip()
            # Update client hostname in storage
            client["hostname"] = hostname
            client["node_name"] = hostname
            storage.backend.save(benchmark_id, "client", client_name, client)
            updated_clients.append((client_name, hostname))
            print(f"  ✓ Client {client_name} running on: {hostname}")
    
    # Also update run.json if it exists
    if updated_clients:
        run_json_path = Path("results") / benchmark_id / "run.json"
        if run_json_path.exists():
            try:
                with open(run_json_path, "r") as f:
                    run_data = json.load(f)
                
                # Update client hostnames in run.json
                for client_info in run_data.get("clients", []):
                    for client_name, hostname in updated_clients:
                        if client_info.get("name") == client_name:
                            client_info["hostname"] = hostname
                            break
                
                with open(run_json_path, "w") as f:
                    json.dump(run_data, f, indent=2, default=str)
                    
            except (json.JSONDecodeError, IOError) as e:
                print(f"  Warning: Could not update run.json: {e}")


def auto_collect_if_complete(benchmark_id: str, target: Optional[str] = None) -> bool:
    """
    Automatically collect artifacts if benchmark is complete.

    Args:
        benchmark_id: Unique benchmark identifier
        target: SSH target for the cluster (auto-resolved if None)

    Returns:
        True if artifacts were collected, False otherwise
    """
    from core.manager import Manager
    from core.lifecycle import get_benchmark_target
    
    # Resolve target if not provided
    if target is None:
        target = get_benchmark_target(benchmark_id)

    # Check if benchmark is complete
    with Manager(target=target, benchmark_id=benchmark_id) as manager:
        status = manager.get_benchmark_status()

        # Check if all clients are done
        all_done = all(
            c["status"] in ["COMPLETED", "FAILED", "CANCELLED", "TIMEOUT"]
            for c in status["clients"]
        )

        if not all_done:
            print("Benchmark not yet complete")
            return False

        print("Benchmark complete, collecting artifacts...")
        return collect_benchmark_artifacts(benchmark_id, target)
