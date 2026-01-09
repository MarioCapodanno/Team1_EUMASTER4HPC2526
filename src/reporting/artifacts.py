"""
Artifact management module for the AI Factory Benchmarking Framework.

This module handles the creation, writing, and reading of benchmark artifacts:
- run.json: metadata about the benchmark run
- requests.jsonl: per-request data (one JSON per line)
- summary.json: aggregated metrics from requests.jsonl
"""

import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import git


def get_git_commit() -> Optional[str]:
    """Get the current git commit hash."""
    try:
        repo = git.Repo(search_parent_directories=True)
        return repo.head.commit.hexsha
    except:
        return None


def calculate_recipe_hash(recipe_data: Dict[str, Any]) -> str:
    """Calculate SHA256 hash of recipe data."""
    recipe_str = json.dumps(recipe_data, sort_keys=True)
    return hashlib.sha256(recipe_str.encode()).hexdigest()


def write_run_json(
    benchmark_id: str,
    recipe: Dict[str, Any],
    service_info: Dict[str, Any],
    client_info: List[Dict[str, Any]],
    target: str = "meluxina",
) -> Path:
    """
    Write run.json artifact with benchmark metadata.

    Args:
        benchmark_id: Unique benchmark identifier
        recipe: The recipe dictionary (may contain dataclasses)
        service_info: Service deployment info (job_id, hostname, etc.)
        client_info: List of client deployment info
        target: Target cluster name

    Returns:
        Path to the written run.json file
    """
    results_dir = Path("results") / benchmark_id
    results_dir.mkdir(parents=True, exist_ok=True)

    # Convert dataclasses to dicts for JSON serialization
    def to_dict(obj):
        if hasattr(obj, "__dict__"):
            return {k: to_dict(v) for k, v in obj.__dict__.items()}
        elif isinstance(obj, dict):
            return {k: to_dict(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [to_dict(v) for v in obj]
        else:
            return obj

    recipe_dict = to_dict(recipe)

    run_data = {
        "benchmark_id": benchmark_id,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "ended_at": None,  # To be updated when benchmark completes
        "git_commit": get_git_commit(),
        "recipe_hash": calculate_recipe_hash(recipe_dict),
        "recipe": recipe_dict,  # Embed full recipe for reproducibility
        "target": target,
        "service": service_info,
        "clients": client_info,
        "environment": {
            "target": target,
            "framework_version": "1.0.0",  # TODO: Get from package
        },
    }

    run_file = results_dir / "run.json"
    with open(run_file, "w") as f:
        json.dump(run_data, f, indent=2)

    return run_file


def write_requests_jsonl(
    benchmark_id: str, requests_data: List[Dict[str, Any]]
) -> Path:
    """
    Write requests.jsonl artifact with per-request data.

    Args:
        benchmark_id: Unique benchmark identifier
        requests_data: List of per-request dictionaries

    Returns:
        Path to the written requests.jsonl file
    """
    results_dir = Path("results") / benchmark_id
    results_dir.mkdir(parents=True, exist_ok=True)

    requests_file = results_dir / "requests.jsonl"
    with open(requests_file, "w") as f:
        for request in requests_data:
            f.write(json.dumps(request) + "\n")

    return requests_file


def read_run_json(benchmark_id: str) -> Optional[Dict[str, Any]]:
    """
    Read run.json artifact for a benchmark.

    Args:
        benchmark_id: Unique benchmark identifier

    Returns:
        Dictionary with run data, or None if not found
    """
    run_file = Path("results") / benchmark_id / "run.json"
    if not run_file.exists():
        return None

    with open(run_file) as f:
        return json.load(f)


def read_requests_jsonl(benchmark_id: str) -> Optional[List[Dict[str, Any]]]:
    """
    Read requests.jsonl artifact for a benchmark.

    Args:
        benchmark_id: Unique benchmark identifier

    Returns:
        List of per-request dictionaries, or None if not found
    """
    results_dir = Path("results") / benchmark_id
    if not results_dir.exists():
        return None

    requests_file = results_dir / "requests.jsonl"
    candidate_files: List[Path]
    if requests_file.exists():
        candidate_files = [requests_file]
    else:
        candidate_files = sorted(results_dir.glob("requests_*.jsonl"))
        if not candidate_files:
            candidate_files = sorted(results_dir.glob("requests*.jsonl"))

    if not candidate_files:
        return None

    requests: List[Dict[str, Any]] = []
    for file_path in candidate_files:
        with open(file_path) as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    requests.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print(
                        f"Warning: Skipping malformed JSON in {file_path.name} on line {line_num}: {e}"
                    )
                    continue

    return requests if requests else None


def read_summary_json(benchmark_id: str) -> Optional[Dict[str, Any]]:
    """
    Read summary.json artifact for a benchmark.

    Args:
        benchmark_id: Unique benchmark identifier

    Returns:
        Dictionary with summary data, or None if not found
    """
    summary_file = Path("results") / benchmark_id / "summary.json"
    if not summary_file.exists():
        return None

    with open(summary_file) as f:
        return json.load(f)


def append_request_jsonl(benchmark_id: str, request_data: Dict[str, Any]) -> None:
    """
    Append a single request to requests.jsonl.

    Args:
        benchmark_id: Unique benchmark identifier
        request_data: Single request dictionary
    """
    results_dir = Path("results") / benchmark_id
    results_dir.mkdir(parents=True, exist_ok=True)

    requests_file = results_dir / "requests.jsonl"
    with open(requests_file, "a") as f:
        f.write(json.dumps(request_data) + "\n")


def ensure_results_dir(benchmark_id: str) -> Path:
    """Ensure the results directory exists for a benchmark."""
    results_dir = Path("results") / benchmark_id
    results_dir.mkdir(parents=True, exist_ok=True)
    return results_dir


def ensure_reports_dir(benchmark_id: str) -> Path:
    """Ensure the reports directory exists for a benchmark."""
    reports_dir = Path("reports") / benchmark_id
    reports_dir.mkdir(parents=True, exist_ok=True)
    return reports_dir


def list_benchmark_artifacts(benchmark_id: str) -> Dict[str, List[Path]]:
    """List all artifacts for a benchmark."""
    artifacts = {"results": [], "reports": []}

    # List results
    results_dir = Path("results") / benchmark_id
    if results_dir.exists():
        artifacts["results"] = list(results_dir.glob("*"))

    # List reports
    reports_dir = Path("reports") / benchmark_id
    if reports_dir.exists():
        artifacts["reports"] = list(reports_dir.glob("*"))

    return artifacts
