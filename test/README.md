# test/ - Test Suite

Pytest test suite for the benchmarking framework.

## Test Files

| File | Description |
|------|-------------|
| `test_aggregator.py` | Tests for benchmark data aggregation |
| `test_integration_e2e.py` | End-to-end integration tests |
| `test_kf_features.py` | Key feature validation tests |
| `test_manager.py` | Manager class functionality tests |
| `test_month4_services.py` | Month 4 service deployment tests |
| `test_new_features.py` | New feature unit tests |
| `test_web_interface.py` | Web UI functionality tests |

## Running Tests

```bash
# Run all tests
python -m pytest test/ -v

# Run specific test file
python -m pytest test/test_manager.py -v

# Run with coverage
python -m pytest test/ --cov=src
```
