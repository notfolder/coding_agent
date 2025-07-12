#!/usr/bin/env python3
"""Interactive demo for real GitHub and GitLab integration testing."""

import logging
import os
import sys

import yaml

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

from clients.mcp_tool_client import MCPToolClient
from handlers.task_getter_github import TaskGetterFromGitHub
from handlers.task_getter_gitlab import TaskGetterFromGitLab
from tests.mocks.mock_llm_client import MockLLMClient


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

    def load_config(self, service):
        """Load configuration for a service."""
        config_path = os.path.join(os.path.dirname(__file__), f"real_test_config_{service}.yaml")

        with open(config_path) as f:
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

            for _tool in tools[:5]:  # Show first 5 tools
                pass
            if len(tools) > 5:
                pass

            # Test a simple tool call
            query = config["github"]["query"]
            result = mcp_client.call_tool("search_issues", {"q": query})

            if isinstance(result, dict) and "items" in result:
                issues = result["items"]

                if issues:
                    issue = issues[0]
            else:
                pass

            # Clean up
            mcp_client.close()

        except Exception as e:
            self.logger.error(f"GitHub MCP demo error: {e}", exc_info=True)

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

            for _tool in tools[:5]:  # Show first 5 tools
                pass
            if len(tools) > 5:
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
                    issue = issues[0]
            else:
                pass

            # Clean up
            mcp_client.close()

        except Exception as e:
            self.logger.error(f"GitLab MCP demo error: {e}", exc_info=True)

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
            llm_client = MockLLMClient(config)

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

                    # Test prompt generation
                    prompt = task.get_prompt()

                else:
                    pass

            # Clean up
            mcp_client.close()

        except Exception as e:
            self.logger.error(f"GitHub workflow demo error: {e}", exc_info=True)

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
            llm_client = MockLLMClient(config)

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

                    # Test prompt generation
                    prompt = task.get_prompt()

                else:
                    pass

            # Clean up
            mcp_client.close()

        except Exception as e:
            self.logger.error(f"GitLab workflow demo error: {e}", exc_info=True)

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
    """Main function."""
    try:
        demo = RealIntegrationDemo()
        demo.run_interactive_demo()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logging.exception("Demo error")


if __name__ == "__main__":
    main()

    # Test system prompt
    prompt = test_client.system_prompt


def demonstrate_mock_llm_client() -> None:
    """Demonstrate mock LLM client usage."""
    config = {"llm": {"provider": "mock"}}
    llm_client = MockLLMClient(config)

    # Send system prompt
    llm_client.send_system_prompt("You are a helpful coding assistant.")

    # Send user message
    llm_client.send_user_message("Please help me with a test task")

    # Get responses
    response1, _ = llm_client.get_response()

    response2, _ = llm_client.get_response()

    # Show interaction history


def demonstrate_test_workflow() -> None:
    """Demonstrate the basic test workflow without GitHub/GitLab specifics."""
    # Load test config
    config_path = os.path.join(os.path.dirname(__file__), "test_config.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Note: GitHub/GitLab specific config removed per user request

    # Create mock clients (generic, not service-specific)
    test_client = MockMCPToolClient({"mcp_server_name": "test_server", "command": ["mock"]})
    llm_client = MockLLMClient(config)



def run_sample_tests() -> None:
    """Run sample tests to show the framework in action."""
    # Run unit tests
    unit_success = run_unit_tests()

    # Run integration tests
    integration_success = run_integration_tests()

    # Overall result
    overall_success = unit_success and integration_success


def main() -> None:
    """Main demo function."""
    try:
        demonstrate_mock_mcp_client()
        demonstrate_mock_llm_client()
        demonstrate_test_workflow()
        run_sample_tests()


    except Exception as e:
        sys.exit(1)


if __name__ == "__main__":
    main()
