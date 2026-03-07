"""パスワードハッシュ化ユーティリティ.

bcryptを使用したパスワードのハッシュ化と検証を提供します。
"""

from __future__ import annotations

import logging

import bcrypt

logger = logging.getLogger(__name__)


def hash_password(password: str, rounds: int = 12) -> str:
    """パスワードをbcryptでハッシュ化する.

    Args:
        password: 平文パスワード
        rounds: bcryptのワークファクター（デフォルト: 12）

    Returns:
        ハッシュ化されたパスワード文字列

    """
    # bcryptはbytes型を要求するためエンコード
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=rounds)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """パスワードをハッシュと照合して検証する.

    Args:
        password: 検証する平文パスワード
        password_hash: データベースに保存されたbcryptハッシュ

    Returns:
        パスワードが一致する場合True

    """
    try:
        password_bytes = password.encode("utf-8")
        hash_bytes = password_hash.encode("utf-8")
        return bcrypt.checkpw(password_bytes, hash_bytes)
    except Exception as e:
        logger.error(f"パスワード検証エラー: {e}")
        return False
