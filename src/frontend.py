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
from typing import Any, Optional

import yaml

from manager import Manager

@dataclass
class Configuration:
    """Configuration section of the recipe."""
    target: str = ""  # SSH alias or hostname (e.g., "meluxina")


@dataclass
class BenchmarkConfig:
    """Benchmark configuration section of the recipe."""
    image: Optional[str] = None  # Docker image for the benchmark
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
        
        # Parse benchmarks section
        if "benchmarks" in yaml_data:
            bench_data = yaml_data["benchmarks"]
            recipe.benchmarks = BenchmarkConfig(
                image=bench_data.get("image"),
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
            f"  benchmarks:\n"
            f"    image: {self.benchmarks.image}\n"
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
            # TODO: Implement loading logic
            # For now, just list the services
            from service import Service
            services = Service.load_all(args.benchmark_id)
            print(f"Found {len(services)} service(s):")
            for service in services:
                print(f"  - {service}")
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
        
        # Get container image from recipe
        container_image = recipe.benchmarks.image
        if not container_image:
            print("Error: No container image specified in benchmarks section", file=sys.stderr)
            return 1
        
        print(f"Target cluster: {target}")
        print(f"Container image: {container_image}\n")
        
        # Create Manager and deploy service
        with Manager(target=target, benchmark_id=benchmark_id) as manager:
            print("Connecting to cluster...")
            
            # Deploy the service
            service = manager.deploy_service(
                service_name=f"service-{benchmark_id}",
                container_image=container_image,
                service_command="ollama serve",  # Default command, can be made configurable
                wait_for_start=True,
                max_wait_time=300
            )
            
            if service:
                print(f"\n{'='*60}")
                print("Service deployed successfully!")
                print(f"{'='*60}")
                print(f"Service name: {service.name}")
                print(f"Job ID: {service.job_id}")
                print(f"Status: Check with 'python frontend.py --id {benchmark_id}'")
                print(f"\nTo access this benchmark later:")
                print(f"  python frontend.py --id {benchmark_id}")
                print(f"{'='*60}\n")
                return 0
            else:
                print("\nError: Service deployment failed", file=sys.stderr)
                return 1
        
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