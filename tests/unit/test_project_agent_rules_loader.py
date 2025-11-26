"""Unit tests for ProjectAgentRulesLoader."""

from __future__ import annotations

import base64
import unittest
from unittest.mock import MagicMock

from mcp import ErrorData, McpError

from handlers.project_agent_rules_loader import ProjectAgentRulesLoader


class TestProjectAgentRulesLoaderMCP(unittest.TestCase):
    """Test ProjectAgentRulesLoader with MCP."""

    def setUp(self) -> None:
        """Set up test environment."""
        self.config = {
            "project_agent_rules": {
                "enabled": True,
            },
        }
        self.mock_mcp_client = MagicMock()

    def test_mcp_mode_initialization(self) -> None:
        """Test MCP mode initialization."""
        loader = ProjectAgentRulesLoader(
            config=self.config,
            mcp_client=self.mock_mcp_client,
            owner="testowner",
            repo="testrepo",
        )
        assert loader.mcp_client is not None
        assert loader.owner == "testowner"
        assert loader.repo == "testrepo"

    def test_gitlab_mode_initialization(self) -> None:
        """Test GitLab mode initialization."""
        loader = ProjectAgentRulesLoader(
            config=self.config,
            mcp_client=self.mock_mcp_client,
            project_id="123",
        )
        assert loader.mcp_client is not None
        assert loader.project_id == "123"

    def test_load_rules_via_mcp_agents_md(self) -> None:
        """Test loading AGENTS.md via MCP."""
        self.mock_mcp_client.call_tool.return_value = {
            "text": "# Agent Rules\nFollow these.",
        }

        loader = ProjectAgentRulesLoader(
            config=self.config,
            mcp_client=self.mock_mcp_client,
            owner="testowner",
            repo="testrepo",
        )
        rules = loader.load_rules()

        assert "Project-Specific Agent Rules" in rules
        assert "# Agent Rules" in rules
        self.mock_mcp_client.call_tool.assert_called()

    def test_parse_mcp_result_text_field(self) -> None:
        """Test parsing MCP result with text field."""
        loader = ProjectAgentRulesLoader(
            config=self.config,
            mcp_client=self.mock_mcp_client,
            owner="testowner",
            repo="testrepo",
        )
        result = loader._parse_mcp_file_result({"text": "# Content"})  # noqa: SLF001
        assert result == "# Content"

    def test_parse_mcp_result_content_field(self) -> None:
        """Test parsing MCP result with base64 content field."""
        loader = ProjectAgentRulesLoader(
            config=self.config,
            mcp_client=self.mock_mcp_client,
            owner="testowner",
            repo="testrepo",
        )
        encoded = base64.b64encode(b"# Content").decode()
        result = loader._parse_mcp_file_result({"content": encoded})  # noqa: SLF001
        assert result == "# Content"

    def test_parse_mcp_result_string(self) -> None:
        """Test parsing MCP result as string."""
        loader = ProjectAgentRulesLoader(
            config=self.config,
            mcp_client=self.mock_mcp_client,
            owner="testowner",
            repo="testrepo",
        )
        result = loader._parse_mcp_file_result("# Content")  # noqa: SLF001
        assert result == "# Content"


if __name__ == "__main__":
    unittest.main()
