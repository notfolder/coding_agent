"""Comprehensive mock MCP client for testing GitHub and GitLab functionality."""

from __future__ import annotations

from typing import Any


class MockTool:
    """Mock tool representation."""

    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description


class MockMCPToolClient:
    """Comprehensive mock implementation of MCPToolClient with GitHub and GitLab support."""

    def __init__(
        self,
        server_config: dict[str, Any],
        *,
        function_calling: bool = True,
    ) -> None:
        self.server_config = server_config
        self.function_calling = function_calling
        self.server_name = server_config.get("mcp_server_name", "unknown")
        self._system_prompt = None

        # Initialize mock data based on server type
        self._setup_mock_data()

    def _setup_mock_data(self) -> None:
        """Set up mock data structures for different server types."""
        if "github" in self.server_name.lower():
            self._setup_github_mock_data()
        elif "gitlab" in self.server_name.lower():
            self._setup_gitlab_mock_data()
        else:
            self.mock_data = {}

    def _setup_github_mock_data(self) -> None:
        """Set up comprehensive GitHub mock data."""
        self.mock_data = {
            "issues": [
                {
                    "number": 1,
                    "title": "Test GitHub Issue 1",
                    "body": "This is a test GitHub issue for automation testing",
                    "state": "open",
                    "repository_url": "https://api.github.com/repos/testorg/testrepo",
                    "labels": [
                        {"name": "coding agent", "color": "blue"},
                        {"name": "bug", "color": "red"},
                    ],
                    "assignees": [],
                    "user": {"login": "testuser"},
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-01-01T12:00:00Z",
                },
                {
                    "number": 2,
                    "title": "Test GitHub Issue 2",
                    "body": "Another test issue with different labels",
                    "state": "open",
                    "repository_url": "https://api.github.com/repos/testorg/testrepo",
                    "labels": [
                        {"name": "coding agent", "color": "blue"},
                        {"name": "enhancement", "color": "green"},
                    ],
                    "assignees": [],
                    "user": {"login": "testuser2"},
                    "created_at": "2024-01-02T00:00:00Z",
                    "updated_at": "2024-01-02T12:00:00Z",
                },
            ],
            "comments": [
                {
                    "id": 1,
                    "body": "First comment on issue 1",
                    "user": {"login": "commenter1"},
                    "created_at": "2024-01-01T01:00:00Z",
                },
                {
                    "id": 2,
                    "body": "Second comment on issue 1",
                    "user": {"login": "commenter2"},
                    "created_at": "2024-01-01T02:00:00Z",
                },
            ],
            "updated_issues": {},  # Track issues that have been updated
        }

    def _setup_gitlab_mock_data(self) -> None:
        """Set up comprehensive GitLab mock data."""
        self.mock_data = {
            "issues": [
                {
                    "iid": 1,
                    "title": "Test GitLab Issue 1",
                    "description": "This is a test GitLab issue for automation testing",
                    "state": "opened",
                    "project_id": 123,
                    "labels": ["coding agent", "bug"],
                    "assignee": {"username": "testuser"},
                    "author": {"username": "testuser"},
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-01-01T12:00:00Z",
                },
                {
                    "iid": 2,
                    "title": "Test GitLab Issue 2",
                    "description": "Another test issue with different labels",
                    "state": "opened",
                    "project_id": 123,
                    "labels": ["coding agent", "enhancement"],
                    "assignee": {"username": "testuser"},
                    "author": {"username": "testuser2"},
                    "created_at": "2024-01-02T00:00:00Z",
                    "updated_at": "2024-01-02T12:00:00Z",
                },
            ],
            "discussions": [
                {
                    "id": "disc1",
                    "notes": [
                        {
                            "id": 1,
                            "body": "First note in discussion",
                            "author": {"username": "commenter1"},
                            "created_at": "2024-01-01T01:00:00Z",
                        },
                        {
                            "id": 2,
                            "body": "Second note in discussion",
                            "author": {"username": "commenter2"},
                            "created_at": "2024-01-01T02:00:00Z",
                        },
                    ],
                },
            ],
            "updated_issues": {},  # Track issues that have been updated
        }

    def call_tool(self, tool: str, args: dict[str, Any]) -> dict[str, Any] | list[dict] | None:
        """Mock tool call implementation with comprehensive GitHub/GitLab support."""
        if "github" in self.server_name.lower():
            return self._handle_github_tool(tool, args)
        if "gitlab" in self.server_name.lower():
            return self._handle_gitlab_tool(tool, args)
        return {}

    def _handle_github_tool(
        self,
        tool: str,
        args: dict[str, Any],
    ) -> dict[str, Any] | list[dict] | None:
        """Handle GitHub-specific tool calls."""
        github_handlers = {
            "search_issues": self._handle_github_search_issues,
            "get_issue": self._handle_github_get_issue,
            "get_issue_comments": self._handle_github_get_issue_comments,
            "update_issue": self._handle_github_update_issue,
            "create_issue_comment": self._handle_github_create_issue_comment,
        }
        handler = github_handlers.get(tool)
        return handler(args) if handler else {}

    def _handle_github_search_issues(self, args: dict[str, Any]) -> dict[str, Any]:
        """Handle GitHub issue search."""
        query = args.get("q", "")
        matching_issues = []
        for issue in self.mock_data["issues"]:
            if "label:" in query:
                label_search = query.split("label:")[1].strip().strip('"')
                if any(label["name"] == label_search for label in issue["labels"]):
                    matching_issues.append(issue)
            else:
                matching_issues.append(issue)
        return {"items": matching_issues, "total_count": len(matching_issues)}

    def _handle_github_get_issue(self, args: dict[str, Any]) -> dict[str, Any] | None:
        """Handle GitHub get issue."""
        issue_number = args.get("issue_number")
        for issue in self.mock_data["issues"]:
            if issue["number"] == issue_number:
                return issue
        return None

    def _handle_github_get_issue_comments(self, args: dict[str, Any]) -> list[dict]:
        """Handle GitHub get issue comments."""
        issue_number = args.get("issue_number")
        if issue_number in [1, 2]:  # Mock comments for specific issues
            return self.mock_data["comments"]
        return []

    def _handle_github_update_issue(self, args: dict[str, Any]) -> dict[str, Any] | None:
        """Handle GitHub update issue."""
        issue_number = args.get("issue_number")
        labels = args.get("labels", [])
        for issue in self.mock_data["issues"]:
            if issue["number"] == issue_number:
                issue["labels"] = [{"name": label, "color": "blue"} for label in labels]
                self.mock_data["updated_issues"][issue_number] = {
                    "labels": labels,
                    "updated_at": "2024-01-01T13:00:00Z",
                }
                return issue
        return None

    def _handle_github_create_issue_comment(self, args: dict[str, Any]) -> dict[str, Any]:
        """Handle GitHub create issue comment."""
        comment_id = len(self.mock_data["comments"]) + 1
        new_comment = {
            "id": comment_id,
            "body": args.get("body", ""),
            "user": {"login": "bot"},
            "created_at": "2024-01-01T13:00:00Z",
        }
        self.mock_data["comments"].append(new_comment)
        return new_comment

    def _handle_gitlab_tool(
        self,
        tool: str,
        args: dict[str, Any],
    ) -> dict[str, Any] | list[dict] | None:
        """Handle GitLab-specific tool calls."""
        gitlab_handlers = {
            "list_issues": self._handle_gitlab_list_issues,
            "get_issue": self._handle_gitlab_get_issue,
            "list_issue_discussions": self._handle_gitlab_list_issue_discussions,
            "update_issue": self._handle_gitlab_update_issue,
            "create_issue_note": self._handle_gitlab_create_issue_note,
        }
        handler = gitlab_handlers.get(tool)
        return handler(args) if handler else {}

    def _handle_gitlab_list_issues(self, args: dict[str, Any]) -> dict[str, Any]:
        """Handle GitLab list issues."""
        project_id = args.get("project_id")
        state = args.get("state", "opened")
        labels = args.get("labels", "")

        matching_issues = [
            issue
            for issue in self.mock_data["issues"]
            if (
                issue["project_id"] == int(project_id)
                and issue["state"] == state
                and (not labels or labels in issue["labels"])
            )
        ]
        return {"items": matching_issues, "total_count": len(matching_issues)}

    def _handle_gitlab_get_issue(self, args: dict[str, Any]) -> dict[str, Any] | None:
        """Handle GitLab get issue."""
        project_id = args.get("project_id")
        issue_iid = args.get("issue_iid")
        for issue in self.mock_data["issues"]:
            if issue["project_id"] == int(project_id) and issue["iid"] == issue_iid:
                return issue
        return None

    def _handle_gitlab_list_issue_discussions(self, args: dict[str, Any]) -> dict[str, Any]:
        """Handle GitLab list issue discussions."""
        project_id = args.get("project_id")
        issue_iid = args.get("issue_iid")
        mock_project_id = 123
        if int(project_id) == mock_project_id and issue_iid in [1, 2]:
            return {"items": self.mock_data["discussions"]}
        return {"items": []}

    def _handle_gitlab_update_issue(self, args: dict[str, Any]) -> dict[str, Any] | None:
        """Handle GitLab update issue."""
        project_id = args.get("project_id")
        issue_iid = args.get("issue_iid")
        labels = args.get("labels", [])
        for issue in self.mock_data["issues"]:
            if issue["project_id"] == int(project_id) and issue["iid"] == issue_iid:
                issue["labels"] = labels
                self.mock_data["updated_issues"][issue_iid] = {
                    "labels": labels,
                    "updated_at": "2024-01-01T13:00:00Z",
                }
                return issue
        return None

    def _handle_gitlab_create_issue_note(self, args: dict[str, Any]) -> dict[str, Any]:
        """Handle GitLab create issue note."""
        note_id = len(self.mock_data["discussions"][0]["notes"]) + 1
        new_note = {
            "id": note_id,
            "body": args.get("body", ""),
            "author": {"username": "bot"},
            "created_at": "2024-01-01T13:00:00Z",
        }
        self.mock_data["discussions"][0]["notes"].append(new_note)
        return new_note

    def call_initialize(self) -> None:
        """Mock initialize call."""
        return

    def list_tools(self) -> list[MockTool]:
        """Mock list tools based on server type."""
        if "github" in self.server_name.lower():
            return [
                MockTool("search_issues", "Search for issues"),
                MockTool("get_issue", "Get issue details"),
                MockTool("get_issue_comments", "Get issue comments"),
                MockTool("update_issue", "Update issue"),
                MockTool("create_issue_comment", "Create issue comment"),
            ]
        if "gitlab" in self.server_name.lower():
            return [
                MockTool("list_issues", "List project issues"),
                MockTool("get_issue", "Get issue details"),
                MockTool("list_issue_discussions", "List issue discussions"),
                MockTool("update_issue", "Update issue"),
                MockTool("create_issue_note", "Create issue note"),
            ]
        return []

    @property
    def system_prompt(self) -> str:
        """Mock system prompt."""
        return f"Mock {self.server_name} MCP server for testing"

    def close(self) -> None:
        """Mock close."""

    def get_function_calling_functions(self) -> list:
        """Mock function calling functions."""
        return []

    def get_function_calling_tools(self) -> list:
        """Mock function calling tools."""
        return []

    def get_mock_data(self) -> dict[str, Any]:
        """Get mock data for inspection in tests."""
        return self.mock_data

    def reset_mock_data(self) -> None:
        """Reset mock data to initial state."""
        self._setup_mock_data()
