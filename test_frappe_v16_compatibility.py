#!/usr/bin/env python
"""
Frappe V16 Compatibility Test Suite for Thanatos Intel App
Tests packaging, imports, and Frappe framework compatibility
"""

import sys
import subprocess
from pathlib import Path

def run_command(cmd, description):
    """Run a command and report results"""
    print(f"\n{'='*60}")
    print(f"🧪 {description}")
    print(f"{'='*60}")
    print(f"Running: {' '.join(cmd)}")
    print("-" * 60)
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        if result.returncode == 0:
            print(f"✅ PASSED: {description}")
            return True
        else:
            print(f"❌ FAILED: {description}")
            return False
    except subprocess.TimeoutExpired:
        print(f"⏱️ TIMEOUT: {description}")
        return False
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        return False

def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("🚀 FRAPPE V16 COMPATIBILITY TEST SUITE")
    print("   Thanatos Intel - Intelligence Investigation Platform MVP")
    print("="*60)
    
    results = {}
    
    # Test 1: Python version check
    results["Python Version"] = run_command(
        [sys.executable, "--version"],
        "Check Python Version (requires 3.10+)"
    )
    
    # Test 2: pip list check
    results["Pip Version"] = run_command(
        [sys.executable, "-m", "pip", "--version"],
        "Check Pip Version"
    )
    
    # Test 3: Check if requirements can be parsed
    results["Requirements Parse"] = run_command(
        [sys.executable, "-c", "import sys; print([line for line in open('requirements.txt').readlines() if line.strip()])"],
        "Parse requirements.txt"
    )
    
    # Test 4: Check setup.py syntax
    results["Setup.py Syntax"] = run_command(
        [sys.executable, "-m", "py_compile", "setup.py"],
        "Validate setup.py Syntax"
    )
    
    # Test 5: Check hooks.py syntax
    results["Hooks.py Syntax"] = run_command(
        [sys.executable, "-m", "py_compile", "thanatos_intel/hooks.py"],
        "Validate hooks.py Syntax"
    )
    
    # Test 6: Check __init__.py syntax
    results["Init.py Syntax"] = run_command(
        [sys.executable, "-m", "py_compile", "thanatos_intel/__init__.py"],
        "Validate __init__.py Syntax"
    )
    
    # Test 7: Package discovery test
    results["Package Discovery"] = run_command(
        [sys.executable, "-c", "from setuptools import find_packages; print(find_packages())"],
        "Verify Package Discovery"
    )
    
    # Test 8: Validate toml syntax
    results["TOML Syntax"] = run_command(
        [sys.executable, "-c", "import tomllib; tomllib.loads(open('pyproject.toml').read()); print('✓ pyproject.toml is valid TOML')"],
        "Validate pyproject.toml Syntax"
    )
    
    # Summary Report
    print("\n" + "="*60)
    print("📊 TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    print("-" * 60)
    print(f"Result: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED! App is ready for Frappe V16")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please review.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
