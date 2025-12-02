#!/usr/bin/env python3
"""
Health check module for the AI Factory Benchmarking Framework.

Provides health checking capabilities to verify services are responsive
before deploying clients.
"""

import time
from typing import Optional
from communicator import SSHCommunicator


def check_http_health(
    communicator: SSHCommunicator,
    url: str,
    timeout: int = 5,
    retries: int = 3,
    retry_delay: int = 5
) -> bool:
    """
    Check if an HTTP service is healthy by making a request from the cluster.
    
    Args:
        communicator: SSH communicator connected to the cluster
        url: URL to check (e.g., http://hostname:port/health)
        timeout: Request timeout in seconds
        retries: Number of retry attempts
        retry_delay: Delay between retries in seconds
        
    Returns:
        True if service is reachable, False otherwise
    """
    for attempt in range(retries):
        # Use curl from the cluster to check the service
        cmd = f"curl -s --max-time {timeout} -o /dev/null -w '%{{http_code}}' {url}"
        result = communicator.execute_command(cmd)
        
        if result.success:
            status_code = result.stdout.strip()
            # Accept 2xx and 3xx status codes as healthy
            if status_code.startswith('2') or status_code.startswith('3'):
                return True
            # Also accept if curl succeeded (some services don't return standard codes)
            if status_code == '000':
                # Try a simpler check - just see if we can connect
                simple_cmd = f"curl -s --max-time {timeout} {url} > /dev/null 2>&1 && echo OK"
                simple_result = communicator.execute_command(simple_cmd)
                if simple_result.success and 'OK' in simple_result.stdout:
                    return True
        
        if attempt < retries - 1:
            print(f"  Health check attempt {attempt + 1}/{retries} failed, retrying in {retry_delay}s...")
            time.sleep(retry_delay)
    
    return False


def check_port_open(
    communicator: SSHCommunicator,
    hostname: str,
    port: int,
    timeout: int = 5
) -> bool:
    """
    Check if a port is open on a host.
    
    Args:
        communicator: SSH communicator connected to the cluster
        hostname: Hostname to check
        port: Port number to check
        timeout: Timeout in seconds
        
    Returns:
        True if port is open, False otherwise
    """
    # Use nc (netcat) or bash /dev/tcp to check port
    cmd = f"timeout {timeout} bash -c 'echo > /dev/tcp/{hostname}/{port}' 2>/dev/null && echo OPEN"
    result = communicator.execute_command(cmd)
    
    return result.success and 'OPEN' in result.stdout


def wait_for_service_healthy(
    communicator: SSHCommunicator,
    url: str,
    max_wait: int = 120,
    check_interval: int = 10
) -> bool:
    """
    Wait for a service to become healthy.
    
    Args:
        communicator: SSH communicator connected to the cluster
        url: URL to check
        max_wait: Maximum time to wait in seconds
        check_interval: Interval between checks in seconds
        
    Returns:
        True if service became healthy, False if timeout
    """
    start_time = time.time()
    attempt = 0
    
    while time.time() - start_time < max_wait:
        attempt += 1
        elapsed = int(time.time() - start_time)
        print(f"  Health check attempt {attempt} ({elapsed}s elapsed)...")
        
        if check_http_health(communicator, url, timeout=5, retries=1, retry_delay=0):
            return True
        
        time.sleep(check_interval)
    
    return False
