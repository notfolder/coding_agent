"""認証サービスのテスト."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# 親ディレクトリをPythonパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.auth.ad_client import ADUser, MockADClient
from app.database import get_db_context, init_db, reset_db, reset_engine
from app.services.auth_service import AuthService


@pytest.fixture(autouse=True)
def setup_test_db() -> None:
    """テスト用データベースをセットアップする."""
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.environ["USE_MOCK_AD"] = "true"
    reset_engine()
    init_db()
    yield
    reset_engine()


class TestMockADClient:
    """モックADクライアントのテストクラス."""

    def test_authenticate_success(self) -> None:
        """認証成功テスト."""
        client = MockADClient()

        user = client.authenticate("admin", "admin123")

        assert user is not None
        assert user.uid == "admin"
        assert user.email == "admin@example.com"
        assert user.derived_username == "admin"

    def test_authenticate_wrong_password(self) -> None:
        """パスワード不一致テスト."""
        client = MockADClient()

        user = client.authenticate("admin", "wrongpassword")

        assert user is None

    def test_authenticate_unknown_user(self) -> None:
        """存在しないユーザーテスト."""
        client = MockADClient()

        user = client.authenticate("unknown", "password")

        assert user is None

    def test_add_mock_user(self) -> None:
        """モックユーザー追加テスト."""
        client = MockADClient()
        client.add_mock_user(
            "newuser",
            "newpass",
            "newuser@example.com",
            "New User",
        )

        user = client.authenticate("newuser", "newpass")

        assert user is not None
        assert user.email == "newuser@example.com"

    def test_get_user_info(self) -> None:
        """ユーザー情報取得テスト."""
        client = MockADClient()

        user = client.get_user_info("admin")

        assert user is not None
        assert user.uid == "admin"

    def test_derived_username(self) -> None:
        """ユーザー名導出テスト."""
        user = ADUser(
            dn="CN=test,OU=Users,DC=example,DC=com",
            uid="testuser",
            email="taro.yamada@example.com",
            display_name="Taro Yamada",
        )

        assert user.derived_username == "taro.yamada"


class TestAuthService:
    """認証サービスのテストクラス."""

    def test_authenticate_creates_new_user(self) -> None:
        """認証時に新規ユーザーが作成されることを確認."""
        with get_db_context() as db:
            service = AuthService(db)

            # モッククライアントのデフォルトユーザーで認証
            user = service.authenticate("admin", "admin123")

            assert user is not None
            assert user.username == "admin"  # メールの@以前
            assert user.ldap_uid == "admin"
            assert user.ldap_email == "admin@example.com"

    def test_authenticate_returns_existing_user(self) -> None:
        """既存ユーザーの認証テスト."""
        with get_db_context() as db:
            service = AuthService(db)

            # 1回目の認証でユーザー作成
            user1 = service.authenticate("admin", "admin123")
            user1_id = user1.id

            # 2回目の認証で既存ユーザーを返す
            user2 = service.authenticate("admin", "admin123")

            assert user2.id == user1_id

    def test_authenticate_fails_for_inactive_user(self) -> None:
        """非アクティブユーザーの認証が失敗することを確認."""
        with get_db_context() as db:
            service = AuthService(db)

            # ユーザー作成
            user = service.authenticate("admin", "admin123")

            # ユーザーを非アクティブに
            service.user_service.update_user(user.id, is_active=False)

            # 再認証は失敗
            result = service.authenticate("admin", "admin123")
            assert result is None

    def test_authenticate_wrong_credentials(self) -> None:
        """認証失敗テスト."""
        with get_db_context() as db:
            service = AuthService(db)

            user = service.authenticate("admin", "wrongpassword")

            assert user is None

    def test_is_admin(self) -> None:
        """管理者判定テスト."""
        with get_db_context() as db:
            service = AuthService(db)

            user = service.authenticate("admin", "admin123")

            # デフォルトは管理者ではない
            assert service.is_admin(user) is False

            # 管理者に設定
            service.user_service.update_user(user.id, is_admin=True)
            db.refresh(user)

            assert service.is_admin(user) is True

    def test_get_user_from_session(self) -> None:
        """セッションからのユーザー取得テスト."""
        with get_db_context() as db:
            service = AuthService(db)

            user = service.authenticate("admin", "admin123")

            # IDでユーザーを取得
            found = service.get_user_from_session(user.id)
            assert found is not None
            assert found.id == user.id

    def test_get_user_from_session_inactive(self) -> None:
        """非アクティブユーザーのセッション取得テスト."""
        with get_db_context() as db:
            service = AuthService(db)

            user = service.authenticate("admin", "admin123")
            service.user_service.update_user(user.id, is_active=False)

            # 非アクティブユーザーはNoneを返す
            found = service.get_user_from_session(user.id)
            assert found is None
