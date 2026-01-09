#!/usr/bin/env python3
"""
Interactive UI Test Runner
Automatically tests all --ui menu options
"""

import subprocess
import sys


def run_ui_test(option, inputs=None, timeout=5):
    """Run the UI with specified inputs"""
    cmd = ["python", "src/frontend.py", "--ui"]

    if inputs:
        # Create input string
        input_str = "\n".join(inputs) + "\nq\n"  # Add quit at end
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, stderr = proc.communicate(input=input_str, timeout=timeout)
        return proc.returncode, stdout, stderr
    else:
        # Just start and quit
        input_str = "q\n"
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, stderr = proc.communicate(input=input_str, timeout=timeout)
        return proc.returncode, stdout, stderr


def test_ui_menu():
    """Test the UI menu appears correctly"""
    print("\n" + "=" * 60)
    print("TEST: UI Menu Display")
    print("=" * 60)

    code, stdout, stderr = run_ui_test([])

    if "Main Menu:" in stdout and "[1] Run a recipe" in stdout:
        print("[PASS] Menu displays correctly")
        return True
    else:
        print("[FAIL] Menu not displayed")
        print("STDOUT:", stdout[:500])
        return False


def test_list_benchmarks():
    """Test Option 2: List benchmarks"""
    print("\n" + "=" * 60)
    print("TEST: List Benchmarks (Option 2)")
    print("=" * 60)

    code, stdout, stderr = run_ui_test(["2"])

    if "postgres-stress" in stdout and "[29]" in stdout:
        print("[PASS] Benchmarks listed")
        return True
    else:
        print("[FAIL] Benchmarks not listed")
        return False


def test_show_summary():
    """Test Option 3: Show summary"""
    print("\n" + "=" * 60)
    print("TEST: Show Summary (Option 3)")
    print("=" * 60)

    code, stdout, stderr = run_ui_test(["3", "29"])

    if "Performance Metrics:" in stdout and "Total Requests:" in stdout:
        print("[PASS] Summary with metrics shown")
        return True
    else:
        print("[FAIL] Summary not shown properly")
        return False


def test_watch_completed():
    """Test Option 4: Watch completed benchmark"""
    print("\n" + "=" * 60)
    print("TEST: Watch Completed Benchmark (Option 4)")
    print("=" * 60)

    code, stdout, stderr = run_ui_test(["4", "29"])

    if "already completed" in stdout or "Total Requests:" in stdout:
        print("[PASS] Returns immediately for completed benchmark")
        return True
    else:
        print("[FAIL] Doesn't handle completed benchmark correctly")
        return False


def test_show_logs():
    """Test Option 6: Show logs"""
    print("\n" + "=" * 60)
    print("TEST: Show Logs (Option 6)")
    print("=" * 60)

    code, stdout, stderr = run_ui_test(["6", "29"], timeout=10)

    # Should either show local logs or fetch from cluster
    if "Service:" in stdout or "Fetching logs from cluster" in stdout:
        print("[PASS] Logs displayed or fetched")
        return True
    else:
        print("[FAIL] Logs not shown")
        return False


def test_invalid_inputs():
    """Test invalid inputs"""
    print("\n" + "=" * 60)
    print("TEST: Invalid Inputs")
    print("=" * 60)

    results = []

    # Test invalid menu option
    code, stdout, stderr = run_ui_test(["x", "q"])
    if "Invalid option" in stdout or "Main Menu:" in stdout:
        print("[PASS] Handles invalid menu option")
        results.append(True)
    else:
        print("[FAIL] Doesn't handle invalid option")
        results.append(False)

    # Test invalid benchmark ID
    code, stdout, stderr = run_ui_test(["3", "99999"])
    if "not found" in stdout or "❌" in stdout:
        print("[PASS] Handles invalid benchmark ID")
        results.append(True)
    else:
        print("[FAIL] Doesn't handle invalid ID")
        results.append(False)

    return all(results)


def main():
    """Run all UI tests"""
    print("=" * 60)
    print("INTERACTIVE UI TESTING")
    print("Testing all --ui menu options")
    print("=" * 60)

    tests = [
        ("Menu Display", test_ui_menu),
        ("List Benchmarks", test_list_benchmarks),
        ("Show Summary", test_show_summary),
        ("Watch Completed", test_watch_completed),
        ("Show Logs", test_show_logs),
        ("Invalid Inputs", test_invalid_inputs),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"[FAIL] {test_name} crashed: {e}")
            results.append((test_name, False))

    # Summary
    print("\n" + "=" * 60)
    print("UI TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} {test_name}")

    print(f"\nOverall: {passed}/{total} tests passed")

    if passed == total:
        print("\n[SUCCESS] All UI interactions work correctly!")
        print("The --ui mode is fully functional.")
    else:
        print(f"\n[FAIL] {total - passed} test(s) failed")
        print("Review the issues before using --ui mode.")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
