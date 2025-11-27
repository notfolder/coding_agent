"""認証サービス.

Active Directory認証のビジネスロジックを提供します。
"""

from __future__ import annotations

import logging
import os
from typing import Any

from sqlalchemy.orm import Session

from app.auth.ad_client import ADClient, MockADClient
from app.config import get_ad_config
from app.models.user import User
from app.services.user_service import UserService

logger = logging.getLogger(__name__)


class AuthService:
    """認証サービス.

    Active Directory認証とユーザー管理を統合します。
    """

    def __init__(self, db: Session, ad_config: dict[str, Any] | None = None) -> None:
        """AuthServiceを初期化する.

        Args:
            db: データベースセッション
            ad_config: Active Directory設定（Noneの場合はconfig.yamlから読み込み）

        """
        self.db = db
        self.user_service = UserService(db)

        # AD設定を読み込み
        if ad_config is None:
            ad_config = get_ad_config()

        # モックモードかどうかをチェック
        use_mock = os.environ.get("USE_MOCK_AD", "").lower() in ("true", "1", "yes")
        if use_mock or not ad_config:
            logger.info("モックADクライアントを使用します")
            self.ad_client: ADClient | MockADClient = MockADClient(ad_config)
        else:
            self.ad_client = ADClient(ad_config)

    def authenticate(self, username: str, password: str) -> User | None:
        """ユーザーを認証する.

        Active Directory認証を行い、成功した場合はデータベースの
        ユーザーを取得または作成します。

        Args:
            username: ユーザー名（sAMAccountName）
            password: パスワード

        Returns:
            認証成功時: Userオブジェクト
            認証失敗時: None

        """
        # AD認証
        ad_user = self.ad_client.authenticate(username, password)
        if not ad_user:
            logger.warning(f"AD認証に失敗しました: {username}")
            return None

        # データベースでユーザーを取得または作成
        user, created = self.user_service.get_or_create_user(
            ad_user.derived_username,
            ldap_uid=ad_user.uid,
            ldap_email=ad_user.email,
            display_name=ad_user.display_name,
        )

        if created:
            logger.info(f"新規ユーザーを作成しました: {user.username}")
        else:
            # 既存ユーザーの情報を更新
            if user.display_name != ad_user.display_name:
                self.user_service.update_user(
                    user.id, display_name=ad_user.display_name,
                )
            if user.ldap_uid != ad_user.uid:
                self.user_service.update_user(user.id, ldap_uid=ad_user.uid)
            if user.ldap_email != ad_user.email:
                self.user_service.update_user(user.id, ldap_email=ad_user.email)

        # アクティブでないユーザーは認証拒否
        if not user.is_active:
            logger.warning(f"無効なユーザーがログインを試みました: {username}")
            return None

        logger.info(f"ユーザーが認証されました: {user.username}")
        return user

    def get_user_from_session(self, user_id: int) -> User | None:
        """セッションからユーザーを取得する.

        Args:
            user_id: ユーザーID

        Returns:
            Userオブジェクト、または None

        """
        user = self.user_service.get_user_by_id(user_id)
        if user and user.is_active:
            return user
        return None

    def is_admin(self, user: User) -> bool:
        """ユーザーが管理者かどうかを判定する.

        Args:
            user: ユーザーオブジェクト

        Returns:
            管理者の場合True

        """
        return user.is_admin

    def test_ad_connection(self) -> bool:
        """AD接続をテストする.

        Returns:
            接続成功の場合True

        """
        return self.ad_client.test_connection()
