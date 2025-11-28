"""Unit tests for FileListContextLoader."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from handlers.file_list_context_loader import FileListContextLoader


class TestFileListContextLoader(unittest.TestCase):
    """Test FileListContextLoader class."""

    def setUp(self) -> None:
        """Set up test environment."""
        self.config = {
            "file_list_context": {
                "enabled": True,
                "max_depth": -1,
            },
        }
        self.mock_mcp_client = MagicMock()

    def test_initialization(self) -> None:
        """Test FileListContextLoader initialization."""
        loader = FileListContextLoader(
            config=self.config,
            mcp_clients={"github": self.mock_mcp_client},
        )
        assert loader.enabled is True
        assert loader.max_depth == -1

    def test_initialization_with_defaults(self) -> None:
        """Test initialization with default values."""
        loader = FileListContextLoader(
            config={},
            mcp_clients={"github": self.mock_mcp_client},
        )
        assert loader.enabled is True
        assert loader.max_depth == -1

    def test_initialization_disabled(self) -> None:
        """Test initialization with disabled flag."""
        config = {
            "file_list_context": {
                "enabled": False,
            },
        }
        loader = FileListContextLoader(
            config=config,
            mcp_clients={"github": self.mock_mcp_client},
        )
        assert loader.enabled is False

    def test_load_file_list_disabled(self) -> None:
        """Test load_file_list returns empty when disabled."""
        config = {
            "file_list_context": {
                "enabled": False,
            },
        }
        loader = FileListContextLoader(
            config=config,
            mcp_clients={"github": self.mock_mcp_client},
        )
        mock_task = MagicMock()

        result = loader.load_file_list(mock_task)

        assert result == ""

    def test_apply_depth_limit_no_limit(self) -> None:
        """Test _apply_depth_limit with no limit."""
        loader = FileListContextLoader(
            config=self.config,
            mcp_clients={"github": self.mock_mcp_client},
        )

        file_list = [
            "file1.py",
            "dir1/file2.py",
            "dir1/dir2/file3.py",
            "dir1/dir2/dir3/file4.py",
        ]

        result = loader._apply_depth_limit(file_list, -1)

        assert len(result) == 4

    def test_apply_depth_limit_with_limit(self) -> None:
        """Test _apply_depth_limit with depth limit."""
        loader = FileListContextLoader(
            config=self.config,
            mcp_clients={"github": self.mock_mcp_client},
        )

        file_list = [
            "file1.py",
            "dir1/file2.py",
            "dir1/dir2/file3.py",
            "dir1/dir2/dir3/file4.py",
        ]

        # max_depth=1 should only include files with depth 0 and 1
        result = loader._apply_depth_limit(file_list, 1)

        assert len(result) == 2
        assert "file1.py" in result
        assert "dir1/file2.py" in result

    def test_apply_depth_limit_zero(self) -> None:
        """Test _apply_depth_limit with depth 0."""
        loader = FileListContextLoader(
            config=self.config,
            mcp_clients={"github": self.mock_mcp_client},
        )

        file_list = [
            "file1.py",
            "dir1/file2.py",
            "dir1/dir2/file3.py",
        ]

        result = loader._apply_depth_limit(file_list, 0)

        assert len(result) == 1
        assert "file1.py" in result

    def test_format_file_list_empty(self) -> None:
        """Test _format_file_list with empty list."""
        loader = FileListContextLoader(
            config=self.config,
            mcp_clients={"github": self.mock_mcp_client},
        )

        result = loader._format_file_list([], "owner", "repo")

        assert result == ""

    def test_format_file_list_with_files(self) -> None:
        """Test _format_file_list with files."""
        loader = FileListContextLoader(
            config=self.config,
            mcp_clients={"github": self.mock_mcp_client},
        )

        file_list = ["b.py", "a.py", "c.py"]
        result = loader._format_file_list(file_list, "owner", "repo")

        assert "## Project File List" in result
        assert "Repository: owner/repo" in result
        assert "Total: 3 files" in result
        # Check alphabetical order
        assert result.index("a.py") < result.index("b.py") < result.index("c.py")

    def test_format_file_list_without_owner(self) -> None:
        """Test _format_file_list without owner."""
        loader = FileListContextLoader(
            config=self.config,
            mcp_clients={"github": self.mock_mcp_client},
        )

        file_list = ["file.py"]
        result = loader._format_file_list(file_list, "", "project123")

        assert "Repository: project123" in result

    def test_fetch_file_list_from_github(self) -> None:
        """Test _fetch_file_list_from_github."""
        self.mock_mcp_client.call_tool.return_value = [
            {"type": "file", "path": "file1.py"},
            {"type": "file", "path": "file2.py"},
        ]

        loader = FileListContextLoader(
            config=self.config,
            mcp_clients={"github": self.mock_mcp_client},
        )

        result = loader._fetch_file_list_from_github("owner", "repo")

        assert len(result) == 2
        assert "file1.py" in result
        assert "file2.py" in result

    def test_fetch_file_list_from_github_with_directories(self) -> None:
        """Test _fetch_file_list_from_github processes directories recursively."""
        # First call returns file and directory, second call (for subdir) returns file
        self.mock_mcp_client.call_tool.side_effect = [
            [
                {"type": "file", "path": "file1.py"},
                {"type": "dir", "path": "subdir"},
            ],
            [
                {"type": "file", "path": "subdir/file2.py"},
            ],
        ]

        loader = FileListContextLoader(
            config=self.config,
            mcp_clients={"github": self.mock_mcp_client},
        )

        result = loader._fetch_file_list_from_github("owner", "repo")

        assert "file1.py" in result
        assert "subdir/file2.py" in result

    def test_fetch_file_list_from_gitlab(self) -> None:
        """Test _fetch_file_list_from_gitlab."""
        self.mock_mcp_client.call_tool.return_value = [
            {"type": "blob", "path": "file1.py"},
            {"type": "blob", "path": "file2.py"},
            {"type": "tree", "path": "dir1"},
        ]

        loader = FileListContextLoader(
            config=self.config,
            mcp_clients={"gitlab": self.mock_mcp_client},
        )

        result = loader._fetch_file_list_from_gitlab("123")

        assert len(result) == 2
        assert "file1.py" in result
        assert "file2.py" in result
        assert "dir1" not in result

    def test_load_file_list_github(self) -> None:
        """Test load_file_list for GitHub."""
        self.mock_mcp_client.call_tool.return_value = [
            {"type": "file", "path": "file1.py"},
        ]

        loader = FileListContextLoader(
            config=self.config,
            mcp_clients={"github": self.mock_mcp_client},
        )

        mock_task = MagicMock()
        mock_task_key = MagicMock()
        mock_task_key.owner = "testowner"
        mock_task_key.repo = "testrepo"
        mock_task_key.project_id = None
        mock_task.get_task_key.return_value = mock_task_key

        result = loader.load_file_list(mock_task)

        assert "## Project File List" in result
        assert "testowner/testrepo" in result

    def test_load_file_list_gitlab(self) -> None:
        """Test load_file_list for GitLab."""
        self.mock_mcp_client.call_tool.return_value = [
            {"type": "blob", "path": "file1.py"},
        ]

        loader = FileListContextLoader(
            config=self.config,
            mcp_clients={"gitlab": self.mock_mcp_client},
        )

        mock_task = MagicMock()
        mock_task_key = MagicMock()
        mock_task_key.owner = None
        mock_task_key.repo = None
        mock_task_key.project_id = "123"
        mock_task.get_task_key.return_value = mock_task_key

        result = loader.load_file_list(mock_task)

        assert "## Project File List" in result
        assert "123" in result

    def test_load_file_list_no_platform_info(self) -> None:
        """Test load_file_list with no platform info."""
        loader = FileListContextLoader(
            config=self.config,
            mcp_clients={"github": self.mock_mcp_client},
        )

        mock_task = MagicMock()
        mock_task_key = MagicMock()
        mock_task_key.owner = None
        mock_task_key.repo = None
        mock_task_key.project_id = None
        mock_task.get_task_key.return_value = mock_task_key

        result = loader.load_file_list(mock_task)

        assert result == ""


if __name__ == "__main__":
    unittest.main()
