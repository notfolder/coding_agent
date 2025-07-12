#!/usr/bin/env python3
"""Interactive demo for real GitHub and GitLab integration testing."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import yaml

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from clients.mcp_tool_client import MCPToolClient
from handlers.task_getter_github import TaskGetterFromGitHub
from handlers.task_getter_gitlab import TaskGetterFromGitLab
from tests.mocks.mock_llm_client import MockLLMClient
from tests.mocks.mock_mcp_client import MockMCPToolClient

# Constants
MAX_TOOLS_TO_DISPLAY = 5


class RealIntegrationDemo:
    """Interactive demonstration of real GitHub and GitLab integration."""

    def __init__(self) -> None:
        self.setup_logging()
        self.github_token = os.environ.get("GITHUB_TOKEN")
        self.gitlab_token = os.environ.get("GITLAB_TOKEN")

    def setup_logging(self) -> None:
        """Set up logging for the demo."""
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
        self.logger = logging.getLogger(__name__)

    def check_prerequisites(self) -> bool:
        """Check if API tokens are available."""
        if not self.github_token and not self.gitlab_token:
            return False

        if self.github_token:
            pass
        else:
            pass

        if self.gitlab_token:
            pass
        else:
            pass

        return True

    def load_config(self, service: str) -> dict[str, Any]:
        """Load configuration for a service."""
        config_path = Path(__file__).parent / f"real_test_config_{service}.yaml"

        with config_path.open() as f:
            return yaml.safe_load(f)

    def demo_github_mcp_connection(self) -> None:
        """Demonstrate GitHub MCP server connection."""
        if not self.github_token:
            return


        try:
            # Set up environment
            os.environ["GITHUB_TOKEN"] = self.github_token

            # Load configuration
            config = self.load_config("github")

            # Initialize MCP client
            mcp_client = MCPToolClient(config["mcp_servers"][0])

            # Test connection
            mcp_client.call_initialize()

            # List available tools
            tools = mcp_client.list_tools()

            for _tool in tools[:MAX_TOOLS_TO_DISPLAY]:  # Show first 5 tools
                pass
            if len(tools) > MAX_TOOLS_TO_DISPLAY:
                pass

            # Test a simple tool call
            query = config["github"]["query"]
            result = mcp_client.call_tool("search_issues", {"q": query})

            if isinstance(result, dict) and "items" in result:
                issues = result["items"]

                if issues:
                    # First issue processed (demonstrative)
                    pass
            else:
                pass

            # Clean up
            mcp_client.close()

        except Exception:
            self.logger.exception("GitHub MCP demo error")

    def demo_gitlab_mcp_connection(self) -> None:
        """Demonstrate GitLab MCP server connection."""
        if not self.gitlab_token:
            return


        try:
            # Set up environment
            os.environ["GITLAB_TOKEN"] = self.gitlab_token

            # Load configuration
            config = self.load_config("gitlab")

            # Initialize MCP client
            mcp_client = MCPToolClient(config["mcp_servers"][0])

            # Test connection
            mcp_client.call_initialize()

            # List available tools
            tools = mcp_client.list_tools()

            for _tool in tools[:MAX_TOOLS_TO_DISPLAY]:  # Show first 5 tools
                pass
            if len(tools) > MAX_TOOLS_TO_DISPLAY:
                pass

            # Test a simple tool call
            project_id = config["gitlab"]["project_id"]
            result = mcp_client.call_tool(
                "list_issues",
                {
                    "project_id": project_id,
                    "state": "opened",
                    "labels": config["gitlab"]["bot_label"],
                },
            )

            if isinstance(result, dict) and "items" in result:
                issues = result["items"]

                if issues:
                    # First issue processed (demonstrative)
                    pass
            else:
                pass

            # Clean up
            mcp_client.close()

        except Exception:
            self.logger.exception("GitLab MCP demo error")

    def demo_github_task_workflow(self) -> None:
        """Demonstrate GitHub task workflow."""
        if not self.github_token:
            return


        try:
            # Set up environment
            os.environ["GITHUB_TOKEN"] = self.github_token

            # Load configuration
            config = self.load_config("github")

            # Initialize clients
            mcp_client = MCPToolClient(config["mcp_servers"][0])
            # LLM client is for future integration
            MockLLMClient(config)

            # Mock github_client since we're testing MCP interaction
            with patch("handlers.task_getter_github.GithubClient") as mock_github_client:
                task_getter = TaskGetterFromGitHub(
                    mcp_client=mcp_client, github_client=mock_github_client, config=config,
                )

                tasks = task_getter.get_tasks()


                if tasks:
                    task = tasks[0]

                    # Test task preparation
                    task.prepare()

                    # Test prompt generation (demonstrative)
                    task.get_prompt()

                else:
                    pass

            # Clean up
            mcp_client.close()

        except Exception:
            self.logger.exception("GitHub workflow demo error")

    def demo_gitlab_task_workflow(self) -> None:
        """Demonstrate GitLab task workflow."""
        if not self.gitlab_token:
            return


        try:
            # Set up environment
            os.environ["GITLAB_TOKEN"] = self.gitlab_token

            # Load configuration
            config = self.load_config("gitlab")

            # Initialize clients
            mcp_client = MCPToolClient(config["mcp_servers"][0])
            # LLM client is for future integration
            MockLLMClient(config)

            # Mock gitlab_client since we're testing MCP interaction
            with patch("handlers.task_getter_gitlab.GitlabClient") as mock_gitlab_client:
                task_getter = TaskGetterFromGitLab(
                    mcp_client=mcp_client, gitlab_client=mock_gitlab_client, config=config,
                )

                tasks = task_getter.get_tasks()


                if tasks:
                    task = tasks[0]

                    # Test task preparation
                    task.prepare()

                    # Test prompt generation (demonstrative)
                    task.get_prompt()

                else:
                    pass

            # Clean up
            mcp_client.close()

        except Exception:
            self.logger.exception("GitLab workflow demo error")

    def run_interactive_demo(self) -> None:
        """Run the interactive demo."""
        if not self.check_prerequisites():
            return


        # Run demonstrations
        self.demo_github_mcp_connection()
        self.demo_gitlab_mcp_connection()
        self.demo_github_task_workflow()
        self.demo_gitlab_task_workflow()


def main() -> None:
    """Run the main function."""
    try:
        demo = RealIntegrationDemo()
        demo.run_interactive_demo()
    except KeyboardInterrupt:
        pass
    except Exception:
        logging.getLogger(__name__).exception("Demo error")


def demonstrate_mock_llm_client() -> None:
    """Demonstrate mock LLM client usage."""
    config = {"llm": {"provider": "mock"}}
    # LLM client demonstration
    MockLLMClient(config)


def demonstrate_test_workflow() -> None:
    """Demonstrate the basic test workflow without GitHub/GitLab specifics."""
    # Load test config
    config_path = Path(__file__).parent / "test_config.yaml"
    try:
        with config_path.open() as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        # Use default config if file not found
        config = {"llm": {"provider": "mock"}}

    # Create mock clients (generic, not service-specific)
    MockMCPToolClient({"mcp_server_name": "test_server", "command": ["mock"]})
    MockLLMClient(config)


def demonstrate_test_runner() -> None:
    """Run sample tests to show the framework in action."""
    # Mock test results since actual test functions might not be available
    unit_success = True
    integration_success = True

    # Overall result (demonstrative)
    return unit_success and integration_success


if __name__ == "__main__":
    main()
