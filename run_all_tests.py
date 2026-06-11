#!/usr/bin/env python3
"""GEO Optimizer — Master Test Runner

Runs all backend and frontend tests with a single command.

Usage:
    python run_all_tests.py          # Run all tests
    python run_all_tests.py --quick  # Backend only (fast)
    python run_all_tests.py -v       # Verbose output
"""

import subprocess
import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
RESET = "\033[0m"
BOLD = "\033[1m"


def run_backend(verbose=False):
    """Run all backend pytest tests."""
    print(f"{CYAN}{'='*60}{RESET}")
    print(f"{BOLD}Backend Tests (pytest){RESET}")
    print(f"{CYAN}{'='*60}{RESET}")

    args = [sys.executable, "-m", "pytest", "tests/"]
    if verbose:
        args.append("-v")
    else:
        args.extend(["-q", "--tb=short"])

    result = subprocess.run(args, cwd=str(BACKEND))
    return result.returncode == 0


def run_frontend(verbose=False):
    """Run all frontend vitest tests."""
    print(f"\n{CYAN}{'='*60}{RESET}")
    print(f"{BOLD}Frontend Tests (vitest){RESET}")
    print(f"{CYAN}{'='*60}{RESET}")

    args = ["npx", "vitest", "run", "src/__tests__/"]
    if verbose:
        args.insert(2, "--reporter=verbose")

    result = subprocess.run(args, cwd=str(FRONTEND), shell=True)
    return result.returncode == 0


def main():
    verbose = "-v" in sys.argv or "--verbose" in sys.argv
    quick = "--quick" in sys.argv

    print(f"{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  GEO Optimizer — Full Test Suite{RESET}")
    print(f"{BOLD}{'='*60}{RESET}")
    print()

    backend_ok = run_backend(verbose)

    if not quick:
        frontend_ok = run_frontend(verbose)
    else:
        print(f"\n{YELLOW}  --quick mode: skipping frontend tests{RESET}")
        frontend_ok = True

    # Summary
    print(f"\n{BOLD}{'='*60}{RESET}")
    if backend_ok and frontend_ok:
        print(f"{GREEN}{BOLD}  ALL TESTS PASSED{RESET}")
        print(f"{GREEN}  Backend: PASS | Frontend: PASS{RESET}")
        return 0
    else:
        print(f"{RED}{BOLD}  SOME TESTS FAILED{RESET}")
        if not backend_ok:
            print(f"{RED}  Backend: FAIL{RESET}")
        if not frontend_ok:
            print(f"{RED}  Frontend: FAIL{RESET}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
