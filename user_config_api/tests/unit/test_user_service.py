"""ユーザーサービスのテスト."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# 親ディレクトリをPythonパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.database import get_db_context, init_db, reset_db, reset_engine
from app.models.user import User
from app.services.user_service import UserService


@pytest.fixture(autouse=True)
def setup_test_db() -> None:
    """テスト用データベースをセットアップする."""
    # テスト用のメモリ内データベースを使用
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    reset_engine()
    init_db()
    yield
    reset_engine()


class TestUserService:
    """ユーザーサービスのテストクラス."""

    def test_create_user(self) -> None:
        """ユーザー作成テスト."""
        with get_db_context() as db:
            service = UserService(db)

            user = service.create_user(
                "testuser",
                ldap_uid="testuser",
                ldap_email="testuser@example.com",
                display_name="Test User",
            )

            assert user.id is not None
            assert user.username == "testuser"
            assert user.ldap_uid == "testuser"
            assert user.ldap_email == "testuser@example.com"
            assert user.display_name == "Test User"
            assert user.is_admin is False
            assert user.is_active is True

    def test_create_user_duplicate_username_fails(self) -> None:
        """重複ユーザー名での作成が失敗することを確認."""
        with get_db_context() as db:
            service = UserService(db)

            service.create_user("testuser")

            with pytest.raises(ValueError, match="既に使用されています"):
                service.create_user("testuser")

    def test_get_user_by_id(self) -> None:
        """IDでのユーザー取得テスト."""
        with get_db_context() as db:
            service = UserService(db)

            created = service.create_user("testuser")
            found = service.get_user_by_id(created.id)

            assert found is not None
            assert found.username == "testuser"

    def test_get_user_by_username(self) -> None:
        """ユーザー名でのユーザー取得テスト."""
        with get_db_context() as db:
            service = UserService(db)

            service.create_user("testuser")
            found = service.get_user_by_username("testuser")

            assert found is not None
            assert found.username == "testuser"

    def test_get_user_by_ldap_uid(self) -> None:
        """LDAP UIDでのユーザー取得テスト."""
        with get_db_context() as db:
            service = UserService(db)

            service.create_user("testuser", ldap_uid="test-ldap-uid")
            found = service.get_user_by_ldap_uid("test-ldap-uid")

            assert found is not None
            assert found.ldap_uid == "test-ldap-uid"

    def test_get_all_users(self) -> None:
        """全ユーザー取得テスト."""
        with get_db_context() as db:
            service = UserService(db)

            service.create_user("user1")
            service.create_user("user2")
            service.create_user("user3", is_active=False)

            # 全ユーザー
            all_users = service.get_all_users()
            assert len(all_users) == 3

            # アクティブのみ
            active_users = service.get_all_users(active_only=True)
            assert len(active_users) == 2

    def test_get_all_users_with_search(self) -> None:
        """検索付きユーザー取得テスト."""
        with get_db_context() as db:
            service = UserService(db)

            service.create_user("john.doe", display_name="John Doe")
            service.create_user("jane.doe", display_name="Jane Doe")
            service.create_user("bob.smith", display_name="Bob Smith")

            # ユーザー名で検索
            results = service.get_all_users(search="doe")
            assert len(results) == 2

            # 表示名で検索
            results = service.get_all_users(search="Bob")
            assert len(results) == 1

    def test_update_user(self) -> None:
        """ユーザー更新テスト."""
        with get_db_context() as db:
            service = UserService(db)

            user = service.create_user("testuser")

            updated = service.update_user(
                user.id,
                display_name="Updated Name",
                is_admin=True,
            )

            assert updated is not None
            assert updated.display_name == "Updated Name"
            assert updated.is_admin is True

    def test_delete_user_soft(self) -> None:
        """論理削除テスト."""
        with get_db_context() as db:
            service = UserService(db)

            user = service.create_user("testuser")

            result = service.delete_user(user.id, soft_delete=True)
            assert result is True

            # ユーザーはまだ存在するが、非アクティブ
            found = service.get_user_by_id(user.id)
            assert found is not None
            assert found.is_active is False

    def test_delete_user_hard(self) -> None:
        """物理削除テスト."""
        with get_db_context() as db:
            service = UserService(db)

            user = service.create_user("testuser")

            result = service.delete_user(user.id, soft_delete=False)
            assert result is True

            # ユーザーは完全に削除
            found = service.get_user_by_id(user.id)
            assert found is None

    def test_get_or_create_user_creates(self) -> None:
        """ユーザーが存在しない場合は作成することを確認."""
        with get_db_context() as db:
            service = UserService(db)

            user, created = service.get_or_create_user(
                "newuser",
                ldap_uid="newuser-uid",
            )

            assert created is True
            assert user.username == "newuser"

    def test_get_or_create_user_gets_existing(self) -> None:
        """ユーザーが存在する場合は取得することを確認."""
        with get_db_context() as db:
            service = UserService(db)

            service.create_user("existinguser", ldap_uid="existing-uid")

            user, created = service.get_or_create_user(
                "existinguser",
                ldap_uid="existing-uid",
            )

            assert created is False
            assert user.username == "existinguser"

    def test_count_users(self) -> None:
        """ユーザー数カウントテスト."""
        with get_db_context() as db:
            service = UserService(db)

            service.create_user("user1")
            service.create_user("user2")
            service.create_user("user3", is_active=False)

            assert service.count_users() == 3
            assert service.count_users(active_only=True) == 2

    def test_update_user_config(self) -> None:
        """ユーザー設定更新テスト."""
        with get_db_context() as db:
            service = UserService(db)

            user = service.create_user("testuser")

            config = service.update_user_config(
                user.id,
                llm_model="gpt-4-turbo",
            )

            assert config is not None
            assert config.llm_model == "gpt-4-turbo"

    def test_update_user_config_api_key_encrypted(self) -> None:
        """APIキーが暗号化されることを確認."""
        with get_db_context() as db:
            service = UserService(db)

            user = service.create_user("testuser")

            config = service.update_user_config(
                user.id,
                llm_api_key="sk-test-api-key",
            )

            # 保存された値は暗号化されている
            assert config.llm_api_key != "sk-test-api-key"

            # 復号化すると元の値が取得できる
            decrypted = service.get_decrypted_api_key(user.id)
            assert decrypted == "sk-test-api-key"

    def test_delete_user_config(self) -> None:
        """ユーザー設定削除テスト."""
        with get_db_context() as db:
            service = UserService(db)

            user = service.create_user("testuser")
            service.update_user_config(user.id, llm_model="gpt-4")

            # 設定が存在することを確認
            config = service.get_user_config(user.id)
            assert config is not None

            # 削除
            result = service.delete_user_config(user.id)
            assert result is True

            # 設定が削除されたことを確認
            config = service.get_user_config(user.id)
            assert config is None
