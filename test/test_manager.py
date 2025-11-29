#!/usr/bin/env python3
"""
Example demonstrating the Manager class functionality.

This script shows how the Manager deploys services to the cluster,
monitors them, and persists their state.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from manager import Manager
from service import Service


def example_deploy_service():
    """Example 1: Deploy a service to the cluster."""
    print("=" * 60)
    print("Example 1: Deploy Service via Manager")
    print("=" * 60)
    
    # Configuration
    target = "meluxina"  # SSH alias from ~/.ssh/config
    benchmark_id = "test-001"
    container_image = "ollama/ollama:latest"
    
    print(f"Target: {target}")
    print(f"Benchmark ID: {benchmark_id}")
    print(f"Container Image: {container_image}\n")
    
    # Create Manager and deploy service
    with Manager(target=target, benchmark_id=benchmark_id) as manager:
        print("✓ Connected to cluster\n")
        
        # Deploy service
        service = manager.deploy_service(
            service_name="ollama-test",
            container_image=container_image,
            service_command="ollama serve",
            wait_for_start=True,
            max_wait_time=180,
            # Optional sbatch parameters
            time_limit="00:30:00",
            num_gpus=1
        )
        
        if service:
            print(f"\n{'='*60}")
            print("✓ Service deployed successfully!")
            print(f"{'='*60}")
            print(f"Name: {service.name}")
            print(f"Job ID: {service.job_id}")
            print(f"Hostname: {service.hostname}")
            print(f"Working Dir: {service.working_dir}")
            print(f"Log File: {service.log_file}")
        else:
            print("\n✗ Service deployment failed")


def example_load_service():
    """Example 2: Load an existing service from storage."""
    print("\n" + "=" * 60)
    print("Example 2: Load Service from Storage")
    print("=" * 60)
    
    benchmark_id = "test-001"
    service_name = "ollama-test"
    
    # Load service
    service = Service.load(benchmark_id, service_name)
    
    if service:
        print(f"✓ Service loaded from storage")
        print(f"  Name: {service.name}")
        print(f"  Job ID: {service.job_id}")
        print(f"  Container: {service.container_image}")
        print(f"  Hostname: {service.hostname}")
    else:
        print(f"✗ Service '{service_name}' not found for benchmark {benchmark_id}")


def example_list_services():
    """Example 3: List all services for a benchmark."""
    print("\n" + "=" * 60)
    print("Example 3: List All Services")
    print("=" * 60)
    
    benchmark_id = "test-001"
    
    # Load all services
    services = Service.load_all(benchmark_id)
    
    print(f"Found {len(services)} service(s) for benchmark {benchmark_id}:")
    for service in services:
        print(f"  - {service.name} (Job: {service.job_id})")


def example_check_job_status():
    """Example 4: Check job status via Manager."""
    print("\n" + "=" * 60)
    print("Example 4: Check Job Status")
    print("=" * 60)
    
    benchmark_id = "test-001"
    target = "meluxina"
    
    # Load service first
    service = Service.load(benchmark_id, "ollama-test")
    
    if not service or not service.job_id:
        print("No service found with job ID")
        return
    
    print(f"Checking status for job: {service.job_id}")
    
    # Check status via Manager
    with Manager(target=target, benchmark_id=benchmark_id) as manager:
        status = manager.get_job_status(service.job_id)
        print(f"✓ Job status: {status}")


def example_manager_methods():
    """Example 5: Demonstrate various Manager methods."""
    print("\n" + "=" * 60)
    print("Example 5: Manager Methods")
    print("=" * 60)
    
    target = "meluxina"
    benchmark_id = "test-002"
    
    with Manager(target=target, benchmark_id=benchmark_id) as manager:
        print("✓ Manager connected\n")
        
        # Load service from storage via Manager
        print("Loading service via Manager:")
        service = manager.load_service("ollama-test")
        if service:
            print(f"  ✓ Loaded: {service.name}")
        else:
            print(f"  - No service found")
        
        # Load all services
        print("\nLoading all services via Manager:")
        services = manager.load_all_services()
        print(f"  Found {len(services)} service(s)")


def main():
    """Run examples."""
    print("\n" + "=" * 60)
    print("Manager Class Examples")
    print("=" * 60)
    print("\nNOTE: These examples require:")
    print("  - SSH access to 'meluxina' (configured in ~/.ssh/config)")
    print("  - Valid Slurm account/project ID")
    print("  - They will submit actual jobs to the cluster!")
    print("\nComment out example_deploy_service() if you don't want to submit jobs.\n")
    
    try:
        # WARNING: This submits an actual job!
        # Comment out if you don't want to use cluster resources
        example_deploy_service()
        
        # These are safe - they just read from storage
        example_load_service()
        example_list_services()
        
        # This requires cluster connection but doesn't submit jobs
        example_check_job_status()
        
        example_manager_methods()
        
        print("\n" + "=" * 60)
        print("Examples completed!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
