"""Task factory for creating tasks from webhook payloads."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from clients.github_client import GithubClient
    from clients.gitlab_client import GitlabClient
    from clients.mcp_tool_client import MCPToolClient
    from handlers.task import Task


logger = logging.getLogger(__name__)


class WebhookTaskFactory:
    """Factory for creating Task objects from webhook payloads."""

    def __init__(
        self,
        config: dict[str, Any],
        mcp_clients: dict[str, MCPToolClient],
    ) -> None:
        """Initialize webhook task factory.

        Args:
            config: Application configuration
            mcp_clients: Dictionary of MCP clients
        """
        self.config = config
        self.mcp_clients = mcp_clients

    def create_github_task(
        self,
        event_type: str,
        payload: dict[str, Any],
    ) -> Task | None:
        """Create a Task from GitHub webhook payload.

        Args:
            event_type: GitHub event type (issues or pull_request)
            payload: GitHub webhook payload

        Returns:
            Task instance or None if event type is not supported
        """
        from handlers.task_getter_github import TaskGitHubIssue, TaskGitHubPullRequest

        mcp_client = self.mcp_clients.get("github")
        if not mcp_client:
            logger.error("GitHub MCP client not found")
            return None

        # Import GithubClient here to avoid circular import
        from clients.github_client import GithubClient

        github_client = GithubClient()

        if event_type == "issues":
            issue = payload.get("issue")
            if not issue:
                logger.error("Issue data not found in payload")
                return None
            return TaskGitHubIssue(issue, mcp_client, github_client, self.config)

        if event_type == "pull_request":
            pr = payload.get("pull_request")
            if not pr:
                logger.error("Pull request data not found in payload")
                return None
            return TaskGitHubPullRequest(pr, mcp_client, github_client, self.config)

        logger.warning("Unsupported GitHub event type: %s", event_type)
        return None

    def create_gitlab_task(
        self,
        event_type: str,
        payload: dict[str, Any],
    ) -> Task | None:
        """Create a Task from GitLab webhook payload.

        Args:
            event_type: GitLab event type (Issue Hook or Merge Request Hook)
            payload: GitLab webhook payload

        Returns:
            Task instance or None if event type is not supported
        """
        from handlers.task_getter_gitlab import TaskGitLabIssue, TaskGitLabMergeRequest

        mcp_client = self.mcp_clients.get("gitlab")
        if not mcp_client:
            logger.error("GitLab MCP client not found")
            return None

        # Import GitlabClient here to avoid circular import
        from clients.gitlab_client import GitlabClient

        gitlab_client = GitlabClient()

        if event_type == "Issue Hook":
            issue = payload.get("object_attributes")
            if not issue:
                logger.error("Issue data not found in payload")
                return None
            # Wrap in a dict that matches expected structure
            issue_data = {"issue": issue, "project": payload.get("project")}
            return TaskGitLabIssue(issue_data, mcp_client, gitlab_client, self.config)

        if event_type == "Merge Request Hook":
            mr = payload.get("object_attributes")
            if not mr:
                logger.error("Merge request data not found in payload")
                return None
            # Wrap in a dict that matches expected structure
            mr_data = {"merge_request": mr, "project": payload.get("project")}
            return TaskGitLabMergeRequest(mr_data, mcp_client, gitlab_client, self.config)

        logger.warning("Unsupported GitLab event type: %s", event_type)
        return None
