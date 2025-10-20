#!/usr/bin/env python3

import subprocess
import time
from typing import Iterable, Optional, Set, Tuple


def _run(cmd: Iterable[str]) -> Tuple[int, str, str]:
    """Run a command and return (returncode, stdout, stderr)."""
    proc = subprocess.run(list(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc.returncode, proc.stdout.decode("utf-8", errors="replace"), proc.stderr.decode("utf-8", errors="replace")


def get_job_state(job_id: str) -> Optional[str]:
    """Return SLURM job state (e.g., PENDING, RUNNING, COMPLETED) or None if not found."""
    rc, out, _ = _run(["squeue", "-j", job_id, "-h", "-o", "%T"])  # %T = state
    if rc != 0:
        return None
    state = out.strip()
    return state if state else None


def get_job_node(job_id: str) -> Optional[str]:
    """Return the allocated node for a SLURM job or None if not available yet."""
    rc, out, _ = _run(["squeue", "-j", job_id, "-h", "-o", "%N"])  # %N = NodeList
    if rc != 0:
        return None
    node = out.strip()
    return node or None


def get_job_name(job_id: str) -> Optional[str]:
    """Return job name (script base name by default) or None if not found."""
    rc, out, _ = _run(["squeue", "-j", job_id, "-h", "-o", "%j"])  # %j = job name
    if rc != 0:
        return None
    name = out.strip()
    return name or None


def wait_for_job_state(job_id: str, desired_states: Set[str], timeout: float = 600.0, poll: float = 2.0) -> Tuple[bool, Optional[str]]:
    """Wait until the job reaches one of the desired states. Returns (reached, last_state)."""
    start = time.time()
    last_state = None
    while True:
        state = get_job_state(job_id)
        last_state = state
        if state in desired_states:
            return True, state
        # If job disappeared from queue and not in desired states, it's likely finished/failed
        if state is None:
            return False, last_state
        if time.time() - start > timeout:
            return False, last_state
        time.sleep(poll)


def is_http_ready(host: str, port: int = 11434, path: str = "/api/version", timeout_sec: int = 2) -> bool:
    """Return True if HTTP endpoint responds successfully within timeout."""
    url = f"http://{host}:{port}{path}"
    rc, _, _ = _run([
        "curl",
        "-sS",
        "--fail",
        "--max-time",
        str(timeout_sec),
        "-o",
        "/dev/null",
        url,
    ])
    # If curl returns non-zero, it's not ready
    if rc != 0:
        return False
    # We cannot read the http_code without capturing stdout separately here, so instead run a simpler probe
    # If curl exited 0, consider it ready.
    return True


def wait_for_http(host: str, port: int = 11434, path: str = "/api/version", timeout: float = 600.0, poll: float = 2.0) -> bool:
    """Wait until an HTTP endpoint at host:port responds. Returns True if ready within timeout."""
    start = time.time()
    while True:
        if is_http_ready(host, port=port, path=path):
            return True
        if time.time() - start > timeout:
            return False
        time.sleep(poll)


def wait_for_jobs_completion(job_ids: Iterable[str], poll: float = 5.0, timeout: Optional[float] = None) -> bool:
    """Wait until all provided job_ids are no longer present in squeue. Returns True if all finished before timeout."""
    ids = list(job_ids)
    start = time.time()
    remaining = set(ids)
    while remaining:
        # Query squeue once for all jobs of current user to minimize calls
        rc, out, _ = _run(["squeue", "-h", "-o", "%A"])  # %A = JobID
        active_ids = set(out.split()) if rc == 0 else set()
        remaining = remaining & active_ids
        if not remaining:
            return True
        if timeout is not None and time.time() - start > timeout:
            return False
        time.sleep(poll)
    # If there were no jobs to begin with, consider it completed.
    return True
