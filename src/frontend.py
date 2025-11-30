"""
Frontend module for the AI Factory Benchmarking Framework.

This module handles command-line argument parsing and recipe YAML configuration loading.
It produces a structured Python object containing all benchmark configuration information.
"""

import argparse
import sys
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

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
        epilog="Example: python frontend.py recipe.yaml"
    )
    
    parser.add_argument(
        "recipe",
        type=Path,
        nargs='?',
        help="Path to the recipe YAML configuration file"
    )
    
    parser.add_argument(
        "--id",
        dest="benchmark_id",
        type=str,
        help="Benchmark ID for loading existing benchmark"
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


def main() -> int:
    """
    Main entry point for the frontend.
    
    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    parser = create_argument_parser()
    args = parser.parse_args()
    
    try:
        # Mode 1: Load existing benchmark by ID
        if args.benchmark_id:
            print(f"Loading benchmark ID: {args.benchmark_id}")
            # List the services and clients
            from service import Service
            from client import Client
            
            services = Service.load_all(args.benchmark_id)
            clients = Client.load_all(args.benchmark_id)
            
            print(f"\nFound {len(services)} service(s):")
            for service in services:
                print(f"  - {service}")
            
            print(f"\nFound {len(clients)} client(s):")
            for client in clients:
                print(f"  - {client}")
            
            return 0
        
        # Mode 2: Create new benchmark from recipe
        if not args.recipe:
            parser.error("Either provide a recipe file or use --id to load existing benchmark")
        
        recipe = parse_recipe(args.recipe)
        
        if args.verbose:
            print(f"Successfully parsed recipe from: {args.recipe}")
            print(recipe)
        
        # Generate unique benchmark ID
        benchmark_id = generate_benchmark_id()
        print(f"\n{'='*60}")
        print(f"Benchmark ID: {benchmark_id}")
        print(f"{'='*60}\n")
        
        # Get target from recipe
        target = recipe.configuration.target
        if not target:
            print("Error: No target specified in recipe configuration", file=sys.stderr)
            return 1
        
        # Get service configuration from recipe
        service_config = recipe.service
        if not service_config.image:
            print("Error: No container image specified in service section", file=sys.stderr)
            return 1
        
        if not service_config.command:
            print("Error: No service command specified in service section", file=sys.stderr)
            return 1
        
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
                return 1
            
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
            
            # Final summary
            print(f"\n{'='*60}")
            print("Benchmark Deployment Summary")
            print(f"{'='*60}")
            print(f"Benchmark ID: {benchmark_id}")
            print(f"Service: {service.name} (Job ID: {service.job_id})")
            if num_clients and num_clients > 0:
                print(f"Clients: {num_clients} deployed")
            print(f"\nTo check benchmark status:")
            print(f"  python frontend.py --id {benchmark_id}")
            print(f"{'='*60}\n")
            
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