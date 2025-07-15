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

        return response.status_code == HTTP_OK

    except requests.RequestException:
        return False


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

        return response.status_code == HTTP_OK

    except requests.RequestException:
        return False


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

    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing.append(package)

    return not missing


def check_mcp_servers() -> bool:
    """Check MCP server availability."""
    # Check if GitHub MCP server exists
    github_server = Path(__file__).parent.parent.parent / "github-mcp-server"
    github_ok = bool(github_server.exists())

    # Check for Node.js and npm packages
    try:
        result = subprocess.run(["npm", "list", "@zereight/mcp-gitlab"],
                              check=False, capture_output=True, text=True)
        gitlab_ok = result.returncode == 0
    except FileNotFoundError:
        gitlab_ok = False

    return github_ok or gitlab_ok


def main() -> None:
    """Main configuration check."""
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
    if gitlab_configured:
        checks.append(("GitLab", lambda: True))

    if not github_configured and not gitlab_configured:
        sys.exit(1)

    # Run remaining checks
    all_passed = True
    for _name, check_func in checks:
        try:
            if not check_func():
                all_passed = False
        except Exception as e:
            all_passed = False

    if all_passed and (github_configured or gitlab_configured):
        pass
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
