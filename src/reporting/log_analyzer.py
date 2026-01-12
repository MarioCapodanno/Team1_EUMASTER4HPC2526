"""
Log analyzer module for categorizing and summarizing benchmark logs.

Parses service and client logs to identify:
- Errors (OOM, timeouts, connection failures, HTTP errors)
- Warnings
- Performance issues
- Success indicators

Produces a structured summary for inclusion in reports.
"""

import json
import re
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class LogCategory:
    """A category of log entries."""
    name: str
    pattern: str
    severity: str  # "error", "warning", "info"
    description: str
    count: int = 0
    examples: List[str] = field(default_factory=list)


# Log patterns to detect common issues
LOG_PATTERNS = [
    # Memory issues
    LogCategory(
        name="out_of_memory",
        pattern=r"(out of memory|oom|cannot allocate|memory allocation failed|killed.*oom)",
        severity="error",
        description="Out of memory errors"
    ),
    LogCategory(
        name="memory_warning",
        pattern=r"(memory usage|low memory|memory pressure|swap)",
        severity="warning",
        description="Memory warnings"
    ),
    
    # Timeout issues
    LogCategory(
        name="timeout",
        pattern=r"(timeout|timed out|deadline exceeded|connection timed out)",
        severity="error",
        description="Timeout errors"
    ),
    
    # Connection issues
    LogCategory(
        name="connection_refused",
        pattern=r"(connection refused|econnrefused|could not connect|failed to connect)",
        severity="error",
        description="Connection refused errors"
    ),
    LogCategory(
        name="connection_reset",
        pattern=r"(connection reset|econnreset|broken pipe|epipe)",
        severity="error",
        description="Connection reset errors"
    ),
    
    # HTTP errors
    LogCategory(
        name="http_500",
        pattern=r"(500|internal server error)",
        severity="error",
        description="HTTP 500 Internal Server Error"
    ),
    LogCategory(
        name="http_502_503",
        pattern=r"(502|503|bad gateway|service unavailable)",
        severity="error",
        description="HTTP 502/503 Gateway errors"
    ),
    LogCategory(
        name="http_4xx",
        pattern=r"(400|401|403|404|bad request|unauthorized|forbidden|not found)",
        severity="warning",
        description="HTTP 4xx client errors"
    ),
    
    # Service-specific errors
    LogCategory(
        name="cuda_error",
        pattern=r"(cuda error|gpu error|nccl error|cudnn error)",
        severity="error",
        description="CUDA/GPU errors"
    ),
    LogCategory(
        name="model_load_error",
        pattern=r"(failed to load model|model not found|error loading)",
        severity="error",
        description="Model loading errors"
    ),
    
    # Database errors
    LogCategory(
        name="db_connection_error",
        pattern=r"(database connection|could not connect to server|connection to .* failed)",
        severity="error",
        description="Database connection errors"
    ),
    LogCategory(
        name="query_error",
        pattern=r"(query failed|sql error|syntax error|relation .* does not exist)",
        severity="error",
        description="Query/SQL errors"
    ),
    
    # Slurm errors
    LogCategory(
        name="slurm_error",
        pattern=r"(slurmstepd|job .* exceeded|cancelled|preempted|node fail)",
        severity="error",
        description="Slurm job errors"
    ),
    
    # General errors and warnings
    LogCategory(
        name="general_error",
        pattern=r"(\berror\b|\bfailed\b|\bfailure\b|\bexception\b)",
        severity="error",
        description="General errors"
    ),
    LogCategory(
        name="general_warning",
        pattern=r"(\bwarning\b|\bwarn\b)",
        severity="warning",
        description="General warnings"
    ),
    
    # Success indicators
    LogCategory(
        name="success",
        pattern=r"(✓|success|completed|ready|started|healthy)",
        severity="info",
        description="Success indicators"
    ),
]


@dataclass
class LogSummary:
    """Summary of analyzed logs."""
    benchmark_id: str
    analyzed_at: str
    total_lines: int
    error_count: int
    warning_count: int
    categories: List[Dict[str, Any]]
    top_issues: List[Dict[str, Any]]
    files_analyzed: List[str]


def analyze_log_content(content: str, max_examples: int = 3) -> List[LogCategory]:
    """
    Analyze log content and categorize entries.
    
    Args:
        content: Log file content
        max_examples: Maximum examples to store per category
        
    Returns:
        List of LogCategory objects with counts and examples
    """
    # Create fresh category instances
    categories = []
    for pattern in LOG_PATTERNS:
        categories.append(LogCategory(
            name=pattern.name,
            pattern=pattern.pattern,
            severity=pattern.severity,
            description=pattern.description,
            count=0,
            examples=[]
        ))
    
    lines = content.split('\n')
    
    for line in lines:
        line_lower = line.lower().strip()
        if not line_lower:
            continue
            
        for category in categories:
            if re.search(category.pattern, line_lower, re.IGNORECASE):
                category.count += 1
                if len(category.examples) < max_examples:
                    # Store truncated example
                    example = line.strip()[:200]
                    if example not in category.examples:
                        category.examples.append(example)
    
    return categories


def analyze_benchmark_logs(benchmark_id: str) -> Optional[LogSummary]:
    """
    Analyze all logs for a benchmark and produce a summary.
    
    Args:
        benchmark_id: Benchmark identifier
        
    Returns:
        LogSummary object, or None if no logs found
    """
    results_dir = Path(f"results/{benchmark_id}")
    logs_dir = results_dir / "logs"
    
    if not logs_dir.exists():
        return None
    
    # Find all log files
    log_files = list(logs_dir.glob("*.out")) + list(logs_dir.glob("*.err")) + list(logs_dir.glob("*.log"))
    
    if not log_files:
        return None
    
    # Aggregate all categories
    all_categories: Dict[str, LogCategory] = {}
    total_lines = 0
    files_analyzed = []
    
    for log_file in log_files:
        try:
            content = log_file.read_text(errors='ignore')
            total_lines += len(content.split('\n'))
            files_analyzed.append(log_file.name)
            
            file_categories = analyze_log_content(content)
            
            for cat in file_categories:
                if cat.name in all_categories:
                    all_categories[cat.name].count += cat.count
                    # Merge examples
                    for ex in cat.examples:
                        if ex not in all_categories[cat.name].examples:
                            if len(all_categories[cat.name].examples) < 5:
                                all_categories[cat.name].examples.append(ex)
                else:
                    all_categories[cat.name] = cat
                    
        except Exception as e:
            print(f"Warning: Could not read {log_file}: {e}")
    
    # Calculate totals
    error_count = sum(
        cat.count for cat in all_categories.values() 
        if cat.severity == "error" and cat.name != "general_error"
    )
    warning_count = sum(
        cat.count for cat in all_categories.values() 
        if cat.severity == "warning" and cat.name != "general_warning"
    )
    
    # Get top issues (non-zero error categories, sorted by count)
    top_issues = [
        {
            "category": cat.name,
            "description": cat.description,
            "count": cat.count,
            "severity": cat.severity,
            "examples": cat.examples[:2]
        }
        for cat in sorted(all_categories.values(), key=lambda x: x.count, reverse=True)
        if cat.count > 0 and cat.severity in ("error", "warning")
    ][:10]  # Top 10 issues
    
    # Format categories for output
    category_list = [
        {
            "name": cat.name,
            "description": cat.description,
            "severity": cat.severity,
            "count": cat.count
        }
        for cat in all_categories.values()
        if cat.count > 0
    ]
    
    return LogSummary(
        benchmark_id=benchmark_id,
        analyzed_at=datetime.now().isoformat(),
        total_lines=total_lines,
        error_count=error_count,
        warning_count=warning_count,
        categories=category_list,
        top_issues=top_issues,
        files_analyzed=files_analyzed
    )


def write_log_summary(benchmark_id: str, summary: LogSummary) -> Path:
    """
    Write log summary to reports directory.
    
    Args:
        benchmark_id: Benchmark identifier
        summary: LogSummary object
        
    Returns:
        Path to written file
    """
    reports_dir = Path(f"reports/{benchmark_id}")
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    output_path = reports_dir / "logs_summary.json"
    
    with open(output_path, 'w') as f:
        json.dump(asdict(summary), f, indent=2)
    
    return output_path


def format_log_summary_markdown(summary: LogSummary) -> str:
    """
    Format log summary as Markdown for inclusion in reports.
    
    Args:
        summary: LogSummary object
        
    Returns:
        Markdown-formatted string
    """
    lines = [
        "## Log Analysis",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Files Analyzed | {len(summary.files_analyzed)} |",
        f"| Total Lines | {summary.total_lines:,} |",
        f"| Errors | {summary.error_count} |",
        f"| Warnings | {summary.warning_count} |",
        "",
    ]
    
    if summary.top_issues:
        lines.extend([
            "### Issues Detected",
            "",
            "| Severity | Description | Count |",
            "|----------|-------------|-------|",
        ])
        
        for issue in summary.top_issues[:5]:
            severity = issue['severity'].upper()
            desc = issue['description'][:40]  # Truncate long descriptions
            lines.append(f"| {severity} | {desc} | {issue['count']} |")
        
        lines.append("")
        
        # More compact example section
        has_examples = any(issue.get('examples') for issue in summary.top_issues[:2])
        if has_examples:
            lines.extend([
                "### Sample Log Entries",
                "",
            ])
            
            for issue in summary.top_issues[:2]:  # Only top 2
                if issue.get('examples'):
                    lines.append(f"**{issue['description'][:50]}**")
                    lines.append("")
                    lines.append("```")
                    for ex in issue['examples'][:1]:  # Only 1 example each
                        # Extract the most relevant part (after timestamp)
                        clean_ex = ex.strip()
                        # Try to extract just the message
                        if 'msg=' in clean_ex:
                            msg_part = clean_ex.split('msg=')[-1][:80]
                            clean_ex = msg_part
                        elif len(clean_ex) > 80:
                            clean_ex = clean_ex[:80] + "..."
                        lines.append(clean_ex)
                    lines.append("```")
                    lines.append("")
    else:
        lines.extend([
            "*No significant errors or warnings detected.*",
            "",
        ])
    
    return "\n".join(lines)


def generate_log_summary_for_report(benchmark_id: str) -> Tuple[Optional[LogSummary], str]:
    """
    Generate log summary and return both the summary object and markdown.
    
    Args:
        benchmark_id: Benchmark identifier
        
    Returns:
        Tuple of (LogSummary or None, markdown string)
    """
    summary = analyze_benchmark_logs(benchmark_id)
    
    if summary is None:
        return None, ""
    
    # Write the JSON summary
    write_log_summary(benchmark_id, summary)
    
    # Generate markdown
    markdown = format_log_summary_markdown(summary)
    
    return summary, markdown
