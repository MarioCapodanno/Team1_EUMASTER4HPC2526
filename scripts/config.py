#!/usr/bin/env python3
"""
Shared configuration and utilities for benchmark campaign scripts.

This module centralizes configuration values and common functions to avoid
duplication across run_campaign.py and launch_overnight.py.
"""

import os
from pathlib import Path
from typing import Dict, Any

# =============================================================================
# Configuration (can be overridden via environment variables)
# =============================================================================

TARGET = os.environ.get("BENCHMARK_TARGET", "meluxina")
ACCOUNT = os.environ.get("SLURM_PROJECT", os.environ.get("BENCHMARK_ACCOUNT", "p200981"))


# =============================================================================
# Recipe Generation
# =============================================================================

def generate_recipe(app_def: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert an app definition to a full YAML recipe structure.
    
    Args:
        app_def: Dictionary containing service, client, and benchmark config
        
    Returns:
        Dictionary ready to be serialized as YAML recipe
    """
    recipe = {
        "configuration": {"target": TARGET},
        "service": {
            "type": app_def["service"]["type"],
            "name": app_def["name"],
            "image": app_def["service"]["image"],
            "partition": app_def["service"]["partition"],
            "time_limit": app_def["service"]["time"],
            "account": ACCOUNT,
            "port": app_def["service"]["port"],
        },
        "client": {
            "type": app_def["client"]["type"],
            "partition": app_def["client"]["partition"],
            "time_limit": app_def["client"]["time"],
            "account": ACCOUNT,
        },
        "benchmarks": {
            "num_clients": app_def["benchmark"]["clients"],
            "metrics": app_def["benchmark"]["metrics"]
        }
    }
    
    # Add optional service settings
    if "settings" in app_def["service"]:
        recipe["service"]["settings"] = app_def["service"]["settings"]
    if "memory" in app_def["service"]:
        recipe["service"]["memory"] = app_def["service"]["memory"]
        
    # Add optional client settings
    if "settings" in app_def["client"]:
        recipe["client"]["settings"] = app_def["client"]["settings"]
        
    return recipe
