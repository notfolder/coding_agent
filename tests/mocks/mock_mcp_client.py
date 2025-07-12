"""Comprehensive mock MCP client for testing GitHub and GitLab functionality."""

import json
from typing import Any, Dict, List, Optional


class MockTool:
    """Mock tool representation."""

    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description


class MockMCPToolClient:
    """Comprehensive mock implementation of MCPToolClient with GitHub and GitLab support."""

    def __init__(self, server_config, function_calling=True) -> None:
        self.server_config = server_config
        self.function_calling = function_calling
        self.server_name = server_config.get("mcp_server_name", "unknown")
        self._system_prompt = None

        # Initialize mock data based on server type
        self._setup_mock_data()

    def _setup_mock_data(self) -> None:
        """Setup mock data structures for different server types."""
        if "github" in self.server_name.lower():
            self._setup_github_mock_data()
        elif "gitlab" in self.server_name.lower():
            self._setup_gitlab_mock_data()
        else:
            self.mock_data = {}

    def _setup_github_mock_data(self) -> None:
        """Setup comprehensive GitHub mock data."""
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
        """Setup comprehensive GitLab mock data."""
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

    def call_tool(self, tool: str, args: dict[str, Any]) -> Any:
        """Mock tool call implementation with comprehensive GitHub/GitLab support."""
        if "github" in self.server_name.lower():
            return self._handle_github_tool(tool, args)
        if "gitlab" in self.server_name.lower():
            return self._handle_gitlab_tool(tool, args)
        return {}

    def _handle_github_tool(self, tool: str, args: dict[str, Any]) -> Any:
        """Handle GitHub-specific tool calls."""
        if tool == "search_issues":
            # Return issues matching query (simple label-based filtering)
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

        if tool == "get_issue":
            # Return specific issue
            issue_number = args.get("issue_number")
            for issue in self.mock_data["issues"]:
                if issue["number"] == issue_number:
                    return issue
            return None

        if tool == "get_issue_comments":
            # Return comments for issue
            issue_number = args.get("issue_number")
            if issue_number in [1, 2]:  # Mock comments for specific issues
                return self.mock_data["comments"]
            return []

        if tool == "update_issue":
            # Mock issue update
            issue_number = args.get("issue_number")
            labels = args.get("labels", [])
            # Find and update issue
            for issue in self.mock_data["issues"]:
                if issue["number"] == issue_number:
                    # Update labels (convert label names to label objects)
                    issue["labels"] = [{"name": label, "color": "blue"} for label in labels]
                    # Track the update
                    self.mock_data["updated_issues"][issue_number] = {
                        "labels": labels,
                        "updated_at": "2024-01-01T13:00:00Z",
                    }
                    return issue
            return None

        if tool == "create_issue_comment":
            # Mock comment creation
            comment_id = len(self.mock_data["comments"]) + 1
            new_comment = {
                "id": comment_id,
                "body": args.get("body", ""),
                "user": {"login": "bot"},
                "created_at": "2024-01-01T13:00:00Z",
            }
            self.mock_data["comments"].append(new_comment)
            return new_comment

        return {}

    def _handle_gitlab_tool(self, tool: str, args: dict[str, Any]) -> Any:
        """Handle GitLab-specific tool calls."""
        if tool == "list_issues":
            # Return issues matching criteria
            project_id = args.get("project_id")
            state = args.get("state", "opened")
            labels = args.get("labels", "")

            matching_issues = []
            for issue in self.mock_data["issues"]:
                if issue["project_id"] == int(project_id) and issue["state"] == state:
                    if not labels or labels in issue["labels"]:
                        matching_issues.append(issue)
            return {"items": matching_issues, "total_count": len(matching_issues)}

        if tool == "get_issue":
            # Return specific issue
            project_id = args.get("project_id")
            issue_iid = args.get("issue_iid")
            for issue in self.mock_data["issues"]:
                if issue["project_id"] == int(project_id) and issue["iid"] == issue_iid:
                    return issue
            return None

        if tool == "list_issue_discussions":
            # Return discussions for issue
            project_id = args.get("project_id")
            issue_iid = args.get("issue_iid")
            if int(project_id) == 123 and issue_iid in [
                1,
                2,
            ]:  # Mock discussions for specific issues
                return {"items": self.mock_data["discussions"]}
            return {"items": []}

        if tool == "update_issue":
            # Mock issue update
            project_id = args.get("project_id")
            issue_iid = args.get("issue_iid")
            labels = args.get("labels", [])
            # Find and update issue
            for issue in self.mock_data["issues"]:
                if issue["project_id"] == int(project_id) and issue["iid"] == issue_iid:
                    issue["labels"] = labels
                    # Track the update
                    self.mock_data["updated_issues"][issue_iid] = {
                        "labels": labels,
                        "updated_at": "2024-01-01T13:00:00Z",
                    }
                    return issue
            return None

        if tool == "create_issue_note":
            # Mock note creation
            note_id = len(self.mock_data["discussions"][0]["notes"]) + 1
            new_note = {
                "id": note_id,
                "body": args.get("body", ""),
                "author": {"username": "bot"},
                "created_at": "2024-01-01T13:00:00Z",
            }
            self.mock_data["discussions"][0]["notes"].append(new_note)
            return new_note

        return {}

    def call_initialize(self) -> None:
        """Mock initialize call."""
        return

    def list_tools(self):
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

    def get_function_calling_functions(self):
        """Mock function calling functions."""
        return []

    def get_function_calling_tools(self):
        """Mock function calling tools."""
        return []

    def get_mock_data(self):
        """Get mock data for inspection in tests."""
        return self.mock_data

    def reset_mock_data(self) -> None:
        """Reset mock data to initial state."""
        self._setup_mock_data()
