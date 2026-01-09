#!/usr/bin/env python3
"""
Lightweight Flask Web UI for AI Factory Benchmarking Framework.

Works with Python 3.14+ (unlike Streamlit which has compatibility issues).
Run with: python src/web/flask_app.py
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, jsonify, redirect, send_file

from storage import (
    list_all_benchmarks,
    get_benchmark_summary,
)
from artifacts import read_run_json, read_summary_json
from reporter import generate_benchmark_report
from collector import collect_benchmark_artifacts

app = Flask(__name__)

# =============================================================================
# HTML TEMPLATES
# =============================================================================

BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Factory Benchmark Framework</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #e0e0e0;
        }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        
        /* Header */
        .header {
            background: rgba(255,255,255,0.05);
            backdrop-filter: blur(10px);
            padding: 20px 40px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
            margin-bottom: 30px;
        }
        .header h1 { 
            font-size: 1.8rem; 
            background: linear-gradient(90deg, #00d4ff, #7b2cbf);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .header p { color: #888; margin-top: 5px; }
        
        /* Navigation */
        .nav { display: flex; gap: 10px; margin-bottom: 30px; }
        .nav a {
            padding: 12px 24px;
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 8px;
            color: #e0e0e0;
            text-decoration: none;
            transition: all 0.3s;
        }
        .nav a:hover, .nav a.active {
            background: rgba(0, 212, 255, 0.2);
            border-color: #00d4ff;
        }
        
        /* Cards */
        .card {
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
        }
        .card h2 { color: #00d4ff; margin-bottom: 15px; font-size: 1.2rem; }
        .card h3 { color: #7b2cbf; margin: 15px 0 10px; font-size: 1rem; }
        
        /* Stats Grid */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 8px;
            padding: 20px;
            text-align: center;
        }
        .stat-card .value { font-size: 2rem; color: #00d4ff; font-weight: bold; }
        .stat-card .label { color: #888; font-size: 0.9rem; margin-top: 5px; }
        
        /* Table */
        .table {
            width: 100%;
            border-collapse: collapse;
        }
        .table th, .table td {
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        .table th { color: #888; font-weight: normal; font-size: 0.85rem; text-transform: uppercase; }
        .table tr:hover { background: rgba(255,255,255,0.02); }
        .table a { color: #00d4ff; text-decoration: none; }
        .table a:hover { text-decoration: underline; }
        
        /* Status badges */
        .badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 500;
        }
        .badge-running { background: rgba(76, 175, 80, 0.2); color: #4CAF50; }
        .badge-pending { background: rgba(255, 152, 0, 0.2); color: #FF9800; }
        .badge-completed { background: rgba(33, 150, 243, 0.2); color: #2196F3; }
        .badge-failed { background: rgba(244, 67, 54, 0.2); color: #f44336; }
        
        /* Code blocks */
        .code {
            background: #0d1117;
            border-radius: 8px;
            padding: 15px;
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 0.85rem;
            overflow-x: auto;
            white-space: pre-wrap;
            color: #c9d1d9;
            max-height: 400px;
            overflow-y: auto;
        }
        
        /* Buttons */
        .btn {
            display: inline-block;
            padding: 10px 20px;
            background: linear-gradient(90deg, #00d4ff, #7b2cbf);
            border: none;
            border-radius: 6px;
            color: white;
            font-weight: 500;
            cursor: pointer;
            text-decoration: none;
            transition: opacity 0.3s;
        }
        .btn:hover { opacity: 0.8; }
        .btn-secondary {
            background: rgba(255,255,255,0.1);
            border: 1px solid rgba(255,255,255,0.2);
        }
        
        /* Info box */
        .info { background: rgba(33, 150, 243, 0.1); border-left: 4px solid #2196F3; padding: 15px; margin: 15px 0; }
        .warning { background: rgba(255, 152, 0, 0.1); border-left: 4px solid #FF9800; padding: 15px; margin: 15px 0; }
        
        /* Details list */
        .details-list { list-style: none; }
        .details-list li { padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.05); }
        .details-list li:last-child { border-bottom: none; }
        .details-list .label { color: #888; display: inline-block; width: 120px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>AI Factory Benchmark Framework</h1>
        <p>MeluXina Supercomputer</p>
    </div>
    
    <div class="container">
        <div class="nav">
            <a href="/" class="{{ 'active' if page == 'dashboard' else '' }}">Dashboard</a>
            <a href="/benchmarks" class="{{ 'active' if page == 'benchmarks' else '' }}">Benchmarks</a>
            <a href="/metrics" class="{{ 'active' if page == 'metrics' else '' }}">Metrics</a>
            <a href="/reports" class="{{ 'active' if page == 'reports' else '' }}">Reports</a>
            <a href="/cli" class="{{ 'active' if page == 'cli' else '' }}">CLI Reference</a>
        </div>
        
        {% block content %}{% endblock %}
    </div>
</body>
</html>
"""

DASHBOARD_TEMPLATE = """
{% extends "base" %}
{% block content %}
<div class="stats-grid">
    <div class="stat-card">
        <div class="value">{{ total }}</div>
        <div class="label">Total Benchmarks</div>
    </div>
    <div class="stat-card">
        <div class="value">{{ postgres }}</div>
        <div class="label">PostgreSQL</div>
    </div>
    <div class="stat-card">
        <div class="value">{{ llm }}</div>
        <div class="label">LLM Services</div>
    </div>
    <div class="stat-card">
        <div class="value">{{ vector }}</div>
        <div class="label">Vector DBs</div>
    </div>
</div>

<div class="card">
    <h2> Recent Benchmarks</h2>
    {% if benchmarks %}
    <table class="table">
        <thead>
            <tr>
                <th>ID</th>
                <th>Service</th>
                <th>Job ID</th>
                <th>Clients</th>
                <th>Created</th>
                <th>Actions</th>
            </tr>
        </thead>
        <tbody>
            {% for b in benchmarks[:10] %}
            <tr>
                <td><strong>#{{ b.benchmark_id }}</strong></td>
                <td>{{ b.service_name or '?' }}</td>
                <td>{{ b.service_job_id or '?' }}</td>
                <td>{{ b.num_clients }}</td>
                <td>{{ b.created_at.strftime('%m/%d %H:%M') if b.created_at else '?' }}</td>
                <td><a href="/benchmark/{{ b.benchmark_id }}">View Details →</a></td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% else %}
    <div class="info">No benchmarks found. Run your first benchmark using the CLI!</div>
    {% endif %}
</div>

<div class="card">
    <h2> Quick Start</h2>
    <div class="code">
# Run a benchmark
python src/frontend.py examples/recipe_postgres.yaml

# Or use interactive mode
python src/frontend.py --ui
    </div>
</div>
{% endblock %}
"""

BENCHMARK_DETAIL_TEMPLATE = """
{% extends "base" %}
{% block content %}
<div class="card">
    <h2>Benchmark #{{ summary.benchmark_id }} - {{ summary.service_name or 'Unknown' }}</h2>
    
    <h3>Service</h3>
    <ul class="details-list">
        <li><span class="label">Name:</span> {{ summary.service_name or '?' }}</li>
        <li><span class="label">Job ID:</span> {{ summary.service_job_id or '?' }}</li>
        <li><span class="label">Hostname:</span> {{ summary.service_hostname or '?' }}</li>
        <li><span class="label">Image:</span> {{ summary.service_image or '?' }}</li>
    </ul>
    
    <h3>Clients ({{ summary.clients|length }})</h3>
    {% if summary.clients %}
    <ul class="details-list">
        {% for c in summary.clients %}
        <li>
            <strong>{{ c.name or '?' }}</strong> - Job {{ c.job_id or '?' }}
            {% if c.hostname %} on {{ c.hostname }}{% endif %}
        </li>
        {% endfor %}
    </ul>
    {% else %}
    <p style="color: #888;">No clients</p>
    {% endif %}
    
    <h3>Info</h3>
    <ul class="details-list">
        <li><span class="label">Created:</span> {{ summary.created_at.strftime('%Y-%m-%d %H:%M:%S') if summary.created_at else '?' }}</li>
        <li><span class="label">Log Dir:</span> {{ summary.log_dir or '?' }}</li>
    </ul>
</div>

<div class="card">
    <h2>💻 CLI Commands</h2>
    <div class="code">
# Watch status
python src/frontend.py --watch {{ summary.benchmark_id }}

# View logs
python src/frontend.py --logs {{ summary.benchmark_id }}

# Collect metrics
python src/frontend.py --metrics {{ summary.benchmark_id }}

# Stop benchmark
python src/frontend.py --stop {{ summary.benchmark_id }}
    </div>
</div>

<a href="/" class="btn btn-secondary">← Back to Dashboard</a>
{% endblock %}
"""

BENCHMARKS_TEMPLATE = """
{% extends "base" %}
{% block content %}
<div class="card">
    <h2>📋 All Benchmarks</h2>
    {% if benchmarks %}
    <table class="table">
        <thead>
            <tr>
                <th>ID</th>
                <th>Service</th>
                <th>Job ID</th>
                <th>Clients</th>
                <th>Created</th>
                <th>Actions</th>
            </tr>
        </thead>
        <tbody>
            {% for b in benchmarks %}
            <tr>
                <td><strong>#{{ b.benchmark_id }}</strong></td>
                <td>{{ b.service_name or '?' }}</td>
                <td>{{ b.service_job_id or '?' }}</td>
                <td>{{ b.num_clients }}</td>
                <td>{{ b.created_at.strftime('%Y-%m-%d %H:%M') if b.created_at else '?' }}</td>
                <td><a href="/benchmark/{{ b.benchmark_id }}">View →</a></td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% else %}
    <div class="info">No benchmarks found.</div>
    {% endif %}
</div>
{% endblock %}
"""

CLI_TEMPLATE = """
{% extends "base" %}
{% block content %}
<div class="card">
    <h2>💻 CLI Reference</h2>
    
    <h3>Interactive Mode</h3>
    <div class="code">python src/frontend.py --ui</div>
    
    <h3>Run Benchmark</h3>
    <div class="code">python src/frontend.py examples/recipe_postgres.yaml
python src/frontend.py examples/recipe_ollama.yaml
python src/frontend.py examples/recipe_vllm.yaml</div>
    
    <h3>List Benchmarks</h3>
    <div class="code">python src/frontend.py --list</div>
    
    <h3>View Benchmark Summary</h3>
    <div class="code">python src/frontend.py --summary BENCHMARK_ID</div>
    
    <h3>Watch Live Status</h3>
    <div class="code">python src/frontend.py --watch BENCHMARK_ID</div>
    
    <h3>View Logs</h3>
    <div class="code">python src/frontend.py --logs BENCHMARK_ID</div>
    
    <h3>Collect Metrics</h3>
    <div class="code">python src/frontend.py --metrics BENCHMARK_ID</div>
    
    <h3>Stop Benchmark</h3>
    <div class="code">python src/frontend.py --stop BENCHMARK_ID</div>
    
    <h3>Launch Web UI</h3>
    <div class="code">python src/web/flask_app.py</div>
</div>
{% endblock %}
"""

METRICS_TEMPLATE = """
{% extends "base" %}
{% block content %}
<div class="card">
    <h2>📊 Benchmark Metrics</h2>
    {% if benchmarks %}
    <div class="stats-grid">
        {% for b in benchmarks[:5] %}
        <div class="stat-card">
            <div class="value">#{{ b.benchmark_id }}</div>
            <div class="label">{{ b.service_name or 'Unknown' }}</div>
        </div>
        {% endfor %}
    </div>
    
    <h3>Recent Performance</h3>
    <table class="table">
        <thead>
            <tr>
                <th>Benchmark</th>
                <th>Service</th>
                <th>Status</th>
                <th>Actions</th>
            </tr>
        </thead>
        <tbody>
            {% for b in benchmarks[:10] %}
            <tr>
                <td><strong>#{{ b.benchmark_id }}</strong></td>
                <td>{{ b.service_name or '?' }}</td>
                <td>
                    {% if b.service_job_id %}
                        <span style="color: #4caf50;">Running</span>
                    {% else %}
                        <span style="color: #888;">Unknown</span>
                    {% endif %}
                </td>
                <td>
                    <a href="/benchmark/{{ b.benchmark_id }}/metrics" class="btn btn-secondary" style="padding: 5px 10px; font-size: 0.85rem;">View Metrics</a>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% else %}
    <div class="info">No benchmarks found. Run your first benchmark using the CLI!</div>
    {% endif %}
</div>

<div class="card">
    <h2>📈 Performance Trends</h2>
    <div class="info">
        <strong>Coming Soon:</strong> Interactive charts showing performance trends over time.
        <br><br>
        For now, check individual benchmark metrics using the View Metrics button above.
    </div>
</div>
{% endblock %}
"""

REPORTS_TEMPLATE = """
{% extends "base" %}
{% block content %}
<div class="card">
    <h2>📄 Benchmark Reports</h2>
    {% if benchmark_data %}
    <div class="info">
        <strong>💡 Tip:</strong> Reports are automatically generated when benchmarks complete.
        If you don't see a report, make sure the benchmark has finished and artifacts were collected.
    </div>
    
    <h3>Available Reports</h3>
    <table class="table">
        <thead>
            <tr>
                <th>Benchmark</th>
                <th>Service</th>
                <th>Report Status</th>
                <th>Actions</th>
            </tr>
        </thead>
        <tbody>
            {% for item in benchmark_data[:20] %}
            <tr>
                <td><strong>#{{ item.benchmark.benchmark_id }}</strong></td>
                <td>{{ item.benchmark.service_name or '?' }}</td>
                <td>
                    {% if item.has_report %}
                        <span style="color: #4caf50;">✓ Available</span>
                    {% elif item.has_artifacts %}
                        <span style="color: #2196f3;">📊 Ready to Generate</span>
                    {% else %}
                        <span style="color: #ff9800;">⏳ Needs Collection</span>
                    {% endif %}
                </td>
                <td>
                    {% if item.has_report %}
                        <a href="/benchmark/{{ item.benchmark.benchmark_id }}/report" class="btn btn-secondary" style="padding: 5px 10px; font-size: 0.85rem;">View Report</a>
                        {% if item.has_plots %}
                        <a href="/benchmark/{{ item.benchmark.benchmark_id }}/plots" class="btn btn-secondary" style="padding: 5px 10px; font-size: 0.85rem; margin-left: 5px;">View Plots</a>
                        {% endif %}
                    {% elif item.has_artifacts %}
                        <a href="/benchmark/{{ item.benchmark.benchmark_id }}/report" class="btn btn-secondary" style="padding: 5px 10px; font-size: 0.85rem;">Generate Report</a>
                    {% else %}
                        <a href="/benchmark/{{ item.benchmark.benchmark_id }}/collect" class="btn" style="padding: 5px 10px; font-size: 0.85rem;">Collect Artifacts</a>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% else %}
    <div class="info">No benchmarks found. Run your first benchmark using the CLI!</div>
    {% endif %}
</div>

<div class="card">
    <h2>🔍 How to Generate Reports</h2>
    <div class="code">
# Reports are generated automatically when benchmarks complete!

# Or generate manually:
python src/frontend.py --report BENCHMARK_ID

# Compare two benchmarks:
python src/frontend.py --compare BASELINE_ID CURRENT_ID
    </div>
</div>
{% endblock %}
"""

# =============================================================================
# TEMPLATE RENDERING
# =============================================================================


def render(template_content, **kwargs):
    """Render a template with base template."""
    from jinja2 import Environment, BaseLoader

    env = Environment(loader=BaseLoader())

    # Register base template
    base_tmpl = env.from_string(BASE_TEMPLATE)

    # Create child template that extends base
    full_template = template_content.replace('{% extends "base" %}', "")
    full_template = BASE_TEMPLATE.replace(
        "{% block content %}{% endblock %}",
        full_template.replace('{% extends "base" %}', "")
        .replace("{% block content %}", "")
        .replace("{% endblock %}", ""),
    )

    tmpl = env.from_string(full_template)
    return tmpl.render(**kwargs)


# =============================================================================
# ROUTES
# =============================================================================


@app.route("/")
def dashboard():
    benchmarks = list_all_benchmarks()

    # Count by type
    postgres = sum(
        1 for b in benchmarks if b.service_name and "postgres" in b.service_name.lower()
    )
    llm = sum(
        1
        for b in benchmarks
        if b.service_name
        and any(x in b.service_name.lower() for x in ["vllm", "ollama"])
    )
    vector = sum(
        1 for b in benchmarks if b.service_name and "chroma" in b.service_name.lower()
    )

    return render(
        DASHBOARD_TEMPLATE,
        page="dashboard",
        benchmarks=benchmarks,
        total=len(benchmarks),
        postgres=postgres,
        llm=llm,
        vector=vector,
    )


@app.route("/benchmarks")
def benchmarks_list():
    benchmarks = list_all_benchmarks()
    return render(BENCHMARKS_TEMPLATE, page="benchmarks", benchmarks=benchmarks)


@app.route("/benchmark/<benchmark_id>")
def benchmark_detail(benchmark_id):
    summary = get_benchmark_summary(benchmark_id)
    if not summary:
        return "Benchmark not found", 404
    return render(BENCHMARK_DETAIL_TEMPLATE, page="benchmarks", summary=summary)


@app.route("/cli")
def cli_reference():
    return render(CLI_TEMPLATE, page="cli")


@app.route("/metrics")
def metrics_page():
    benchmarks = list_all_benchmarks()
    return render(METRICS_TEMPLATE, page="metrics", benchmarks=benchmarks)


@app.route("/reports")
def reports_page():
    benchmarks = list_all_benchmarks()

    # Check which benchmarks have reports available
    benchmark_data = []
    for b in benchmarks:
        report_path = Path(f"reports/{b.benchmark_id}/report.md")
        plots_path = Path(f"reports/{b.benchmark_id}/plots/latency_percentiles.png")
        requests_path = Path(f"results/{b.benchmark_id}/requests.jsonl")

        benchmark_data.append(
            {
                "benchmark": b,
                "has_report": report_path.exists(),
                "has_plots": plots_path.exists(),
                "has_artifacts": requests_path.exists(),
            }
        )

    return render(REPORTS_TEMPLATE, page="reports", benchmark_data=benchmark_data)


@app.route("/benchmark/<benchmark_id>/collect")
def collect_artifacts(benchmark_id):
    """Collect artifacts for a benchmark from the cluster."""
    try:
        # Get target from run.json
        run_data = read_run_json(benchmark_id)
        target = run_data.get("target", "meluxina") if run_data else "meluxina"

        # Collect artifacts
        success = collect_benchmark_artifacts(benchmark_id, target)

        if success:
            # Try to generate report automatically
            try:
                generate_benchmark_report(benchmark_id)
                return redirect(f"/benchmark/{benchmark_id}/report")
            except:
                return redirect("/reports")
        else:
            return (
                "Failed to collect artifacts. Make sure benchmark has completed.",
                500,
            )
    except Exception as e:
        return f"Error collecting artifacts: {e}", 500


@app.route("/benchmark/<benchmark_id>/report")
def benchmark_report(benchmark_id):
    """Display the generated report for a benchmark."""
    report_path = Path(f"reports/{benchmark_id}/report.md")
    if not report_path.exists():
        # Try to generate it if it doesn't exist
        try:
            generate_benchmark_report(benchmark_id)
        except Exception as e:
            return f"Report not found and could not be generated: {e}", 404

    # Read and display the report
    with open(report_path) as f:
        report_content = f.read()

    # Convert markdown to HTML for display
    import markdown

    html_content = markdown.markdown(
        report_content, extensions=["tables", "fenced_code"]
    )

    report_template = """
{% extends "base" %}
{% block content %}
<div class="card">
    <h2>📄 Report for Benchmark #{{ benchmark_id }}</h2>
    <div style="background: rgba(255,255,255,0.05); padding: 20px; border-radius: 8px;">
        {{ html_content | safe }}
    </div>
    <br>
    <a href="/reports" class="btn btn-secondary">← Back to Reports</a>
</div>
{% endblock %}
"""

    return render(
        report_template,
        page="reports",
        benchmark_id=benchmark_id,
        html_content=html_content,
    )


@app.route("/benchmark/<benchmark_id>/plots")
def benchmark_plots(benchmark_id):
    """Display plots for a benchmark."""
    plots_dir = Path(f"reports/{benchmark_id}/plots")
    if not plots_dir.exists():
        return "No plots found", 404

    # List all plot files
    plot_files = list(plots_dir.glob("*.png"))

    plots_template = """
{% extends "base" %}
{% block content %}
<div class="card">
    <h2>📊 Plots for Benchmark #{{ benchmark_id }}</h2>
    {% if plot_files %}
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(500px, 1fr)); gap: 20px;">
        {% for plot in plot_files %}
            <div>
                <h3>{{ plot.stem.replace('_', ' ').title() }}</h3>
                <img src="/benchmark/{{ benchmark_id }}/plot/{{ plot.name }}" 
                     style="width: 100%; border-radius: 8px; background: white;">
            </div>
        {% endfor %}
        </div>
    {% else %}
        <div class="info">No plots found for this benchmark.</div>
    {% endif %}
    <br>
    <a href="/reports" class="btn btn-secondary">← Back to Reports</a>
</div>
{% endblock %}
"""

    return render(
        plots_template, page="reports", benchmark_id=benchmark_id, plot_files=plot_files
    )


@app.route("/benchmark/<benchmark_id>/plot/<plot_name>")
def serve_plot(benchmark_id, plot_name):
    """Serve individual plot files."""
    # Use absolute path from project root
    plot_path = (
        Path(__file__).parent.parent.parent
        / f"reports/{benchmark_id}/plots/{plot_name}"
    )
    if not plot_path.exists():
        return "Plot not found", 404
    return send_file(plot_path)


@app.route("/benchmark/<benchmark_id>/metrics")
def benchmark_metrics(benchmark_id):
    """Display detailed metrics for a benchmark."""
    # Try to read summary
    summary = read_summary_json(benchmark_id)
    if not summary:
        # Try to generate it
        try:
            from aggregator import aggregate_benchmark

            aggregate_benchmark(benchmark_id)
            summary = read_summary_json(benchmark_id)
            if not summary:
                return (
                    "Metrics not available. Ensure benchmark has completed and artifacts were collected.",
                    404,
                )
        except Exception as e:
            return (
                f"Metrics not available: {e}<br><br>Make sure to run: python src/frontend.py --collect {benchmark_id}",
                404,
            )

    metrics_template = """
{% extends "base" %}
{% block content %}
<div class="card">
    <h2>📊 Metrics for Benchmark #{{ benchmark_id }}</h2>
    
    <h3>Performance Summary</h3>
    <div class="stats-grid">
        <div class="stat-card">
            <div class="value">{{ summary['total_requests'] }}</div>
            <div class="label">Total Requests</div>
        </div>
        <div class="stat-card">
            <div class="value">{{ "%.1f"|format(summary['success_rate']) }}%</div>
            <div class="label">Success Rate</div>
        </div>
        <div class="stat-card">
            <div class="value">{{ "%.3f"|format(summary['latency_s']['avg']) }}s</div>
            <div class="label">Avg Latency</div>
        </div>
        <div class="stat-card">
            <div class="value">{{ "%.2f"|format(summary['requests_per_second']) }}</div>
            <div class="label">RPS</div>
        </div>
    </div>
    
    <h3>Latency Percentiles</h3>
    <table class="table">
        <thead>
            <tr>
                <th>P50</th>
                <th>P90</th>
                <th>P95</th>
                <th>P99</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td>{{ "%.3f"|format(summary['latency_s']['p50']) }}s</td>
                <td>{{ "%.3f"|format(summary['latency_s']['p90']) }}s</td>
                <td>{{ "%.3f"|format(summary['latency_s']['p95']) }}s</td>
                <td>{{ "%.3f"|format(summary['latency_s']['p99']) }}s</td>
            </tr>
        </tbody>
    </table>
    
    {% if summary.get('error_summary') %}
    <h3>Error Summary</h3>
    <table class="table">
        <thead>
            <tr>
                <th>Error Type</th>
                <th>Count</th>
            </tr>
        </thead>
        <tbody>
            {% for error, count in summary['error_summary'].items() %}
            <tr>
                <td>{{ error }}</td>
                <td>{{ count }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% endif %}
    
    <br>
    <a href="/metrics" class="btn btn-secondary">← Back to Metrics</a>
</div>
{% endblock %}
"""

    return render(
        metrics_template, page="metrics", benchmark_id=benchmark_id, summary=summary
    )


@app.route("/api/benchmarks")
def api_benchmarks():
    """API endpoint for benchmarks list."""
    benchmarks = list_all_benchmarks()
    return jsonify(
        [
            {
                "id": b.benchmark_id,
                "service_name": b.service_name,
                "service_job_id": b.service_job_id,
                "num_clients": b.num_clients,
                "created_at": b.created_at.isoformat() if b.created_at else None,
            }
            for b in benchmarks
        ]
    )


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("AI Factory Benchmark")
    print("=" * 50)
    print("\n   Open http://localhost:5000 in your browser\n")
    print("   Press Ctrl+C to stop\n")
    print("=" * 50 + "\n")

    app.run(host="0.0.0.0", port=5000, debug=True)
