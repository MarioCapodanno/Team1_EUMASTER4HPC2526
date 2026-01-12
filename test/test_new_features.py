
import sys
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
import json

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from frontend import cmd_list_recipes, cmd_compare_benchmarks, cmd_rerun_benchmark
from web.flask_app import app

class TestNewFeatures(unittest.TestCase):
    
    def test_cli_list_recipes(self):
        """Test --list-recipes command."""
        with patch('frontend.get_available_recipes') as mock_get:
            mock_recipe = MagicMock()
            mock_recipe.stem = "recipe_test"
            mock_recipe.__str__ = lambda x: "examples/recipe_test.yaml"
            mock_get.return_value = [mock_recipe]
            
            # Should return 0 (success)
            ret = cmd_list_recipes()
            self.assertEqual(ret, 0)
            
    def test_cli_compare(self):
        """Test --compare command."""
        with patch('frontend.read_summary_json') as mock_read:
            # Mock summaries
            mock_read.side_effect = [
                {"service_type": "test", "success_rate": 100, "latency_s": {"avg": 0.1}}, # Baseline
                {"service_type": "test", "success_rate": 99, "latency_s": {"avg": 0.15}}  # Current
            ]
            
            with patch('frontend.compare_summaries') as mock_compare:
                mock_compare.return_value = {
                    "verdict": "FAIL",
                    "metrics": {
                        "latency": {"label": "Latency", "baseline": 0.1, "current": 0.15, "delta": 0.05, "percent_change": 50, "regression": True}
                    }
                }
                
                ret = cmd_compare_benchmarks("BM-1", "BM-2")
                # Should return 1 because verdict is FAIL
                self.assertEqual(ret, 1)

    def test_web_compare_route(self):
        """Test Web UI /compare route."""
        with app.test_client() as client:
            # 1. Test GET without args (render selection)
            resp = client.get("/compare")
            self.assertEqual(resp.status_code, 200)
            self.assertIn(b"Compare Benchmarks", resp.data)
            
            # 2. Test GET with args
            with patch('web.flask_app.read_summary_json') as mock_read:
                mock_read.return_value = {"service_type": "test", "created_at": "2023-01-01"}
                
                resp = client.get("/compare?baseline=BM-1&current=BM-2")
                self.assertEqual(resp.status_code, 200)
                # Should show verdict logic if comparison worked
                # (We didn't mock list_all_benchmarks, so benchmarks dropdown might be empty, but that's fine)
    
    def test_web_rerun_route(self):
        """Test Web UI /benchmark/rerun route."""
        with app.test_client() as client:
            with patch('web.flask_app.read_run_json') as mock_read:
                mock_read.return_value = {"recipe": {"foo": "bar"}}
                
                with patch('frontend.run_benchmark_from_recipe') as mock_run:
                    mock_run.return_value = "BM-NEW-1"
                    
                    resp = client.get("/benchmark/BM-OLD-1/rerun")
                    # Should redirect
                    self.assertEqual(resp.status_code, 302)
                    self.assertIn("BM-NEW-1", resp.location)

if __name__ == "__main__":
    unittest.main()
