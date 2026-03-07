"""パスワード認証のテスト."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# 親ディレクトリをPythonパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.auth.password_hasher import hash_password, verify_password
from app.auth.password_policy import PasswordPolicy, validate_password
from app.auth.password_auth import authenticate_with_password
from app.database import get_db_context, init_db, reset_engine
from app.models.user import User
from app.services.auth_service import AuthService
from app.services.user_service import UserService


@pytest.fixture(autouse=True)
def setup_test_db() -> None:
    """テスト用データベースをセットアップする."""
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.environ["USE_MOCK_AD"] = "true"
    reset_engine()
    init_db()
    yield
    reset_engine()


class TestPasswordHasher:
    """パスワードハッシュユーティリティのテスト."""

    def test_hash_password_returns_hash(self) -> None:
        """ハッシュ化が成功することを確認."""
        hashed = hash_password("TestPass1")
        assert hashed != "TestPass1"
        # bcryptハッシュは$2b$で始まる
        assert hashed.startswith("$2b$")

    def test_verify_password_correct(self) -> None:
        """正しいパスワードで検証が成功することを確認."""
        hashed = hash_password("TestPass1")
        assert verify_password("TestPass1", hashed) is True

    def test_verify_password_wrong(self) -> None:
        """誤ったパスワードで検証が失敗することを確認."""
        hashed = hash_password("TestPass1")
        assert verify_password("WrongPass1", hashed) is False

    def test_hash_is_different_each_time(self) -> None:
        """同一パスワードでも毎回異なるハッシュが生成されることを確認（ソルト）."""
        hashed1 = hash_password("TestPass1")
        hashed2 = hash_password("TestPass1")
        # ソルトが異なるためハッシュ値は異なる
        assert hashed1 != hashed2
        # ただし両方とも検証は成功する
        assert verify_password("TestPass1", hashed1) is True
        assert verify_password("TestPass1", hashed2) is True


class TestPasswordPolicy:
    """パスワードポリシー検証のテスト."""

    def test_policy_from_config(self) -> None:
        """設定辞書からポリシーが生成されることを確認."""
        config = {
            "min_length": 10,
            "require_uppercase": True,
            "require_lowercase": True,
            "require_digit": True,
            "require_special": True,
            "bcrypt_rounds": 12,
        }
        policy = PasswordPolicy.from_config(config)
        assert policy.min_length == 10
        assert policy.require_uppercase is True
        assert policy.require_special is True

    def test_validate_password_too_short(self) -> None:
        """最小文字数未満のパスワードが拒否されることを確認."""
        policy = PasswordPolicy(min_length=8)
        valid, errors = validate_password("Ab1", policy)
        assert valid is False
        assert len(errors) > 0

    def test_validate_password_no_uppercase(self) -> None:
        """大文字がないパスワードが拒否されることを確認（require_uppercase=True）."""
        policy = PasswordPolicy(require_uppercase=True)
        valid, errors = validate_password("testpass1", policy)
        assert valid is False
        assert any("大文字" in e for e in errors)

    def test_validate_password_no_lowercase(self) -> None:
        """小文字がないパスワードが拒否されることを確認（require_lowercase=True）."""
        policy = PasswordPolicy(require_lowercase=True)
        valid, errors = validate_password("TESTPASS1", policy)
        assert valid is False
        assert any("小文字" in e for e in errors)

    def test_validate_password_no_digit(self) -> None:
        """数字がないパスワードが拒否されることを確認（require_digit=True）."""
        policy = PasswordPolicy(require_digit=True)
        valid, errors = validate_password("TestPassword", policy)
        assert valid is False
        assert any("数字" in e for e in errors)

    def test_validate_password_no_special(self) -> None:
        """特殊文字がないパスワードが拒否されることを確認（require_special=True）."""
        policy = PasswordPolicy(require_special=True)
        valid, errors = validate_password("TestPass1", policy)
        assert valid is False
        assert any("特殊文字" in e for e in errors)

    def test_validate_password_success(self) -> None:
        """ポリシーを満たすパスワードが受け入れられることを確認."""
        policy = PasswordPolicy(
            min_length=8,
            require_uppercase=True,
            require_lowercase=True,
            require_digit=True,
            require_special=False,
        )
        valid, errors = validate_password("TestPass1", policy)
        assert valid is True
        assert errors == []

    def test_validate_password_with_special(self) -> None:
        """特殊文字を含むパスワードがポリシーを満たすことを確認."""
        policy = PasswordPolicy(
            min_length=8,
            require_uppercase=True,
            require_lowercase=True,
            require_digit=True,
            require_special=True,
        )
        valid, errors = validate_password("TestPass1!", policy)
        assert valid is True
        assert errors == []

    def test_policy_description(self) -> None:
        """ポリシー説明文字列が生成されることを確認."""
        policy = PasswordPolicy(min_length=10, require_uppercase=True)
        desc = policy.get_description()
        assert "10文字" in desc
        assert "英大文字" in desc


class TestPasswordAuth:
    """パスワード認証ロジックのテスト."""

    def test_authenticate_with_password_success(self) -> None:
        """正しいパスワードでの認証成功を確認."""
        with get_db_context() as db:
            user_service = UserService(db)
            user = user_service.create_user(
                "testuser",
                auth_type="password",
                initial_password="TestPass1",
            )
            assert authenticate_with_password(user, "TestPass1") is True

    def test_authenticate_with_password_wrong(self) -> None:
        """誤ったパスワードでの認証失敗を確認."""
        with get_db_context() as db:
            user_service = UserService(db)
            user = user_service.create_user(
                "testuser",
                auth_type="password",
                initial_password="TestPass1",
            )
            assert authenticate_with_password(user, "WrongPass1") is False

    def test_authenticate_with_ldap_type_fails(self) -> None:
        """LDAPタイプのユーザーはパスワード認証できないことを確認."""
        with get_db_context() as db:
            user_service = UserService(db)
            # LDAPタイプのユーザー（auth_type="ldap"がデフォルト）
            user = user_service.create_user("ldapuser")
            # 手動でpassword_hashを設定（通常はないが、テスト用）
            user.password_hash = hash_password("TestPass1")
            db.commit()
            db.refresh(user)
            # auth_type="ldap"なのでパスワード認証は拒否される
            assert authenticate_with_password(user, "TestPass1") is False


class TestUserServicePasswordMethods:
    """UserServiceのパスワード関連メソッドのテスト."""

    def test_create_user_with_password(self) -> None:
        """パスワード認証タイプでユーザー作成を確認."""
        with get_db_context() as db:
            user_service = UserService(db)
            user = user_service.create_user(
                "testuser",
                auth_type="password",
                initial_password="TestPass1",
            )
            assert user.auth_type == "password"
            assert user.password_hash is not None
            assert user.password_must_change is True

    def test_create_user_with_password_sets_must_change(self) -> None:
        """初期パスワード設定時にpassword_must_changeがTrueになることを確認."""
        with get_db_context() as db:
            user_service = UserService(db)
            user = user_service.create_user(
                "testuser",
                auth_type="password",
                initial_password="TestPass1",
            )
            assert user.password_must_change is True

    def test_create_user_without_password_fails(self) -> None:
        """パスワードタイプでパスワードなしのユーザー作成が失敗することを確認."""
        with get_db_context() as db:
            user_service = UserService(db)
            with pytest.raises(ValueError, match="パスワードが必須"):
                user_service.create_user("testuser", auth_type="password")

    def test_create_user_weak_password_fails(self) -> None:
        """ポリシー違反のパスワードでのユーザー作成が失敗することを確認."""
        with get_db_context() as db:
            user_service = UserService(db)
            # 小文字のみ・短すぎる
            with pytest.raises(ValueError):
                user_service.create_user(
                    "testuser",
                    auth_type="password",
                    initial_password="abc",
                )

    def test_create_user_ldap_type_default(self) -> None:
        """デフォルトはLDAPタイプになることを確認."""
        with get_db_context() as db:
            user_service = UserService(db)
            user = user_service.create_user("testuser")
            assert user.auth_type == "ldap"
            assert user.password_hash is None
            assert user.password_must_change is False

    def test_reset_password(self) -> None:
        """管理者によるパスワードリセットを確認."""
        with get_db_context() as db:
            user_service = UserService(db)
            user = user_service.create_user(
                "testuser",
                auth_type="password",
                initial_password="TestPass1",
            )
            # password_must_changeをFalseにリセット
            user.password_must_change = False
            db.commit()

            # パスワードリセット
            result = user_service.reset_password(user.id, "NewPass1")
            assert result is True

            # リセット後の確認
            db.refresh(user)
            assert user.password_must_change is True
            assert user.password_updated_at is not None
            assert verify_password("NewPass1", user.password_hash)

    def test_reset_password_ldap_user_fails(self) -> None:
        """LDAPユーザーのパスワードリセットが失敗することを確認."""
        with get_db_context() as db:
            user_service = UserService(db)
            user = user_service.create_user("ldapuser")
            with pytest.raises(ValueError, match="パスワード認証タイプ"):
                user_service.reset_password(user.id, "NewPass1")

    def test_change_password_success(self) -> None:
        """ユーザー自身によるパスワード変更を確認."""
        with get_db_context() as db:
            user_service = UserService(db)
            user = user_service.create_user(
                "testuser",
                auth_type="password",
                initial_password="TestPass1",
            )

            result = user_service.change_password(user.id, "TestPass1", "NewPass2")
            assert result is True

            # 変更後の確認
            db.refresh(user)
            assert user.password_must_change is False
            assert user.password_updated_at is not None
            assert verify_password("NewPass2", user.password_hash)

    def test_change_password_wrong_current_fails(self) -> None:
        """現在のパスワードが誤っている場合に変更が失敗することを確認."""
        with get_db_context() as db:
            user_service = UserService(db)
            user = user_service.create_user(
                "testuser",
                auth_type="password",
                initial_password="TestPass1",
            )
            with pytest.raises(ValueError, match="現在のパスワード"):
                user_service.change_password(user.id, "WrongPass", "NewPass2")

    def test_change_password_updates_must_change_flag(self) -> None:
        """パスワード変更後にpassword_must_changeがFalseになることを確認."""
        with get_db_context() as db:
            user_service = UserService(db)
            user = user_service.create_user(
                "testuser",
                auth_type="password",
                initial_password="TestPass1",
            )
            assert user.password_must_change is True

            user_service.change_password(user.id, "TestPass1", "NewPass2")
            db.refresh(user)
            assert user.password_must_change is False


class TestAuthServicePasswordBranch:
    """AuthServiceのパスワード認証分岐テスト."""

    def test_authenticate_password_user_success(self) -> None:
        """パスワードタイプのユーザーの認証成功を確認."""
        with get_db_context() as db:
            # まずパスワードユーザーを作成
            user_service = UserService(db)
            user_service.create_user(
                "pwuser",
                auth_type="password",
                initial_password="TestPass1",
            )

        with get_db_context() as db:
            auth_service = AuthService(db)
            result = auth_service.authenticate("pwuser", "TestPass1")
            assert result is not None
            assert result.username == "pwuser"

    def test_authenticate_password_user_wrong_password(self) -> None:
        """パスワードタイプのユーザーが誤ったパスワードで認証失敗することを確認."""
        with get_db_context() as db:
            user_service = UserService(db)
            user_service.create_user(
                "pwuser",
                auth_type="password",
                initial_password="TestPass1",
            )

        with get_db_context() as db:
            auth_service = AuthService(db)
            result = auth_service.authenticate("pwuser", "WrongPass1")
            assert result is None

    def test_authenticate_ldap_user_still_works(self) -> None:
        """LDAPタイプのユーザーが引き続きAD認証できることを確認."""
        with get_db_context() as db:
            auth_service = AuthService(db)
            # モックADのデフォルトユーザーで認証
            result = auth_service.authenticate("admin", "admin123")
            assert result is not None
            assert result.auth_type == "ldap"

    def test_authenticate_inactive_password_user_fails(self) -> None:
        """無効なパスワードユーザーの認証が失敗することを確認."""
        with get_db_context() as db:
            user_service = UserService(db)
            user = user_service.create_user(
                "pwuser",
                auth_type="password",
                initial_password="TestPass1",
            )
            user_service.update_user(user.id, is_active=False)

        with get_db_context() as db:
            auth_service = AuthService(db)
            result = auth_service.authenticate("pwuser", "TestPass1")
            assert result is None
