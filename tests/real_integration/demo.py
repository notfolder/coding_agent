#!/usr/bin/env python3
"""Demo script showing how to run real integration tests step by step.

This script demonstrates the complete workflow of setting up and running
real integration tests for the coding agent.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def print_step(step: str, description: str) -> None:
    """Print a step header."""


def print_substep(substep: str) -> None:
    """Print a substep."""


def check_environment() -> bool:
    """Check if environment is properly configured."""
    print_step("1", "Checking Environment Configuration")

    # Check for tokens
    github_token = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN") or os.environ.get("GITHUB_TOKEN")
    gitlab_token = os.environ.get("GITLAB_PERSONAL_ACCESS_TOKEN") or os.environ.get("GITLAB_TOKEN")
    openai_key = os.environ.get("OPENAI_API_KEY")

    if not github_token and not gitlab_token:
        return False

    return openai_key


def run_config_check() -> bool:
    """Run the configuration checker."""
    print_step("2", "Running Configuration Checker")

    try:
        # Safe subprocess call: using sys.executable and hardcoded script path
        demo_args = [sys.executable, "tests/real_integration/check_config.py"]
        result = subprocess.run(  # noqa: S603
            demo_args,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,  # Add timeout for security
        )

        if result.stderr:
            pass
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    else:
        return result.returncode == 0


def run_mock_tests() -> bool:
    """Run mock tests to ensure basic functionality."""
    print_step("3", "Running Mock Tests (Baseline)")

    print_substep("Running existing mock tests to ensure functionality...")

    try:
        # Safe subprocess call: using sys.executable and hardcoded script path
        test_args = [sys.executable, "tests/run_tests.py", "--mock"]
        result = subprocess.run(  # noqa: S603
            test_args,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,  # Add timeout for security
        )

        # Print summary
        lines = result.stdout.split("\n")
        for line in lines:
            if ("Ran" in line and "tests" in line) or "OK" in line or "FAILED" in line:
                pass
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    else:
        return result.returncode == 0


def run_real_tests() -> bool:
    """Run the real integration tests."""
    print_step("4", "Running Real Integration Tests")

    print_substep("🚀 Starting real integration tests with actual APIs...")

    try:
        # Safe subprocess call: using sys.executable and hardcoded script path
        real_test_args = [sys.executable, "tests/run_tests.py", "--real"]
        result = subprocess.run(  # noqa: S603
            real_test_args,
            check=False,
            text=True,
            timeout=1800,  # Add timeout for security (30 minutes)
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    else:
        return result.returncode == 0


def main() -> None:
    """Run main demo function."""
    # Step 1: Check environment
    if not check_environment():
        sys.exit(1)

    # Step 2: Run configuration checker
    if not run_config_check():
        sys.exit(1)

    # Step 3: Run mock tests first
    print_substep("Running baseline tests to ensure the system is working...")
    if not run_mock_tests():
        sys.exit(1)


    # Step 4: Ask user if they want to proceed

    response = input("\nDo you want to proceed? (y/N): ").strip().lower()
    if response not in ["y", "yes"]:
        sys.exit(0)

    # Step 5: Run real tests
    if run_real_tests():
        pass
    else:
        sys.exit(1)


if __name__ == "__main__":
    # Change to the coding agent directory
    script_dir = Path(__file__).parent
    agent_dir = script_dir.parent.parent
    os.chdir(agent_dir)

    main()
