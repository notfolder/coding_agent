"""初期管理者作成コマンド.

データベースに初期管理者ユーザーを作成します。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# 親ディレクトリをPythonパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.database import get_db_context, init_db
from app.services.user_service import UserService


def create_admin(
    username: str,
    ldap_uid: str | None = None,
    ldap_email: str | None = None,
    display_name: str | None = None,
) -> None:
    """初期管理者ユーザーを作成する.

    Args:
        username: GitHub/GitLabユーザー名
        ldap_uid: Active DirectoryのUID
        ldap_email: Active Directoryのメールアドレス
        display_name: 表示名

    """
    # データベース初期化
    init_db()

    with get_db_context() as db:
        user_service = UserService(db)

        # 既存ユーザーのチェック
        existing = user_service.get_user_by_username(username)
        if existing:
            print(f"ユーザー '{username}' は既に存在します。")
            if not existing.is_admin:
                # 管理者権限を付与
                user_service.update_user(existing.id, is_admin=True)
                print(f"ユーザー '{username}' に管理者権限を付与しました。")
            else:
                print(f"ユーザー '{username}' は既に管理者です。")
            return

        # 新規作成
        user = user_service.create_user(
            username,
            ldap_uid=ldap_uid,
            ldap_email=ldap_email,
            display_name=display_name,
            is_admin=True,
            is_active=True,
        )
        print(f"管理者ユーザー '{user.username}' を作成しました。")
        print(f"  ID: {user.id}")
        print(f"  LDAP UID: {user.ldap_uid}")
        print(f"  LDAP Email: {user.ldap_email}")
        print(f"  表示名: {user.display_name}")


def main() -> None:
    """メインエントリポイント."""
    parser = argparse.ArgumentParser(
        description="初期管理者ユーザーを作成します。",
    )
    parser.add_argument(
        "--username",
        required=True,
        help="GitHub/GitLabユーザー名",
    )
    parser.add_argument(
        "--ldap-uid",
        help="Active DirectoryのUID (sAMAccountName)",
    )
    parser.add_argument(
        "--ldap-email",
        help="Active Directoryのメールアドレス",
    )
    parser.add_argument(
        "--display-name",
        help="表示名",
    )

    args = parser.parse_args()

    # 環境変数からのフォールバック
    ldap_uid = args.ldap_uid or os.environ.get("INITIAL_ADMIN_LDAP_UID")
    ldap_email = args.ldap_email or os.environ.get("INITIAL_ADMIN_LDAP_EMAIL")
    display_name = args.display_name or os.environ.get("INITIAL_ADMIN_DISPLAY_NAME")

    create_admin(
        username=args.username,
        ldap_uid=ldap_uid,
        ldap_email=ldap_email,
        display_name=display_name,
    )


if __name__ == "__main__":
    main()
