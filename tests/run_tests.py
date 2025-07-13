#!/usr/bin/env python3
"""Comprehensive test runner for coding agent with mock and real integration tests."""

import logging
import os
import sys
import unittest
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def run_tests() -> bool:
    """Run all tests and return results."""
    # Setup logging to suppress noise during tests
    logging.basicConfig(level=logging.CRITICAL)

    # Discover and run tests
    loader = unittest.TestLoader()
    start_dir = str(Path(__file__).parent)
    suite = loader.discover(start_dir, pattern="test_*.py")

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Return success status
    return result.wasSuccessful()


def run_unit_tests() -> bool:
    """Run only unit tests."""
    logging.basicConfig(level=logging.CRITICAL)

    loader = unittest.TestLoader()
    unit_dir = str(Path(__file__).parent / "unit")
    suite = loader.discover(unit_dir, pattern="test_*.py")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


def run_integration_tests() -> bool:
    """Run only integration tests."""
    logging.basicConfig(level=logging.CRITICAL)

    loader = unittest.TestLoader()
    integration_dir = str(Path(__file__).parent / "integration")
    suite = loader.discover(integration_dir, pattern="test_*.py")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


def run_real_tests() -> bool:
    """Run real integration tests (requires API tokens)."""
    # Check for API tokens
    github_token = os.environ.get("GITHUB_TOKEN")
    gitlab_token = os.environ.get("GITLAB_TOKEN")
    github_repo = os.environ.get("GITHUB_TEST_REPO")
    gitlab_project = os.environ.get("GITLAB_TEST_PROJECT")

    if not github_token and not gitlab_token:
        print("❌ No API tokens found. Please set GITHUB_TOKEN or GITLAB_TOKEN environment variables.")
        return False

    if github_token and not github_repo:
        print("❌ GITHUB_TOKEN is set but GITHUB_TEST_REPO is missing. Please set GITHUB_TEST_REPO (format: owner/repo).")
        return False
        
    if gitlab_token and not gitlab_project:
        print("❌ GITLAB_TOKEN is set but GITLAB_TEST_PROJECT is missing. Please set GITLAB_TEST_PROJECT.")
        return False

    if github_token and github_repo:
        print(f"✅ GitHub testing enabled for repository: {github_repo}")
    else:
        print("⚠️  GitHub testing disabled (no token or repo configured)")

    if gitlab_token and gitlab_project:
        print(f"✅ GitLab testing enabled for project: {gitlab_project}")
    else:
        print("⚠️  GitLab testing disabled (no token or project configured)")

    # Check for LLM configuration
    llm_provider = os.environ.get("LLM_PROVIDER", "openai")
    if llm_provider == "openai" and not os.environ.get("OPENAI_API_KEY"):
        print("❌ LLM_PROVIDER is 'openai' but OPENAI_API_KEY is not set.")
        return False
    elif llm_provider == "openai":
        print("✅ OpenAI LLM configured")

    print("\n🚀 Running real integration tests...")
    logging.basicConfig(level=logging.INFO)

    # Import and run real integration tests
    try:
        loader = unittest.TestLoader()
        real_integration_dir = str(Path(__file__).parent / "real_integration")
        suite = loader.discover(real_integration_dir, pattern="test_*.py")

        # Create a detailed test runner
        runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
        result = runner.run(suite)

        # Print summary
        print(f"\n📊 Test Results:")
        print(f"Tests run: {result.testsRun}")
        print(f"Failures: {len(result.failures)}")
        print(f"Errors: {len(result.errors)}")

        if result.failures:
            print("\n❌ FAILURES:")
            for test, traceback in result.failures:
                print(f"- {test}: {traceback}")

        if result.errors:
            print("\n❌ ERRORS:")
            for test, traceback in result.errors:
                print(f"- {test}: {traceback}")

        return result.wasSuccessful()

    except ImportError as e:
        print(f"❌ Failed to import real integration tests: {e}")
        return False
    except (OSError, RuntimeError) as e:
        print(f"❌ Failed to run real integration tests: {e}")
        return False


def run_mock_tests() -> bool:
    """Run comprehensive tests with mock services."""
    logging.basicConfig(level=logging.CRITICAL)

    # Import test modules to ensure they're available
    try:

        # Run comprehensive test suite
        loader = unittest.TestLoader()
        start_dir = str(Path(__file__).parent)
        suite = loader.discover(start_dir, pattern="test_*.py")

        # Create a detailed test runner
        runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
        result = runner.run(suite)

        # Print summary

        if result.failures:
            for _test, _traceback in result.failures:
                pass

        if result.errors:
            for _test, _traceback in result.errors:
                pass

        return result.wasSuccessful()

    except ImportError:
        return False
    except (OSError, RuntimeError):
        return False


def run_coverage_tests() -> bool:
    """Run tests with coverage analysis (if coverage is available)."""
    try:
        import coverage  # noqa: PLC0415
    except ImportError:
        return run_mock_tests()

    # Create coverage instance
    cov = coverage.Coverage()
    cov.start()

    # Run tests
    success = run_mock_tests()

    # Stop coverage and generate report
    cov.stop()
    cov.save()

    cov.report()

    return success


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run coding agent tests")
    parser.add_argument("--unit", action="store_true", help="Run only unit tests")
    parser.add_argument("--integration", action="store_true", help="Run only integration tests")
    parser.add_argument(
        "--real", action="store_true", help="Run real API integration tests (requires tokens)",
    )
    parser.add_argument("--mock", action="store_true", help="Run comprehensive mock tests")
    parser.add_argument("--coverage", action="store_true", help="Run tests with coverage analysis")
    args = parser.parse_args()

    if args.unit:
        success = run_unit_tests()
    elif args.integration:
        success = run_integration_tests()
    elif args.real:
        success = run_real_tests()
    elif args.coverage:
        success = run_coverage_tests()
    elif args.mock:
        success = run_mock_tests()
    else:
        # Default: run comprehensive mock tests
        success = run_mock_tests()

    sys.exit(0 if success else 1)
