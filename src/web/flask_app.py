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

from flask import Flask, jsonify, redirect, send_file, request
import json
from pathlib import Path as FilePath

from infra.storage import (
    list_all_benchmarks,
    get_benchmark_summary,
)
from reporting.artifacts import read_run_json, read_summary_json
from reporting.reporter import generate_benchmark_report
from core.collector import collect_benchmark_artifacts
from core.lifecycle import get_benchmark_target, handle_benchmark_completion, check_benchmark_complete
from monitoring.stack import StackManager
from monitoring.monitor import format_prometheus_metrics, BenchmarkMetrics
from core.manager import Manager


def get_available_recipes():
    """Find all available recipe files in examples directory."""
    examples_dir = FilePath(__file__).parent.parent.parent / "examples"
    if not examples_dir.exists():
        return []
    recipes = list(examples_dir.glob("recipe_*.yaml"))
    return sorted(recipes)

app = Flask(__name__)

# Global state for async deployment jobs
# {job_id: {"status": "running"|"done"|"error", "logs": [], "benchmark_id": None}}
DEPLOYMENT_JOBS = {}
import threading
import uuid
import time
import subprocess
import re
stack_manager = StackManager()

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
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {
            --bg-body: #1c1c1e;
            --bg-card: #2c2c2e;
            --bg-card-hover: #3a3a3c;
            --text-primary: #ffffff;
            --text-secondary: #8e8e93;
            --accent-blue: #0a84ff;
            --accent-green: #30d158;
            --accent-red: #ff453a;
            --accent-orange: #ff9f0a;
            --border-color: rgba(255, 255, 255, 0.1);
            --font-stack: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", Arial, sans-serif;
        }
        
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: var(--font-stack);
            background-color: var(--bg-body);
            color: var(--text-primary);
            -webkit-font-smoothing: antialiased;
            line-height: 1.5;
            min-height: 100vh;
        }
        
        .container { max-width: 1100px; margin: 0 auto; padding: 40px 20px; }
        
        /* Header */
        .header {
            margin-bottom: 40px;
            padding-bottom: 20px;
            border-bottom: 1px solid var(--border-color);
        }
        .header h1 { 
            font-size: 24px; 
            font-weight: 600;
            letter-spacing: -0.02em;
            color: var(--text-primary);
            margin-bottom: 4px;
        }
        .header p { 
            color: var(--text-secondary); 
            font-size: 15px; 
        }
        
        /* Navigation */
        .nav { 
            display: flex; 
            gap: 24px; 
            margin-bottom: 40px; 
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 15px;
        }
        .nav a {
            color: var(--text-secondary);
            text-decoration: none;
            font-size: 14px;
            font-weight: 500;
            transition: color 0.2s;
            padding-bottom: 15px;
            margin-bottom: -16px;
        }
        .nav a:hover { color: var(--text-primary); }
        .nav a.active {
            color: var(--accent-blue);
            border-bottom: 2px solid var(--accent-blue);
        }
        
        /* Cards */
        .card {
            background-color: var(--bg-card);
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }
        .card h2 { 
            font-size: 19px; 
            font-weight: 600; 
            margin-bottom: 20px; 
            color: var(--text-primary);
        }
        .card h3 {
            font-size: 15px;
            font-weight: 600;
            color: var(--text-primary);
            margin: 20px 0 12px;
        }
        
        /* Stats Grid */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 20px;
            text-align: center;
        }
        .stat-card .value { 
            font-size: 28px; 
            font-weight: 600; 
            color: var(--text-primary); 
            margin-bottom: 4px;
            letter-spacing: -0.02em;
        }
        .stat-card .label { color: var(--text-secondary); font-size: 13px; }
        
        /* Table */
        .table { width: 100%; border-collapse: collapse; font-size: 14px; }
        .table th { 
            text-align: left; 
            color: var(--text-secondary); 
            font-weight: 500; 
            padding: 12px 0;
            border-bottom: 1px solid var(--border-color);
        }
        .table td { 
            padding: 14px 0; 
            border-bottom: 1px solid var(--border-color);
            color: var(--text-primary);
        }
        .table tr:last-child td { border-bottom: none; }
        .table a { color: var(--accent-blue); text-decoration: none; }
        .table a:hover { text-decoration: underline; }
        
        /* Badges */
        .badge {
            display: inline-flex;
            align-items: center;
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 500;
            line-height: 1;
        }
        .badge-running { background: rgba(10, 132, 255, 0.15); color: var(--accent-blue); }
        .badge-completed { background: rgba(48, 209, 88, 0.15); color: var(--accent-green); }
        .badge-failed { background: rgba(255, 69, 58, 0.15); color: var(--accent-red); }
        .badge-pending { background: rgba(255, 159, 10, 0.15); color: var(--accent-orange); }
        
        /* Buttons */
        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 8px 16px;
            background-color: var(--accent-blue);
            color: white;
            border-radius: 8px;
            text-decoration: none;
            font-size: 14px;
            font-weight: 500;
            border: none;
            cursor: pointer;
            transition: background-color 0.2s;
        }
        .btn:hover { background-color: #007aff; }
        .btn-secondary {
            background-color: rgba(255, 255, 255, 0.08);
            color: var(--text-primary);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        .btn-secondary:hover { background-color: rgba(255, 255, 255, 0.15); border-color: rgba(255, 255, 255, 0.3); }
        
        /* Code */
        .code {
            font-family: "SF Mono", Menlo, Monaco, Consolas, monospace;
            font-size: 13px;
            background-color: #1c1c1e;
            padding: 16px;
            border-radius: 8px;
            color: var(--text-primary);
            border: 1px solid var(--border-color);
            overflow-x: auto;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        
        /* Info/Warning */
        .info, .warning {
            padding: 16px;
            border-radius: 10px;
            background-color: rgba(10, 132, 255, 0.1);
            color: var(--text-primary);
            font-size: 14px;
            border: 1px solid rgba(10, 132, 255, 0.2);
            margin-bottom: 24px;
        }
        .warning {
            background-color: rgba(255, 159, 10, 0.1);
            border-color: rgba(255, 159, 10, 0.2);
        }
        
        /* Details List */
        .details-list { list-style: none; }
        .details-list li { 
            padding: 12px 0; 
            border-bottom: 1px solid var(--border-color); 
            display: flex;
            align-items: center;
        }
        .details-list li:last-child { border-bottom: none; }
        .details-list .label { 
            color: var(--text-secondary); 
            width: 140px; 
            flex-shrink: 0;
            font-size: 14px;
        }
        
        /* Charts */
        canvas { filter: saturate(1.1); }

        /* Apple-style Loading Spinner */
        .loading-spinner {
            display: inline-block;
            width: 16px;
            height: 16px;
            border: 2px solid rgba(255, 255, 255, 0.3);
            border-radius: 50%;
            border-top-color: #fff;
            animation: spin 0.8s ease-in-out infinite;
            margin-right: 8px;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        .btn.loading {
            pointer-events: none;
            opacity: 0.7;
        }
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
            <a href="/run" class="{{ 'active' if page == 'run' else '' }}">Run Recipe</a>
            <a href="/benchmarks" class="{{ 'active' if page == 'benchmarks' else '' }}">Benchmarks</a>
            <a href="/monitoring" class="{{ 'active' if page == 'monitoring' else '' }}">Monitoring</a>
            <a href="/metrics-dashboard" class="{{ 'active' if page == 'metrics' else '' }}">Metrics</a>
            <a href="/reports" class="{{ 'active' if page == 'reports' else '' }}">Reports</a>
            <a href="/cli" class="{{ 'active' if page == 'cli' else '' }}">CLI Reference</a>
        </div>
        
        {% block content %}{% endblock %}
    </div>
    </div>
    
    <script>
        function startLoading(btn) {
            // Add loading class for opacity/pointer-events
            btn.classList.add('loading');
            
            // Save original text
            if (!btn.dataset.originalText) {
                btn.dataset.originalText = btn.innerHTML;
            }
            
            // Insert spinner and change text to "Loading..." if it's not already
            if (!btn.innerHTML.includes('loading-spinner')) {
                btn.innerHTML = '<span class="loading-spinner"></span> Loading...';
            }
        }
    </script>
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
    <div class="stat-card">
        <div class="value">{{ redis }}</div>
        <div class="label">Redis/Cache</div>
    </div>
</div>

<div style="display: flex; gap: 20px; flex-wrap: wrap; margin-bottom: 20px;">
    <div class="card" style="flex: 1; min-width: 300px;">
        <h2>Service Distribution</h2>
        <canvas id="serviceChart" style="max-height: 250px;"></canvas>
    </div>
    <div class="card" style="flex: 1; min-width: 300px;">
        <h2>Recent Performance</h2>
        {% if recent_metrics %}
        <table class="table">
            <thead>
                <tr>
                    <th>Benchmark</th>
                    <th>RPS</th>
                    <th>P99</th>
                    <th>Success</th>
                </tr>
            </thead>
            <tbody>
                {% for m in recent_metrics[:5] %}
                <tr>
                    <td><a href="/benchmark/{{ m.id }}/metrics">{{ m.id }}</a></td>
                    <td>{{ "%.1f"|format(m.rps) }}</td>
                    <td>{{ "%.2f"|format(m.p99) }}s</td>
                    <td style="color: {{ '#4CAF50' if m.success >= 99 else '#FF9800' if m.success >= 90 else '#f44336' }}">{{ "%.0f"|format(m.success) }}%</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <p style="color: #888; padding: 20px;">No metrics collected yet. Run benchmarks and collect artifacts.</p>
        {% endif %}
    </div>
</div>

<div class="card">
    <h2>Recent Benchmarks</h2>
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
                <td>
                    <a href="/benchmark/{{ b.benchmark_id }}">Details</a> |
                    <a href="/benchmark/{{ b.benchmark_id }}/metrics">Metrics</a>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    <div style="margin-top: 10px;">
        <a href="/benchmarks" class="btn btn-secondary">View All Benchmarks</a>
    </div>
    {% else %}
    <div class="info">No benchmarks found. Run your first benchmark!</div>
    {% endif %}
</div>

<div class="card">
    <h2>Quick Start</h2>
    <div class="code">
# Run a benchmark from recipe
python src/frontend.py examples/recipe_ollama.yaml

# Or use interactive UI
python src/frontend.py --ui

# Start monitoring stack
python src/frontend.py --monitor-stack start
    </div>
</div>

<script>
// Service Distribution Pie Chart
const serviceCtx = document.getElementById('serviceChart').getContext('2d');
new Chart(serviceCtx, {
    type: 'doughnut',
    data: {
        labels: ['PostgreSQL', 'LLM (vLLM/Ollama)', 'Vector DBs', 'Redis/Cache', 'Other'],
        datasets: [{
            data: [{{ postgres }}, {{ llm }}, {{ vector }}, {{ redis }}, {{ other }}],
            backgroundColor: [
                'rgba(33, 150, 243, 0.8)',
                'rgba(156, 39, 176, 0.8)',
                'rgba(0, 188, 212, 0.8)',
                'rgba(244, 67, 54, 0.8)',
                'rgba(158, 158, 158, 0.8)'
            ],
            borderWidth: 1
        }]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: { position: 'right', labels: { color: '#e0e0e0', boxWidth: 12 } }
        }
    }
});
</script>
{% endblock %}
"""

BENCHMARK_DETAIL_TEMPLATE = """
{% extends "base" %}
{% block content %}
<div class="card">
    <h2>Benchmark #{{ summary.benchmark_id }} - {{ summary.service_name or 'Unknown' }}</h2>
    
    <div style="margin-bottom: 24px;">
        <a href="/benchmark/{{ summary.benchmark_id }}/watch" class="btn">Watch Status</a>
        <a href="/benchmark/{{ summary.benchmark_id }}/logs" class="btn btn-secondary">Logs</a>
        <a href="/benchmark/{{ summary.benchmark_id }}/metrics" class="btn btn-secondary">Metrics</a>
        <a href="/benchmark/{{ summary.benchmark_id }}/report" class="btn btn-secondary">Report</a>
        <a href="/benchmark/{{ summary.benchmark_id }}/collect" class="btn btn-secondary" onclick="startLoading(this)">Collect</a>
        <a href="/benchmark/{{ summary.benchmark_id }}/rerun" class="btn btn-secondary" onclick="startLoading(this)">Rerun</a>
        <a href="/compare?baseline={{ summary.benchmark_id }}" class="btn btn-secondary">Compare</a>
        {% if not is_completed %}
        <a href="/benchmark/{{ summary.benchmark_id }}/stop" class="btn btn-secondary" style="color: #ff453a; border-color: rgba(255, 69, 58, 0.3);" onclick="if(confirm('Stop this benchmark?')) startLoading(this); else return false;">Stop</a>
        {% endif %}
    </div>
    
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
    <h2>CLI Commands</h2>
    <div class="code">
# Watch status
python src/frontend.py --watch {{ summary.benchmark_id }}

# View logs
python src/frontend.py --logs {{ summary.benchmark_id }}

# Collect artifacts & generate report
python src/frontend.py --collect {{ summary.benchmark_id }}
python src/frontend.py --report {{ summary.benchmark_id }}

# Stop benchmark
python src/frontend.py --stop {{ summary.benchmark_id }}
    </div>
</div>

<a href="/" class="btn btn-secondary">Back to Dashboard</a>
{% endblock %}
"""

BENCHMARKS_TEMPLATE = """
{% extends "base" %}
{% block content %}
<div class="card">
    <h2>All Benchmarks</h2>
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
                <td><a href="/benchmark/{{ b.benchmark_id }}">View</a></td>
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
    <h2>CLI Reference</h2>
    
    <h3>Interactive Mode</h3>
    <div class="code">python src/frontend.py --ui</div>
    
    <h3>Run Benchmark</h3>
    <div class="code">python src/frontend.py examples/recipe_postgres.yaml</div>
    <div class="code">python src/frontend.py examples/recipe_ollama.yaml</div>
    <div class="code">python src/frontend.py examples/recipe_vllm.yaml</div>
    
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
    
    <h3>Generate Report</h3>
    <div class="code">python src/frontend.py --report BENCHMARK_ID</div>
    
    <h3>Compare Benchmarks</h3>
    <div class="code">python src/frontend.py --compare BASELINE_ID CURRENT_ID</div>
    
    <h3>Launch Web UI</h3>
    <div class="code">python src/web/flask_app.py</div>
</div>
{% endblock %}
"""

RUN_RECIPE_TEMPLATE = """
{% extends "base" %}
{% block content %}
<div class="card">
    <h2>Run a Benchmark Recipe</h2>
    
    <div id="deployment-status" style="display: none;">
        <h3>Deploying Benchmark...</h3>
        <div id="deployment-logs" class="code" style="height: 400px; overflow-y: auto; white-space: pre-wrap; font-size: 0.9em; background: #0d1117; color: #c9d1d9; border: 1px solid #30363d;">Initializing...</div>
        <div id="deployment-spinner" style="margin-top: 15px; display: flex; align-items: center; justify-content: center;">
            <div class="loading-spinner"></div>
            <span style="color: #888; font-size: 0.9em; margin-left: 10px;">Waiting for deployment to complete...</span>
        </div>
    </div>
    
    <div id="recipe-selector">
        {% if message %}
        <div class="{{ 'info' if success else 'warning' }}">
            {{ message }}
        </div>
        {% endif %}
        
        <h3>Available Recipes</h3>
        {% if recipes %}
        <form id="run-form" onsubmit="runRecipe(event)">
            <table class="table">
                <thead>
                    <tr>
                        <th style="width: 50px;">Select</th>
                        <th>Recipe</th>
                        <th>Description</th>
                    </tr>
                </thead>
                <tbody>
                    {% for recipe in recipes %}
                    <tr>
                        <td><input type="radio" name="recipe" value="{{ recipe.path }}" required></td>
                        <td><strong>{{ recipe.name }}</strong></td>
                        <td style="color: #888;">{{ recipe.filename }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            <br>
            <button type="submit" class="btn">Run Selected Recipe</button>
        </form>
        {% else %}
        <div class="warning">No recipes found in examples/ directory.</div>
        {% endif %}
    </div>
</div>

<div class="card">
    <h2>Recipe Tips</h2>
    <ul class="details-list">
        <li>Recipes define service, client, and benchmark parameters</li>
        <li>Benchmarks run asynchronously on the cluster</li>
        <li>Use "Watch Status" to monitor progress in real-time</li>
        <li>Results are collected automatically when complete</li>
    </ul>
</div>

<script>
function runRecipe(e) {
    e.preventDefault();
    const form = e.target;
    const formData = new FormData(form);
    const recipe = formData.get('recipe');
    
    if (!recipe) {
        alert("Please select a recipe");
        return;
    }
    
    // UI update
    document.getElementById('recipe-selector').style.display = 'none';
    document.getElementById('deployment-status').style.display = 'block';
    
    const logsDiv = document.getElementById('deployment-logs');
    logsDiv.innerHTML = "Initializing deployment...";
    
    // Start deployment
    fetch('/run', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({recipe: recipe})
    })
    .then(res => res.json())
    .then(data => {
        if (data.error) throw new Error(data.error);
        pollStatus(data.job_id);
    })
    .catch(err => {
        logsDiv.innerHTML += "\\n\\nCRITICAL ERROR: " + err.message;
        document.getElementById('deployment-spinner').style.display = 'none';
        
        // Show retry button
        const retryBtn = document.createElement('button');
        retryBtn.className = 'btn btn-secondary';
        retryBtn.innerText = 'Retry';
        retryBtn.onclick = () => window.location.reload();
        logsDiv.parentNode.appendChild(retryBtn);
    });
}

function pollStatus(jobId) {
    const logsDiv = document.getElementById('deployment-logs');
    let lastLogLength = 0;
    
    const interval = setInterval(() => {
        fetch('/api/deployment/' + jobId)
            .then(res => res.json())
            .then(data => {
                // Only update if logs changed to avoid flicker
                if (data.logs.length > lastLogLength) {
                    logsDiv.innerHTML = data.logs.join("");
                    logsDiv.scrollTop = logsDiv.scrollHeight;
                    lastLogLength = data.logs.length;
                }
                
                if (data.status === 'done' || (data.benchmark_id && data.logs.join("").includes("deployed successfully"))) {
                    // Check if we have an ID
                    if (data.benchmark_id) {
                        clearInterval(interval);
                        logsDiv.innerHTML += "\\n\\nDeployment complete! Redirecting to status page...";
                        logsDiv.scrollTop = logsDiv.scrollHeight;
                        setTimeout(() => {
                            window.location.href = '/benchmark/' + data.benchmark_id + '/watch';
                        }, 1500);
                    }
                } else if (data.status === 'error') {
                     clearInterval(interval);
                     document.getElementById('deployment-spinner').style.display = 'none';
                     logsDiv.innerHTML += "\\n\\nDEPLOYMENT FAILED. Check logs above.";
                     logsDiv.scrollTop = logsDiv.scrollHeight;
                     
                     const retryBtn = document.createElement('button');
                     retryBtn.className = 'btn btn-secondary';
                     retryBtn.style.marginTop = '20px';
                     retryBtn.innerText = 'Back to Recipes';
                     retryBtn.onclick = () => window.location.reload();
                     logsDiv.parentNode.appendChild(retryBtn);
                }
            })
            .catch(err => {
                console.error(err);
            });
    }, 1000);
}
</script>
{% endblock %}
"""



WATCH_STATUS_TEMPLATE = """
{% extends "base" %}
{% block content %}
<div class="card">
    <h2>Watch Benchmark #{{ benchmark_id }}</h2>
    
    <div id="status-container">
        <div class="info">Loading status...</div>
    </div>
    
    <div style="margin-top: 24px;">
        <a href="/benchmark/{{ benchmark_id }}" class="btn btn-secondary">View Details</a>
        <a href="/benchmark/{{ benchmark_id }}/stop" class="btn btn-secondary" style="color: #ff453a; border-color: rgba(255, 69, 58, 0.3);" onclick="return confirm('Stop this benchmark?')">Stop Benchmark</a>
    </div>
</div>

<script>
function updateStatus() {
    fetch('/api/benchmark/{{ benchmark_id }}/status')
        .then(response => response.json())
        .then(data => {
            let html = '<div class="stats-grid">';
            html += '<div class="stat-card"><div class="value">' + data.service_status + '</div><div class="label">Service</div></div>';
            html += '<div class="stat-card"><div class="value">' + data.clients_done + '/' + data.clients_total + '</div><div class="label">Clients Done</div></div>';
            html += '</div>';
            
            if (data.services && data.services.length > 0) {
                html += '<h3>Service</h3><table class="table"><thead><tr><th>Job ID</th><th>Name</th><th>Status</th><th>Node</th></tr></thead><tbody>';
                data.services.forEach(s => {
                    html += '<tr><td>' + s.job_id + '</td><td>' + s.name + '</td><td><span class="badge badge-' + s.status.toLowerCase() + '">' + s.status + '</span></td><td>' + (s.hostname || '?') + '</td></tr>';
                });
                html += '</tbody></table>';
            }
            
            if (data.clients && data.clients.length > 0) {
                html += '<h3>Clients</h3><table class="table"><thead><tr><th>Job ID</th><th>Name</th><th>Status</th><th>Node</th></tr></thead><tbody>';
                data.clients.forEach(c => {
                    html += '<tr><td>' + c.job_id + '</td><td>' + c.name + '</td><td><span class="badge badge-' + c.status.toLowerCase() + '">' + c.status + '</span></td><td>' + (c.hostname || '?') + '</td></tr>';
                });
                html += '</tbody></table>';
            }
            
            html += '<p style="color: #888; margin-top: 15px;">Last updated: ' + new Date().toLocaleTimeString() + ' (auto-refreshes every 5s)</p>';
            
            document.getElementById('status-container').innerHTML = html;
            
            // Check if all done
            if (data.all_done) {
                html += '<div class="info" style="margin-top: 20px;"><strong>Benchmark complete!</strong> <a href="/benchmark/' + '{{ benchmark_id }}' + '/report">View Report</a></div>';
                document.getElementById('status-container').innerHTML = html;
            } else {
                setTimeout(updateStatus, 5000);
            }
        })
        .catch(err => {
            document.getElementById('status-container').innerHTML = '<div class="warning">Error loading status: ' + err + '</div>';
            setTimeout(updateStatus, 5000);
        });
}
updateStatus();
</script>
{% endblock %}
"""

LOGS_TEMPLATE = """
{% extends "base" %}
{% block content %}
<div class="card">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
        <h2>Logs for Benchmark #{{ benchmark_id }}</h2>
        <div>
            <button id="check-updates-btn" onclick="checkLogUpdates()" class="btn btn-secondary">Check for Updates</button>
            <a id="update-logs-btn" href="/benchmark/{{ benchmark_id }}/collect" class="btn" onclick="startLoading(this)" style="display: none;">Update Logs</a>
        </div>
    </div>
    
    {% if log_files %}
    <h3>Available Log Files</h3>
    <table class="table">
        <thead>
            <tr>
                <th>File</th>
                <th>Size</th>
                <th>Actions</th>
            </tr>
        </thead>
        <tbody>
            {% for log in log_files %}
            <tr>
                <td><strong>{{ log.name }}</strong></td>
                <td>{{ log.size }}</td>
                <td><a href="/benchmark/{{ benchmark_id }}/log/{{ log.name }}" class="btn btn-secondary" style="padding: 5px 10px; font-size: 0.85rem;">View</a></td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% else %}
    <div class="info">
        <strong>Logs not available yet</strong><br><br>
        Logs become available <em>after</em> the benchmark completes and artifacts are collected from the cluster.
        <br><br>
        <strong>If the benchmark is still running:</strong> Use the <a href="/monitoring">Monitoring page</a> to track progress and view real-time metrics via Prometheus.
        <br><br>
        <strong>If the benchmark has completed:</strong>
        <a href="/benchmark/{{ benchmark_id }}/collect" class="btn" onclick="startLoading(this)" style="margin-top: 5px;">Collect Artifacts from Cluster</a>
    </div>
    {% endif %}
    
    {% if selected_log %}
    <h3>{{ selected_log_name }}</h3>
    <div class="code" style="max-height: 600px;">{{ selected_log }}</div>
    {% endif %}
</div>
<a href="/benchmark/{{ benchmark_id }}" class="btn btn-secondary">Back to Benchmark</a>

<script>
function checkLogUpdates() {
    const btn = document.getElementById('check-updates-btn');
    startLoading(btn);
    
    fetch('/api/benchmark/{{ benchmark_id }}/check_logs')
        .then(response => response.json())
        .then(data => {
            btn.classList.remove('loading');
            btn.innerHTML = 'Check for Updates';
            
            if (data.available) {
                document.getElementById('update-logs-btn').style.display = 'inline-flex';
                // Hide check button when update is available
                btn.style.display = 'none';
                
                // Show notification
                const note = document.createElement('div');
                note.className = 'info';
                note.style.marginBottom = '20px';
                note.innerHTML = '<strong>New logs found!</strong> Remote: ' + data.remote_count + ', Local: ' + data.local_count + '. Click "Update Logs" to download them.';
                btn.parentNode.parentNode.after(note);
            } else {
                if (data.error) {
                    alert('Error checking logs: ' + data.error);
                } else {
                    const originalText = btn.innerHTML;
                    btn.innerHTML = 'No New Updates';
                    setTimeout(() => {
                        btn.innerHTML = originalText;
                    }, 2000);
                }
            }
        })
        .catch(err => {
            btn.classList.remove('loading');
            btn.innerHTML = 'Check Failed';
            console.error(err);
        });
}
</script>
{% endblock %}
"""

METRICS_TEMPLATE = """
{% extends "base" %}
{% block content %}
<div class="card">
    <h2>Benchmark Metrics</h2>
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
                    {% if b.status == "Completed" %}
                         <span class="badge badge-completed">Completed</span>
                    {% elif b.service_job_id %}
                        <span class="badge badge-running">Running</span>
                    {% else %}
                        <span class="badge badge-pending">Unknown</span>
                    {% endif %}
                </td>
                <td>
                    <a href="/benchmark/{{ b.benchmark_id }}/metrics" class="btn btn-secondary">View Metrics</a>
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
    <h2>Performance Trends</h2>
    <div class="info">
        <strong>Coming Soon:</strong> Interactive charts showing performance trends over time.
        <br><br>
        For now, check individual benchmark metrics using the View Metrics button above.
    </div>
</div>
{% endblock %}
"""

COMPARE_TEMPLATE = """
{% extends "base" %}
{% block content %}
<div class="card">
    <h2>Compare Benchmarks</h2>
    
    <form action="/compare" method="GET" id="compareForm">
        <div style="display: flex; gap: 20px; flex-wrap: wrap;">
            <div style="flex: 1; min-width: 300px;">
                <h3>Baseline Benchmark</h3>
                <select name="baseline" class="btn btn-secondary" style="width: 100%; padding: 10px; text-align: left;" required>
                    <option value="">Select Baseline...</option>
                    {% for b in benchmarks %}
                    <option value="{{ b.benchmark_id }}" {% if baseline_id == b.benchmark_id %}selected{% endif %}>
                        #{{ b.benchmark_id }} - {{ b.service_name }} ({{ b.created_at.strftime('%Y-%m-%d %H:%M') if b.created_at else '?' }})
                    </option>
                    {% endfor %}
                </select>
            </div>
            
            <div style="flex: 1; min-width: 300px;">
                <h3>Current Benchmark</h3>
                <select name="current" class="btn btn-secondary" style="width: 100%; padding: 10px; text-align: left;" required>
                    <option value="">Select Current...</option>
                    {% for b in benchmarks %}
                    <option value="{{ b.benchmark_id }}" {% if current_id == b.benchmark_id %}selected{% endif %}>
                        #{{ b.benchmark_id }} - {{ b.service_name }} ({{ b.created_at.strftime('%Y-%m-%d %H:%M') if b.created_at else '?' }})
                    </option>
                    {% endfor %}
                </select>
            </div>
        </div>
        
        <div style="margin-top: 20px; text-align: center;">
            <button type="submit" class="btn">Compare</button>
        </div>
    </form>
</div>

{% if comparison %}
<div class="card">
    <h2>Comparison Results</h2>
    
    <div style="display: flex; justify-content: space-between; margin-bottom: 20px;">
        <div class="stat-card" style="flex: 1; margin-right: 10px;">
            <div class="label">Baseline</div>
            <div class="value" style="font-size: 1.2rem;">#{{ comparison.baseline_id }}</div>
            <div class="label">{{ comparison.baseline }}</div>
        </div>
        <div class="stat-card" style="flex: 1; margin-left: 10px;">
            <div class="label">Current</div>
            <div class="value" style="font-size: 1.2rem;">#{{ comparison.current_id }}</div>
            <div class="label">{{ comparison.current }}</div>
        </div>
    </div>
    
    <div class="info" style="text-align: center; font-size: 1.2rem; background: {{ 'rgba(76, 175, 80, 0.2)' if comparison.verdict == 'PASS' else 'rgba(244, 67, 54, 0.2)' }}; color: {{ '#4CAF50' if comparison.verdict == 'PASS' else '#f44336' }}; border: 1px solid {{ '#4CAF50' if comparison.verdict == 'PASS' else '#f44336' }};">
        Verdict: <strong>{{ comparison.verdict }}</strong>
        {% if comparison.verdict == 'FAIL' %}
        <br>
        <span style="font-size: 0.9rem;">Regression Detected</span>
        {% endif %}
    </div>

    <table class="table">
        <thead>
            <tr>
                <th>Metric</th>
                <th>Baseline</th>
                <th>Current</th>
                <th>Delta</th>
                <th>% Change</th>
                <th>Status</th>
            </tr>
        </thead>
        <tbody>
            {% for key, metric in comparison.metrics.items() %}
            <tr style="{{ 'background: rgba(244, 67, 54, 0.1);' if metric.regression else ('background: rgba(76, 175, 80, 0.1);' if metric.improvement else '') }}">
                <td><strong>{{ metric.label }}</strong></td>
                <td>
                    {% if "Rate" in metric.label %}
                        {{ "%.1f"|format(metric.baseline) }}%
                    {% elif "Latency" in metric.label %}
                        {{ "%.3f"|format(metric.baseline) }}s
                    {% else %}
                        {{ "%.2f"|format(metric.baseline) }}
                    {% endif %}
                </td>
                <td>
                    {% if "Rate" in metric.label %}
                        {{ "%.1f"|format(metric.current) }}%
                    {% elif "Latency" in metric.label %}
                        {{ "%.3f"|format(metric.current) }}s
                    {% else %}
                        {{ "%.2f"|format(metric.current) }}
                    {% endif %}
                </td>
                <td>
                    {% if "Rate" in metric.label %}
                        {{ "%+.1f"|format(metric.delta) }}%
                    {% elif "Latency" in metric.label %}
                        {{ "%+.3f"|format(metric.delta) }}s
                    {% else %}
                        {{ "%+.2f"|format(metric.delta) }}
                    {% endif %}
                </td>
                <td>{{ "%+.1f"|format(metric.percent_change) }}%</td>
                <td>
                    {% if metric.regression %}
                        <span class="badge badge-failed">REGRESSED</span>
                    {% elif metric.improvement %}
                        <span class="badge badge-completed">IMPROVED</span>
                    {% else %}
                        <span class="badge" style="color: #888;">STABLE</span>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
{% endif %}
{% endblock %}
"""

MONITORING_TEMPLATE = """
{% extends "base" %}
{% block content %}
<div class="card">
    <h2>Real-Time Monitoring</h2>
    <div class="info" style="margin-bottom: 20px;">
        <strong>Note:</strong> Use this page to monitor <strong>running benchmarks in real-time</strong>. 
        Prometheus scrapes metrics every 5s from the Flask app. 
        <br>For <strong>completed benchmark results</strong>, use the 
        <a href="/metrics-dashboard">Metrics</a> and <a href="/reports">Reports</a> pages.
    </div>
</div>

<div class="card">
    <h2>Live Benchmark Status</h2>
    <div style="margin-bottom: 15px;">
        <label for="benchmark-select" style="color: #888;">Select a running benchmark to track:</label>
        <select id="benchmark-select" style="margin-left: 10px; padding: 8px; background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2); border-radius: 6px; color: #e0e0e0;">
            <option value="">-- Select Benchmark --</option>
            {% for b in benchmarks %}
            <option value="{{ b.benchmark_id }}">{{ b.benchmark_id }} - {{ b.service_name or 'Unknown' }}</option>
            {% endfor %}
        </select>
        <button onclick="refreshBenchmarkStatus(); startLoading(this); setTimeout(() => { this.classList.remove('loading'); this.innerHTML = 'Refresh'; }, 1000);" class="btn" style="margin-left: 10px;">Refresh</button>
    </div>
    
    <div id="benchmark-status" style="display: none;">
        <h3>Status</h3>
        
        <div id="status-loading" style="display: none; justify-content: center; padding: 40px;">
            <div class="loading-spinner"></div>
            <div style="margin-left: 15px; color: #888;">Fetching status...</div>
        </div>

        <div class="stats-grid" id="status-grid">
            <div class="stat-card">
                <div class="value" id="svc-status">-</div>
                <div class="label">Service</div>
            </div>
            <div class="stat-card">
                <div class="value" id="clients-done">-</div>
                <div class="label">Clients Done</div>
            </div>
            <div class="stat-card">
                <div class="value" id="all-done">-</div>
                <div class="label">Complete</div>
            </div>
        </div>
        <div id="status-message" class="info" style="margin-top: 15px;"></div>
    </div>
    
    <div id="no-benchmark" class="info" style="color: #888;">
        Select a benchmark above to see live status.
    </div>
</div>

<div class="card">
    <h2>Monitoring Stack (Optional)</h2>
    <p style="color: #888; margin-bottom: 15px;">
        For advanced monitoring with Prometheus + Grafana.
    </p>
    
    <div class="stats-grid">
        <div class="stat-card">
            <div class="value" id="prom-status">?</div>
            <div class="label">Prometheus</div>
        </div>
        <div class="stat-card">
            <div class="value" id="graf-status">?</div>
            <div class="label">Grafana</div>
        </div>
    </div>

    <div style="margin: 15px 0;">
        <button onclick="controlStack('start'); startLoading(this);" class="btn">Start Stack</button>
        <button onclick="controlStack('stop'); startLoading(this);" class="btn btn-secondary" style="color: #ff453a; border-color: rgba(255, 69, 58, 0.3);">Stop Stack</button>
        <a href="http://localhost:9090" target="_blank" class="btn btn-secondary">Open Prometheus</a>
        <a href="http://localhost:3000" target="_blank" class="btn btn-secondary">Open Grafana</a>
    </div>
    
    <div id="stack-log" class="code" style="max-height: 150px; display: none;"></div>
</div>

<div class="card">
    <h2>SSH Tunnel Setup</h2>
    <p style="color: #888; margin-bottom: 15px;">
        Required to access Prometheus/Grafana running on MeluXina from your local machine.
    </p>
    
    <div class="code" style="font-size: 0.9rem;">
# Step 1: Get the cluster node IP (shown when stack starts)
python src/frontend.py --monitor-stack status

# Step 2: Create SSH tunnels (replace NODE_IP with actual IP)
ssh -p 8822 YOUR_USERNAME@login.lxp.lu -NL 9090:NODE_IP:9090
ssh -p 8822 YOUR_USERNAME@login.lxp.lu -NL 3000:NODE_IP:3000

# Example with real values:
# ssh -p 8822 u103229@login.lxp.lu -NL 9090:10.3.24.92:9090
    </div>
    
    <h3 style="margin-top: 20px;">Port Already in Use?</h3>
    <div class="code" style="font-size: 0.9rem;">
# Find what's using the port
lsof -i :9090

# Kill the process
kill $(lsof -t -i :9090)

# Or use a different local port (e.g., 9091 instead of 9090):
ssh -p 8822 u103229@login.lxp.lu -NL 9091:NODE_IP:9090
# Then access Prometheus at http://localhost:9091
    </div>
    
    <div class="info" style="margin-top: 15px;">
        <strong>Tip:</strong> Set <code>export MELUXINA_USER=u103229</code> in your <code>~/.bashrc</code> 
        to have the CLI show correct tunnel commands.
    </div>
</div>

<div class="card">
    <h2>Quick Reference</h2>
    <table class="table">
        <tbody>
            <tr>
                <td><strong>Real-time metrics</strong></td>
                <td>Available via Prometheus scraping <code>/metrics</code> endpoint every 5s</td>
            </tr>
            <tr>
                <td><strong>Logs</strong></td>
                <td>Available <em>after</em> benchmark completes and artifacts are collected</td>
            </tr>
            <tr>
                <td><strong>Reports</strong></td>
                <td>Generated <em>after</em> benchmark completes</td>
            </tr>
            <tr>
                <td><strong>Prometheus URL</strong></td>
                <td><a href="http://localhost:9090" target="_blank">http://localhost:9090</a></td>
            </tr>
            <tr>
                <td><strong>Grafana URL</strong></td>
                <td><a href="http://localhost:3000" target="_blank">http://localhost:3000</a> (admin/admin)</td>
            </tr>
            <tr>
                <td><strong>Metrics endpoint</strong></td>
                <td><a href="/metrics" target="_blank">/metrics</a> (Prometheus format)</td>
            </tr>
        </tbody>
    </table>
</div>

<script>
let currentBenchmarkId = null;
let statusInterval = null;

// Add onchange handler to select
document.getElementById('benchmark-select').onchange = refreshBenchmarkStatus;

function refreshBenchmarkStatus() {
    const select = document.getElementById('benchmark-select');
    const benchmarkId = select.value;
    
    if (!benchmarkId) {
        document.getElementById('benchmark-status').style.display = 'none';
        document.getElementById('no-benchmark').style.display = 'block';
        if (statusInterval) clearInterval(statusInterval);
        return;
    }
    
    currentBenchmarkId = benchmarkId;
    document.getElementById('benchmark-status').style.display = 'block';
    document.getElementById('no-benchmark').style.display = 'none';
    
    // Show loading state initially
    document.getElementById('status-loading').style.display = 'flex';
    document.getElementById('status-grid').style.display = 'none';
    document.getElementById('status-message').innerHTML = '';
    
    fetchBenchmarkStatus(benchmarkId);
    
    // Auto-refresh every 5s
    if (statusInterval) clearInterval(statusInterval);
    statusInterval = setInterval(() => fetchBenchmarkStatus(benchmarkId), 5000);
}

function fetchBenchmarkStatus(benchmarkId) {
    // Add timestamp to prevent caching
    fetch('/api/benchmark/' + benchmarkId + '/status?_t=' + Date.now())
        .then(res => res.json())
        .then(data => {
            // Hide loading, show grid
            document.getElementById('status-loading').style.display = 'none';
            document.getElementById('status-grid').style.display = 'grid';

            if (data.error) {
                document.getElementById('status-message').innerHTML = 
                    '<span style="color: #FF9800;">Error: ' + data.error + '</span>';
                return;
            }
            
            // Use top-level service_status which is normalized by the API
            document.getElementById('svc-status').innerHTML = formatStatus(data.service_status || 'Unknown');
            document.getElementById('clients-done').textContent = data.clients_done + '/' + data.clients_total;
            document.getElementById('all-done').innerHTML = data.all_done ? 
                '<span style="color: #4CAF50;">Yes</span>' : 
                '<span style="color: #2196F3;">Running...</span>';
            
            if (data.all_done) {
                document.getElementById('status-message').innerHTML = 
                    '<span style="color: #4CAF50;">Benchmark complete! <a href="/benchmark/' + benchmarkId + '/metrics">View Metrics</a> | <a href="/benchmark/' + benchmarkId + '/logs">View Logs</a></span>';
                if (statusInterval) clearInterval(statusInterval);
            } else {
                document.getElementById('status-message').innerHTML = 
                    '<span style="color: #2196F3;">Benchmark running... Real-time metrics available via <a href="http://localhost:9090" target="_blank">Prometheus</a>.</span>';
            }
        })
        .catch(err => {
            document.getElementById('status-loading').style.display = 'none';
            document.getElementById('status-message').innerHTML = 
                '<span style="color: #f44336;">Error fetching status: ' + err + '</span>';
        });
}

function formatStatus(status) {
    if (status.includes('RUNNING')) return '<span style="color: #4CAF50;">' + status + '</span>';
    if (status.includes('COMPLETED')) return '<span style="color: #4CAF50;">' + status + '</span>';
    if (status.includes('FAILED') || status.includes('CANCELLED')) return '<span style="color: #f44336;">' + status + '</span>';
    return '<span style="color: #888;">' + status + '</span>';
}

function updateStackStatus() {
    fetch('/api/stack/status')
        .then(res => res.json())
        .then(data => {
            document.getElementById('prom-status').innerHTML = data.prometheus ? 
                '<span style="color: #4CAF50">Running</span>' : '<span style="color: #888">Stopped</span>';
            document.getElementById('graf-status').innerHTML = data.grafana ? 
                '<span style="color: #4CAF50">Running</span>' : '<span style="color: #888">Stopped</span>';
        })
        .catch(() => {
            document.getElementById('prom-status').innerHTML = '<span style="color: #888">?</span>';
            document.getElementById('graf-status').innerHTML = '<span style="color: #888">?</span>';
        });
}

function controlStack(action) {
    const logDiv = document.getElementById('stack-log');
    logDiv.style.display = 'block';
    logDiv.innerText = 'Executing ' + action + '... please wait...';
    
    fetch('/api/stack/' + action, { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            logDiv.innerText = data.message;
            if (data.error) {
                logDiv.innerHTML = data.message + '<br><span style="color: #FF9800;">Note: ' + data.error + '</span>';
            }
            updateStackStatus();
        })
        .catch(err => {
            logDiv.innerHTML = '<span style="color: #f44336;">Error: ' + err + '</span>';
        });
}

// Auto-select if only one benchmark or recent one
document.getElementById('benchmark-select').addEventListener('change', refreshBenchmarkStatus);

updateStackStatus();
setInterval(updateStackStatus, 10000);
</script>
{% endblock %}
"""

REPORTS_TEMPLATE = """
{% extends "base" %}
{% block content %}
<div class="card">
    <h2>Benchmark Reports</h2>
    {% if benchmark_data %}
    <div class="info">
        <strong>Tip:</strong> Reports are automatically generated when benchmarks complete.
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
                        <span class="badge badge-completed">Available</span>
                    {% elif item.has_artifacts %}
                        <span class="badge badge-running">Ready to Generate</span>
                    {% else %}
                        <span class="badge badge-pending">Needs Collection</span>
                    {% endif %}
                </td>
                <td>
                    {% if item.has_report %}
                        <a href="/benchmark/{{ item.benchmark.benchmark_id }}/report" class="btn btn-secondary">View Report</a>
                    {% elif item.has_artifacts %}
                        <a href="/benchmark/{{ item.benchmark.benchmark_id }}/report" class="btn btn-secondary">Generate Report</a>
                    {% else %}
                        <a href="/benchmark/{{ item.benchmark.benchmark_id }}/collect" class="btn" style="color: #ffffff;" onclick="startLoading(this)">Collect Artifacts</a>
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
    <h2>How to Generate Reports</h2>
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
        1 for b in benchmarks if b.service_name and any(x in b.service_name.lower() for x in ["chroma", "qdrant", "milvus"])
    )
    redis = sum(
        1 for b in benchmarks if b.service_name and any(x in b.service_name.lower() for x in ["redis", "minio"])
    )
    other = len(benchmarks) - postgres - llm - vector - redis

    # Get recent performance metrics
    recent_metrics = []
    for b in benchmarks[:10]:
        summary = read_summary_json(b.benchmark_id)
        if summary:
            recent_metrics.append({
                "id": b.benchmark_id,
                "rps": summary.get("requests_per_second", 0),
                "p99": summary.get("latency_s", {}).get("p99", 0),
                "success": summary.get("success_rate", 0)
            })

    return render(
        DASHBOARD_TEMPLATE,
        page="dashboard",
        benchmarks=benchmarks,
        total=len(benchmarks),
        postgres=postgres,
        llm=llm,
        vector=vector,
        redis=redis,
        other=other,
        recent_metrics=recent_metrics,
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
        
    # Check if benchmark is completed (has summary.json)
    from reporting.artifacts import read_summary_json
    metrics = read_summary_json(benchmark_id)
    is_completed = metrics is not None
    
    return render(BENCHMARK_DETAIL_TEMPLATE, page="benchmarks", summary=summary, is_completed=is_completed)


@app.route("/benchmark/<benchmark_id>/rerun")
def benchmark_rerun(benchmark_id):
    """Trigger a rerun of an existing benchmark."""
    try:
        # Load run.json to get recipe
        run_data = read_run_json(benchmark_id)
        if not run_data or "recipe" not in run_data:
            return f"Cannot rerun {benchmark_id}: missing recipe in run.json", 400
        
        # Create temp recipe file
        import tempfile
        import yaml
        from frontend import run_benchmark_from_recipe
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
            yaml.dump(run_data["recipe"], tmp)
            tmp_path = Path(tmp.name)
            
        # Run it
        new_id = run_benchmark_from_recipe(tmp_path)
        
        # Cleanup
        if tmp_path.exists():
            import os
            os.unlink(tmp_path)
            
        if new_id:
            return redirect(f"/benchmark/{new_id}/watch")
        else:
            return "Failed to start rerun", 500
            
    except Exception as e:
        return f"Error triggering rerun: {e}", 500


@app.route("/compare")
def compare_page():
    """Render comparison page."""
    baseline_id = request.args.get("baseline", "")
    current_id = request.args.get("current", "")
    
    benchmarks = list_all_benchmarks()
    comparison = None
    
    if baseline_id and current_id:
        # Perform comparison
        try:
            from core.aggregator import compare_summaries
            s1 = read_summary_json(baseline_id)
            s2 = read_summary_json(current_id)
            
            if s1 and s2:
                comparison = compare_summaries(s1, s2)
                # Add IDs to comparison object for template
                comparison["baseline_id"] = baseline_id
                comparison["current_id"] = current_id
        except Exception as e:
            print(f"Error comparing {baseline_id} and {current_id}: {e}")
            
    return render(
        COMPARE_TEMPLATE, 
        page="benchmarks", 
        benchmarks=benchmarks,
        baseline_id=baseline_id,
        current_id=current_id,
        comparison=comparison
    )


@app.route("/cli")
def cli_reference():
    return render(CLI_TEMPLATE, page="cli")



def run_recipe_worker(job_id, recipe_path):
    """Worker thread to run recipe and capture output."""
    job = DEPLOYMENT_JOBS[job_id]
    
    try:
        process = subprocess.Popen(
            ["python", "-u", "src/frontend.py", recipe_path],  # -u for unbuffered
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=str(FilePath(__file__).parent.parent.parent)
        )
        
        for line in iter(process.stdout.readline, ''):
            job["logs"].append(line)
            # Check for benchmark ID
            if not job["benchmark_id"]:
                match = re.search(r'Benchmark ID[:\s]+(\S+)', line)
                if match:
                    job["benchmark_id"] = match.group(1)
        
        process.wait()
        
        if process.returncode == 0:
            job["status"] = "done"
            job["logs"].append(f"\nSUCCESS: Recipe execution completed.")
        else:
            job["status"] = "error"
            job["logs"].append(f"\nERROR: Process failed with code {process.returncode}")
            
    except Exception as e:
        job["status"] = "error"
        job["logs"].append(f"\nEXCEPTION: {str(e)}")


@app.route("/api/deployment/<job_id>")
def api_deployment_status(job_id):
    job = DEPLOYMENT_JOBS.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@app.route("/run", methods=["GET", "POST"])
def run_recipe_page():
    """Run a benchmark recipe."""
    if request.method == "POST":
        recipe_path = request.form.get("recipe")
        # Support JSON payload as well
        if not recipe_path and request.is_json:
             recipe_path = request.json.get("recipe")

        if recipe_path:
            job_id = str(uuid.uuid4())
            DEPLOYMENT_JOBS[job_id] = {
                "status": "running",
                "logs": ["Starting deployment...\n"],
                "benchmark_id": None,
                "created_at": time.time()
            }
            
            thread = threading.Thread(target=run_recipe_worker, args=(job_id, recipe_path))
            thread.daemon = True
            thread.start()
            
            return jsonify({"job_id": job_id, "status": "started"})
        
        return jsonify({"error": "No recipe specified"}), 400
    
    # GET: List recipes
    message = None
    success = False
    
    # Get available recipes
    recipes = []
    for recipe_path in get_available_recipes():
        name = recipe_path.stem.replace("recipe_", "").replace("_", " ").title()
        recipes.append({
            "name": name,
            "path": str(recipe_path),
            "filename": recipe_path.name
        })
    
    return render(
        RUN_RECIPE_TEMPLATE,
        page="run",
        recipes=recipes,
        message=message,
        success=success,
        benchmark_id=None
    )


@app.route("/benchmark/<benchmark_id>/watch")
def watch_benchmark(benchmark_id):
    """Watch benchmark status with auto-refresh."""
    return render(WATCH_STATUS_TEMPLATE, page="benchmarks", benchmark_id=benchmark_id)


@app.route("/benchmark/<benchmark_id>/stop")
def stop_benchmark(benchmark_id):
    """Stop a benchmark."""
    try:
        target = get_benchmark_target(benchmark_id)
        
        with Manager(target=target, benchmark_id=benchmark_id) as manager:
            result = manager.stop_benchmark()
            cancelled = len(result.get("services", [])) + len(result.get("clients", []))
            
        if cancelled > 0:
            return redirect(f"/benchmark/{benchmark_id}?message=Cancelled {cancelled} job(s)")
        else:
            return redirect(f"/benchmark/{benchmark_id}?message=No jobs to cancel")
    except Exception as e:
        return redirect(f"/benchmark/{benchmark_id}?message=Error: {e}")


@app.route("/benchmark/<benchmark_id>/logs")
def benchmark_logs(benchmark_id):
    """View logs for a benchmark."""
    log_files = []
    
    # Check local logs directory
    logs_dir = FilePath(__file__).parent.parent.parent / f"logs/{benchmark_id}"
    results_dir = FilePath(__file__).parent.parent.parent / f"results/{benchmark_id}"
    results_logs_dir = FilePath(__file__).parent.parent.parent / f"results/{benchmark_id}/logs"
    
    for search_dir in [logs_dir, results_logs_dir, results_dir]:
        if search_dir.exists():
            for ext in ["*.log", "*.out", "*.err"]:
                for log_file in search_dir.glob(ext):
                    size = log_file.stat().st_size
                    size_str = f"{size} B" if size < 1024 else f"{size/1024:.1f} KB"
                    log_files.append({
                        "name": log_file.name,
                        "size": size_str,
                        "path": str(log_file)
                    })
    
    return render(
        LOGS_TEMPLATE,
        page="benchmarks",
        benchmark_id=benchmark_id,
        log_files=log_files,
        selected_log=None,
        selected_log_name=None
    )


@app.route("/benchmark/<benchmark_id>/log/<log_name>")
def view_log_file(benchmark_id, log_name):
    """View a specific log file."""
    log_files = []
    selected_log = None
    selected_log_name = log_name
    
    logs_dir = FilePath(__file__).parent.parent.parent / f"logs/{benchmark_id}"
    results_dir = FilePath(__file__).parent.parent.parent / f"results/{benchmark_id}"
    results_logs_dir = FilePath(__file__).parent.parent.parent / f"results/{benchmark_id}/logs"
    
    # First build list of all available log files
    for search_dir in [logs_dir, results_logs_dir, results_dir]:
        if search_dir.exists():
            for ext in ["*.log", "*.out", "*.err"]:
                for log_file in search_dir.glob(ext):
                    size = log_file.stat().st_size
                    size_str = f"{size} B" if size < 1024 else f"{size/1024:.1f} KB"
                    # Avoid duplicates if multiple dirs contain same file (unlikely but safe)
                    if not any(l["name"] == log_file.name for l in log_files):
                        log_files.append({
                            "name": log_file.name,
                            "size": size_str,
                            "path": str(log_file)
                        })

    # Then find and read the specific log file
    for search_dir in [logs_dir, results_logs_dir, results_dir]:
        log_path = search_dir / log_name
        if log_path.exists():
            try:
                with open(log_path, 'r', errors='replace') as f:
                    selected_log = f.read()[-50000:]  # Last 50KB
            except Exception as e:
                selected_log = f"Error reading log: {e}"
            break
    
    return render(
        LOGS_TEMPLATE,
        page="benchmarks",
        benchmark_id=benchmark_id,
        log_files=log_files,
        selected_log=selected_log,
        selected_log_name=selected_log_name
    )


@app.route("/api/benchmark/<benchmark_id>/status")
def api_benchmark_status(benchmark_id):
    """API endpoint for benchmark status (used by watch page).
    
    Automatically stops service and collects artifacts when clients finish.
    Uses lifecycle module for consistent behavior with CLI.
    """
    target = get_benchmark_target(benchmark_id)
    auto_action = None
    
    # Check benchmark status
    status_result = check_benchmark_complete(benchmark_id, target)
    
    if status_result.get("error"):
        return jsonify({
            "service_status": "ERROR",
            "clients_done": 0,
            "clients_total": 0,
            "all_done": False,
            "error": status_result["error"],
            "services": [],
            "clients": []
        })
    
    all_done = status_result["complete"]
    service_status = status_result["service_status"]
    
    # FIX: If all clients are done (success or otherwise), report service as COMPLETED
    # This prevents the UI from showing "CANCELLED" when the service was correctly stopped after work.
    if all_done:
        service_status = "COMPLETED"
    
    # When clients finish, auto-stop service and collect artifacts
    if all_done:
        # Check if we need to collect (no summary yet)
        summary = read_summary_json(benchmark_id)
        if not summary:
            # Use lifecycle module with locking to prevent race conditions
            completion_result = handle_benchmark_completion(
                benchmark_id,
                target=target,
                stop_service=(service_status not in ["COMPLETED", "FAILED", "CANCELLED", "TIMEOUT"]),
                collect_artifacts=True,
                generate_report=True
            )
            if completion_result["collected"]:
                auto_action = "artifacts_collected"
            elif completion_result["stopped"]:
                auto_action = "service_stopped"
            elif completion_result["errors"]:
                auto_action = f"error: {completion_result['errors'][0]}"
    
    return jsonify({
        "service_status": service_status,
        "clients_done": status_result["clients_done"],
        "clients_total": status_result["clients_total"],
        "all_done": all_done,
        "services": status_result["services"],
        "clients": status_result["clients"],
        "auto_action": auto_action
    })


@app.route("/api/benchmark/<benchmark_id>/check_logs")
def api_check_logs(benchmark_id):
    """Check if new logs are available on the cluster."""
    from infra.communicator import SSHCommunicator
    
    target = get_benchmark_target(benchmark_id)
    communicator = SSHCommunicator(target=target)
    
    if not communicator.connect():
        return jsonify({"available": False, "error": "Connection failed"})
        
    try:
        # Get remote log count/size
        # Simply counting .out and .err files
        working_dir = f"~/benchmark_{benchmark_id}"
        
        # Need to resolve home dir first
        result = communicator.execute_command("echo $HOME")
        if not result.success:
             return jsonify({"available": False, "error": "Could not find home"})
        
        home_dir = result.stdout.strip()
        abs_working_dir = working_dir.replace("~", home_dir)
        logs_dir = f"{abs_working_dir}/logs"
        
        # List files
        cmd = f"ls -1 {logs_dir}/*.out {logs_dir}/*.err 2>/dev/null | wc -l"
        result = communicator.execute_command(cmd)
        
        if not result.success:
            return jsonify({"available": False, "error": "Listing failed"})
            
        remote_count = int(result.stdout.strip())
        
        # Check local count
        local_dir = Path("results") / benchmark_id / "logs"
        local_count = 0
        if local_dir.exists():
            local_count = len(list(local_dir.parent.glob("logs/*.out"))) + len(list(local_dir.parent.glob("logs/*.err")))
            # Also check inside the logs dir specifically
            if local_count == 0:
                 local_count = len(list(local_dir.glob("*.out"))) + len(list(local_dir.glob("*.err")))
                 
        return jsonify({
            "available": remote_count > local_count,
            "remote_count": remote_count,
            "local_count": local_count
        })
        
    except Exception as e:
        return jsonify({"available": False, "error": str(e)})
    finally:
        communicator.disconnect()


@app.route("/metrics-dashboard")
def metrics_page():
    benchmarks = list_all_benchmarks()
    # Check status for each benchmark to avoid "Running" for completed ones
    from reporting.artifacts import read_summary_json
    
    for b in benchmarks:
        # Check if we have a summary - if so, it's completed
        summary = read_summary_json(b.benchmark_id)
        if summary:
            b.status = "Completed"
            b.service_job_id = None  # Clear job ID so template shows "Completed"/Status
        elif b.service_job_id: # If job ID exists and no summary, it's likely running
             # Verify it's not a stale job ID (optional, but good for robustness)
             pass
             
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
        # Get target using lifecycle module
        target = get_benchmark_target(benchmark_id)

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
<style>
    /* Report-specific styling for markdown content */
    .report-content {
        background: rgba(255,255,255,0.03);
        padding: 32px;
        border-radius: 12px;
        line-height: 1.7;
    }
    
    /* Headings */
    .report-content h1 {
        font-size: 28px;
        font-weight: 600;
        color: #fff;
        margin-bottom: 16px;
        padding-bottom: 12px;
        border-bottom: 2px solid rgba(10, 132, 255, 0.3);
    }
    .report-content h2 {
        font-size: 20px;
        font-weight: 600;
        color: #fff;
        margin: 32px 0 16px 0;
        padding-bottom: 8px;
        border-bottom: 1px solid rgba(255,255,255,0.1);
    }
    .report-content h3 {
        font-size: 16px;
        font-weight: 600;
        color: rgba(255,255,255,0.9);
        margin: 24px 0 12px 0;
    }
    
    /* Tables - professional styling */
    .report-content table {
        width: 100%;
        border-collapse: collapse;
        margin: 20px 0;
        background: rgba(0,0,0,0.2);
        border-radius: 8px;
        overflow: hidden;
        font-size: 14px;
    }
    .report-content thead {
        background: rgba(10, 132, 255, 0.2);
    }
    .report-content th {
        padding: 14px 16px;
        text-align: left;
        font-weight: 600;
        color: #fff;
        border-bottom: 2px solid rgba(10, 132, 255, 0.3);
    }
    .report-content td {
        padding: 12px 16px;
        border-bottom: 1px solid rgba(255,255,255,0.08);
        color: rgba(255,255,255,0.85);
    }
    .report-content tr:last-child td {
        border-bottom: none;
    }
    .report-content tbody tr:hover {
        background: rgba(255,255,255,0.03);
    }
    
    /* Paragraphs */
    .report-content p {
        margin: 12px 0;
        color: rgba(255,255,255,0.85);
    }
    
    /* Lists */
    .report-content ul, .report-content ol {
        margin: 16px 0;
        padding-left: 24px;
    }
    .report-content li {
        margin: 8px 0;
        color: rgba(255,255,255,0.85);
    }
    
    /* Emphasis */
    .report-content strong {
        color: #fff;
        font-weight: 600;
    }
    
    /* Horizontal rules */
    .report-content hr {
        border: none;
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
        margin: 32px 0;
    }
    
    /* Code blocks */
    .report-content code {
        background: rgba(0,0,0,0.3);
        padding: 2px 8px;
        border-radius: 4px;
        font-family: 'SF Mono', Monaco, Consolas, monospace;
        font-size: 13px;
        color: #ff9f0a;
    }
    .report-content pre {
        background: rgba(0,0,0,0.4);
        padding: 16px;
        border-radius: 8px;
        overflow-x: auto;
        margin: 16px 0;
    }
    .report-content pre code {
        background: none;
        padding: 0;
        color: rgba(255,255,255,0.9);
    }
    
    /* Blockquotes for findings */
    .report-content blockquote {
        border-left: 4px solid rgba(10, 132, 255, 0.5);
        margin: 16px 0;
        padding: 12px 20px;
        background: rgba(10, 132, 255, 0.1);
        border-radius: 0 8px 8px 0;
    }
    
    /* Links */
    .report-content a {
        color: #0a84ff;
        text-decoration: none;
    }
    .report-content a:hover {
        text-decoration: underline;
    }
</style>

<div class="card">
    <div class="report-content">
        {{ html_content | safe }}
    </div>
    <div style="margin-top: 24px; padding-top: 20px; border-top: 1px solid rgba(255,255,255,0.1);">
        <a href="/benchmark/{{ benchmark_id }}/plots" class="btn btn-primary">View Plots</a>
        <a href="/benchmark/{{ benchmark_id }}/metrics" class="btn btn-secondary">Detailed Metrics</a>
        <a href="/reports" class="btn btn-secondary">Back to Reports</a>
    </div>
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
    <h2>Plots for Benchmark #{{ benchmark_id }}</h2>
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
    <a href="/reports" class="btn btn-secondary">Back to Reports</a>
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
            from core.aggregator import aggregate_benchmark

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
    <h2>Metrics for Benchmark #{{ benchmark_id }}</h2>
    
    <h3>Performance Summary</h3>
    <div class="stats-grid">
        <div class="stat-card">
            <div class="value">{{ summary['total_requests'] }}</div>
            <div class="label">Total Requests</div>
        </div>
        <div class="stat-card">
            <div class="value" style="color: {{ '#4CAF50' if summary['success_rate'] >= 99 else '#FF9800' if summary['success_rate'] >= 90 else '#f44336' }}">{{ "%.1f"|format(summary['success_rate']) }}%</div>
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
        {% if summary.get('test_duration_s') %}
        <div class="stat-card">
            <div class="value">{{ "%.1f"|format(summary['test_duration_s']) }}s</div>
            <div class="label">Duration</div>
        </div>
        {% endif %}
        {% if summary.get('tokens_per_second') %}
        <div class="stat-card">
            <div class="value">{{ "%.0f"|format(summary['tokens_per_second']) }}</div>
            <div class="label">Tokens/s</div>
        </div>
        {% endif %}
    </div>
</div>

<div class="card">
    <h2>Latency Distribution</h2>
    <div style="display: flex; gap: 20px; flex-wrap: wrap;">
        <div style="flex: 2; min-width: 300px;">
            <canvas id="latencyChart"></canvas>
        </div>
        <div style="flex: 1; min-width: 200px;">
            <canvas id="successChart"></canvas>
        </div>
    </div>
</div>

<div class="card">
    <h2>Detailed Metrics</h2>
    <table class="table">
        <thead>
            <tr>
                <th>Metric</th>
                <th>Value</th>
            </tr>
        </thead>
        <tbody>
            <tr><td>Min Latency</td><td>{{ "%.3f"|format(summary['latency_s']['min']) }}s</td></tr>
            <tr><td>Avg Latency</td><td>{{ "%.3f"|format(summary['latency_s']['avg']) }}s</td></tr>
            <tr><td>P50 Latency</td><td>{{ "%.3f"|format(summary['latency_s']['p50']) }}s</td></tr>
            <tr><td>P90 Latency</td><td>{{ "%.3f"|format(summary['latency_s']['p90']) }}s</td></tr>
            <tr><td>P95 Latency</td><td>{{ "%.3f"|format(summary['latency_s']['p95']) }}s</td></tr>
            <tr><td>P99 Latency</td><td>{{ "%.3f"|format(summary['latency_s']['p99']) }}s</td></tr>
            <tr><td>Max Latency</td><td>{{ "%.3f"|format(summary['latency_s']['max']) }}s</td></tr>
            <tr><td>Std Dev</td><td>{{ "%.3f"|format(summary['latency_s']['std']) }}s</td></tr>
        </tbody>
    </table>
    
    {% if summary.get('error_summary') and summary['error_summary'] %}
    <h3 style="margin-top: 20px;">Error Summary</h3>
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
</div>

<div style="margin-top: 20px;">
    <a href="/benchmark/{{ benchmark_id }}" class="btn btn-secondary">Back to Benchmark</a>
    <a href="/metrics-dashboard" class="btn btn-secondary">All Metrics</a>
    <a href="/api/benchmark/{{ benchmark_id }}/metrics/prometheus" class="btn btn-secondary" target="_blank">Prometheus Format</a>
</div>

<script>
// Latency Percentiles Bar Chart
const latencyCtx = document.getElementById('latencyChart').getContext('2d');
new Chart(latencyCtx, {
    type: 'bar',
    data: {
        labels: ['Min', 'P50', 'P90', 'P95', 'P99', 'Max'],
        datasets: [{
            label: 'Latency (seconds)',
            data: [
                {{ summary['latency_s']['min'] }},
                {{ summary['latency_s']['p50'] }},
                {{ summary['latency_s']['p90'] }},
                {{ summary['latency_s']['p95'] }},
                {{ summary['latency_s']['p99'] }},
                {{ summary['latency_s']['max'] }}
            ],
            backgroundColor: [
                'rgba(76, 175, 80, 0.7)',
                'rgba(0, 212, 255, 0.7)',
                'rgba(33, 150, 243, 0.7)',
                'rgba(255, 193, 7, 0.7)',
                'rgba(255, 152, 0, 0.7)',
                'rgba(244, 67, 54, 0.7)'
            ],
            borderColor: [
                'rgba(76, 175, 80, 1)',
                'rgba(0, 212, 255, 1)',
                'rgba(33, 150, 243, 1)',
                'rgba(255, 193, 7, 1)',
                'rgba(255, 152, 0, 1)',
                'rgba(244, 67, 54, 1)'
            ],
            borderWidth: 1
        }]
    },
    options: {
        responsive: true,
        plugins: {
            legend: { display: false },
            title: { display: true, text: 'Latency Percentiles', color: '#e0e0e0' }
        },
        scales: {
            y: { 
                beginAtZero: true, 
                grid: { color: 'rgba(255,255,255,0.1)' },
                ticks: { color: '#888' }
            },
            x: { 
                grid: { color: 'rgba(255,255,255,0.1)' },
                ticks: { color: '#888' }
            }
        }
    }
});

// Success Rate Pie Chart
const successCtx = document.getElementById('successChart').getContext('2d');
new Chart(successCtx, {
    type: 'doughnut',
    data: {
        labels: ['Success', 'Failed'],
        datasets: [{
            data: [{{ summary['successful_requests'] }}, {{ summary['failed_requests'] }}],
            backgroundColor: ['rgba(76, 175, 80, 0.8)', 'rgba(244, 67, 54, 0.8)'],
            borderColor: ['rgba(76, 175, 80, 1)', 'rgba(244, 67, 54, 1)'],
            borderWidth: 1
        }]
    },
    options: {
        responsive: true,
        plugins: {
            legend: { position: 'bottom', labels: { color: '#e0e0e0' } },
            title: { display: true, text: 'Request Success Rate', color: '#e0e0e0' }
        }
    }
});
</script>
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


@app.route("/api/metrics/prometheus")
def prometheus_metrics_all():
    """Export all benchmark metrics in comprehensive Prometheus format.
    
    This endpoint provides extensive metrics for each benchmark including:
    - Request counts and success/failure rates
    - Latency statistics (percentiles, min, max, std)
    - Service-specific metrics (tokens/s for LLM, TPS for DB)
    - Error breakdown by type
    - Client concurrency information
    """
    from monitoring.monitor import format_prometheus_metrics
    
    benchmarks = list_all_benchmarks()
    all_metrics = []
    
    for b in benchmarks[:20]:  # Limit to recent 20
        summary = read_summary_json(b.benchmark_id)
        if summary:
            service_type = summary.get("service_type", b.service_name or "unknown")
            # Also load run_data for additional context
            run_data = read_run_json(b.benchmark_id)
            metrics_text = format_prometheus_metrics(
                summary, 
                str(b.benchmark_id), 
                service_type,
                run_data=run_data
            )
            all_metrics.append(metrics_text)
    
    if not all_metrics:
        return "# No metrics available\n", 200, {'Content-Type': 'text/plain; charset=utf-8'}
    
    return "\n\n".join(all_metrics), 200, {'Content-Type': 'text/plain; charset=utf-8'}


@app.route("/api/benchmark/<benchmark_id>/metrics/prometheus")
def prometheus_metrics(benchmark_id):
    """Export comprehensive benchmark metrics in Prometheus format.
    
    Provides detailed metrics for a single benchmark including:
    - All latency percentiles (p50, p90, p95, p99) plus min/max/std
    - Throughput (RPS) and service-specific metrics
    - Error breakdown by type
    - Test duration and timing
    - Client concurrency from run configuration
    """
    from monitoring.monitor import format_prometheus_metrics
    
    summary = read_summary_json(benchmark_id)
    if not summary:
        return "# No metrics available\n", 404, {'Content-Type': 'text/plain; charset=utf-8'}
    
    service_type = summary.get("service_type", "unknown")
    run_data = read_run_json(benchmark_id)
    metrics_text = format_prometheus_metrics(
        summary, 
        benchmark_id, 
        service_type,
        run_data=run_data
    )
    return metrics_text, 200, {'Content-Type': 'text/plain; charset=utf-8'}


@app.route("/monitoring")
def monitoring():
    """Monitoring dashboard page with live benchmark tracking."""
    benchmarks = list_all_benchmarks()
    return render(MONITORING_TEMPLATE, page="monitoring", benchmarks=benchmarks)

@app.route("/metrics")
def metrics():
    """Prometheus metrics endpoint (alias)."""
    return prometheus_metrics_all()

@app.route("/api/stack/start", methods=["POST"])
def stack_start():
    """Start the monitoring stack."""
    try:
        urls = stack_manager.start()
        return jsonify({"message": f"Stack started! Grafana at {urls['grafana']}, Prometheus at {urls['prometheus']}", "urls": urls})
    except Exception as e:
        return jsonify({"message": "Failed to start stack", "error": str(e)}), 500

@app.route("/api/stack/stop", methods=["POST"])
def stack_stop():
    """Stop the monitoring stack."""
    try:
        stack_manager.stop()
        return jsonify({"message": "Stack stopped successfully"})
    except Exception as e:
        return jsonify({"message": "Failed to stop stack", "error": str(e)}), 500

@app.route("/api/stack/status")
def stack_status():
    """Get stack status."""
    return jsonify(stack_manager.status())

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
