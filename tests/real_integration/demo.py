#!/usr/bin/env python3
"""
Demo script showing how to run real integration tests step by step.

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
    print(f"\n{'='*60}")
    print(f"STEP {step}: {description}")
    print('='*60)


def print_substep(substep: str) -> None:
    """Print a substep."""
    print(f"\n  → {substep}")


def check_environment() -> bool:
    """Check if environment is properly configured."""
    print_step("1", "Checking Environment Configuration")
    
    # Check for tokens
    github_token = os.environ.get("GITHUB_TOKEN")
    gitlab_token = os.environ.get("GITLAB_TOKEN")
    openai_key = os.environ.get("OPENAI_API_KEY")
    
    if not github_token and not gitlab_token:
        print("❌ No API tokens found!")
        print("\n📝 To set up environment variables:")
        print("   1. Copy tests/real_integration/.env.example to .env")
        print("   2. Fill in your API tokens and repository information")
        print("   3. Source the environment: source .env")
        return False
        
    if not openai_key:
        print("❌ No OpenAI API key found!")
        print("   Please set OPENAI_API_KEY environment variable")
        return False
        
    print("✅ Environment appears to be configured")
    return True


def run_config_check() -> bool:
    """Run the configuration checker."""
    print_step("2", "Running Configuration Checker")
    
    try:
        result = subprocess.run(
            [sys.executable, "tests/real_integration/check_config.py"],
            capture_output=True,
            text=True,
        )
        
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
            
        return result.returncode == 0
        
    except Exception as e:
        print(f"❌ Failed to run configuration checker: {e}")
        return False


def run_mock_tests() -> bool:
    """Run mock tests to ensure basic functionality."""
    print_step("3", "Running Mock Tests (Baseline)")
    
    print_substep("Running existing mock tests to ensure functionality...")
    
    try:
        result = subprocess.run(
            [sys.executable, "tests/run_tests.py", "--mock"],
            capture_output=True,
            text=True,
        )
        
        # Print summary
        lines = result.stdout.split('\n')
        for line in lines:
            if 'Ran' in line and 'tests' in line:
                print(f"  {line}")
            elif 'OK' in line or 'FAILED' in line:
                print(f"  {line}")
                
        return result.returncode == 0
        
    except Exception as e:
        print(f"❌ Failed to run mock tests: {e}")
        return False


def run_real_tests() -> bool:
    """Run the real integration tests."""
    print_step("4", "Running Real Integration Tests")
    
    print_substep("🚀 Starting real integration tests with actual APIs...")
    print("   This may take several minutes as it involves:")
    print("   - Creating actual GitHub/GitLab issues")
    print("   - Running the coding agent")
    print("   - Verifying file creation and execution")
    print("   - Creating pull requests and comments")
    
    try:
        result = subprocess.run(
            [sys.executable, "tests/run_tests.py", "--real"],
            text=True,
        )
        
        return result.returncode == 0
        
    except Exception as e:
        print(f"❌ Failed to run real integration tests: {e}")
        return False


def main() -> None:
    """Main demo function."""
    print("🤖 Coding Agent Real Integration Test Demo")
    print("This script will guide you through running real integration tests")
    
    # Step 1: Check environment
    if not check_environment():
        sys.exit(1)
        
    # Step 2: Run configuration checker
    if not run_config_check():
        print("\n❌ Configuration check failed!")
        print("Please fix the configuration issues and try again.")
        sys.exit(1)
        
    # Step 3: Run mock tests first
    print_substep("Running baseline tests to ensure the system is working...")
    if not run_mock_tests():
        print("\n❌ Mock tests failed!")
        print("Please fix any issues with the basic functionality first.")
        sys.exit(1)
        
    print("\n✅ Mock tests passed! System is ready for real integration tests.")
    
    # Step 4: Ask user if they want to proceed
    print("\n⚠️  WARNING: Real integration tests will:")
    print("  - Create actual issues in your test repository")
    print("  - Make commits to your repository")
    print("  - Create branches and pull requests")
    print("  - Use your LLM API quota")
    print("  - May take 10-15 minutes to complete")
    
    response = input("\nDo you want to proceed? (y/N): ").strip().lower()
    if response not in ['y', 'yes']:
        print("Demo cancelled by user.")
        sys.exit(0)
        
    # Step 5: Run real tests
    if run_real_tests():
        print("\n🎉 Real integration tests completed successfully!")
        print("\nNext steps:")
        print("  - Check your test repository for created files and issues")
        print("  - Review the test logs for detailed information")
        print("  - Clean up test artifacts if needed")
    else:
        print("\n❌ Real integration tests failed!")
        print("Check the output above for details about what went wrong.")
        sys.exit(1)


if __name__ == "__main__":
    # Change to the coding agent directory
    script_dir = Path(__file__).parent
    agent_dir = script_dir.parent.parent
    os.chdir(agent_dir)
    
    main()