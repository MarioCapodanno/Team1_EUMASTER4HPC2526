"""
Frontend module for the AI Factory Benchmarking Framework.

This module handles command-line argument parsing and recipe YAML configuration loading.
It produces a structured Python object containing all benchmark configuration information.
Now includes an interactive CLI UI for managing benchmarks.
"""

import argparse
import sys
import os
import time
import glob
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, List

import yaml

from manager import Manager
from command_builders import (
    build_service_command,
    build_client_command,
    get_default_image,
    get_default_port,
    get_default_env,
    validate_service_type,
    validate_client_type,
    validate_settings,
)
from storage import (
    list_all_benchmarks,
    get_benchmark_summary,
    format_benchmark_table,
    format_benchmark_summary,
)
from monitor import (
    BenchmarkMetrics,
    MetricsCollector,
    format_metrics_report,
)
from health import check_http_health, wait_for_service_healthy

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
            recipe.configuration = Configuration(
                target=config_data.get("target", "")
            )
        
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
            image = service_data.get("image") or (get_default_image(service_type) if service_type else None)
            port = service_data.get("port") or (get_default_port(service_type) if service_type else None)
            env = service_data.get("env") or (get_default_env(service_type, settings) if service_type else None)
            
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
                env=env
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
                account=client_data.get("account")
            )
        
        # Parse benchmarks section
        if "benchmarks" in yaml_data:
            bench_data = yaml_data["benchmarks"]
            recipe.benchmarks = BenchmarkConfig(
                num_clients=bench_data.get("num_clients"),
                metrics=bench_data.get("metrics") or []
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
        epilog="Example: python frontend.py recipe.yaml\n         python frontend.py --ui"
    )
    
    parser.add_argument(
        "recipe",
        type=Path,
        nargs='?',
        help="Path to the recipe YAML configuration file"
    )
    
    parser.add_argument(
        "--ui",
        action="store_true",
        help="Launch interactive UI mode"
    )
    
    parser.add_argument(
        "--id",
        dest="benchmark_id",
        type=str,
        help="Benchmark ID for loading existing benchmark"
    )
    
    parser.add_argument(
        "--list", "--list-benchmarks",
        dest="list_benchmarks",
        action="store_true",
        help="List all benchmarks"
    )
    
    parser.add_argument(
        "--summary",
        type=str,
        metavar="BENCHMARK_ID",
        help="Show summary for a benchmark"
    )
    
    parser.add_argument(
        "--stop",
        type=str,
        metavar="BENCHMARK_ID",
        help="Stop all jobs for a benchmark"
    )
    
    parser.add_argument(
        "--logs",
        type=str,
        metavar="BENCHMARK_ID",
        help="Show logs for a benchmark"
    )
    
    parser.add_argument(
        "--watch",
        type=str,
        metavar="BENCHMARK_ID",
        help="Watch live status for a benchmark"
    )
    
    parser.add_argument(
        "--metrics",
        type=str,
        metavar="BENCHMARK_ID",
        help="Collect and show metrics for a benchmark"
    )
    
    parser.add_argument(
        "--web",
        action="store_true",
        help="Launch web UI (requires streamlit)"
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    
    return parser


def generate_benchmark_id() -> str:
    """
    Generate a unique benchmark ID.
    
    Returns:
        Unique benchmark ID string
    """
    # Use a simple incrementing counter stored in a file
    id_file = Path(".benchmark_id_counter")
    
    if id_file.exists():
        current_id = int(id_file.read_text().strip())
    else:
        current_id = 0
    
    new_id = current_id + 1
    id_file.write_text(str(new_id))
    
    return str(new_id)


# =============================================================================
# INTERACTIVE UI
# =============================================================================

def clear_screen():
    """Clear the terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')


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
    
    print(f"\n👁 Watching benchmark {bid} (Ctrl+C to stop)...\n")
    
    try:
        with Manager(target="meluxina", benchmark_id=bid) as manager:
            while True:
                status = manager.get_benchmark_status()
                
                # Clear line and print status
                print(f"\r[{time.strftime('%H:%M:%S')}] ", end="")
                
                # Services
                for svc in status['services']:
                    state = svc['status']
                    icon = "✓" if state == "COMPLETED" else ("▶" if state == "RUNNING" else "⏳")
                    print(f"Service: {icon} {state}  ", end="")
                
                # Clients summary
                client_states = [c['status'] for c in status['clients']]
                running = client_states.count('RUNNING')
                completed = client_states.count('COMPLETED')
                pending = client_states.count('PENDING')
                total = len(client_states)
                
                if total > 0:
                    print(f"Clients: {completed}/{total} done, {running} running, {pending} pending", end="")
                
                # Check if all done
                all_terminal = all(s in ['COMPLETED', 'FAILED', 'CANCELLED'] 
                                   for s in [svc['status'] for svc in status['services']] + client_states)
                
                if all_terminal:
                    print("\n\n✓ All jobs completed!")
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
    if confirm != 'y':
        print("Cancelled.")
        return
    
    print(f"\n⏹ Stopping benchmark {bid}...")
    
    try:
        with Manager(target="meluxina", benchmark_id=bid) as manager:
            result = manager.stop_benchmark()
            
            if result['services']:
                print(f"  Cancelled {len(result['services'])} service(s)")
            if result['clients']:
                print(f"  Cancelled {len(result['clients'])} client(s)")
            if result['errors']:
                for err in result['errors']:
                    print(f"  ⚠ {err}")
            
            print("✓ Done")
    except Exception as e:
        print(f"\n❌ Error: {e}")


def ui_show_logs():
    """Show logs for a benchmark."""
    bid = input("\nEnter benchmark ID: ").strip()
    if not bid:
        return
    
    summary = get_benchmark_summary(bid)
    if not summary:
        print(f"\n❌ Benchmark {bid} not found")
        return
    
    print(f"\n📋 Fetching logs for benchmark {bid}...")
    
    try:
        with Manager(target="meluxina", benchmark_id=bid) as manager:
            logs = manager.tail_logs(num_lines=30)
            
            # Show service logs
            for name, log in logs['services'].items():
                print(f"\n{'='*60}")
                print(f"Service: {name}")
                print("=" * 60)
                print(log or "(empty)")
            
            # Show client logs
            for name, log in logs['clients'].items():
                print(f"\n{'-'*60}")
                print(f"Client: {name}")
                print("-" * 60)
                print(log or "(empty)")
                
    except Exception as e:
        print(f"\n❌ Error: {e}")


def run_benchmark_from_recipe(recipe_path: Path) -> Optional[int]:
    """
    Run a benchmark from a recipe file and return the benchmark ID.
    
    This is a refactored version of the main benchmark running logic.
    """
    try:
        recipe = parse_recipe(recipe_path)
        
        # Generate unique benchmark ID
        benchmark_id = generate_benchmark_id()
        print(f"\n{'='*60}")
        print(f"Benchmark ID: {benchmark_id}")
        print(f"{'='*60}\n")
        
        # Get target from recipe
        target = recipe.configuration.target
        if not target:
            print("Error: No target specified in recipe configuration", file=sys.stderr)
            return None
        
        # Get service configuration from recipe
        service_config = recipe.service
        if not service_config.image:
            print("Error: No container image specified in service section", file=sys.stderr)
            return None
        
        if not service_config.command:
            print("Error: No service command specified in service section", file=sys.stderr)
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
                **sbatch_params
            )
            
            if not service:
                print("\nError: Service deployment failed", file=sys.stderr)
                return None
            
            print(f"\n{'='*60}")
            print("Service deployed successfully!")
            print(f"{'='*60}")
            print(f"Service name: {service.name}")
            print(f"Job ID: {service.job_id}")
            print(f"{'='*60}\n")
            
            # Deploy clients if configured
            num_clients = recipe.benchmarks.num_clients
            client_command = recipe.client.command
            
            if num_clients and num_clients > 0 and client_command:
                print(f"\n{'='*60}")
                print(f"Deploying {num_clients} benchmark client(s)...")
                print(f"{'='*60}\n")
                
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
                
                # Deploy multiple clients
                clients = manager.deploy_multiple_clients(
                    service_name=service_name,
                    benchmark_command=client_command,
                    num_clients=num_clients,
                    client_name_prefix=f"client-{service_name}",
                    service=service,
                    **client_sbatch_params
                )
                
                print(f"\n{'='*60}")
                print(f"Deployed {len(clients)} client(s) successfully!")
                print(f"{'='*60}")
                for client in clients:
                    print(f"  - {client.name} (Job ID: {client.job_id})")
                print(f"{'='*60}\n")
            else:
                print("\nNo clients configured for deployment.")
            
            return int(benchmark_id)
            
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
                    watch = input("Watch status? [y/N]: ").strip().lower()
                    if watch == 'y':
                        # Set the benchmark_id for watching
                        summary = get_benchmark_summary(str(benchmark_id))
                        if summary:
                            # Mini watch loop
                            try:
                                with Manager(target="meluxina", benchmark_id=str(benchmark_id)) as manager:
                                    for _ in range(12):  # Watch for ~1 minute
                                        status = manager.get_benchmark_status()
                                        svc_status = status['services'][0]['status'] if status['services'] else '?'
                                        client_done = sum(1 for c in status['clients'] if c['status'] == 'COMPLETED')
                                        total_clients = len(status['clients'])
                                        print(f"  [{time.strftime('%H:%M:%S')}] Service: {svc_status}, Clients: {client_done}/{total_clients} done")
                                        
                                        all_done = all(c['status'] in ['COMPLETED', 'FAILED', 'CANCELLED'] for c in status['clients'])
                                        svc_done = svc_status in ['COMPLETED', 'FAILED', 'CANCELLED']
                                        if all_done and (svc_done or not status['services']):
                                            print("  ✓ All jobs finished!")
                                            break
                                        time.sleep(5)
                            except KeyboardInterrupt:
                                print("\n  Stopped watching.")
                                
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
    summary = get_benchmark_summary(benchmark_id)
    if summary:
        print(format_benchmark_summary(summary))
        return 0
    else:
        print(f"Benchmark {benchmark_id} not found", file=sys.stderr)
        return 1


def cmd_stop_benchmark(benchmark_id: str):
    """Handle --stop command."""
    print(f"Stopping benchmark {benchmark_id}...")
    try:
        with Manager(target="meluxina", benchmark_id=benchmark_id) as manager:
            result = manager.stop_benchmark()
            
            cancelled = len(result['services']) + len(result['clients'])
            if cancelled > 0:
                print(f"✓ Cancelled {cancelled} job(s)")
            else:
                print("No jobs to cancel")
            
            for err in result.get('errors', []):
                print(f"⚠ {err}", file=sys.stderr)
            
            return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_show_logs(benchmark_id: str):
    """Handle --logs command."""
    summary = get_benchmark_summary(benchmark_id)
    if not summary:
        print(f"Benchmark {benchmark_id} not found", file=sys.stderr)
        return 1
    
    try:
        with Manager(target="meluxina", benchmark_id=benchmark_id) as manager:
            logs = manager.tail_logs(num_lines=50)
            
            for name, log in logs['services'].items():
                print(f"\n=== Service: {name} ===")
                print(log or "(no logs)")
            
            for name, log in logs['clients'].items():
                print(f"\n--- Client: {name} ---")
                print(log or "(no logs)")
            
            return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_watch_benchmark(benchmark_id: str):
    """Handle --watch command."""
    summary = get_benchmark_summary(benchmark_id)
    if not summary:
        print(f"Benchmark {benchmark_id} not found", file=sys.stderr)
        return 1
    
    print(f"Watching benchmark {benchmark_id} (Ctrl+C to stop)...")
    
    try:
        with Manager(target="meluxina", benchmark_id=benchmark_id) as manager:
            while True:
                status = manager.get_benchmark_status()
                
                print(f"\n[{time.strftime('%H:%M:%S')}]")
                for svc in status['services']:
                    print(f"  Service {svc['name']}: {svc['status']}")
                for client in status['clients']:
                    print(f"  Client {client['name']}: {client['status']}")
                
                # Check if all done
                all_states = [s['status'] for s in status['services']] + [c['status'] for c in status['clients']]
                if all(s in ['COMPLETED', 'FAILED', 'CANCELLED'] for s in all_states):
                    print("\n✓ All jobs finished!")
                    break
                
                time.sleep(5)
                
        return 0
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
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
        print(f"Found existing metrics (collected {existing.collected_at.strftime('%Y-%m-%d %H:%M:%S')})")
        print(format_metrics_report(existing))
        
        recollect = input("\nRecollect metrics? [y/N]: ").strip().lower()
        if recollect != 'y':
            return 0
    
    print(f"Collecting metrics for benchmark {benchmark_id}...")
    
    try:
        with Manager(target="meluxina", benchmark_id=benchmark_id) as manager:
            collector = MetricsCollector(manager.communicator)
            
            # Get job IDs from summary
            service_job_id = summary.service_job_id
            client_job_ids = [c.get('job_id') for c in summary.clients if c.get('job_id')]
            
            metrics = collector.collect_benchmark_metrics(
                benchmark_id=benchmark_id,
                service_job_id=service_job_id,
                client_job_ids=client_job_ids,
                service_hostname=summary.service_hostname
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
        
        # --id: Load existing benchmark by ID
        if args.benchmark_id:
            return cmd_show_summary(args.benchmark_id)
        
        # Recipe file provided: Run benchmark
        if args.recipe:
            result = run_benchmark_from_recipe(args.recipe)
            if result:
                # Final summary
                print(f"\n{'='*60}")
                print("Benchmark Deployment Summary")
                print(f"{'='*60}")
                print(f"Benchmark ID: {result}")
                print(f"\nUseful commands:")
                print(f"  python frontend.py --summary {result}   # Show summary")
                print(f"  python frontend.py --watch {result}     # Watch status")
                print(f"  python frontend.py --logs {result}      # Show logs")
                print(f"  python frontend.py --stop {result}      # Stop benchmark")
                print(f"{'='*60}\n")
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