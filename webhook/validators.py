"""Webhook signature and token validation."""
from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

logger = logging.getLogger(__name__)


class GitHubWebhookValidator:
    """Validator for GitHub webhook signatures."""

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize GitHub webhook validator.

        Args:
            config: Application configuration containing webhook secret

        Raises:
            ValueError: If webhook secret is not configured

        """
        webhook_config = config.get("webhook", {}).get("github", {})
        self.secret = webhook_config.get("secret", "")

        if not self.secret:
            msg = "GitHub webhook secret is not configured. Set GITHUB_WEBHOOK_SECRET environment variable."
            logger.error(msg)
            raise ValueError(msg)

    def validate_signature(self, payload: bytes, signature: str | None) -> bool:
        """Validate GitHub webhook signature using HMAC-SHA256.

        Args:
            payload: Raw request body as bytes
            signature: X-Hub-Signature-256 header value

        Returns:
            True if signature is valid, False otherwise

        """
        if not signature:
            return False

        # Remove "sha256=" prefix
        signature = signature.removeprefix("sha256=")

        # Calculate expected signature
        expected = hmac.new(
            self.secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

        # Use timing-attack resistant comparison
        return hmac.compare_digest(expected, signature)


class GitLabWebhookValidator:
    """Validator for GitLab webhook tokens."""

    def __init__(self, config: dict[str, Any], *, is_system_hook: bool = False) -> None:
        """Initialize GitLab webhook validator.

        Args:
            config: Application configuration containing webhook token
            is_system_hook: Whether this is for system hook validation

        Raises:
            ValueError: If webhook token is not configured (system hook token is optional)

        """
        webhook_config = config.get("webhook", {}).get("gitlab", {})
        if is_system_hook:
            # System hook token is optional - only validate if configured
            self.token = webhook_config.get("system_hook_token", "")
        else:
            # Project webhook token is required
            self.token = webhook_config.get("token", "")
            if not self.token:
                msg = "GitLab webhook token is not configured. Set GITLAB_WEBHOOK_TOKEN environment variable."
                logger.error(msg)
                raise ValueError(msg)

    def validate_token(self, token: str | None) -> bool:
        """Validate GitLab webhook token.

        Args:
            token: X-Gitlab-Token header value

        Returns:
            True if token is valid, False otherwise

        """
        if not token:
            return False

        # Reject if no token is configured (security: prevent empty token bypass)
        if not self.token:
            return False

        # Use timing-attack resistant comparison
        return hmac.compare_digest(self.token, token)
