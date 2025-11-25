"""Unit tests for ProjectAgentRulesLoader."""

from __future__ import annotations

import base64
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from handlers.project_agent_rules_loader import ProjectAgentRulesLoader


class TestProjectAgentRulesLoaderLocal(unittest.TestCase):
    """Test ProjectAgentRulesLoader with local files."""

    def setUp(self) -> None:
        """Set up test environment."""
        # Create a temporary directory for testing
        self.test_dir = tempfile.mkdtemp()
        self.config = {
            "project_agent_rules": {
                "enabled": True,
                "search": {
                    "root_files": True,
                    "agent_files": True,
                    "prompt_files": True,
                    "case_insensitive": True,
                },
                "limits": {
                    "max_file_size": 102400,
                    "max_total_size": 512000,
                    "max_agent_files": 10,
                    "max_prompt_files": 50,
                    "max_depth": 10,
                },
            },
        }

    def tearDown(self) -> None:
        """Clean up test environment."""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_loader_creation(self) -> None:
        """Test ProjectAgentRulesLoader creation."""
        loader = ProjectAgentRulesLoader(self.test_dir, self.config)
        assert loader.project_root == Path(self.test_dir)
        assert loader.max_file_size == 102400
        assert loader.max_agent_files == 10

    def test_loader_with_default_config(self) -> None:
        """Test ProjectAgentRulesLoader with default config."""
        loader = ProjectAgentRulesLoader(self.test_dir)
        assert loader.max_file_size == 102400
        assert loader.max_total_size == 512000
        assert loader.max_agent_files == 10
        assert loader.max_prompt_files == 50
        assert loader.max_depth == 10

    def test_find_agent_md(self) -> None:
        """Test finding AGENT.md file."""
        # Create AGENT.md
        agent_md = Path(self.test_dir) / "AGENT.md"
        agent_md.write_text("# Agent Rules\nFollow these rules.", encoding="utf-8")

        loader = ProjectAgentRulesLoader(self.test_dir, self.config)
        files = loader.find_rule_files()

        assert len(files) == 1
        assert files[0]["path"] == agent_md
        assert files[0]["type"] == "root"

    def test_find_claude_md(self) -> None:
        """Test finding CLAUDE.md file."""
        # Create CLAUDE.md
        claude_md = Path(self.test_dir) / "CLAUDE.md"
        claude_md.write_text("# Claude Rules\nSpecific for Claude.", encoding="utf-8")

        loader = ProjectAgentRulesLoader(self.test_dir, self.config)
        files = loader.find_rule_files()

        assert len(files) == 1
        assert files[0]["path"] == claude_md
        assert files[0]["type"] == "root"

    def test_find_both_root_files(self) -> None:
        """Test finding both AGENT.md and CLAUDE.md."""
        # Create both files
        agent_md = Path(self.test_dir) / "AGENT.md"
        agent_md.write_text("# Agent Rules", encoding="utf-8")
        claude_md = Path(self.test_dir) / "CLAUDE.md"
        claude_md.write_text("# Claude Rules", encoding="utf-8")

        loader = ProjectAgentRulesLoader(self.test_dir, self.config)
        files = loader.find_rule_files()

        assert len(files) == 2
        # AGENT.md should come first (priority order)
        assert files[0]["path"].name.lower() == "agent.md"
        assert files[1]["path"].name.lower() == "claude.md"

    def test_case_insensitive_search(self) -> None:
        """Test case-insensitive file search."""
        # Create agent.md (lowercase)
        agent_md = Path(self.test_dir) / "agent.md"
        agent_md.write_text("# Agent Rules", encoding="utf-8")

        loader = ProjectAgentRulesLoader(self.test_dir, self.config)
        files = loader.find_rule_files()

        assert len(files) == 1
        assert files[0]["path"] == agent_md

    def test_find_agent_files(self) -> None:
        """Test finding .github/agents/*.agent.md files."""
        # Create .github/agents directory
        agents_dir = Path(self.test_dir) / ".github" / "agents"
        agents_dir.mkdir(parents=True)

        # Create agent files
        (agents_dir / "code-review.agent.md").write_text("# Code Review", encoding="utf-8")
        (agents_dir / "docs.agent.md").write_text("# Docs", encoding="utf-8")

        loader = ProjectAgentRulesLoader(self.test_dir, self.config)
        files = loader.find_rule_files()

        assert len(files) == 2
        assert all(f["type"] == "agent" for f in files)

    def test_find_prompt_files(self) -> None:
        """Test finding **/*.prompt.md files."""
        # Create prompt files
        src_dir = Path(self.test_dir) / "src"
        src_dir.mkdir()
        (Path(self.test_dir) / "api.prompt.md").write_text("# API Prompt", encoding="utf-8")
        (src_dir / "frontend.prompt.md").write_text("# Frontend Prompt", encoding="utf-8")

        loader = ProjectAgentRulesLoader(self.test_dir, self.config)
        files = loader.find_rule_files()

        assert len(files) == 2
        assert all(f["type"] == "prompt" for f in files)

    def test_validate_file_valid_markdown(self) -> None:
        """Test validation of valid markdown file."""
        md_file = Path(self.test_dir) / "test.md"
        md_file.write_text("# Test\nThis is a test.", encoding="utf-8")

        loader = ProjectAgentRulesLoader(self.test_dir, self.config)
        assert loader.validate_file(md_file) is True

    def test_validate_file_empty(self) -> None:
        """Test validation of empty file."""
        md_file = Path(self.test_dir) / "empty.md"
        md_file.write_text("", encoding="utf-8")

        loader = ProjectAgentRulesLoader(self.test_dir, self.config)
        assert loader.validate_file(md_file) is False

    def test_validate_file_too_large(self) -> None:
        """Test validation of file exceeding size limit."""
        md_file = Path(self.test_dir) / "large.md"
        # Create a file larger than max_file_size
        md_file.write_text("x" * 150000, encoding="utf-8")  # 150KB

        loader = ProjectAgentRulesLoader(self.test_dir, self.config)
        assert loader.validate_file(md_file) is False

    def test_validate_file_binary(self) -> None:
        """Test validation of binary file."""
        bin_file = Path(self.test_dir) / "binary.md"
        bin_file.write_bytes(b"\x00\x01\x02\x03")

        loader = ProjectAgentRulesLoader(self.test_dir, self.config)
        assert loader.validate_file(bin_file) is False

    def test_validate_file_wrong_extension(self) -> None:
        """Test validation of file with wrong extension."""
        txt_file = Path(self.test_dir) / "test.txt"
        txt_file.write_text("# Test", encoding="utf-8")

        loader = ProjectAgentRulesLoader(self.test_dir, self.config)
        assert loader.validate_file(txt_file) is False

    def test_load_rules_single_file(self) -> None:
        """Test loading rules from a single file."""
        agent_md = Path(self.test_dir) / "AGENT.md"
        agent_md.write_text("# Project Rules\nFollow these.", encoding="utf-8")

        loader = ProjectAgentRulesLoader(self.test_dir, self.config)
        rules = loader.load_rules()

        assert "Project-Specific Agent Rules" in rules
        assert "From: AGENT.md" in rules
        assert "# Project Rules" in rules

    def test_load_rules_multiple_files(self) -> None:
        """Test loading rules from multiple files."""
        agent_md = Path(self.test_dir) / "AGENT.md"
        agent_md.write_text("# Agent Rules", encoding="utf-8")
        claude_md = Path(self.test_dir) / "CLAUDE.md"
        claude_md.write_text("# Claude Rules", encoding="utf-8")

        loader = ProjectAgentRulesLoader(self.test_dir, self.config)
        rules = loader.load_rules()

        assert "From: AGENT.md" in rules
        assert "From: CLAUDE.md" in rules

    def test_load_rules_disabled(self) -> None:
        """Test loading rules when feature is disabled."""
        agent_md = Path(self.test_dir) / "AGENT.md"
        agent_md.write_text("# Agent Rules", encoding="utf-8")

        config = {
            "project_agent_rules": {
                "enabled": False,
            },
        }
        loader = ProjectAgentRulesLoader(self.test_dir, config)
        rules = loader.load_rules()

        assert rules == ""

    def test_load_rules_no_files(self) -> None:
        """Test loading rules when no files exist."""
        loader = ProjectAgentRulesLoader(self.test_dir, self.config)
        rules = loader.load_rules()

        assert rules == ""

    def test_load_rules_nonexistent_directory(self) -> None:
        """Test loading rules from non-existent directory."""
        loader = ProjectAgentRulesLoader("/nonexistent/path", self.config)
        rules = loader.load_rules()

        assert rules == ""

    def test_format_rules(self) -> None:
        """Test rules formatting."""
        loader = ProjectAgentRulesLoader(self.test_dir, self.config)
        files_content = [
            ("AGENT.md", "# Agent\nRule 1"),
            ("CLAUDE.md", "# Claude\nRule 2"),
        ]
        formatted = loader._format_rules(files_content)  # noqa: SLF001

        assert "---" in formatted
        assert "## Project-Specific Agent Rules" in formatted
        assert "### From: AGENT.md" in formatted
        assert "### From: CLAUDE.md" in formatted
        assert "# Agent\nRule 1" in formatted
        assert "# Claude\nRule 2" in formatted

    def test_max_depth_limit(self) -> None:
        """Test max depth limit for prompt file search."""
        # Create nested directories beyond max_depth
        deep_dir = Path(self.test_dir)
        for i in range(15):
            deep_dir = deep_dir / f"level{i}"
        deep_dir.mkdir(parents=True)
        (deep_dir / "deep.prompt.md").write_text("# Deep", encoding="utf-8")

        loader = ProjectAgentRulesLoader(self.test_dir, self.config)
        files = loader.find_rule_files()

        # File should not be found due to depth limit
        assert len(files) == 0

    def test_search_config_disabled(self) -> None:
        """Test with specific search types disabled."""
        # Create various files
        agent_md = Path(self.test_dir) / "AGENT.md"
        agent_md.write_text("# Agent", encoding="utf-8")

        config = {
            "project_agent_rules": {
                "enabled": True,
                "search": {
                    "root_files": False,  # Disable root file search
                    "agent_files": True,
                    "prompt_files": True,
                },
            },
        }
        loader = ProjectAgentRulesLoader(self.test_dir, config)
        files = loader.find_rule_files()

        # AGENT.md should not be found
        assert len(files) == 0


class TestProjectAgentRulesLoaderMCP(unittest.TestCase):
    """Test ProjectAgentRulesLoader with MCP client."""

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
        assert loader.use_mcp is True
        assert loader.mcp_client is not None

    def test_mcp_mode_without_owner(self) -> None:
        """Test MCP mode without owner."""
        loader = ProjectAgentRulesLoader(
            config=self.config,
            mcp_client=self.mock_mcp_client,
            owner=None,
            repo="testrepo",
        )
        assert loader.use_mcp is False

    def test_load_rules_via_mcp_agent_md(self) -> None:
        """Test loading AGENT.md via MCP."""
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

    def test_load_rules_via_mcp_file_not_found(self) -> None:
        """Test loading via MCP when file not found."""
        self.mock_mcp_client.call_tool.side_effect = OSError("File not found")

        loader = ProjectAgentRulesLoader(
            config=self.config,
            mcp_client=self.mock_mcp_client,
            owner="testowner",
            repo="testrepo",
        )
        rules = loader.load_rules()

        # Should return empty string when no files found
        assert rules == ""

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
        result = loader._parse_mcp_file_result("# Content")
        assert result == "# Content"


if __name__ == "__main__":
    unittest.main()
