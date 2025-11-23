"""Webhook signature and token validation."""
from __future__ import annotations

import hashlib
import hmac
from typing import Any


class GitHubWebhookValidator:
    """Validator for GitHub webhook signatures."""

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize GitHub webhook validator.

        Args:
            config: Application configuration containing webhook secret
        """
        webhook_config = config.get("webhook", {}).get("github", {})
        self.secret = webhook_config.get("secret", "")

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
        if signature.startswith("sha256="):
            signature = signature[7:]

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
        """
        webhook_config = config.get("webhook", {}).get("gitlab", {})
        if is_system_hook:
            self.token = webhook_config.get("system_hook_token", "")
        else:
            self.token = webhook_config.get("token", "")

    def validate_token(self, token: str | None) -> bool:
        """Validate GitLab webhook token.

        Args:
            token: X-Gitlab-Token header value

        Returns:
            True if token is valid, False otherwise
        """
        if not token:
            return False

        # Use timing-attack resistant comparison
        return hmac.compare_digest(self.token, token)
