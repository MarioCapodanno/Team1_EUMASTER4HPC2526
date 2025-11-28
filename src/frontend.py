"""
Frontend module for the AI Factory Benchmarking Framework.

This module handles command-line argument parsing and recipe YAML configuration loading.
It produces a structured Python object containing all benchmark configuration information.
"""

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

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
        help="Path to the recipe YAML configuration file"
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    
    return parser


def main() -> int:
    """
    Main entry point for the frontend.
    
    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    parser = create_argument_parser()
    args = parser.parse_args()
    
    try:
        recipe = parse_recipe(args.recipe)
        
        if args.verbose:
            print(f"Successfully parsed recipe from: {args.recipe}")
        
        print(recipe)
        
        # Return the recipe object for further processing
        return 0
        
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except yaml.YAMLError as e:
        print(f"Error parsing YAML: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())