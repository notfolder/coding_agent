#!/usr/bin/env python3
"""Configuration test script for real integration tests.

This script validates that the environment is properly configured
for running real integration tests.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def check_github_config() -> bool:
    """Check GitHub configuration."""
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_TEST_REPO")
    
    if not token:
        print("❌ GITHUB_TOKEN not set")
        return False
        
    if not repo:
        print("❌ GITHUB_TEST_REPO not set")
        return False
        
    if "/" not in repo:
        print("❌ GITHUB_TEST_REPO should be in format 'owner/repo'")
        return False
        
    # Test GitHub API access
    try:
        import requests
        headers = {"Authorization": f"token {token}"}
        response = requests.get(f"https://api.github.com/repos/{repo}", headers=headers)
        
        if response.status_code == 200:
            print(f"✅ GitHub configuration valid for {repo}")
            return True
        elif response.status_code == 404:
            print(f"❌ Repository {repo} not found or not accessible")
            return False
        else:
            print(f"❌ GitHub API error: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ GitHub API test failed: {e}")
        return False


def check_gitlab_config() -> bool:
    """Check GitLab configuration."""
    token = os.environ.get("GITLAB_TOKEN")
    project = os.environ.get("GITLAB_TEST_PROJECT")
    api_url = os.environ.get("GITLAB_API_URL", "https://gitlab.com/api/v4")
    
    if not token:
        print("❌ GITLAB_TOKEN not set")
        return False
        
    if not project:
        print("❌ GITLAB_TEST_PROJECT not set")
        return False
        
    # Test GitLab API access
    try:
        import requests
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{api_url}/projects/{project}", headers=headers)
        
        if response.status_code == 200:
            project_data = response.json()
            print(f"✅ GitLab configuration valid for {project_data['name']}")
            return True
        elif response.status_code == 404:
            print(f"❌ Project {project} not found or not accessible")
            return False
        else:
            print(f"❌ GitLab API error: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ GitLab API test failed: {e}")
        return False


def check_llm_config() -> bool:
    """Check LLM configuration."""
    provider = os.environ.get("LLM_PROVIDER", "openai")
    
    if provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            print("❌ OPENAI_API_KEY not set")
            return False
        elif not api_key.startswith("sk-"):
            print("❌ OPENAI_API_KEY does not appear to be valid")
            return False
        else:
            print("✅ OpenAI configuration appears valid")
            return True
    else:
        print(f"⚠️  LLM provider '{provider}' not tested by this script")
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
            
    if missing:
        print(f"❌ Missing dependencies: {', '.join(missing)}")
        print("Install with: pip install " + " ".join(missing))
        return False
    else:
        print("✅ All required dependencies installed")
        return True


def check_mcp_servers() -> bool:
    """Check MCP server availability."""
    # Check if GitHub MCP server exists
    github_server = Path(__file__).parent.parent.parent / "github-mcp-server"
    if github_server.exists():
        print("✅ GitHub MCP server found")
        github_ok = True
    else:
        print("⚠️  GitHub MCP server not found at expected location")
        github_ok = False
        
    # Check for Node.js and npm packages
    try:
        import subprocess
        result = subprocess.run(["npm", "list", "@zereight/mcp-gitlab"], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ GitLab MCP server (npm package) available")
            gitlab_ok = True
        else:
            print("⚠️  GitLab MCP server npm package not found")
            gitlab_ok = False
    except FileNotFoundError:
        print("⚠️  npm not found, cannot check GitLab MCP server")
        gitlab_ok = False
        
    return github_ok or gitlab_ok


def main() -> None:
    """Main configuration check."""
    print("🔍 Checking Real Integration Test Configuration\n")
    
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
        print("\n❌ No platform configured. Please set up GitHub or GitLab configuration.")
        print("\nFor GitHub:")
        print("  export GITHUB_TOKEN='your_token'")
        print("  export GITHUB_TEST_REPO='owner/repo'")
        print("\nFor GitLab:")
        print("  export GITLAB_TOKEN='your_token'")
        print("  export GITLAB_TEST_PROJECT='project_id'")
        sys.exit(1)
        
    # Run remaining checks
    all_passed = True
    for name, check_func in checks:
        try:
            if not check_func():
                all_passed = False
        except Exception as e:
            print(f"❌ {name} check failed: {e}")
            all_passed = False
            
    print("\n" + "="*50)
    if all_passed and (github_configured or gitlab_configured):
        print("🎉 Configuration is ready for real integration tests!")
        print("\nRun tests with:")
        print("  python tests/run_tests.py --real")
    else:
        print("❌ Configuration issues found. Please fix them before running tests.")
        sys.exit(1)


if __name__ == "__main__":
    main()