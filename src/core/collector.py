"""
Collector module for retrieving benchmark artifacts from the cluster.

This module handles downloading JSONL files and other artifacts from
the cluster after benchmark completion.
"""

import os
from pathlib import Path
from typing import Optional

from infra.communicator import SSHCommunicator


def collect_benchmark_artifacts(benchmark_id: str, target: str = "meluxina") -> bool:
    """
    Collect artifacts from the cluster for a completed benchmark.

    This downloads:
    - requests.jsonl files from all clients
    - Any other metrics files

    Args:
        benchmark_id: Unique benchmark identifier
        target: SSH target for the cluster

    Returns:
        True if collection was successful, False otherwise
    """
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

            return True
        else:
            print("No JSONL files found on cluster")
            print(f"Checked: {metrics_dir}")
            return False

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
    # Ensure results_dir is a Path object
    results_dir = (
        Path(results_dir) if not isinstance(results_dir, Path) else results_dir
    )

    # Find all requests.jsonl files
    jsonl_files = list(results_dir.glob("requests*.jsonl"))

    if not jsonl_files:
        print("No requests.jsonl files to merge")
        return None

    # If only one file, rename it
    if len(jsonl_files) == 1:
        target = results_dir / "requests.jsonl"
        if jsonl_files[0] != target:
            jsonl_files[0].rename(target)
        print("✓ Single requests.jsonl file ready")
        return target

    # Merge multiple files
    print(f"Merging {len(jsonl_files)} JSONL files...")

    merged_file = results_dir / "requests.jsonl"
    all_lines = []

    # Read all files
    for jsonl_file in sorted(jsonl_files):
        with open(jsonl_file, "r") as f:
            lines = f.readlines()
            all_lines.extend(lines)

        # Remove individual file after merging
        if jsonl_file != merged_file:
            jsonl_file.unlink()

    # Write merged file
    with open(merged_file, "w") as f:
        f.writelines(all_lines)

    print(f"✓ Merged into {merged_file} ({len(all_lines)} lines)")
    return merged_file


def auto_collect_if_complete(benchmark_id: str, target: str = "meluxina") -> bool:
    """
    Automatically collect artifacts if benchmark is complete.

    Args:
        benchmark_id: Unique benchmark identifier
        target: SSH target for the cluster

    Returns:
        True if artifacts were collected, False otherwise
    """
    from manager import Manager

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
