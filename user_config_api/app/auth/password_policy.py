"""パスワードポリシー検証.

config.yamlで設定されたパスワードポリシーに基づいてパスワードを検証します。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PasswordPolicy:
    """パスワードポリシー設定.

    Attributes:
        min_length: パスワード最小文字数
        require_uppercase: 英大文字を必須とするか
        require_lowercase: 英小文字を必須とするか
        require_digit: 数字を必須とするか
        require_special: 特殊文字を必須とするか
        bcrypt_rounds: bcryptのワークファクター

    """

    min_length: int = 8
    require_uppercase: bool = True
    require_lowercase: bool = True
    require_digit: bool = True
    require_special: bool = False
    bcrypt_rounds: int = 12

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "PasswordPolicy":
        """設定辞書からポリシーを生成する.

        Args:
            config: password_authセクションの設定辞書

        Returns:
            PasswordPolicyインスタンス

        """
        return cls(
            min_length=config.get("min_length", 8),
            require_uppercase=config.get("require_uppercase", True),
            require_lowercase=config.get("require_lowercase", True),
            require_digit=config.get("require_digit", True),
            require_special=config.get("require_special", False),
            bcrypt_rounds=config.get("bcrypt_rounds", 12),
        )

    def get_description(self) -> str:
        """ポリシーの説明文字列を返す.

        Returns:
            ポリシー説明のテキスト

        """
        requirements = [f"最小{self.min_length}文字"]
        if self.require_uppercase:
            requirements.append("英大文字を含む")
        if self.require_lowercase:
            requirements.append("英小文字を含む")
        if self.require_digit:
            requirements.append("数字を含む")
        if self.require_special:
            requirements.append("特殊文字を含む")
        return "、".join(requirements)


def validate_password(password: str, policy: PasswordPolicy) -> tuple[bool, list[str]]:
    """パスワードポリシーに基づいてパスワードを検証する.

    Args:
        password: 検証するパスワード
        policy: 適用するパスワードポリシー

    Returns:
        (検証結果, エラーメッセージリスト) のタプル
        エラーなしの場合はエラーメッセージリストが空

    """
    errors: list[str] = []

    # 最小文字数チェック
    if len(password) < policy.min_length:
        errors.append(f"パスワードは{policy.min_length}文字以上で入力してください")

    # 英大文字チェック
    if policy.require_uppercase and not re.search(r"[A-Z]", password):
        errors.append("パスワードに英大文字を含めてください")

    # 英小文字チェック
    if policy.require_lowercase and not re.search(r"[a-z]", password):
        errors.append("パスワードに英小文字を含めてください")

    # 数字チェック
    if policy.require_digit and not re.search(r"\d", password):
        errors.append("パスワードに数字を含めてください")

    # 特殊文字チェック
    if policy.require_special and not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", password):
        errors.append("パスワードに特殊文字を含めてください")

    return len(errors) == 0, errors
