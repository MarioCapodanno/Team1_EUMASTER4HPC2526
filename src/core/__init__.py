"""
Core business logic for the benchmarking framework.

Contains:
- manager: Job orchestration and lifecycle management
- collector: Artifact collection from cluster
- aggregator: Metrics aggregation and analysis
- saturation: Saturation analysis (KF1)
"""

from .manager import Manager
from .collector import collect_benchmark_artifacts, auto_collect_if_complete
from .aggregator import aggregate_benchmark, compare_summaries
from .saturation import analyze_saturation
