"""FastAPI webhook server for receiving GitHub and GitLab events."""
from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse

from webhook.task_factory import WebhookTaskFactory
from webhook.validators import GitHubWebhookValidator, GitLabWebhookValidator

if TYPE_CHECKING:
    from queueing import InMemoryTaskQueue, RabbitMQTaskQueue

logger = logging.getLogger(__name__)


class WebhookServer:
    """FastAPI server for receiving webhook events from GitHub and GitLab."""

    def __init__(
        self,
        config: dict[str, Any],
        mcp_clients: dict[str, Any],
        task_queue: RabbitMQTaskQueue | InMemoryTaskQueue,
    ) -> None:
        """Initialize webhook server.

        Args:
            config: Application configuration
            mcp_clients: Dictionary of MCP clients
            task_queue: Task queue for adding tasks

        """
        self.config = config
        self.mcp_clients = mcp_clients
        self.task_queue = task_queue
        self.app = FastAPI(title="Coding Agent Webhook Server")

        # Initialize validators
        self.github_validator = GitHubWebhookValidator(config)
        self.gitlab_validator = GitLabWebhookValidator(config, is_system_hook=False)
        self.gitlab_system_validator = GitLabWebhookValidator(config, is_system_hook=True)

        # Initialize task factory
        self.task_factory = WebhookTaskFactory(config, mcp_clients)

        # Setup routes
        self._setup_routes()

    def _setup_routes(self) -> None:  # noqa: C901
        """Set up FastAPI routes."""

        @self.app.get("/health")
        async def health_check() -> dict[str, str]:
            """Health check endpoint."""
            return {"status": "healthy"}

        @self.app.post("/webhook/github")
        async def github_webhook(
            request: Request,
            x_github_event: str | None = Header(None, alias="X-GitHub-Event"),
            x_hub_signature_256: str | None = Header(None, alias="X-Hub-Signature-256"),
        ) -> JSONResponse:
            """Handle GitHub webhook events.

            Args:
                request: FastAPI request object
                x_github_event: GitHub event type header
                x_hub_signature_256: GitHub signature header

            Returns:
                JSON response with status

            """
            # Read raw body for signature validation
            body = await request.body()
            payload = await request.json()

            # Validate signature
            if not self.github_validator.validate_signature(body, x_hub_signature_256):
                logger.error("GitHub webhook signature validation failed")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid signature",
                )

            logger.info("Received GitHub webhook: event=%s, action=%s", x_github_event, payload.get("action"))

            # Filter by event type
            if x_github_event not in ["issues", "pull_request"]:
                logger.info("Ignoring GitHub event type: %s", x_github_event)
                return JSONResponse({"status": "ignored", "reason": "unsupported event type"})

            # Filter by action
            action = payload.get("action")
            if action != "labeled":
                logger.info("Ignoring GitHub action: %s", action)
                return JSONResponse({"status": "ignored", "reason": "unsupported action"})

            # Filter by label
            label = payload.get("label", {}).get("name")
            bot_label = self.config.get("github", {}).get("bot_label", "coding agent")
            if label != bot_label:
                logger.info("Ignoring label: %s (expected: %s)", label, bot_label)
                return JSONResponse({"status": "ignored", "reason": "label mismatch"})

            logger.info("Label matched: %s", label)

            # Create task
            task = self.task_factory.create_github_task(x_github_event, payload)
            if not task:
                logger.error("Failed to create task from GitHub webhook")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create task",
                )

            # Prepare task and add to queue
            task.prepare()
            task_dict = task.get_task_key().to_dict()
            task_dict["uuid"] = str(uuid.uuid4())
            task_dict["user"] = task.get_user()
            self.task_queue.put(task_dict)

            logger.info("Task queued successfully: %s", task_dict)

            return JSONResponse({"status": "success", "task": task_dict})

        @self.app.post("/webhook/gitlab")
        async def gitlab_webhook(
            request: Request,
            x_gitlab_event: str | None = Header(None, alias="X-Gitlab-Event"),
            x_gitlab_token: str | None = Header(None, alias="X-Gitlab-Token"),
        ) -> JSONResponse:
            """Handle GitLab webhook events.

            Args:
                request: FastAPI request object
                x_gitlab_event: GitLab event type header
                x_gitlab_token: GitLab token header

            Returns:
                JSON response with status

            """
            payload = await request.json()

            # Validate token
            if not self.gitlab_validator.validate_token(x_gitlab_token):
                logger.error("GitLab webhook token validation failed")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token",
                )

            logger.info("Received GitLab webhook: event=%s", x_gitlab_event)

            return self._process_gitlab_webhook(x_gitlab_event, payload)

        @self.app.post("/webhook/gitlab/system")
        async def gitlab_system_hook(
            request: Request,
            x_gitlab_event: str | None = Header(None, alias="X-Gitlab-Event"),
            x_gitlab_token: str | None = Header(None, alias="X-Gitlab-Token"),
        ) -> JSONResponse:
            """Handle GitLab system hook events.

            Args:
                request: FastAPI request object
                x_gitlab_event: GitLab event type header
                x_gitlab_token: GitLab system hook token header

            Returns:
                JSON response with status

            """
            payload = await request.json()

            # Validate token with system hook validator
            if not self.gitlab_system_validator.validate_token(x_gitlab_token):
                logger.error("GitLab system hook token validation failed")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token",
                )

            logger.info("Received GitLab system hook: event=%s", x_gitlab_event)

            return self._process_gitlab_webhook(x_gitlab_event, payload)

    def _process_gitlab_webhook(
        self,
        event_type: str | None,
        payload: dict[str, Any],
    ) -> JSONResponse:
        """Process GitLab webhook payload.

        Args:
            event_type: GitLab event type
            payload: GitLab webhook payload

        Returns:
            JSON response with status

        """
        # Filter by event type
        if event_type not in ["Issue Hook", "Merge Request Hook"]:
            logger.info("Ignoring GitLab event type: %s", event_type)
            return JSONResponse({"status": "ignored", "reason": "unsupported event type"})

        # Get object attributes
        obj_attrs = payload.get("object_attributes", {})
        action = obj_attrs.get("action")

        # Filter by action (GitLab uses "update" when labels change)
        if action != "update":
            logger.info("Ignoring GitLab action: %s", action)
            return JSONResponse({"status": "ignored", "reason": "unsupported action"})

        # Filter by label
        labels = payload.get("labels", [])
        bot_label = self.config.get("gitlab", {}).get("bot_label", "coding agent")

        # Check if bot label is in the labels list
        has_bot_label = any(label.get("title") == bot_label for label in labels)
        if not has_bot_label:
            logger.info("Bot label '%s' not found in labels", bot_label)
            return JSONResponse({"status": "ignored", "reason": "label mismatch"})

        logger.info("Label matched: %s", bot_label)

        # Create task
        task = self.task_factory.create_gitlab_task(event_type, payload)
        if not task:
            logger.error("Failed to create task from GitLab webhook")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create task",
            )

        # Prepare task and add to queue
        task.prepare()
        task_dict = task.get_task_key().to_dict()
        task_dict["uuid"] = str(uuid.uuid4())
        task_dict["user"] = task.get_user()
        self.task_queue.put(task_dict)

        logger.info("Task queued successfully: %s", task_dict)

        return JSONResponse({"status": "success", "task": task_dict})

    def run(self, host: str = "0.0.0.0", port: int = 8000) -> None:  # noqa: S104
        """Run the webhook server.

        Note: Default host 0.0.0.0 binds to all interfaces, required for Docker containers.
        For production deployments, use a reverse proxy (nginx/Caddy) with HTTPS.
        For local development without Docker, override with host='127.0.0.1'.

        Args:
            host: Host to bind to (default: 0.0.0.0 for Docker compatibility)
            port: Port to bind to (default: 8000)

        """
        logger.info("Starting webhook server on %s:%d", host, port)
        uvicorn.run(self.app, host=host, port=port, log_level="info")
