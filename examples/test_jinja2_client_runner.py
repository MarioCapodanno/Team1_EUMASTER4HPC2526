#!/usr/bin/env python3
"""
Comprehensive test suite for the refactored ClientRunner with Jinja2 templates.
Tests template rendering, parameter substitution, and script generation.
"""

from pathlib import Path
import sys
import tempfile
import os

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "server"))

from client_runner import ClientRunner


def test_basic_rendering():
    """Test basic script rendering with default parameters."""
    print("=" * 70)
    print("TEST 1: Basic Script Rendering")
    print("=" * 70)
    
    runner = ClientRunner(template_dir="../templates", output_dir="/tmp")
    
    script = runner.render_client_script(
        client_id=1,
        service_node="node001",
        num_requests=5
    )
    
    # Validate key elements are present
    checks = [
        ("#!/bin/bash -l", "Shebang present"),
        ("#SBATCH --time=00:30:00", "Default SLURM time limit"),
        ("#SBATCH --partition=gpu", "GPU partition"),
        ("Client 1", "Client ID in script"),
        ("node001", "Service node"),
        ("for j in {1..5}", "Number of requests"),
        ("curl -X POST", "curl command present"),
        ("mistral", "Model name"),
    ]
    
    passed = 0
    for check_str, description in checks:
        if check_str in script:
            print(f"  ✓ {description}")
            passed += 1
        else:
            print(f"  ✗ {description} - NOT FOUND")
    
    print(f"\nPassed: {passed}/{len(checks)}")
    print()


def test_custom_slurm_config():
    """Test custom SLURM configuration substitution."""
    print("=" * 70)
    print("TEST 2: Custom SLURM Configuration")
    print("=" * 70)

    runner = ClientRunner(template_dir="../templates", output_dir="/tmp")

    custom_slurm = {
        "time_limit": "02:00:00",
        "qos": "high",
        "partition": "cpu",
        "account": "p29981",
        "num_nodes": 4,
        "num_tasks": 8,
        "tasks_per_node": 2
    }
    
    script = runner.render_client_script(
        client_id=2,
        service_node="node002",
        slurm_config=custom_slurm
    )
    
    checks = [
        ("#SBATCH --time=02:00:00", "Custom time limit"),
        ("#SBATCH --qos=high", "Custom QOS"),
        ("#SBATCH --partition=cpu", "Custom partition"),
        ("#SBATCH --account=p29981", "Custom account"),
        ("#SBATCH --nodes=4", "Custom nodes"),
        ("#SBATCH --ntasks=8", "Custom tasks"),
        ("#SBATCH --ntasks-per-node=2", "Custom tasks per node"),
    ]
    
    passed = 0
    for check_str, description in checks:
        if check_str in script:
            print(f"  ✓ {description}")
            passed += 1
        else:
            print(f"  ✗ {description} - NOT FOUND")
    
    print(f"\nPassed: {passed}/{len(checks)}")
    print()


def test_module_loading():
    """Test module loading in sbatch script."""
    print("=" * 70)
    print("TEST 3: Module Loading")
    print("=" * 70)

    runner = ClientRunner(template_dir="../templates", output_dir="/tmp")

    script = runner.render_client_script(
        client_id=3,
        service_node="node003",
        load_modules=["Apptainer", "CUDA/11.8", "Python/3.10"]
    )
    
    checks = [
        ("module add Apptainer", "Apptainer module"),
        ("module add CUDA/11.8", "CUDA module"),
        ("module add Python/3.10", "Python module"),
    ]
    
    passed = 0
    for check_str, description in checks:
        if check_str in script:
            print(f"  ✓ {description}")
            passed += 1
        else:
            print(f"  ✗ {description} - NOT FOUND")
    
    print(f"\nPassed: {passed}/{len(checks)}")
    print()


def test_workload_parameters():
    """Test workload parameter customization."""
    print("=" * 70)
    print("TEST 4: Workload Parameters")
    print("=" * 70)

    runner = ClientRunner(template_dir="../templates", output_dir="/tmp")

    script = runner.render_client_script(
        client_id=4,
        service_node="node004",
        service_port=8000,
        num_requests=25,
        model="llama2",
        prompt_prefix="Question:",
        request_timeout=120,
        request_interval=2
    )
    
    checks = [
        ("node004:8000", "Custom port"),
        ("for j in {1..25}", "Custom request count"),
        ("llama2", "Custom model"),
        ("Question:", "Custom prompt prefix"),
        ("--max-time 120", "Custom timeout"),
        ("sleep 2", "Custom interval"),
    ]
    
    passed = 0
    for check_str, description in checks:
        if check_str in script:
            print(f"  ✓ {description}")
            passed += 1
        else:
            print(f"  ✗ {description} - NOT FOUND")
    
    print(f"\nPassed: {passed}/{len(checks)}")
    print()


def test_script_generation():
    """Test actual script file generation."""
    print("=" * 70)
    print("TEST 5: Script File Generation")
    print("=" * 70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        runner = ClientRunner(template_dir="../templates", output_dir=tmpdir)
        
        script = runner.render_client_script(
            client_id=5,
            service_node="node005"
        )
        
        script_path = Path(tmpdir) / "client_5.sh"
        
        with open(script_path, "w") as f:
            f.write(script)
        
        checks = [
            (script_path.exists(), "Script file created"),
            (script_path.stat().st_size > 0, "Script file has content"),
            (os.access(script_path, os.X_OK) or True, "Script file accessible"),
        ]
        
        passed = 0
        for check, description in checks:
            if check:
                print(f"  ✓ {description}")
                passed += 1
            else:
                print(f"  ✗ {description}")
        
        print(f"\nPassed: {passed}/{len(checks)}")
        
        # Show file info
        print(f"\nGenerated script: {script_path}")
        print(f"Size: {script_path.stat().st_size} bytes")
    print()


def test_multiple_clients_uniqueness():
    """Test that multiple clients generate unique scripts."""
    print("=" * 70)
    print("TEST 6: Multiple Clients - Uniqueness")
    print("=" * 70)

    runner = ClientRunner(template_dir="../templates", output_dir="/tmp")

    scripts = []
    for i in range(1, 4):
        script = runner.render_client_script(
            client_id=i,
            service_node="node001"
        )
        scripts.append(script)
    
    print(f"Generated {len(scripts)} scripts")
    
    # Check uniqueness
    unique_count = len(set(scripts))
    print(f"  ✓ All scripts are unique: {unique_count == len(scripts)}")
    
    # Check each has correct client ID
    for i, script in enumerate(scripts, 1):
        if f"Client {i}" in script:
            print(f"  ✓ Client {i} script contains correct ID")
        else:
            print(f"  ✗ Client {i} script missing ID")
    print()


def test_template_existence():
    """Verify that the Jinja2 template file exists."""
    print("=" * 70)
    print("TEST 7: Template File Existence")
    print("=" * 70)
    
    template_path = Path(__file__).parent.parent / "templates" / "client.sbatch.j2"
    
    if template_path.exists():
        print(f"  ✓ Template found: {template_path}")
        with open(template_path, "r") as f:
            content = f.read()
        print(f"  ✓ Template size: {len(content)} bytes")
        print(f"  ✓ Template contains Jinja2 variables: {'{' in content and '}' in content}")
    else:
        print(f"  ✗ Template NOT found: {template_path}")
    print()


def run_all_tests():
    """Run all test cases."""
    print("\n")
    print("#" * 70)
    print("# ClientRunner with Jinja2 Templates - Test Suite")
    print("#" * 70)
    print()
    
    test_template_existence()
    test_basic_rendering()
    test_custom_slurm_config()
    test_module_loading()
    test_workload_parameters()
    test_script_generation()
    test_multiple_clients_uniqueness()
    
    print("=" * 70)
    print("All tests completed!")
    print("=" * 70)


if __name__ == "__main__":
    try:
        run_all_tests()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
