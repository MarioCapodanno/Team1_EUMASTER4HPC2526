"""
Reporting and output generation for the benchmarking framework.

Contains:
- reporter: Markdown report generation
- plotting: Chart generation
- artifacts: JSON artifact handling
"""

from .reporter import generate_benchmark_report
from .artifacts import (
    write_run_json,
    read_run_json,
    read_summary_json,
    read_requests_jsonl,
    ensure_results_dir,
    ensure_reports_dir,
)
