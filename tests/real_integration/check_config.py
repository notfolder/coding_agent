#!/usr/bin/env python3
"""Configuration test script for real integration tests.

This script validates that the environment is properly configured
for running real integration tests.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import requests

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# HTTP status constants
HTTP_OK = 200
HTTP_NOT_FOUND = 404
REQUEST_TIMEOUT = 30


def check_github_config() -> bool:
    """Check GitHub configuration."""
    token = (
        os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
    )
    repo = os.environ.get("GITHUB_TEST_REPO")

    if not token or not repo or "/" not in repo:
        return False

    # Test GitHub API access
    try:
        headers = {"Authorization": f"token {token}"}
        response = requests.get(
            f"https://api.github.com/repos/{repo}",
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException:
        return False
    else:
        return response.status_code == HTTP_OK


def check_gitlab_config() -> bool:
    """Check GitLab configuration."""
    token = (
        os.environ.get("GITLAB_PERSONAL_ACCESS_TOKEN")
        or os.environ.get("GITLAB_TOKEN")
    )
    project = os.environ.get("GITLAB_TEST_PROJECT")
    api_url = os.environ.get("GITLAB_API_URL", "https://gitlab.com/api/v4")

    if not token or not project:
        return False

    # Test GitLab API access
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(
            f"{api_url}/projects/{project}",
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException:
        return False
    else:
        return response.status_code == HTTP_OK


def check_llm_config() -> bool:
    """Check LLM configuration."""
    provider = os.environ.get("LLM_PROVIDER", "openai")

    if provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return False
        return api_key.startswith("sk-")
    return True


def check_dependencies() -> bool:
    """Check required dependencies."""
    required_packages = ["requests", "yaml", "portalocker"]
    missing = []

    # Check packages and collect missing ones using list comprehension for better performance
    missing = [package for package in required_packages if not _check_package_import(package)]

    return not missing


def _check_package_import(package: str) -> bool:
    """Check if a single package can be imported."""
    try:
        __import__(package)
    except ImportError:
        return False
    else:
        return True


def _run_check_safely(check_func: callable) -> bool:
    """Run a check function safely, catching exceptions."""
    try:
        return check_func()
    except (ImportError, OSError, subprocess.SubprocessError):
        return False


def check_mcp_servers() -> bool:
    """Check MCP server availability."""
    # Check if GitHub MCP server exists
    github_server = Path(__file__).parent.parent.parent / "github-mcp-server"
    github_ok = bool(github_server.exists())

    # Check for Node.js and npm packages
    try:
        # Use absolute path for security
        npm_cmd = "/usr/bin/npm"
        if not Path(npm_cmd).exists():
            npm_cmd = "npm"  # Fallback to PATH lookup

        # This subprocess call is safe: using validated npm command with fixed arguments
        npm_args = [npm_cmd, "list", "@zereight/mcp-gitlab"]
        result = subprocess.run(  # noqa: S603
            npm_args,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,  # Add timeout for security
        )
        gitlab_ok = result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        gitlab_ok = False

    return github_ok or gitlab_ok


def main() -> None:
    """Check and validate configuration settings."""
    checks = [
        ("Dependencies", check_dependencies),
        ("MCP Servers", check_mcp_servers),
        ("LLM Configuration", check_llm_config),
    ]

    # Check platform configurations
    github_configured = check_github_config()
    gitlab_configured = check_gitlab_config()

    if github_configured:
        checks.append(("GitHub", lambda: True))
        print("✅ GitHub testing enabled")  # noqa: T201
        github_bot = os.environ.get("GITHUB_BOT_NAME")
        if github_bot:
            print(f"   Bot assignment: {github_bot}")  # noqa: T201
        else:
            print("   Bot assignment: Not configured (issues won't be assigned)")  # noqa: T201

    if gitlab_configured:
        checks.append(("GitLab", lambda: True))
        print("✅ GitLab testing enabled")  # noqa: T201
        gitlab_bot = os.environ.get("GITLAB_BOT_NAME")
        if gitlab_bot:
            print(f"   Bot assignment: {gitlab_bot}")  # noqa: T201
        else:
            print("   Bot assignment: Not configured (issues won't be assigned)")  # noqa: T201

    if not github_configured and not gitlab_configured:
        print("❌ No platform configured. Please set up GitHub or GitLab credentials.")  # noqa: T201
        sys.exit(1)

    # Run remaining checks
    all_passed = True
    for _name, check_func in checks:
        if not _run_check_safely(check_func):
            all_passed = False

    if all_passed and (github_configured or gitlab_configured):
        print("\n🎉 All configuration checks passed! Ready to run real integration tests.")  # noqa: T201
        print("Run: python tests/run_tests.py --real")  # noqa: T201
    else:
        print("\n❌ Some configuration checks failed. Please review your setup.")  # noqa: T201
        sys.exit(1)


if __name__ == "__main__":
    main()
