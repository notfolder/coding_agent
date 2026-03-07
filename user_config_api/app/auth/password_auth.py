"""パスワード認証ロジック.

パスワードハッシュによる認証処理を提供します。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.auth.password_hasher import verify_password

if TYPE_CHECKING:
    from app.models.user import User

logger = logging.getLogger(__name__)


def authenticate_with_password(user: "User", password: str) -> bool:
    """パスワードでユーザーを認証する.

    ユーザーの認証タイプがpasswordであり、パスワードハッシュが
    入力されたパスワードと一致する場合に認証成功とします。

    Args:
        user: データベースのUserオブジェクト
        password: 認証するパスワード（平文）

    Returns:
        認証成功の場合True

    """
    # 認証タイプがpasswordでない場合は拒否
    if user.auth_type != "password":
        logger.warning(
            f"パスワード認証が試みられましたが、認証タイプが異なります: "
            f"username={user.username}, auth_type={user.auth_type}"
        )
        return False

    # パスワードハッシュが設定されていない場合は拒否
    if not user.password_hash:
        logger.warning(f"パスワードハッシュが設定されていません: username={user.username}")
        return False

    # パスワード検証
    result = verify_password(password, user.password_hash)
    if not result:
        logger.warning(f"パスワード認証に失敗しました: username={user.username}")
    return result
