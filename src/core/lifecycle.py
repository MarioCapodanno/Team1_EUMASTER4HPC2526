"""
Lifecycle management for benchmarks.

This module provides a single source of truth for benchmark lifecycle operations,
including completion handling, artifact collection, and report generation.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from reporting.artifacts import read_run_json


def get_benchmark_target(benchmark_id: str) -> str:
    """
    Get target cluster from run.json or default to meluxina.
    
    Args:
        benchmark_id: Unique benchmark identifier
        
    Returns:
        Target cluster name (SSH alias)
    """
    run_data = read_run_json(benchmark_id)
    return run_data.get("target", "meluxina") if run_data else "meluxina"


def is_collection_in_progress(benchmark_id: str) -> bool:
    """
    Check if artifact collection is already in progress for a benchmark.
    
    Args:
        benchmark_id: Unique benchmark identifier
        
    Returns:
        True if collection is in progress, False otherwise
    """
    lock_file = Path(f"results/{benchmark_id}/.collecting")
    return lock_file.exists()


def acquire_collection_lock(benchmark_id: str) -> bool:
    """
    Acquire a lock for artifact collection to prevent race conditions.
    
    Args:
        benchmark_id: Unique benchmark identifier
        
    Returns:
        True if lock was acquired, False if already locked
    """
    lock_file = Path(f"results/{benchmark_id}/.collecting")
    
    if lock_file.exists():
        return False
    
    try:
        lock_file.parent.mkdir(parents=True, exist_ok=True)
        lock_file.write_text(str(datetime.now()))
        return True
    except Exception:
        return False


def release_collection_lock(benchmark_id: str) -> None:
    """
    Release the collection lock for a benchmark.
    
    Args:
        benchmark_id: Unique benchmark identifier
    """
    lock_file = Path(f"results/{benchmark_id}/.collecting")
    try:
        lock_file.unlink(missing_ok=True)
    except Exception:
        pass


def handle_benchmark_completion(
    benchmark_id: str, 
    target: Optional[str] = None,
    stop_service: bool = True,
    collect_artifacts: bool = True,
    generate_report: bool = True
) -> dict:
    """
    Handle the complete post-benchmark workflow.
    
    This is the single source of truth for what happens when a benchmark completes.
    All CLI and web UI code should call this function instead of implementing
    their own completion logic.
    
    Steps:
    1. Stop service if running (optional)
    2. Collect artifacts from cluster (optional)
    3. Generate report (optional)
    
    Args:
        benchmark_id: Unique benchmark identifier
        target: SSH target for cluster (auto-resolved if None)
        stop_service: Whether to stop the service
        collect_artifacts: Whether to collect artifacts
        generate_report: Whether to generate the report
        
    Returns:
        dict with status of each step:
        {
            "stopped": bool,
            "collected": bool,
            "reported": bool,
            "errors": list[str]
        }
    """
    from core.manager import Manager
    from core.collector import collect_benchmark_artifacts
    from reporting.reporter import generate_benchmark_report
    
    # Resolve target if not provided
    if target is None:
        target = get_benchmark_target(benchmark_id)
    
    result = {
        "stopped": False,
        "collected": False,
        "reported": False,
        "errors": []
    }
    
    # Step 1: Stop service if requested
    if stop_service:
        try:
            with Manager(target=target, benchmark_id=benchmark_id) as mgr:
                mgr.stop_benchmark()
                result["stopped"] = True
        except Exception as e:
            result["errors"].append(f"Stop service failed: {e}")
    
    # Step 2: Collect artifacts if requested
    if collect_artifacts:
        # Use lock to prevent concurrent collection
        if not acquire_collection_lock(benchmark_id):
            result["errors"].append("Collection already in progress")
        else:
            try:
                if collect_benchmark_artifacts(benchmark_id, target):
                    result["collected"] = True
                else:
                    result["errors"].append("Artifact collection failed")
            except Exception as e:
                result["errors"].append(f"Collection error: {e}")
            finally:
                release_collection_lock(benchmark_id)
    
    # Step 3: Generate report if requested and collection succeeded
    if generate_report and result["collected"]:
        try:
            generate_benchmark_report(benchmark_id)
            result["reported"] = True
        except Exception as e:
            result["errors"].append(f"Report generation failed: {e}")
    
    return result


def check_benchmark_complete(benchmark_id: str, target: Optional[str] = None) -> dict:
    """
    Check if a benchmark has completed (all clients done).
    
    Args:
        benchmark_id: Unique benchmark identifier
        target: SSH target for cluster (auto-resolved if None)
        
    Returns:
        dict with completion status:
        {
            "complete": bool,
            "service_status": str,
            "clients_done": int,
            "clients_total": int,
            "error": str or None
        }
    """
    from core.manager import Manager
    
    if target is None:
        target = get_benchmark_target(benchmark_id)
    
    try:
        with Manager(target=target, benchmark_id=benchmark_id) as manager:
            status = manager.get_benchmark_status()
        
        services = status.get("services", [])
        clients = status.get("clients", [])
        
        service_status = services[0]["status"] if services else "UNKNOWN"
        
        clients_done = sum(
            1 for c in clients
            if c.get("status") in ["COMPLETED", "FAILED", "CANCELLED", "TIMEOUT"]
        )
        clients_total = len(clients)
        
        # All clients must be in terminal state
        all_done = clients_done == clients_total and clients_total > 0
        
        # Fallback for clients_total if 0 (during startup)
        if clients_total == 0:
             run_data = read_run_json(benchmark_id)
             if run_data and "clients" in run_data:
                 clients_total = len(run_data["clients"])
        
        return {
            "complete": all_done,
            "service_status": service_status,
            "clients_done": clients_done,
            "clients_total": clients_total,
            "services": services,
            "clients": clients,
            "error": None
        }
        
    except Exception as e:
        return {
            "complete": False,
            "service_status": "ERROR",
            "clients_done": 0,
            "clients_total": 0,
            "services": [],
            "clients": [],
            "error": str(e)
        }
