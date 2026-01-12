#!/usr/bin/env python3
"""
Test script for Month 4 services: Redis, MinIO, and Qdrant.

This script validates the new services by:
1. Testing command generation from builders
2. Validating bash syntax of generated scripts
3. Testing with local Docker containers (if Docker is available)
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from builders.command_builders import (
    build_service_command,
    build_client_command,
    get_default_image,
    get_default_port,
    validate_service_type,
    validate_client_type,
)


class TestResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = 0
        self.failed = 0
        self.errors = []

    def ok(self, msg: str):
        self.passed += 1
        print(f"  ✓ {msg}")

    def fail(self, msg: str, error: str = ""):
        self.failed += 1
        self.errors.append(f"{msg}: {error}")
        print(f"  ✗ {msg}")
        if error:
            print(f"    Error: {error}")

    def summary(self):
        status = "PASS" if self.failed == 0 else "FAIL"
        return f"{self.name}: {status} ({self.passed} passed, {self.failed} failed)"


def check_docker_available():
    """Check if Docker is available."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10
        )
        return result.returncode == 0
    except Exception:
        return False


def validate_bash_syntax(script: str) -> tuple[bool, str]:
    """Validate bash script syntax using bash -n."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
        f.write("#!/bin/bash\n")
        f.write(script)
        f.flush()
        temp_path = f.name

    try:
        result = subprocess.run(
            ["bash", "-n", temp_path],
            capture_output=True,
            text=True,
            timeout=10
        )
        os.unlink(temp_path)
        if result.returncode == 0:
            return True, ""
        return False, result.stderr
    except Exception as e:
        os.unlink(temp_path)
        return False, str(e)


def test_command_generation():
    """Test that command builders generate valid commands."""
    result = TestResult("Command Generation")
    print("\n=== Testing Command Generation ===")

    services = [
        ("redis", {"port": 6379}),
        ("minio", {"data_dir": "/data", "console_port": 9001}),
        ("qdrant", {}),
    ]

    clients = [
        ("redis_stress", {"num_requests": 100, "warmup_delay": 1}),
        ("minio_stress", {"num_objects": 10, "object_size_bytes": 1024, "warmup_delay": 1}),
        ("qdrant_stress", {"num_points": 100, "num_queries": 10, "warmup_delay": 1}),
    ]

    # Test service commands
    for svc_type, settings in services:
        try:
            cmd = build_service_command(svc_type, settings)
            if cmd and len(cmd) > 0:
                result.ok(f"{svc_type} service command generated ({len(cmd)} chars)")
            else:
                result.fail(f"{svc_type} service command", "Empty command")
        except Exception as e:
            result.fail(f"{svc_type} service command", str(e))

    # Test client commands
    for client_type, settings in clients:
        try:
            cmd = build_client_command(client_type, settings)
            if cmd and len(cmd) > 0:
                result.ok(f"{client_type} client command generated ({len(cmd)} chars)")
            else:
                result.fail(f"{client_type} client command", "Empty command")
        except Exception as e:
            result.fail(f"{client_type} client command", str(e))

    return result


def test_bash_syntax():
    """Test that generated scripts have valid bash syntax."""
    result = TestResult("Bash Syntax Validation")
    print("\n=== Testing Bash Syntax ===")

    # Generate client commands with environment variable stubs
    clients = [
        ("redis_stress", {"num_requests": 100, "warmup_delay": 1}),
        ("minio_stress", {"num_objects": 10, "object_size_bytes": 1024, "warmup_delay": 1}),
        ("qdrant_stress", {"num_points": 100, "num_queries": 10, "warmup_delay": 1}),
    ]

    env_stub = """
export SERVICE_HOSTNAME="localhost"
export SERVICE_PORT="8080"
export SERVICE_URL="http://localhost:8080"
export BENCHMARK_ID="test-001"
export BENCHMARK_OUTPUT_DIR="/tmp/benchmark"
export CLIENT_NAME="client-1"
export MINIO_ROOT_USER="minioadmin"
export MINIO_ROOT_PASSWORD="minioadmin"
"""

    for client_type, settings in clients:
        try:
            cmd = build_client_command(client_type, settings)
            full_script = env_stub + "\n" + cmd
            valid, error = validate_bash_syntax(full_script)
            if valid:
                result.ok(f"{client_type} bash syntax valid")
            else:
                result.fail(f"{client_type} bash syntax", error)
        except Exception as e:
            result.fail(f"{client_type} bash syntax", str(e))

    return result


def test_defaults():
    """Test that default images and ports are defined."""
    result = TestResult("Default Values")
    print("\n=== Testing Default Values ===")

    services = ["redis", "minio", "qdrant"]

    for svc in services:
        # Check image
        image = get_default_image(svc)
        if image:
            result.ok(f"{svc} default image: {image}")
        else:
            result.fail(f"{svc} default image", "Not defined")

        # Check port
        port = get_default_port(svc)
        if port:
            result.ok(f"{svc} default port: {port}")
        else:
            result.fail(f"{svc} default port", "Not defined")

    return result


def test_type_validation():
    """Test type validation functions."""
    result = TestResult("Type Validation")
    print("\n=== Testing Type Validation ===")

    # Valid types should not raise
    for svc in ["redis", "minio", "qdrant"]:
        try:
            validate_service_type(svc)
            result.ok(f"validate_service_type('{svc}') - accepted")
        except Exception as e:
            result.fail(f"validate_service_type('{svc}')", str(e))

    for client in ["redis_stress", "minio_stress", "qdrant_stress"]:
        try:
            validate_client_type(client)
            result.ok(f"validate_client_type('{client}') - accepted")
        except Exception as e:
            result.fail(f"validate_client_type('{client}')", str(e))

    # Invalid types should raise
    try:
        validate_service_type("invalid_service")
        result.fail("validate_service_type('invalid_service')", "Should have raised ValueError")
    except ValueError:
        result.ok("validate_service_type('invalid_service') - correctly rejected")

    try:
        validate_client_type("invalid_client")
        result.fail("validate_client_type('invalid_client')", "Should have raised ValueError")
    except ValueError:
        result.ok("validate_client_type('invalid_client') - correctly rejected")

    return result


def test_recipe_parsing():
    """Test that recipe files parse correctly."""
    result = TestResult("Recipe Parsing")
    print("\n=== Testing Recipe Parsing ===")

    from frontend import parse_recipe

    recipes = [
        "examples/recipe_redis.yaml",
        "examples/recipe_redis_stress.yaml",
        "examples/recipe_minio.yaml",
        "examples/recipe_minio_stress.yaml",
        "examples/recipe_qdrant.yaml",
        "examples/recipe_qdrant_stress.yaml",
    ]

    for recipe_path in recipes:
        full_path = Path(__file__).parent.parent / recipe_path
        if not full_path.exists():
            result.fail(f"{recipe_path}", "File not found")
            continue

        try:
            recipe = parse_recipe(full_path)
            if recipe.service.type and recipe.client.type:
                result.ok(f"{recipe_path} - service={recipe.service.type}, client={recipe.client.type}")
            else:
                result.fail(f"{recipe_path}", "Missing service or client type")
        except Exception as e:
            result.fail(f"{recipe_path}", str(e))

    return result


def run_docker_test(service_name: str, image: str, port: int, health_check: callable, timeout: int = 30):
    """Run a Docker container and check health."""
    container_name = f"test_{service_name}_{int(time.time())}"
    
    try:
        # Start container
        cmd = [
            "docker", "run", "-d",
            "--name", container_name,
            "-p", f"{port}:{port}",
        ]
        
        # Add service-specific options
        if service_name == "minio":
            cmd.extend(["-e", "MINIO_ROOT_USER=minioadmin", "-e", "MINIO_ROOT_PASSWORD=minioadmin"])
            cmd.extend([image, "server", "/data"])
        elif service_name == "redis":
            cmd.extend([image])
        elif service_name == "qdrant":
            cmd.extend([image])
        else:
            cmd.extend([image])
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return False, f"Failed to start container: {result.stderr}"
        
        # Wait for health check
        start_time = time.time()
        while time.time() - start_time < timeout:
            if health_check(port):
                return True, ""
            time.sleep(1)
        
        return False, "Health check timeout"
        
    except Exception as e:
        return False, str(e)
    finally:
        # Cleanup
        subprocess.run(["docker", "stop", container_name], capture_output=True, timeout=10)
        subprocess.run(["docker", "rm", container_name], capture_output=True, timeout=10)


def redis_health_check(port: int) -> bool:
    """Check if Redis is healthy."""
    try:
        result = subprocess.run(
            ["redis-cli", "-p", str(port), "PING"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return "PONG" in result.stdout
    except Exception:
        # Try with nc if redis-cli not available
        try:
            result = subprocess.run(
                ["bash", "-c", f"echo PING | nc localhost {port}"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return "PONG" in result.stdout
        except Exception:
            return False


def minio_health_check(port: int) -> bool:
    """Check if MinIO is healthy."""
    try:
        result = subprocess.run(
            ["curl", "-s", f"http://localhost:{port}/minio/health/live"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


def qdrant_health_check(port: int) -> bool:
    """Check if Qdrant is healthy."""
    try:
        result = subprocess.run(
            ["curl", "-s", f"http://localhost:{port}/healthz"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0 or "ok" in result.stdout.lower()
    except Exception:
        return False


def test_docker_services():
    """Test services with Docker containers."""
    result = TestResult("Docker Container Tests")
    print("\n=== Testing Docker Containers ===")

    if not check_docker_available():
        print("  ⚠ Docker not available, skipping container tests")
        return result

    services = [
        ("redis", "redis:latest", 6379, redis_health_check),
        ("minio", "minio/minio:latest", 9000, minio_health_check),
        ("qdrant", "qdrant/qdrant:latest", 6333, qdrant_health_check),
    ]

    for name, image, port, health_fn in services:
        print(f"  Testing {name}...")
        success, error = run_docker_test(name, image, port, health_fn)
        if success:
            result.ok(f"{name} container started and healthy")
        else:
            result.fail(f"{name} container test", error)

    return result


def main():
    """Run all tests."""
    print("=" * 60)
    print("Month 4 Services Validation Test")
    print("Services: Redis, MinIO, Qdrant")
    print("=" * 60)

    results = []

    # Run tests
    results.append(test_command_generation())
    results.append(test_bash_syntax())
    results.append(test_defaults())
    results.append(test_type_validation())
    results.append(test_recipe_parsing())
    results.append(test_docker_services())

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    total_passed = 0
    total_failed = 0

    for r in results:
        print(r.summary())
        total_passed += r.passed
        total_failed += r.failed

    print("-" * 60)
    print(f"TOTAL: {total_passed} passed, {total_failed} failed")

    if total_failed == 0:
        print("\n✅ ALL TESTS PASSED")
        return 0
    else:
        print("\n❌ SOME TESTS FAILED")
        for r in results:
            if r.errors:
                print(f"\nErrors in {r.name}:")
                for e in r.errors:
                    print(f"  - {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
