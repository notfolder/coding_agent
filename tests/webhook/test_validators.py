"""Unit tests for webhook validators."""
from __future__ import annotations

import hashlib
import hmac

from webhook.validators import GitHubWebhookValidator, GitLabWebhookValidator


class TestGitHubWebhookValidator:
    """Test GitHub webhook signature validation."""

    def test_valid_signature(self) -> None:
        """Test validation with valid signature."""
        config = {"webhook": {"github": {"secret": "test_secret"}}}
        validator = GitHubWebhookValidator(config)

        payload = b'{"action":"labeled"}'
        signature = "sha256=" + hmac.new(
            b"test_secret",
            payload,
            hashlib.sha256,
        ).hexdigest()

        assert validator.validate_signature(payload, signature) is True

    def test_invalid_signature(self) -> None:
        """Test validation with invalid signature."""
        config = {"webhook": {"github": {"secret": "test_secret"}}}
        validator = GitHubWebhookValidator(config)

        payload = b'{"action":"labeled"}'
        invalid_signature = "sha256=invalid_signature_here"

        assert validator.validate_signature(payload, invalid_signature) is False

    def test_no_signature(self) -> None:
        """Test validation with no signature."""
        config = {"webhook": {"github": {"secret": "test_secret"}}}
        validator = GitHubWebhookValidator(config)

        payload = b'{"action":"labeled"}'

        assert validator.validate_signature(payload, None) is False

    def test_signature_without_prefix(self) -> None:
        """Test validation with signature without sha256= prefix."""
        config = {"webhook": {"github": {"secret": "test_secret"}}}
        validator = GitHubWebhookValidator(config)

        payload = b'{"action":"labeled"}'
        signature = hmac.new(
            b"test_secret",
            payload,
            hashlib.sha256,
        ).hexdigest()

        assert validator.validate_signature(payload, signature) is True


class TestGitLabWebhookValidator:
    """Test GitLab webhook token validation."""

    def test_valid_token(self) -> None:
        """Test validation with valid token."""
        config = {"webhook": {"gitlab": {"token": "test_token"}}}
        validator = GitLabWebhookValidator(config, is_system_hook=False)

        assert validator.validate_token("test_token") is True

    def test_invalid_token(self) -> None:
        """Test validation with invalid token."""
        config = {"webhook": {"gitlab": {"token": "test_token"}}}
        validator = GitLabWebhookValidator(config, is_system_hook=False)

        assert validator.validate_token("wrong_token") is False

    def test_no_token(self) -> None:
        """Test validation with no token."""
        config = {"webhook": {"gitlab": {"token": "test_token"}}}
        validator = GitLabWebhookValidator(config, is_system_hook=False)

        assert validator.validate_token(None) is False

    def test_valid_system_hook_token(self) -> None:
        """Test validation with valid system hook token."""
        config = {"webhook": {"gitlab": {"system_hook_token": "system_token"}}}
        validator = GitLabWebhookValidator(config, is_system_hook=True)

        assert validator.validate_token("system_token") is True

    def test_invalid_system_hook_token(self) -> None:
        """Test validation with invalid system hook token."""
        config = {"webhook": {"gitlab": {"system_hook_token": "system_token"}}}
        validator = GitLabWebhookValidator(config, is_system_hook=True)

        assert validator.validate_token("wrong_token") is False
