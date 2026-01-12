"""
Frontend module for the AI Factory Benchmarking Framework.

This module handles command-line argument parsing and recipe YAML configuration loading.
It produces a structured Python object containing all benchmark configuration information.
Now includes an interactive CLI UI for managing benchmarks.
"""

import argparse
import glob
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from builders.command_builders import (
    build_client_command,
    build_service_command,
    get_default_env,
    get_default_image,
    get_default_port,
    validate_client_type,
    validate_service_type,
    validate_settings,
)
from infra.health import check_http_health, wait_for_service_healthy
from core.manager import Manager
from monitoring.monitor import (
    BenchmarkMetrics,
    MetricsCollector,
    format_metrics_report,
)
from infra.storage import (
    format_benchmark_summary,
    format_benchmark_table,
    get_benchmark_summary,
    list_all_benchmarks,
)
from reporting.artifacts import write_run_json, ensure_results_dir, read_run_json, read_summary_json
from core.aggregator import aggregate_benchmark, compare_summaries
from reporting.reporter import generate_benchmark_report
from core.collector import collect_benchmark_artifacts, auto_collect_if_complete
from core.lifecycle import get_benchmark_target, handle_benchmark_completion
from monitoring.manager import MonitorManager


@dataclass
class Configuration:
    """Configuration section of the recipe."""

    target: str = ""  # SSH alias or hostname (e.g., "meluxina")


@dataclass
class ServiceConfig:
    """Service configuration section of the recipe."""

    name: Optional[str] = None  # Service name
    type: Optional[str] = None  # Service type (e.g., "postgres", "chroma", "vllm")
    image: Optional[str] = None  # Container image
    command: Optional[str] = None  # Command to run in container
    settings: Optional[Dict[str, Any]] = None  # Type-specific settings
    partition: str = "gpu"  # Slurm partition
    num_gpus: int = 1  # Number of GPUs
    time_limit: str = "01:00:00"  # Job time limit
    account: Optional[str] = None  # Slurm account (optional)
    port: Optional[int] = None  # Service port (for SERVICE_URL construction)
    env: Optional[Dict[str, str]] = None  # Environment variables for container
    
    # Advanced Hardware Config
    gpus_per_node: Optional[int] = None  # Explicit GPUs per node
    cpus_per_task: Optional[int] = None  # CPUs per task
    memory: Optional[str] = None  # Explicit memory request (e.g. "64G")
    constraints: Optional[str] = None  # Node features (e.g. "a100")
    exclude_nodes: Optional[str] = None  # Nodes to exclude
    
    # Advanced Runtime Config
    volumes: List[str] = field(default_factory=list)  # Bind mounts
    modules: List[str] = field(default_factory=list)  # Modules to load
    pre_run_commands: List[str] = field(default_factory=list)  # Setup commands


@dataclass
class ClientConfig:
    """Client configuration section of the recipe."""

    type: Optional[str] = None  # Client type (e.g., "postgres_smoke", "chroma_stress")
    command: Optional[str] = None  # Benchmark command to run
    settings: Optional[Dict[str, Any]] = None  # Type-specific settings
    partition: str = "cpu"  # Slurm partition
    num_gpus: int = 0  # Number of GPUs
    time_limit: str = "01:00:00"  # Job time limit
    account: Optional[str] = None  # Slurm account (optional)


@dataclass
class BenchmarkConfig:
    """Benchmark configuration section of the recipe."""

    num_clients: Optional[int] = None  # Number of clients to simulate
    metrics: list[str] = field(default_factory=list)  # List of metrics to collect


@dataclass
class Recipe:
    """
    Main recipe object containing all benchmark configuration.

    This object represents the complete parsed recipe.yaml file
    and provides structured access to all configuration parameters.
    """

    configuration: Configuration = field(default_factory=Configuration)
    service: ServiceConfig = field(default_factory=ServiceConfig)
    client: ClientConfig = field(default_factory=ClientConfig)
    benchmarks: BenchmarkConfig = field(default_factory=BenchmarkConfig)
    raw_data: dict[str, Any] = field(default_factory=dict)  # Original parsed YAML data

    @classmethod
    def from_yaml(cls, yaml_data: dict[str, Any]) -> "Recipe":
        """
        Create a Recipe object from parsed YAML data.

        Args:
            yaml_data: Dictionary containing the parsed YAML content

        Returns:
            Recipe object with all configuration loaded
        """
        recipe = cls(raw_data=yaml_data)

        # Parse configuration section
        if "configuration" in yaml_data:
            config_data = yaml_data["configuration"]
            recipe.configuration = Configuration(target=config_data.get("target", ""))

        # Parse service section
        if "service" in yaml_data:
            service_data = yaml_data["service"]
            service_type = service_data.get("type")
            settings = service_data.get("settings", {})

            # Validate type and settings if specified
            if service_type:
                validate_service_type(service_type)
                validate_settings(settings, context="service")

            # Get command: use type-based builder if type is specified, else use raw command
            command = service_data.get("command")
            if service_type and not command:
                command = build_service_command(service_type, settings)

            # Get defaults based on type
            image = service_data.get("image") or (
                get_default_image(service_type) if service_type else None
            )
            port = service_data.get("port") or (
                get_default_port(service_type) if service_type else None
            )
            env = service_data.get("env") or (
                get_default_env(service_type, settings) if service_type else None
            )

            recipe.service = ServiceConfig(
                name=service_data.get("name"),
                type=service_type,
                image=image,
                command=command,
                settings=settings,
                partition=service_data.get("partition", "gpu"),
                num_gpus=service_data.get("num_gpus", 1),
                time_limit=service_data.get("time_limit", "01:00:00"),
                account=service_data.get("account"),
                port=port,
                env=env,
                # Advanced Hardware
                gpus_per_node=service_data.get("gpus_per_node"),
                cpus_per_task=service_data.get("cpus_per_task"),
                memory=service_data.get("memory"),
                constraints=service_data.get("constraints"),
                exclude_nodes=service_data.get("exclude_nodes"),
                # Advanced Runtime
                volumes=service_data.get("volumes", []),
                modules=service_data.get("modules", []),
                pre_run_commands=service_data.get("pre_run_commands", []),
            )

        # Parse client section
        if "client" in yaml_data:
            client_data = yaml_data["client"]
            client_type = client_data.get("type")
            settings = client_data.get("settings", {})

            # Validate type and settings if specified
            if client_type:
                validate_client_type(client_type)
                validate_settings(settings, context="client")

            # Get command: use type-based builder if type is specified, else use raw command
            command = client_data.get("command")
            if client_type and not command:
                command = build_client_command(client_type, settings)

            recipe.client = ClientConfig(
                type=client_type,
                command=command,
                settings=settings,
                partition=client_data.get("partition", "cpu"),
                num_gpus=client_data.get("num_gpus", 0),
                time_limit=client_data.get("time_limit", "01:00:00"),
                account=client_data.get("account"),
            )

        # Parse benchmarks section
        if "benchmarks" in yaml_data:
            bench_data = yaml_data["benchmarks"]
            recipe.benchmarks = BenchmarkConfig(
                num_clients=bench_data.get("num_clients"),
                metrics=bench_data.get("metrics") or [],
            )

        return recipe

    def __str__(self) -> str:
        """Return a human-readable string representation of the recipe."""
        return (
            f"Recipe(\n"
            f"  configuration:\n"
            f"    target: {self.configuration.target}\n"
            f"  service:\n"
            f"    name: {self.service.name}\n"
            f"    image: {self.service.image}\n"
            f"    command: {self.service.command}\n"
            f"    partition: {self.service.partition}\n"
            f"    num_gpus: {self.service.num_gpus}\n"
            f"  client:\n"
            f"    command: {self.client.command}\n"
            f"    partition: {self.client.partition}\n"
            f"    num_gpus: {self.client.num_gpus}\n"
            f"  benchmarks:\n"
            f"    num_clients: {self.benchmarks.num_clients}\n"
            f"    metrics: {self.benchmarks.metrics}\n"
            f")"
        )


def parse_recipe(path: Path) -> Recipe:
    """
    Parse and validate a recipe YAML file.

    Args:
        path: Path to the recipe.yaml file

    Returns:
        Recipe object containing all parsed configuration

    Raises:
        FileNotFoundError: If the recipe file does not exist
        yaml.YAMLError: If the file contains invalid YAML
    """
    if not path.exists():
        raise FileNotFoundError(f"Recipe file not found: {path}")

    if not path.is_file():
        raise ValueError(f"Recipe path is not a file: {path}")

    with open(path, "r") as file:
        yaml_data = yaml.safe_load(file)

    if yaml_data is None:
        yaml_data = {}

    return Recipe.from_yaml(yaml_data)


def create_argument_parser() -> argparse.ArgumentParser:
    """
    Create and configure the command-line argument parser.

    Returns:
        Configured ArgumentParser instance
    """
    parser = argparse.ArgumentParser(
        prog="benchmark-frontend",
        description="AI Factory Benchmarking Framework Frontend",
        epilog="Example: python frontend.py recipe.yaml\n         python frontend.py --ui",
    )

    parser.add_argument(
        "recipe",
        type=Path,
        nargs="?",
        help="Path to the recipe YAML configuration file",
    )

    parser.add_argument("--ui", action="store_true", help="Launch interactive UI mode")

    parser.add_argument(
        "--id",
        dest="benchmark_id",
        type=str,
        help="Benchmark ID for loading existing benchmark",
    )

    parser.add_argument(
        "--list-recipes",
        action="store_true",
        help="List all available recipes",
    )

    parser.add_argument(
        "--rerun",
        type=str,
        metavar="BENCHMARK_ID",
        help="Rerun a benchmark using its original configuration",
    )

    parser.add_argument(
        "--list",
        "--list-benchmarks",
        dest="list_benchmarks",
        action="store_true",
        help="List all benchmarks",
    )

    parser.add_argument(
        "--summary",
        type=str,
        metavar="BENCHMARK_ID",
        help="Show summary for a benchmark",
    )

    parser.add_argument(
        "--stop", type=str, metavar="BENCHMARK_ID", help="Stop all jobs for a benchmark"
    )

    parser.add_argument(
        "--logs", type=str, metavar="BENCHMARK_ID", help="Show logs for a benchmark"
    )

    parser.add_argument(
        "--watch",
        type=str,
        metavar="BENCHMARK_ID",
        help="Watch live status for a benchmark",
    )

    parser.add_argument(
        "--metrics",
        type=str,
        metavar="BENCHMARK_ID",
        help="Collect and show metrics for a benchmark",
    )

    parser.add_argument("--web", action="store_true", help="Launch web UI (Flask)")
    
    parser.add_argument(
        "--report",
        type=str,
        metavar="BENCHMARK_ID",
        help="Generate report for a benchmark"
    )
    
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("BASELINE_ID", "CURRENT_ID"),
        help="Compare two benchmark runs"
    )
    
    parser.add_argument(
        "--collect",
        type=str,
        metavar="BENCHMARK_ID",
        help="Collect artifacts from cluster for a benchmark"
    )
    
    parser.add_argument(
        "--download-logs",
        type=str,
        metavar="BENCHMARK_ID",
        help="Download all logs and artifacts for a benchmark to local machine"
    )
    
    parser.add_argument(
        "--sweep-report",
        nargs="+",
        metavar="BENCHMARK_ID",
        help="Generate sweep report with saturation analysis from multiple benchmark IDs"
    )
    
    parser.add_argument(
        "--slo",
        type=float,
        metavar="SECONDS",
        help="SLO threshold for P99 latency (used with --sweep-report)"
    )

    parser.add_argument(
        "--monitor-stack",
        choices=["start", "stop", "status"],
        help="Control the monitoring stack (Prometheus + Grafana)"
    )

    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )

    return parser


def generate_benchmark_id() -> str:
    """
    Generate a unique benchmark ID with fixed length format: BM-YYYYMMDD-NNN
    
    Format: BM-20260108-001
    - BM: Benchmark prefix
    - YYYYMMDD: Date
    - NNN: 3-digit sequence number for the day

    Returns:
        Unique benchmark ID string
    """
    from datetime import datetime
    
    # Get current date
    today = datetime.now().strftime("%Y%m%d")
    
    # Use a counter file per day
    id_file = Path(f".benchmark_id_counter_{today}")
    
    if id_file.exists():
        current_id = int(id_file.read_text().strip())
    else:
        current_id = 0
    
    new_id = current_id + 1
    id_file.write_text(str(new_id))
    
    # Format: BM-YYYYMMDD-NNN
    return f"BM-{today}-{new_id:03d}"


# =============================================================================
# INTERACTIVE UI
# =============================================================================


def clear_screen():
    """Clear the terminal screen."""
    os.system("cls" if os.name == "nt" else "clear")


def print_header():
    """Print the application header."""
    print("\n" + "=" * 60)
    print("   AI Factory Benchmarking Framework")
    print("   MeluXina Supercomputer")
    print("=" * 60 + "\n")


def print_main_menu():
    """Print the main menu options."""
    print("\nMain Menu:")
    print("-" * 30)
    print("  [1] Run a recipe")
    print("  [2] List benchmarks")
    print("  [3] Show benchmark summary")
    print("  [4] Watch benchmark status")
    print("  [5] Stop a benchmark")
    print("  [6] Show logs")
    print("  [q] Quit")
    print("-" * 30)


def get_available_recipes() -> List[Path]:
    """Find all available recipe files in examples directory."""
    examples_dir = Path("examples")
    if not examples_dir.exists():
        return []
    recipes = list(examples_dir.glob("recipe_*.yaml"))
    return sorted(recipes)


def ui_run_recipe() -> Optional[int]:
    """Interactive recipe runner. Returns benchmark ID if successful."""
    recipes = get_available_recipes()

    if not recipes:
        print("\n❌ No recipes found in examples/ directory")
        return None

    print("\nAvailable Recipes:")
    print("-" * 50)
    for i, recipe in enumerate(recipes, 1):
        # Extract a friendly name from the recipe filename
        name = recipe.stem.replace("recipe_", "").replace("_", " ").title()
        print(f"  [{i}] {name:<25} ({recipe})")
    print("  [0] Cancel")
    print("-" * 50)

    try:
        choice = input("\nSelect recipe: ").strip()
        if choice == "0" or choice.lower() == "q":
            return None

        idx = int(choice) - 1
        if 0 <= idx < len(recipes):
            recipe_path = recipes[idx]
            print(f"\n▶ Running recipe: {recipe_path}")

            # Run the benchmark and capture the ID
            result = run_benchmark_from_recipe(recipe_path)
            return result
        else:
            print("Invalid selection")
            return None
    except ValueError:
        print("Invalid input")
        return None


def ui_list_benchmarks():
    """Show list of all benchmarks."""
    print("\n")
    benchmarks = list_all_benchmarks()
    print(format_benchmark_table(benchmarks))
    print()


def ui_show_summary():
    """Show detailed summary for a benchmark."""
    bid = input("\nEnter benchmark ID: ").strip()
    if not bid:
        return

    summary = get_benchmark_summary(bid)
    if summary:
        print(format_benchmark_summary(summary))
        
        # Also show metrics if available locally
        from reporting.artifacts import read_summary_json
        try:
            metrics = read_summary_json(bid)
        except Exception:
            metrics = None
        if metrics:
            print(f"\nPerformance Metrics:")
            print(f"  Total Requests:    {metrics.get('total_requests', 0):,}")
            print(f"  Success Rate:      {metrics.get('success_rate', 0):.2f}%")
            print(f"  Throughput:        {metrics.get('requests_per_second', 0):.2f} RPS")
            print(f"  Avg Latency:       {metrics.get('latency_s', {}).get('avg', 0)*1000:.1f} ms")
            print(f"  P50 Latency:       {metrics.get('latency_s', {}).get('p50', 0)*1000:.1f} ms")
            print(f"  P95 Latency:       {metrics.get('latency_s', {}).get('p95', 0)*1000:.1f} ms")
            print(f"  P99 Latency:       {metrics.get('latency_s', {}).get('p99', 0)*1000:.1f} ms")
            print(f"  Test Duration:     {metrics.get('test_duration_s', 0):.1f} s")
            print("")
    else:
        print(f"\n❌ Benchmark {bid} not found")


def ui_watch_status():
    """Watch live status of a benchmark."""
    bid = input("\nEnter benchmark ID to watch: ").strip()
    if not bid:
        return

    summary = get_benchmark_summary(bid)
    if not summary:
        print(f"\n❌ Benchmark {bid} not found")
        return

    # Check if benchmark is already completed by looking at local artifacts
    from reporting.artifacts import read_summary_json
    metrics = read_summary_json(bid)
    if metrics:
        print(f"\n✓ Benchmark {bid} is already completed!")
        print(f"  Total Requests: {metrics.get('total_requests', 0):,}")
        print(f"  Success Rate: {metrics.get('success_rate', 0):.2f}%")
        print(f"  Duration: {metrics.get('test_duration_s', 0):.1f}s")
        print(f"\nUse option 3 to view full summary.")
        print(f"\nPrometheus Metrics: http://localhost:5000/api/benchmark/{bid}/metrics/prometheus")
        return

    print(f"\n👁 Watching benchmark {bid} (Ctrl+C to stop)...\n")

    # Get target from run.json using lifecycle module
    target = get_benchmark_target(bid)

    try:
        with Manager(target=target, benchmark_id=bid) as manager:
            while True:
                status = manager.get_benchmark_status()

                # Clear line and print status
                print(f"\r[{time.strftime('%H:%M:%S')}] ", end="")

                # Services
                for svc in status["services"]:
                    state = svc["status"].split(" ")[0]
                    icon = (
                        "✓"
                        if state == "COMPLETED"
                        else ("▶" if state == "RUNNING" else "⏳")
                    )
                    print(f"Service: {icon} {state}  ", end="")

                # Clients summary
                client_states = [c["status"] for c in status["clients"]]
                running = client_states.count("RUNNING")
                completed = client_states.count("COMPLETED")
                pending = client_states.count("PENDING")
                total = len(client_states)

                if total > 0:
                    print(
                        f"Clients: {completed}/{total} done, {running} running, {pending} pending",
                        end="",
                    )
                elif total == 0:
                    # Check if clients were expected
                    from reporting.artifacts import read_run_json
                    run_data = read_run_json(bid)
                    expected_clients = 0
                    if run_data and "recipe" in run_data:
                        benchmarks = run_data["recipe"].get("benchmarks", {})
                        expected_clients = benchmarks.get("num_clients", 0) if isinstance(benchmarks, dict) else 0
                    if expected_clients > 0:
                        print(" ⚠ No clients deployed (expected {})".format(expected_clients), end="")

                # Check if all CLIENTS are done (this is what defines benchmark completion)
                clients_terminal = all(
                    c["status"] in ["COMPLETED", "FAILED", "CANCELLED", "TIMEOUT"]
                    for c in status["clients"]
                ) if status["clients"] else False  # False if no clients
                total_clients = len(status["clients"])
                
                # When clients are done, stop service and collect
                if clients_terminal and total_clients > 0:
                    print("\n\n✓ All clients completed!")
                    
                    # Auto-stop the service (it's no longer needed)
                    print("Stopping service...")
                    try:
                        manager.stop_benchmark()
                        print("✓ Service stopped.")
                    except Exception as e:
                        print(f"⚠ {e}")
                    
                    # Collect artifacts (including logs and client hostnames)
                    print("\nCollecting artifacts and logs...")
                    try:
                        from core.collector import collect_benchmark_artifacts
                        if collect_benchmark_artifacts(bid, target):
                            print("✓ Artifacts collected.")
                            
                            # Generate report
                            print("Generating report...")
                            try:
                                from reporting.reporter import generate_benchmark_report
                                generate_benchmark_report(bid)
                                print("✓ Report generated.")
                            except Exception as e:
                                print(f"⚠ Report failed: {e}")
                            
                            # Show metrics summary
                            from reporting.artifacts import read_summary_json
                            metrics = read_summary_json(bid)
                            if metrics:
                                print(f"\nPerformance Summary:")
                                print(f"  Throughput: {metrics.get('requests_per_second', 0):.2f} RPS")
                                print(f"  P99 Latency: {metrics.get('latency_s', {}).get('p99', 0)*1000:.1f} ms")
                        else:
                            print("⚠ Collection failed")
                    except Exception as e:
                        print(f"⚠ Error: {e}")
                    
                    print(f"\n✓ Benchmark {bid} completed!")
                    print(f"Artifacts: results/{bid}/")
                    print(f"Logs: results/{bid}/logs/")
                    print(f"\nPrometheus Metrics: http://localhost:5000/api/benchmark/{bid}/metrics/prometheus")
                    break

                print("", flush=True)
                time.sleep(5)

    except KeyboardInterrupt:
        print("\n\nStopped watching.")
    except Exception as e:
        print(f"\n❌ Error: {e}")


def ui_stop_benchmark():
    """Stop all jobs for a benchmark."""
    # Show recent benchmarks first
    benchmarks = list_all_benchmarks()[:5]
    if benchmarks:
        print("\nRecent benchmarks:")
        for b in benchmarks:
            print(f"  [{b.benchmark_id}] {b.service_name or '?'}")

    bid = input("\nEnter benchmark ID to stop: ").strip()
    if not bid:
        return

    confirm = input(f"Stop all jobs for benchmark {bid}? [y/N]: ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        return

    print(f"\n⏹ Stopping benchmark {bid}...")

    # Get target from run.json using lifecycle module
    target = get_benchmark_target(bid)

    try:
        with Manager(target=target, benchmark_id=bid) as manager:
            result = manager.stop_benchmark()

            if result["services"]:
                print(f"  Cancelled {len(result['services'])} service(s)")
            if result["clients"]:
                print(f"  Cancelled {len(result['clients'])} client(s)")
            if result["errors"]:
                for err in result["errors"]:
                    print(f"  ⚠ {err}")

            print("✓ Done")
    except Exception as e:
        print(f"\n❌ Error: {e}")


def ui_show_logs():
    """Show logs for a benchmark with interactive selection."""
    bid = input("\nEnter benchmark ID: ").strip()
    if not bid:
        return

    summary = get_benchmark_summary(bid)
    if not summary:
        print(f"\n❌ Benchmark {bid} not found")
        return

    # Check for local log files first
    log_dir = Path(f"results/{bid}/logs")
    
    # If no local logs, fetch from cluster first
    if not log_dir.exists() or not list(log_dir.glob("*.out")):
        print(f"\n📋 No local logs found. Fetching from cluster...")
        
        # Get target using lifecycle module
        target = get_benchmark_target(bid)
        
        try:
            with Manager(target=target, benchmark_id=bid) as manager:
                logs = manager.tail_logs(num_lines=30)

                # Save logs locally for future use
                from reporting.artifacts import ensure_results_dir
                results_dir = ensure_results_dir(bid)
                logs_dir = results_dir / "logs"
                logs_dir.mkdir(exist_ok=True)

                # Save service logs
                for name, log in logs["services"].items():
                    if log:
                        log_file = logs_dir / f"{name}_service.out"
                        with open(log_file, 'w') as f:
                            f.write(log)

                # Save client logs
                for name, log in logs["clients"].items():
                    if log:
                        log_file = logs_dir / f"{name}_client.out"
                        with open(log_file, 'w') as f:
                            f.write(log)
                
                print(f"\n✓ Logs saved locally to {logs_dir}")
                
        except Exception as e:
            print(f"\n❌ Error fetching logs: {e}")
            return
    
    # Interactive log selection
    while True:
        log_files = sorted(log_dir.glob("*.out"))
        
        if not log_files:
            print(f"\n❌ No log files found for benchmark {bid}")
            return
        
        print(f"\n📋 Available logs for benchmark {bid}:")
        print("-" * 40)
        for i, log_file in enumerate(log_files, 1):
            size = log_file.stat().st_size
            print(f"  [{i}] {log_file.name} ({size} bytes)")
        print(f"  [Q] Return to menu")
        print("-" * 40)
        
        choice = input("\nSelect log to view: ").strip().lower()
        
        if choice == 'q':
            break
        
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(log_files):
                selected_log = log_files[idx]
                print(f"\n{'=' * 60}")
                print(f"Viewing: {selected_log.name}")
                print("=" * 60)
                
                with open(selected_log) as f:
                    lines = f.readlines()
                    # Show last 50 lines or all if less
                    start_idx = max(0, len(lines) - 50)
                    for i, line in enumerate(lines[start_idx:], start=start_idx + 1):
                        print(f"{i:5d}: {line.rstrip()}")
                
                print(f"\n{'=' * 60}")
                print(f"End of {selected_log.name}")
                
                # Ask what to do next
                while True:
                    action = input("\n[Q]uit to menu or [R]eturn to log list: ").strip().lower()
                    if action == 'q':
                        return
                    elif action == 'r':
                        break
                    else:
                        print("Please enter 'Q' or 'R'")
            else:
                print(f"\n❌ Invalid selection. Please choose 1-{len(log_files)} or Q")
        except ValueError:
            print(f"\n❌ Please enter a number or Q")


def run_benchmark_from_recipe(recipe_path: Path) -> Optional[int]:
    """
    Run a benchmark from a recipe file and return the benchmark ID.

    This is a refactored version of the main benchmark running logic.
    """
    try:
        recipe = parse_recipe(recipe_path)

        # Generate unique benchmark ID
        benchmark_id = generate_benchmark_id()
        print(f"\n{'=' * 60}")
        print(f"Benchmark ID: {benchmark_id}")
        print(f"{'=' * 60}\n")

        # Get target from recipe
        target = recipe.configuration.target
        if not target:
            print("Error: No target specified in recipe configuration", file=sys.stderr)
            return None

        # Get service configuration from recipe
        service_config = recipe.service
        if not service_config.image:
            print(
                "Error: No container image specified in service section",
                file=sys.stderr,
            )
            return None

        if not service_config.command:
            print(
                "Error: No service command specified in service section",
                file=sys.stderr,
            )
            return None

        # Use service name from config or generate default
        service_name = service_config.name or f"service-{benchmark_id}"

        print(f"Target cluster: {target}")
        print(f"Service: {service_name}")
        print(f"Container image: {service_config.image}")
        print(f"Command: {service_config.command}\n")

        # Create Manager and deploy service
        with Manager(target=target, benchmark_id=benchmark_id) as manager:
            print("Connecting to cluster...")

            # Prepare sbatch parameters for service
            sbatch_params = {
                "partition": service_config.partition,
                "num_gpus": service_config.num_gpus,
                "time_limit": service_config.time_limit,
                # Advanced hardware/runtime
                "gpus_per_node": service_config.gpus_per_node,
                "cpus_per_task": service_config.cpus_per_task,
                "memory": service_config.memory,
                "constraints": service_config.constraints,
                "exclude_nodes": service_config.exclude_nodes,
                "volumes": service_config.volumes,
                "modules": service_config.modules,
                "pre_run_commands": service_config.pre_run_commands,
            }

            # Add account if specified
            if service_config.account:
                sbatch_params["account"] = service_config.account

            # Deploy the service
            service = manager.deploy_service(
                service_name=service_name,
                container_image=service_config.image,
                service_command=service_config.command,
                port=service_config.port,
                env_vars=service_config.env,
                wait_for_start=True,
                max_wait_time=300,
                **sbatch_params,
            )

            if not service:
                print("\nError: Service deployment failed", file=sys.stderr)
                return None

            print(f"\n{'=' * 60}")
            print("Service deployed successfully!")
            print(f"{'=' * 60}")
            print(f"Service name: {service.name}")
            print(f"Job ID: {service.job_id}")
            print(f"{'=' * 60}\n")
            
            # MONITORING INTEGRATION: Register service with MonitorManager
            try:
                mon_mgr = MonitorManager()
                # Determine which port/target to scrape
                # The hardware scraper sidecar runs on 8010
                if service.hostname:
                    mon_mgr.update_prometheus_target(
                        job_name=f"{service_name}_hw",
                        ip_address=service.hostname,
                        port=8010
                    )
                    
                    # If this is vLLM, it also exposes metrics on its main port (8000) at /metrics
                    if service_config.type == "vllm":
                         mon_mgr.update_prometheus_target(
                            job_name=f"{service_name}_vllm",
                            ip_address=service.hostname,
                            port=8000 # vLLM default
                        )
            except Exception as e:
                print(f"Warning: Failed to register with monitoring stack: {e}")

            # Deploy clients if configured
            num_clients = recipe.benchmarks.num_clients
            client_command = recipe.client.command

            if num_clients and num_clients > 0 and client_command:
                print(f"\n{'=' * 60}")
                print(f"Deploying {num_clients} benchmark client(s)...")
                print(f"{'=' * 60}\n")

                # Prepare sbatch parameters for clients
                client_sbatch_params = {
                    "partition": recipe.client.partition,
                    "num_gpus": recipe.client.num_gpus,
                    "time_limit": recipe.client.time_limit,
                }

                # Add account if specified
                if recipe.client.account:
                    client_sbatch_params["account"] = recipe.client.account
                elif service_config.account:
                    # Use service account as fallback
                    client_sbatch_params["account"] = service_config.account

                # Deploy multiple clients (with service readiness check)
                # Extract model name for LLM services from settings
                expected_model = None
                if service_config.settings:
                    expected_model = service_config.settings.get("model")
                
                clients = manager.deploy_multiple_clients(
                    service_name=service_name,
                    benchmark_command=client_command,
                    num_clients=num_clients,
                    client_name_prefix=f"client-{service_name}",
                    service=service,
                    service_type=service_config.type,  # For readiness check
                    expected_model=expected_model,      # Model to wait for
                    **client_sbatch_params,
                )

                print(f"\n{'=' * 60}")
                print(f"Deployed {len(clients)} client(s) successfully!")
                print(f"{'=' * 60}")
                for client in clients:
                    print(f"  - {client.name} (Job ID: {client.job_id})")
                print(f"{'=' * 60}\n")
                
                # Check if deployment failed (0 clients when we expected some)
                if len(clients) == 0 and num_clients > 0:
                    print(f"\n{'=' * 60}")
                    print("❌ ERROR: Client deployment FAILED!")
                    print(f"   Expected {num_clients} client(s), deployed 0")
                    print("   Stopping service to avoid wasting resources...")
                    print(f"{'=' * 60}\n")
                    
                    # Stop the service since no clients were deployed
                    try:
                        manager.stop_benchmark()
                        print("✓ Service stopped.")
                    except Exception as e:
                        print(f"⚠ Warning: Could not stop service: {e}")
                    
                    return None  # Signal failure
            else:
                print("\nNo clients configured for deployment.")

            # Write run.json artifact with benchmark metadata
            service_info = {
                "name": service.name,
                "type": service_config.type or "unknown",
                "job_id": service.job_id,
                "hostname": service.hostname,
                "image": service_config.image,
                "port": service.port,
                "command": service_config.command,
                "partition": service_config.partition,
                "num_gpus": service_config.num_gpus,
                "time_limit": service_config.time_limit,
                "account": service_config.account,
                "env": service_config.env
            }
            
            client_info = []
            if 'clients' in locals() and clients:
                for client in clients:
                    client_info.append({
                        "name": client.name,
                        "job_id": client.job_id,
                        "hostname": client.hostname,
                        "command": client.benchmark_command,
                        "partition": recipe.client.partition,
                        "num_gpus": recipe.client.num_gpus,
                        "time_limit": recipe.client.time_limit,
                        "account": recipe.client.account
                    })
            
            # Write the run.json artifact
            write_run_json(
                benchmark_id=benchmark_id,
                recipe=recipe.__dict__,  # Convert to dict for JSON serialization
                service_info=service_info,
                client_info=client_info,
                target=target
            )
            print(f"✓ Run metadata written to results/{benchmark_id}/run.json")
            
            # Benchmark is now running - return control to caller
            # The UI will ask if user wants to watch status
            return benchmark_id

    except Exception as e:
        print(f"Error running benchmark: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return None


def run_interactive_ui():
    """Run the interactive UI loop."""
    clear_screen()
    print_header()

    while True:
        print_main_menu()

        try:
            choice = input("\nSelect option: ").strip().lower()

            if choice == "1":
                benchmark_id = ui_run_recipe()
                if benchmark_id:
                    print(f"\n✓ Benchmark {benchmark_id} started!")
                    
                    # Ask if user wants to watch status
                    watch = input("\nWatch benchmark status in real-time? [y/N]: ").strip().lower()
                    
                    if watch == "y":
                        # Watch the benchmark status live
                        print(f"\nWatching benchmark {benchmark_id}...")
                        print("(Press Ctrl+C to stop watching and return to menu)\n")
                        
                        try:
                            # Get target using lifecycle module
                            target = get_benchmark_target(str(benchmark_id))
                            
                            # Load run data for expected client count
                            run_data = read_run_json(str(benchmark_id))

                            with Manager(target=target, benchmark_id=str(benchmark_id)) as manager:
                                while True:
                                    status = manager.get_benchmark_status()
                                    
                                    # Display service status
                                    svc_status = (
                                        status["services"][0]["status"]
                                        if status["services"]
                                        else "UNKNOWN"
                                    )
                                    
                                    # Count completed clients
                                    client_done = sum(
                                        1
                                        for c in status["clients"]
                                        if c["status"] in ["COMPLETED", "FAILED", "CANCELLED", "TIMEOUT"]
                                    )
                                    total_clients = len(status["clients"])
                                    
                                    # Check if clients were expected
                                    expected_clients = 0
                                    if run_data and "recipe" in run_data:
                                        benchmarks = run_data["recipe"].get("benchmarks", {})
                                        expected_clients = benchmarks.get("num_clients", 0) if isinstance(benchmarks, dict) else 0
                                    
                                    if total_clients > 0:
                                        print(
                                            f"[{time.strftime('%H:%M:%S')}] Service: {svc_status}, "
                                            f"Clients: {client_done}/{total_clients} done",
                                            end="\r"
                                        )
                                    elif expected_clients > 0:
                                        print(
                                            f"[{time.strftime('%H:%M:%S')}] Service: {svc_status}, "
                                            f"⚠ No clients deployed (expected {expected_clients})",
                                            end="\r"
                                        )
                                    else:
                                        print(
                                            f"[{time.strftime('%H:%M:%S')}] Service: {svc_status}",
                                            end="\r"
                                        )
                                    
                                    # Check if all CLIENTS are done - then stop service and collect
                                    clients_done = all(
                                        c["status"] in ["COMPLETED", "FAILED", "CANCELLED", "TIMEOUT"]
                                        for c in status["clients"]
                                    ) if status["clients"] else True
                                    total_clients = len(status["clients"])
                                    
                                    if clients_done and total_clients > 0:
                                        print(f"\n\n✓ All clients finished!")
                                        
                                        # Auto-stop the service
                                        print("Stopping service...")
                                        try:
                                            manager.stop_benchmark()
                                            print("✓ Service stopped.")
                                        except Exception as e:
                                            print(f"⚠ {e}")
                                        
                                        # Auto-collect and report
                                        print("\nCollecting artifacts...")
                                        try:
                                            if collect_benchmark_artifacts(str(benchmark_id), target):
                                                print("✓ Artifacts collected.")
                                                print("Generating report...")
                                                try:
                                                    generate_benchmark_report(str(benchmark_id))
                                                    print("✓ Report generated.")
                                                except Exception as e:
                                                    print(f"⚠ Report failed: {e}")
                                            else:
                                                print("⚠ Collection failed")
                                        except Exception as e:
                                            print(f"⚠ Error: {e}")
                                        
                                        print(f"\nBenchmark {benchmark_id} finished.")
                                        print(f"Artifacts: results/{benchmark_id}/")
                                        input("\nPress Enter to return to menu...")
                                        break
                                    
                                    time.sleep(5)
                                    
                        except KeyboardInterrupt:
                            print("\n\nStopped watching.")
                            print(f"Benchmark {benchmark_id} is still running.")
                            print("Use option 4 to watch status later.")
                            input("\nPress Enter to return to menu...")
                    else:
                        print(f"\nBenchmark {benchmark_id} is running in the background.")
                        print("You can:")
                        print("  - Use option 4 to watch status")
                        print("  - Use option 3 to view summary when complete")
                        print("  - Use option 6 to view logs")
                        input("\nPress Enter to return to menu...")

            elif choice == "2":
                ui_list_benchmarks()

            elif choice == "3":
                ui_show_summary()

            elif choice == "4":
                ui_watch_status()

            elif choice == "5":
                ui_stop_benchmark()

            elif choice == "6":
                ui_show_logs()

            elif choice in ("q", "quit", "exit"):
                print("\nGoodbye! 👋\n")
                break

            else:
                print("\n⚠ Invalid option, please try again.")

        except KeyboardInterrupt:
            print("\n\nUse 'q' to quit.")
        except Exception as e:
            print(f"\n❌ Error: {e}")


# =============================================================================
# CLI COMMAND HANDLERS
# =============================================================================


def cmd_list_benchmarks():
    """Handle --list-benchmarks command."""
    benchmarks = list_all_benchmarks()
    print(format_benchmark_table(benchmarks))
    return 0


def cmd_show_summary(benchmark_id: str):
    """Handle --summary command."""
    from reporting.artifacts import read_summary_json
    
    summary = get_benchmark_summary(benchmark_id)
    if summary:
        print(format_benchmark_summary(summary))
        
        # Also show metrics if available
        metrics = read_summary_json(benchmark_id)
        if metrics:
            print(f"\nPerformance Metrics:")
            print(f"  Total Requests:    {metrics.get('total_requests', 0):,}")
            print(f"  Success Rate:      {metrics.get('success_rate', 0):.2f}%")
            print(f"  Throughput:        {metrics.get('requests_per_second', 0):.2f} RPS")
            print(f"  Avg Latency:       {metrics.get('latency_s', {}).get('avg', 0)*1000:.1f} ms")
            print(f"  P50 Latency:       {metrics.get('latency_s', {}).get('p50', 0)*1000:.1f} ms")
            print(f"  P95 Latency:       {metrics.get('latency_s', {}).get('p95', 0)*1000:.1f} ms")
            print(f"  P99 Latency:       {metrics.get('latency_s', {}).get('p99', 0)*1000:.1f} ms")
            print(f"  Test Duration:     {metrics.get('test_duration_s', 0):.1f} s")
            print("")
        
        return 0
    else:
        print(f"Benchmark {benchmark_id} not found", file=sys.stderr)
        return 1


def cmd_stop_benchmark(benchmark_id: str):
    """Handle --stop command."""
    print(f"Stopping benchmark {benchmark_id}...")
    try:
        target = get_benchmark_target(benchmark_id)
        with Manager(target=target, benchmark_id=benchmark_id) as manager:
            result = manager.stop_benchmark()

            cancelled = len(result["services"]) + len(result["clients"])
            if cancelled > 0:
                print(f"✓ Cancelled {cancelled} job(s)")
            else:
                print("No jobs to cancel")

            for err in result.get("errors", []):
                print(f"⚠ {err}", file=sys.stderr)

            return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_show_logs(benchmark_id: str):
    """Handle --logs command with interactive selection."""
    summary = get_benchmark_summary(benchmark_id)
    if not summary:
        print(f"Benchmark {benchmark_id} not found", file=sys.stderr)
        return 1

    # Check for local log files first
    log_dir = Path(f"results/{benchmark_id}/logs")
    
    # If no local logs, fetch from cluster first
    if not log_dir.exists() or not list(log_dir.glob("*.out")):
        print(f"Fetching logs from cluster...")
        try:
            target = get_benchmark_target(benchmark_id)
            with Manager(target=target, benchmark_id=benchmark_id) as manager:
                logs = manager.tail_logs(num_lines=50)

                # Save logs locally for future use
                from reporting.artifacts import ensure_results_dir
                results_dir = ensure_results_dir(benchmark_id)
                logs_dir = results_dir / "logs"
                logs_dir.mkdir(exist_ok=True)

                for name, log in logs["services"].items():
                    if log:
                        log_file = logs_dir / f"{name}_service.out"
                        with open(log_file, 'w') as f:
                            f.write(log)

                for name, log in logs["clients"].items():
                    if log:
                        log_file = logs_dir / f"{name}_client.out"
                        with open(log_file, 'w') as f:
                            f.write(log)
                
                print(f"Logs saved locally to {logs_dir}")
                
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
    
    # Interactive log selection
    while True:
        log_files = sorted(log_dir.glob("*.out"))
        
        if not log_files:
            print(f"No log files found for benchmark {benchmark_id}")
            return 1
        
        print(f"\nAvailable logs for benchmark {benchmark_id}:")
        print("-" * 40)
        for i, log_file in enumerate(log_files, 1):
            size = log_file.stat().st_size
            print(f"  [{i}] {log_file.name} ({size} bytes)")
        print(f"  [Q] Quit")
        print("-" * 40)
        
        choice = input("\nSelect log to view: ").strip().lower()
        
        if choice == 'q':
            break
        
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(log_files):
                selected_log = log_files[idx]
                print(f"\n{'=' * 60}")
                print(f"Viewing: {selected_log.name}")
                print("=" * 60)
                
                with open(selected_log) as f:
                    lines = f.readlines()
                    # Show last 50 lines or all if less
                    start_idx = max(0, len(lines) - 50)
                    for i, line in enumerate(lines[start_idx:], start=start_idx + 1):
                        print(f"{i:5d}: {line.rstrip()}")
                
                print(f"\n{'=' * 60}")
                print(f"End of {selected_log.name}")
                
                # Ask what to do next
                while True:
                    action = input("\n[Q]uit or [R]eturn to log list: ").strip().lower()
                    if action == 'q':
                        return 0
                    elif action == 'r':
                        break
                    else:
                        print("Please enter 'Q' or 'R'")
            else:
                print(f"\nInvalid selection. Please choose 1-{len(log_files)} or Q")
        except ValueError:
            print(f"\nPlease enter a number or Q")
    
    return 0


def cmd_watch_benchmark(benchmark_id: str):
    """Handle --watch command."""
    summary = get_benchmark_summary(benchmark_id)
    if not summary:
        print(f"Benchmark {benchmark_id} not found", file=sys.stderr)
        return 1
    
    # Check if benchmark is already completed
    from reporting.artifacts import read_summary_json
    metrics = read_summary_json(benchmark_id)
    if metrics:
        print(f"Benchmark {benchmark_id} is already completed!")
        print(f"  Total Requests: {metrics.get('total_requests', 0):,}")
        print(f"  Success Rate: {metrics.get('success_rate', 0):.2f}%")
        print(f"  Duration: {metrics.get('test_duration_s', 0):.1f}s")
        print(f"\nUse --summary {benchmark_id} to view full details.")
        return 0

    print(f"Watching benchmark {benchmark_id} (Ctrl+C to stop)...")

    # Get target using lifecycle module
    target = get_benchmark_target(benchmark_id)

    try:
        with Manager(target=target, benchmark_id=benchmark_id) as manager:
            while True:
                status = manager.get_benchmark_status()

                print(f"\n[{time.strftime('%H:%M:%S')}]")
                for svc in status["services"]:
                    print(f"  Service {svc['name']}: {svc['status']}")
                for client in status["clients"]:
                    print(f"  Client {client['name']}: {client['status']}")

                # Check if all done (services + clients)
                svc_terminal = all(
                    s["status"] in ["COMPLETED", "FAILED", "CANCELLED", "TIMEOUT"]
                    for s in status["services"]
                ) if status["services"] else True
                clients_terminal = all(
                    c["status"] in ["COMPLETED", "FAILED", "CANCELLED", "TIMEOUT"]
                    for c in status["clients"]
                ) if status["clients"] else True
                
                # Once clients are done, stop service and collect
                if clients_terminal and len(status["clients"]) > 0:
                    print("\n\n✓ All clients finished!")
                    
                    # Auto-stop the service
                    print("Stopping service...")
                    try:
                        manager.stop_benchmark()
                        print("✓ Service stopped.")
                    except Exception as e:
                        print(f"⚠ {e}")
                    
                    # Auto-collect artifacts
                    print("\nCollecting artifacts...")
                    if collect_benchmark_artifacts(benchmark_id, target):
                        print("✓ Artifacts collected.")
                        
                        # Auto-generate report
                        print("Generating report...")
                        try:
                            generate_benchmark_report(benchmark_id)
                            print("✓ Report generated.")
                            print(f"\nArtifacts: results/{benchmark_id}/")
                            print(f"Report: reports/{benchmark_id}/report.md")
                        except Exception as e:
                            print(f"⚠ Report failed: {e}")
                    else:
                        print("⚠ Collection failed")
                    break

                time.sleep(5)

        return 0
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_sweep_report(benchmark_ids: list, slo_threshold: float = None):
    """Handle --sweep-report command."""
    from reporting.reporter import generate_sweep_report
    
    print(f"Generating sweep report for {len(benchmark_ids)} benchmarks...")
    if slo_threshold:
        print(f"  SLO threshold: {slo_threshold}s")
    
    try:
        report_files = generate_sweep_report(benchmark_ids, slo_threshold)
        
        print(f"\n✓ Sweep report generated!")
        print(f"  - Markdown: {report_files['markdown']}")
        print(f"  - JSON: {report_files['json']}")
        return 0
        
    except Exception as e:
        print(f"Error generating sweep report: {e}", file=sys.stderr)
        return 1


def cmd_download_logs(benchmark_id: str):
    """Handle --download-logs command."""
    print(f"Downloading logs and artifacts for benchmark {benchmark_id}...")
    
    # Load benchmark to get target
    summary = get_benchmark_summary(benchmark_id)
    if not summary:
        print(f"Benchmark {benchmark_id} not found", file=sys.stderr)
        return 1
    
    # Get target using lifecycle module
    target = get_benchmark_target(benchmark_id)
    
    # Create local logs directory
    logs_dir = Path(f"logs/{benchmark_id}")
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    # Collect artifacts first (this downloads JSONL and metrics)
    print("  Collecting artifacts from cluster...")
    collect_benchmark_artifacts(benchmark_id, target)
    
    # Download additional log files
    try:
        with Manager(target=target, benchmark_id=benchmark_id) as manager:
            # Get working directory on cluster
            working_dir = f"/home/users/{manager.communicator.username}/benchmark_{benchmark_id}"
            
            # Download service and client logs
            print("  Downloading Slurm logs...")
            remote_logs = f"{working_dir}/logs/"
            
            # Use rsync/scp to download logs
            import subprocess
            result = subprocess.run(
                ["rsync", "-avz", f"{target}:{remote_logs}", str(logs_dir) + "/"],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                print(f"✓ Logs downloaded to {logs_dir}/")
            else:
                # Fallback: try scp
                result = subprocess.run(
                    ["scp", "-r", f"{target}:{remote_logs}*", str(logs_dir) + "/"],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    print(f"✓ Logs downloaded to {logs_dir}/")
                else:
                    print(f"  Warning: Could not download logs: {result.stderr}")
    except Exception as e:
        print(f"  Warning: Error downloading logs: {e}")
    
    # Show summary of downloaded files
    results_dir = Path(f"results/{benchmark_id}")
    reports_dir = Path(f"reports/{benchmark_id}")
    
    print(f"\n{'=' * 50}")
    print(f"Downloaded artifacts for {benchmark_id}:")
    print(f"{'=' * 50}")
    
    if results_dir.exists():
        print(f"\nResults ({results_dir}):")
        for f in results_dir.iterdir():
            print(f"  - {f.name}")
    
    if reports_dir.exists():
        print(f"\nReports ({reports_dir}):")
        for f in reports_dir.iterdir():
            if f.is_file():
                print(f"  - {f.name}")
            elif f.is_dir():
                print(f"  - {f.name}/ ({len(list(f.iterdir()))} files)")
    
    if logs_dir.exists() and any(logs_dir.iterdir()):
        print(f"\nLogs ({logs_dir}):")
        for f in logs_dir.iterdir():
            print(f"  - {f.name}")
    
    print(f"\n{'=' * 50}")
    return 0


def cmd_collect_artifacts(benchmark_id: str):
    """Handle --collect command."""
    print(f"Collecting artifacts for benchmark {benchmark_id}...")
    
    # Load benchmark to get target
    summary = get_benchmark_summary(benchmark_id)
    if not summary:
        print(f"Benchmark {benchmark_id} not found", file=sys.stderr)
        return 1
    
    # Get target using lifecycle module
    target = get_benchmark_target(benchmark_id)
    
    # Collect artifacts
    success = collect_benchmark_artifacts(benchmark_id, target)
    
    if success:
        print(f"\n✓ Artifacts collected successfully!")
        print(f"\nNext steps:")
        print(f"  python src/frontend.py --report {benchmark_id}")
        return 0
    else:
        print(f"\n✗ Failed to collect artifacts", file=sys.stderr)
        return 1


def cmd_generate_report(benchmark_id: str):
    """Handle --report command."""
    print(f"Generating report for benchmark {benchmark_id}...")
    
    try:
        # Generate complete report
        report_files = generate_benchmark_report(benchmark_id)
        
        print("✓ Report generated successfully!")
        print(f"\nFiles created:")
        print(f"  - Markdown: {report_files['markdown']}")
        print(f"  - JSON: {report_files['json']}")
        
        # Show plot files
        if 'plots' in report_files:
            print(f"\nPlots generated:")
            for plot_name, plot_path in report_files['plots'].items():
                print(f"  - {plot_name}: {plot_path}")
        
        # Load and display summary
        summary_file = Path(f"results/{benchmark_id}/summary.json")
        if summary_file.exists():
            with open(summary_file) as f:
                summary = json.load(f)
            
            print(f"\nSummary:")
            print(f"  Total requests: {summary.get('total_requests', 0)}")
            print(f"  Success rate: {summary.get('success_rate', 0):.1f}%")
            print(f"  Avg latency: {summary.get('latency_s', {}).get('avg', 0):.3f}s")
            print(f"  P95 latency: {summary.get('latency_s', {}).get('p95', 0):.3f}s")
            print(f"  Throughput: {summary.get('requests_per_second', 0):.2f} RPS")
        
        return 0
        
    except Exception as e:
        print(f"Error generating report: {e}", file=sys.stderr)
        return 1


def cmd_collect_metrics(benchmark_id: str):
    """Handle --metrics command."""
    summary = get_benchmark_summary(benchmark_id)
    if not summary:
        print(f"Benchmark {benchmark_id} not found", file=sys.stderr)
        return 1

    # Check for existing metrics
    existing = BenchmarkMetrics.load(benchmark_id)
    if existing:
        print(
            f"Found existing metrics (collected {existing.collected_at.strftime('%Y-%m-%d %H:%M:%S')})"
        )
        print(format_metrics_report(existing))

        recollect = input("\nRecollect metrics? [y/N]: ").strip().lower()
        if recollect != "y":
            return 0

    print(f"Collecting metrics for benchmark {benchmark_id}...")

    try:
        target = get_benchmark_target(benchmark_id)
        with Manager(target=target, benchmark_id=benchmark_id) as manager:
            collector = MetricsCollector(manager.communicator)

            # Get job IDs from summary
            service_job_id = summary.service_job_id
            client_job_ids = [
                c.get("job_id") for c in summary.clients if c.get("job_id")
            ]

            metrics = collector.collect_benchmark_metrics(
                benchmark_id=benchmark_id,
                service_job_id=service_job_id,
                client_job_ids=client_job_ids,
                service_hostname=summary.service_hostname,
            )

            # Save metrics
            metrics.save()
            print("✓ Metrics saved")

            # Print report
            print(format_metrics_report(metrics))

        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_launch_web():
    """Handle --web command."""
    import subprocess

    flask_app_path = Path(__file__).parent / "web" / "flask_app.py"

    if not flask_app_path.exists():
        print(f"Web app not found at {flask_app_path}", file=sys.stderr)
        return 1

    print("🌐 Launching Web UI...")
    print("   Open http://localhost:5000 in your browser")
    print("   Press Ctrl+C to stop\n")

    try:
        subprocess.run([sys.executable, str(flask_app_path)], check=True)
        return 0
    except KeyboardInterrupt:
        print("\nWeb UI stopped.")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1



def cmd_list_recipes() -> int:
    """Handle --list-recipes (via --list with no arg, or explicit flag if we added it)."""
    # Note: Using existing get_available_recipes
    recipes = get_available_recipes()
    
    if not recipes:
        print("No recipes found in examples/ directory")
        return 0
        
    print(f"\nFound {len(recipes)} recipes:")
    print("-" * 50)
    for i, recipe in enumerate(recipes, 1):
        name = recipe.stem.replace("recipe_", "").replace("_", " ").title()
        print(f"  {name:<25} ({recipe})")
    print("-" * 50)
    return 0


def cmd_rerun_benchmark(benchmark_id: str) -> int:
    """
    Handle --rerun command.
    
    Re-executes a benchmark using the exact configuration from its run.json.
    """
    print(f"Preparing to rerun benchmark {benchmark_id}...")
    
    # 1. Load run.json to get the recipe
    run_data = read_run_json(benchmark_id)
    if not run_data:
        print(f"Error: Could not find run data for {benchmark_id}", file=sys.stderr)
        return 1
        
    if "recipe" not in run_data:
        print(f"Error: run.json for {benchmark_id} does not contain recipe snapshot", file=sys.stderr)
        return 1
    
    # 2. Extract recipe data
    recipe_data = run_data["recipe"]
    
    # 3. Create a temporary recipe file to execute
    # This ensures we use the exact same logic as a fresh run
    import tempfile
    
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
        yaml.dump(recipe_data, tmp)
        tmp_path = Path(tmp.name)
        
    print(f"  Restored configuration from {benchmark_id}")
    print(f"  Created temporary recipe: {tmp_path}")
    
    try:
        # 4. Run the benchmark
        print(f"\n▶ Starting Rerun...")
        new_id = run_benchmark_from_recipe(tmp_path)
        
        if new_id:
            print(f"\n✓ Rerun successful: {benchmark_id} -> {new_id}")
            # Optional: Link them in metadata? (Future improvement)
            return 0
        else:
            print("\n❌ Rerun failed to start")
            return 1
            
    finally:
        # Cleanup
        if tmp_path.exists():
            os.unlink(tmp_path)


def cmd_compare_benchmarks(id1: str, id2: str) -> int:
    """
    Handle --compare command.
    
    Compares two benchmark summaries and reports regressions.
    """
    print(f"Comparing {id1} (Baseline) vs {id2} (Current)...\n")
    
    # 1. Load summaries
    s1 = read_summary_json(id1)
    s2 = read_summary_json(id2)
    
    if not s1:
        print(f"Error: Summary not found for {id1}", file=sys.stderr)
        return 1
    if not s2:
        print(f"Error: Summary not found for {id2}", file=sys.stderr)
        return 1
        
    # 2. Run comparison
    try:
        comparison = compare_summaries(s1, s2)
    except Exception as e:
        print(f"Error comparing summaries: {e}", file=sys.stderr)
        return 1
        
    # 3. Pretty print results
    print(f"{'Metric':<25} {'Baseline':<12} {'Current':<12} {'Delta':<12} {'% Change':<10} {'Status':<8}")
    print("-" * 85)
    
    for metric_key, data in comparison["metrics"].items():
        label = data["label"]
        baseline_val = data["baseline"]
        current_val = data["current"]
        delta = data["delta"]
        pct_change = data["percent_change"]
        is_regression = data["regression"]
        
        # Format values
        if "Rate" in label:
            baseline_str = f"{baseline_val:.1f}%"
            current_str = f"{current_val:.1f}%"
            delta_str = f"{delta:+.1f}%"
        elif "Latency" in label:
            baseline_str = f"{baseline_val:.3f}s"
            current_str = f"{current_val:.3f}s"
            delta_str = f"{delta:+.3f}s"
        else:
            baseline_str = f"{baseline_val:.2f}"
            current_str = f"{current_val:.2f}"
            delta_str = f"{delta:+.2f}"
        
        pct_str = f"{pct_change:+.1f}%"
        status = "REGRESS" if is_regression else "OK"
        
        # Highlight regressions in red if possible, or just bold/marked
        row = f"{label:<25} {baseline_str:<12} {current_str:<12} {delta_str:<12} {pct_str:<10} {status:<8}"
        if is_regression:
            print(f"\033[91m{row}\033[0m")  # Red
        else:
            print(row)
    
    print("-" * 85)
    
    # Overall verdict
    if comparison["verdict"] == "FAIL":
        print("\n\033[91m⚠ RESULT: FAIL - REGRESSIONS DETECTED\033[0m")
        return 1
    else:
        print("\n\033[92m✓ RESULT: PASS - NO SIGNIFICANT REGRESSIONS\033[0m")
        return 0


def main() -> int:
    """
    Main entry point for the frontend.

    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    parser = create_argument_parser()
    args = parser.parse_args()

    try:
        # Handle CLI commands first

        # --ui: Launch interactive UI
        if args.ui:
            run_interactive_ui()
            return 0

        # --monitor-stack: Control monitoring stack
        if args.monitor_stack:
            manager = MonitorManager()
            if args.monitor_stack == "start":
                print("Starting monitoring stack...")
                
                # Verify environment / Setup
                if not manager.setup_stack():
                    print("❌ Stack setup failed. Aborting start.")
                    return 1
                    
                if manager.start_stack():
                    print(f"✓ Stack start command issued.")
                    print("  Run 'python src/frontend.py --monitor-stack status' to check IP.")
                else:
                    print("❌ Stack start failed.")
                     
            elif args.monitor_stack == "stop":
                print("Stopping monitoring stack...")
                manager.stop_stack()
                    
            elif args.monitor_stack == "status":
                job_id, ip, ready = manager.check_status()
                if job_id:
                    print(f"Stack Status: RUNNING (Job {job_id})")
                    if ip:
                         print(f"  Head IP:    {ip}")
                         print(f"  Prometheus: http://localhost:9090")
                         print(f"  Grafana:    http://localhost:3000")
                         print(f"\\nSSH Tunnels required:")
                         ssh_user = os.environ.get('MELUXINA_USER', os.environ.get('USER', 'YOUR_USERNAME'))
                         print(f"  ssh -p 8822 {ssh_user}@login.lxp.lu -NL 9090:{ip}:9090")
                         print(f"  ssh -p 8822 {ssh_user}@login.lxp.lu -NL 3000:{ip}:3000")
                         if ssh_user == os.environ.get('USER'):
                             print(f"\\n  (Set MELUXINA_USER env var if '{ssh_user}' is not your MeluXina username)")
                    else:
                        print("  Waiting for IP address allocation...")
                else:
                    print("Stack Status: STOPPED")
            return 0

        # --list-recipes: List available recipes
        if args.list_recipes:
            return cmd_list_recipes()

        # --rerun: Rerun a benchmark
        if args.rerun:
            return cmd_rerun_benchmark(args.rerun)



        # --list-benchmarks: List all benchmarks
        if args.list_benchmarks:
            return cmd_list_benchmarks()

        # --summary: Show benchmark summary
        if args.summary:
            return cmd_show_summary(args.summary)

        # --stop: Stop a benchmark
        if args.stop:
            return cmd_stop_benchmark(args.stop)

        # --logs: Show logs for a benchmark
        if args.logs:
            return cmd_show_logs(args.logs)

        # --watch: Watch benchmark status
        if args.watch:
            return cmd_watch_benchmark(args.watch)

        # --metrics: Collect and show metrics
        if args.metrics:
            return cmd_collect_metrics(args.metrics)

        # --web: Launch web UI
        if args.web:
            return cmd_launch_web()
        
        # --report: Generate report
        if args.report:
            return cmd_generate_report(args.report)
        
        # --compare: Compare benchmarks
        if args.compare:
            return cmd_compare_benchmarks(args.compare[0], args.compare[1])
        
        # --collect: Collect artifacts from cluster
        if args.collect:
            return cmd_collect_artifacts(args.collect)
        
        # --download-logs: Download all logs and artifacts
        if args.download_logs:
            return cmd_download_logs(args.download_logs)
        
        # --sweep-report: Generate sweep report with saturation analysis
        if args.sweep_report:
            return cmd_sweep_report(args.sweep_report, args.slo)

        # --id: Load existing benchmark by ID
        if args.benchmark_id:
            return cmd_show_summary(args.benchmark_id)

        # Recipe file provided: Run benchmark
        if args.recipe:
            benchmark_id = run_benchmark_from_recipe(args.recipe)
            if benchmark_id:
                # Get target using lifecycle module
                target = get_benchmark_target(benchmark_id)
                
                # Wait for benchmark completion and auto-collect artifacts
                print(f"\n{'=' * 60}")
                print("Waiting for benchmark to complete...")
                print(f"{'=' * 60}")
                print("(Press Ctrl+C to detach - benchmark will continue running)\n")
                
                try:
                    with Manager(target=target, benchmark_id=benchmark_id) as manager:
                        while True:
                            status = manager.get_benchmark_status()
                            
                            # Get client progress
                            client_done = sum(1 for c in status["clients"] if c["status"] in ["COMPLETED", "FAILED", "CANCELLED", "TIMEOUT"])
                            total_clients = len(status["clients"])
                            svc_status = status["services"][0]["status"] if status["services"] else "UNKNOWN"
                            
                            print(f"\r[{time.strftime('%H:%M:%S')}] Service: {svc_status}, Clients: {client_done}/{total_clients} done", end="", flush=True)
                            
                            # Check if all CLIENTS are done (terminal state)
                            clients_done_all = all(
                                c["status"] in ["COMPLETED", "FAILED", "CANCELLED", "TIMEOUT"]
                                for c in status["clients"]
                            ) if status["clients"] else True
                            
                            if clients_done_all and total_clients > 0:
                                print(f"\n\n✓ All clients finished!")
                                
                                # Auto-stop the service (it's no longer needed)
                                print(f"Stopping service...")
                                try:
                                    manager.stop_benchmark()
                                    print(f"✓ Service stopped.")
                                except Exception as e:
                                    print(f"⚠ Warning: {e}")
                                
                                # Auto-collect artifacts
                                print(f"\nCollecting artifacts...")
                                if collect_benchmark_artifacts(str(benchmark_id), target):
                                    print(f"✓ Artifacts collected.")
                                    
                                    # Auto-generate report
                                    print(f"Generating report...")
                                    try:
                                        generate_benchmark_report(str(benchmark_id))
                                        print(f"✓ Report generated.")
                                    except Exception as e:
                                        print(f"⚠ Report failed: {e}")
                                else:
                                    print(f"⚠ Collection failed")
                                
                                break
                            
                            time.sleep(5)
                            
                except KeyboardInterrupt:
                    print(f"\n\nDetached from benchmark {benchmark_id}.")
                    print("Benchmark is running in the background.")
                    print(f"Use: python frontend.py --watch {benchmark_id}")
                    return 0
                
                # Final summary
                print(f"\n{'=' * 60}")
                print("Benchmark Complete!")
                print(f"{'=' * 60}")
                print(f"Benchmark ID: {benchmark_id}")
                print(f"\nArtifacts available in: results/{benchmark_id}/")
                print(f"Report available in: reports/{benchmark_id}/report.md")
                print(f"\nPrometheus Metrics: http://localhost:5000/api/benchmark/{benchmark_id}/metrics/prometheus")
                print(f"{'=' * 60}\n")
                return 0
            else:
                return 1

        # No arguments: Launch interactive UI
        run_interactive_ui()
        return 0

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except yaml.YAMLError as e:
        print(f"Error parsing YAML: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 3


if __name__ == "__main__":
    sys.exit(main())
