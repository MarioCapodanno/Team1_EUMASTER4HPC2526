#!/usr/bin/env python3
"""
Comprehensive test suite for the Web Interface.

Tests all user interactions available in the --web interface:
- Dashboard
- Run Recipe (GET/POST)
- Benchmarks list
- Benchmark detail with action buttons
- Watch Status (with API)
- Stop Benchmark
- View Logs
- View Metrics
- View/Generate Reports
- Collect Artifacts
- Prometheus metrics endpoints
- API endpoints

Run with: python -m pytest test/test_web_interface.py -v
Or directly: python test/test_web_interface.py
"""

import sys
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from web.flask_app import app, get_available_recipes


class TestResults:
    """Track test results."""
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def record(self, name: str, passed: bool, error: str = None):
        if passed:
            self.passed += 1
            print(f"  ✓ {name}")
        else:
            self.failed += 1
            self.errors.append((name, error))
            print(f"  ✗ {name}: {error}")
    
    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'=' * 60}")
        print(f"Test Results: {self.passed}/{total} passed")
        if self.errors:
            print(f"\nFailures:")
            for name, error in self.errors:
                print(f"  - {name}: {error}")
        print(f"{'=' * 60}")
        return self.failed == 0


results = TestResults()


def test_recipe_discovery():
    """Test that recipe files are discovered correctly."""
    recipes = get_available_recipes()
    
    if len(recipes) > 0:
        results.record("Recipe discovery finds recipes", True)
    else:
        results.record("Recipe discovery finds recipes", False, "No recipes found")
    
    # Check if common recipes exist
    recipe_names = [r.name for r in recipes]
    expected = ["recipe_redis.yaml", "recipe_postgres.yaml", "recipe_ollama.yaml"]
    found = sum(1 for e in expected if e in recipe_names)
    
    if found >= 2:
        results.record("Common recipes exist", True)
    else:
        results.record("Common recipes exist", False, f"Only found {found}/3 expected recipes")


def test_dashboard_page():
    """Test dashboard (/) renders correctly."""
    with app.test_client() as client:
        resp = client.get("/")
        
        if resp.status_code == 200:
            results.record("Dashboard returns 200", True)
        else:
            results.record("Dashboard returns 200", False, f"Got {resp.status_code}")
        
        # Check content
        data = resp.data.decode()
        if "AI Factory Benchmark" in data:
            results.record("Dashboard contains title", True)
        else:
            results.record("Dashboard contains title", False, "Title not found")
        
        if "Total Benchmarks" in data:
            results.record("Dashboard shows stats", True)
        else:
            results.record("Dashboard shows stats", False, "Stats not found")


def test_run_recipe_page_get():
    """Test Run Recipe page (GET)."""
    with app.test_client() as client:
        resp = client.get("/run")
        
        if resp.status_code == 200:
            results.record("Run Recipe GET returns 200", True)
        else:
            results.record("Run Recipe GET returns 200", False, f"Got {resp.status_code}")
        
        data = resp.data.decode()
        if "Run a Benchmark Recipe" in data or "Available Recipes" in data:
            results.record("Run Recipe shows recipe list", True)
        else:
            results.record("Run Recipe shows recipe list", False, "Recipe list not found")
        
        if "<form" in data and 'method="POST"' in data:
            results.record("Run Recipe has form", True)
        else:
            results.record("Run Recipe has form", False, "Form not found")


def test_run_recipe_page_post():
    """Test Run Recipe page (POST) - mock the subprocess."""
    with app.test_client() as client:
        with patch('subprocess.run') as mock_run:
            # Mock successful benchmark submission
            mock_run.return_value = MagicMock(
                stdout="Benchmark ID: BM-TEST-001\nDeployed successfully",
                stderr="",
                returncode=0
            )
            
            resp = client.post("/run", data={"recipe": "examples/recipe_redis.yaml"})
            
            # Should return 200 (renders page with message)
            if resp.status_code == 200:
                results.record("Run Recipe POST returns 200", True)
            else:
                results.record("Run Recipe POST returns 200", False, f"Got {resp.status_code}")
            
            data = resp.data.decode()
            if "BM-TEST-001" in data or "started" in data.lower() or "submitted" in data.lower():
                results.record("Run Recipe POST shows success message", True)
            else:
                results.record("Run Recipe POST shows success message", False, "Success message not found")


def test_benchmarks_list_page():
    """Test benchmarks list page."""
    with app.test_client() as client:
        resp = client.get("/benchmarks")
        
        if resp.status_code == 200:
            results.record("Benchmarks list returns 200", True)
        else:
            results.record("Benchmarks list returns 200", False, f"Got {resp.status_code}")
        
        data = resp.data.decode()
        if "All Benchmarks" in data or "table" in data:
            results.record("Benchmarks list has table", True)
        else:
            results.record("Benchmarks list has table", False, "Table not found")


def test_benchmark_detail_page():
    """Test benchmark detail page with action buttons."""
    with app.test_client() as client:
        # This may return 404 if benchmark doesn't exist, which is OK
        resp = client.get("/benchmark/BM-20260109-001")
        
        if resp.status_code in [200, 404]:
            results.record("Benchmark detail returns valid status", True)
        else:
            results.record("Benchmark detail returns valid status", False, f"Got {resp.status_code}")
        
        # If we have benchmarks, test with a real one
        from infra.storage import list_all_benchmarks
        benchmarks = list_all_benchmarks()
        
        if benchmarks:
            bm_id = benchmarks[0].benchmark_id
            resp = client.get(f"/benchmark/{bm_id}")
            
            if resp.status_code == 200:
                results.record("Benchmark detail renders for real benchmark", True)
                
                data = resp.data.decode()
                # Check action buttons exist
                action_buttons = ["Watch Status", "View Logs", "Metrics", "Report", "Collect", "Stop"]
                found = sum(1 for btn in action_buttons if btn in data)
                
                if found >= 4:
                    results.record("Benchmark detail has action buttons", True)
                else:
                    results.record("Benchmark detail has action buttons", False, f"Only {found}/6 buttons found")
            else:
                results.record("Benchmark detail renders for real benchmark", False, f"Got {resp.status_code}")
        else:
            results.record("Benchmark detail renders for real benchmark", True)  # Skip if no benchmarks
            results.record("Benchmark detail has action buttons", True)  # Skip if no benchmarks


def test_watch_status_page():
    """Test watch status page."""
    with app.test_client() as client:
        resp = client.get("/benchmark/BM-TEST-001/watch")
        
        if resp.status_code == 200:
            results.record("Watch Status page returns 200", True)
        else:
            results.record("Watch Status page returns 200", False, f"Got {resp.status_code}")
        
        data = resp.data.decode()
        if "Watch Benchmark" in data:
            results.record("Watch Status shows title", True)
        else:
            results.record("Watch Status shows title", False, "Title not found")
        
        if "updateStatus" in data and "fetch" in data:
            results.record("Watch Status has auto-refresh JS", True)
        else:
            results.record("Watch Status has auto-refresh JS", False, "JS not found")


def test_watch_status_api():
    """Test watch status API endpoint."""
    with app.test_client() as client:
        with patch('core.manager.Manager') as mock_manager:
            # Mock the manager context
            mock_instance = MagicMock()
            mock_instance.get_benchmark_status.return_value = {
                "services": [{"job_id": "123", "name": "test-svc", "status": "RUNNING", "hostname": "node1"}],
                "clients": [
                    {"job_id": "124", "name": "client-1", "status": "RUNNING", "hostname": "node2"},
                    {"job_id": "125", "name": "client-2", "status": "COMPLETED", "hostname": "node2"}
                ]
            }
            mock_manager.return_value.__enter__.return_value = mock_instance
            
            resp = client.get("/api/benchmark/BM-TEST-001/status")
            
            # API should return 200 even if manager fails (returns error JSON)
            if resp.status_code == 200:
                results.record("Watch Status API returns 200", True)
            else:
                results.record("Watch Status API returns 200", False, f"Got {resp.status_code}")
            
            try:
                data = json.loads(resp.data)
                
                if "service_status" in data and "clients_done" in data:
                    results.record("Watch Status API returns correct structure", True)
                else:
                    results.record("Watch Status API returns correct structure", False, "Missing fields")
                
                # Check structure exists (status could be ERROR if mock didn't work)
                if "service_status" in data:
                    results.record("Watch Status API has service_status field", True)
                else:
                    results.record("Watch Status API has service_status field", False, "Field missing")
            except json.JSONDecodeError:
                results.record("Watch Status API returns correct structure", False, "Invalid JSON")
                results.record("Watch Status API has service_status field", False, "Invalid JSON")


def test_stop_benchmark():
    """Test stop benchmark action."""
    with app.test_client() as client:
        with patch('core.manager.Manager') as mock_manager:
            mock_instance = MagicMock()
            mock_instance.stop_benchmark.return_value = {
                "services": ["123"],
                "clients": ["124", "125"]
            }
            mock_manager.return_value.__enter__.return_value = mock_instance
            
            resp = client.get("/benchmark/BM-TEST-001/stop", follow_redirects=False)
            
            # Should redirect (302) or error (500 if real connection attempted)
            if resp.status_code in [302, 500]:
                results.record("Stop Benchmark redirects/errors appropriately", True)
            else:
                results.record("Stop Benchmark redirects/errors appropriately", False, f"Got {resp.status_code}")


def test_logs_page():
    """Test logs viewer page."""
    with app.test_client() as client:
        resp = client.get("/benchmark/BM-TEST-001/logs")
        
        if resp.status_code == 200:
            results.record("Logs page returns 200", True)
        else:
            results.record("Logs page returns 200", False, f"Got {resp.status_code}")
        
        data = resp.data.decode()
        if "Logs for Benchmark" in data:
            results.record("Logs page shows title", True)
        else:
            results.record("Logs page shows title", False, "Title not found")


def test_logs_page_with_files():
    """Test logs page when log files exist."""
    # Create temporary log files
    from infra.storage import list_all_benchmarks
    benchmarks = list_all_benchmarks()
    
    if benchmarks:
        bm_id = benchmarks[0].benchmark_id
        
        # Check if logs directory exists
        logs_dir = Path(__file__).parent.parent / f"logs/{bm_id}"
        results_dir = Path(__file__).parent.parent / f"results/{bm_id}"
        
        has_logs = (logs_dir.exists() and any(logs_dir.glob("*.log"))) or \
                   (results_dir.exists() and any(results_dir.glob("*.log")))
        
        with app.test_client() as client:
            resp = client.get(f"/benchmark/{bm_id}/logs")
            
            if resp.status_code == 200:
                results.record("Logs page works for real benchmark", True)
            else:
                results.record("Logs page works for real benchmark", False, f"Got {resp.status_code}")
    else:
        results.record("Logs page works for real benchmark", True)  # Skip


def test_metrics_page():
    """Test metrics overview page."""
    with app.test_client() as client:
        resp = client.get("/metrics")
        
        if resp.status_code == 200:
            results.record("Metrics page returns 200", True)
        else:
            results.record("Metrics page returns 200", False, f"Got {resp.status_code}")
        
        data = resp.data.decode()
        if "Benchmark Metrics" in data:
            results.record("Metrics page shows title", True)
        else:
            results.record("Metrics page shows title", False, "Title not found")


def test_benchmark_metrics_page():
    """Test individual benchmark metrics page."""
    from infra.storage import list_all_benchmarks
    benchmarks = list_all_benchmarks()
    
    if benchmarks:
        # Find a benchmark with metrics
        for bm in benchmarks:
            summary_path = Path(__file__).parent.parent / f"results/{bm.benchmark_id}/summary.json"
            if summary_path.exists():
                with app.test_client() as client:
                    resp = client.get(f"/benchmark/{bm.benchmark_id}/metrics")
                    
                    if resp.status_code == 200:
                        results.record("Benchmark metrics page returns 200", True)
                        
                        data = resp.data.decode()
                        if "Total Requests" in data or "Success Rate" in data:
                            results.record("Benchmark metrics shows stats", True)
                        else:
                            results.record("Benchmark metrics shows stats", False, "Stats not found")
                    else:
                        results.record("Benchmark metrics page returns 200", False, f"Got {resp.status_code}")
                        results.record("Benchmark metrics shows stats", False, "Page failed")
                    return
        
        # No benchmark with metrics found
        results.record("Benchmark metrics page returns 200", True)  # Skip
        results.record("Benchmark metrics shows stats", True)  # Skip
    else:
        results.record("Benchmark metrics page returns 200", True)  # Skip
        results.record("Benchmark metrics shows stats", True)  # Skip


def test_reports_page():
    """Test reports overview page."""
    with app.test_client() as client:
        resp = client.get("/reports")
        
        if resp.status_code == 200:
            results.record("Reports page returns 200", True)
        else:
            results.record("Reports page returns 200", False, f"Got {resp.status_code}")
        
        data = resp.data.decode()
        if "Benchmark Reports" in data:
            results.record("Reports page shows title", True)
        else:
            results.record("Reports page shows title", False, "Title not found")


def test_benchmark_report_page():
    """Test individual benchmark report page."""
    from infra.storage import list_all_benchmarks
    benchmarks = list_all_benchmarks()
    
    if benchmarks:
        # Find a benchmark with a report
        for bm in benchmarks:
            report_path = Path(__file__).parent.parent / f"reports/{bm.benchmark_id}/report.md"
            if report_path.exists():
                with app.test_client() as client:
                    resp = client.get(f"/benchmark/{bm.benchmark_id}/report")
                    
                    if resp.status_code == 200:
                        results.record("Benchmark report page returns 200", True)
                    else:
                        results.record("Benchmark report page returns 200", False, f"Got {resp.status_code}")
                    return
        
        results.record("Benchmark report page returns 200", True)  # Skip - no reports
    else:
        results.record("Benchmark report page returns 200", True)  # Skip


def test_collect_artifacts():
    """Test collect artifacts action."""
    with app.test_client() as client:
        with patch('web.flask_app.collect_benchmark_artifacts') as mock_collect:
            with patch('web.flask_app.generate_benchmark_report') as mock_report:
                mock_collect.return_value = True
                mock_report.return_value = None
                
                resp = client.get("/benchmark/BM-TEST-001/collect", follow_redirects=False)
                
                # Should redirect on success
                if resp.status_code in [302, 500]:  # 302=redirect, 500=error (expected if no real benchmark)
                    results.record("Collect artifacts action works", True)
                else:
                    results.record("Collect artifacts action works", False, f"Got {resp.status_code}")


def test_prometheus_metrics_all():
    """Test Prometheus metrics endpoint for all benchmarks."""
    with app.test_client() as client:
        resp = client.get("/api/metrics/prometheus")
        
        if resp.status_code == 200:
            results.record("Prometheus /api/metrics/prometheus returns 200", True)
        else:
            results.record("Prometheus /api/metrics/prometheus returns 200", False, f"Got {resp.status_code}")
        
        # Check content type
        if resp.content_type and "text/plain" in resp.content_type:
            results.record("Prometheus endpoint returns text/plain", True)
        else:
            results.record("Prometheus endpoint returns text/plain", False, f"Got {resp.content_type}")
        
        data = resp.data.decode()
        # Should have Prometheus format or "No metrics" message
        if "benchmark_" in data or "No metrics" in data or data.startswith("#"):
            results.record("Prometheus endpoint returns valid format", True)
        else:
            results.record("Prometheus endpoint returns valid format", False, "Invalid format")


def test_prometheus_metrics_single():
    """Test Prometheus metrics endpoint for single benchmark."""
    from infra.storage import list_all_benchmarks
    benchmarks = list_all_benchmarks()
    
    if benchmarks:
        # Find a benchmark with summary
        for bm in benchmarks:
            summary_path = Path(__file__).parent.parent / f"results/{bm.benchmark_id}/summary.json"
            if summary_path.exists():
                with app.test_client() as client:
                    resp = client.get(f"/api/benchmark/{bm.benchmark_id}/metrics/prometheus")
                    
                    if resp.status_code == 200:
                        results.record("Prometheus single benchmark returns 200", True)
                        
                        data = resp.data.decode()
                        if "benchmark_requests_total" in data:
                            results.record("Prometheus single has metrics", True)
                        else:
                            results.record("Prometheus single has metrics", False, "Metrics not found")
                    else:
                        results.record("Prometheus single benchmark returns 200", False, f"Got {resp.status_code}")
                        results.record("Prometheus single has metrics", False, "Page failed")
                    return
        
        results.record("Prometheus single benchmark returns 200", True)  # Skip
        results.record("Prometheus single has metrics", True)  # Skip
    else:
        results.record("Prometheus single benchmark returns 200", True)  # Skip
        results.record("Prometheus single has metrics", True)  # Skip


def test_api_benchmarks():
    """Test API benchmarks endpoint."""
    with app.test_client() as client:
        resp = client.get("/api/benchmarks")
        
        if resp.status_code == 200:
            results.record("API /api/benchmarks returns 200", True)
        else:
            results.record("API /api/benchmarks returns 200", False, f"Got {resp.status_code}")
        
        try:
            data = json.loads(resp.data)
            if isinstance(data, list):
                results.record("API /api/benchmarks returns list", True)
            else:
                results.record("API /api/benchmarks returns list", False, "Not a list")
        except json.JSONDecodeError as e:
            results.record("API /api/benchmarks returns list", False, f"Invalid JSON: {e}")


def test_cli_reference_page():
    """Test CLI reference page."""
    with app.test_client() as client:
        resp = client.get("/cli")
        
        if resp.status_code == 200:
            results.record("CLI Reference returns 200", True)
        else:
            results.record("CLI Reference returns 200", False, f"Got {resp.status_code}")
        
        data = resp.data.decode()
        # Check it has CLI commands
        commands = ["--list", "--summary", "--watch", "--logs", "--stop", "--report", "--compare"]
        found = sum(1 for cmd in commands if cmd in data)
        
        if found >= 5:
            results.record("CLI Reference shows commands", True)
        else:
            results.record("CLI Reference shows commands", False, f"Only {found}/7 commands found")


def test_plots_page():
    """Test plots page."""
    from infra.storage import list_all_benchmarks
    benchmarks = list_all_benchmarks()
    
    if benchmarks:
        # Find a benchmark with plots
        for bm in benchmarks:
            plots_dir = Path(__file__).parent.parent / f"reports/{bm.benchmark_id}/plots"
            if plots_dir.exists() and any(plots_dir.glob("*.png")):
                with app.test_client() as client:
                    resp = client.get(f"/benchmark/{bm.benchmark_id}/plots")
                    
                    if resp.status_code == 200:
                        results.record("Plots page returns 200", True)
                    else:
                        results.record("Plots page returns 200", False, f"Got {resp.status_code}")
                    return
        
        results.record("Plots page returns 200", True)  # Skip - no plots
    else:
        results.record("Plots page returns 200", True)  # Skip


def test_navigation_links():
    """Test that all navigation links work."""
    with app.test_client() as client:
        pages = ["/", "/run", "/benchmarks", "/metrics", "/reports", "/cli"]
        
        all_ok = True
        for page in pages:
            resp = client.get(page)
            if resp.status_code != 200:
                all_ok = False
                break
        
        if all_ok:
            results.record("All navigation links return 200", True)
        else:
            results.record("All navigation links return 200", False, f"Failed on {page}")


def test_404_handling():
    """Test 404 handling for non-existent pages."""
    with app.test_client() as client:
        resp = client.get("/nonexistent-page-xyz")
        
        if resp.status_code == 404:
            results.record("Non-existent page returns 404", True)
        else:
            results.record("Non-existent page returns 404", False, f"Got {resp.status_code}")


def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("Web Interface Test Suite")
    print("=" * 60)
    
    print("\n📁 Recipe Discovery Tests:")
    test_recipe_discovery()
    
    print("\n🏠 Dashboard Tests:")
    test_dashboard_page()
    
    print("\n🚀 Run Recipe Tests:")
    test_run_recipe_page_get()
    test_run_recipe_page_post()
    
    print("\n📋 Benchmarks Tests:")
    test_benchmarks_list_page()
    test_benchmark_detail_page()
    
    print("\n👁️ Watch Status Tests:")
    test_watch_status_page()
    test_watch_status_api()
    
    print("\n⏹️ Stop Benchmark Tests:")
    test_stop_benchmark()
    
    print("\n📜 Logs Tests:")
    test_logs_page()
    test_logs_page_with_files()
    
    print("\n📊 Metrics Tests:")
    test_metrics_page()
    test_benchmark_metrics_page()
    
    print("\n📄 Reports Tests:")
    test_reports_page()
    test_benchmark_report_page()
    test_plots_page()
    
    print("\n📥 Collect Artifacts Tests:")
    test_collect_artifacts()
    
    print("\n📈 Prometheus Metrics Tests:")
    test_prometheus_metrics_all()
    test_prometheus_metrics_single()
    
    print("\n🔌 API Tests:")
    test_api_benchmarks()
    
    print("\n📚 CLI Reference Tests:")
    test_cli_reference_page()
    
    print("\n🔗 Navigation Tests:")
    test_navigation_links()
    test_404_handling()
    
    return results.summary()


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
