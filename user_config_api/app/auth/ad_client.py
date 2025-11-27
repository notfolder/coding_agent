"""Active Directory クライアント.

Active Directory/LDAPサーバーへの接続と認証を提供します。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ADUser:
    """Active Directoryユーザー情報.

    Attributes:
        dn: 識別名
        uid: sAMAccountName
        email: メールアドレス
        display_name: 表示名
        derived_username: 導出されたGitHub/GitLabユーザー名（メールの@以前）

    """

    dn: str
    uid: str
    email: str
    display_name: str

    @property
    def derived_username(self) -> str:
        """メールアドレスからGitHub/GitLabユーザー名を導出する.

        Returns:
            メールアドレスの@以前の部分

        """
        if self.email and "@" in self.email:
            return self.email.split("@")[0]
        return self.uid


class ADClient:
    """Active Directoryクライアント.

    Active Directory/LDAPサーバーへの接続と認証を行います。
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """ADClientを初期化する.

        Args:
            config: Active Directory設定辞書

        """
        self.config = config
        self._connection = None

        # サーバー設定
        server_config = config.get("server", {})
        self.host = server_config.get("host", "localhost")
        self.port = server_config.get("port", 636)
        self.use_ssl = server_config.get("use_ssl", True)

        # バインド設定
        bind_config = config.get("bind", {})
        self.bind_dn = bind_config.get("dn", "")
        password_env = bind_config.get("password_env", "AD_BIND_PASSWORD")
        self.bind_password = os.environ.get(password_env, "")

        # ユーザー検索設定
        user_search_config = config.get("user_search", {})
        self.base_dn = user_search_config.get("base_dn", "")
        self.user_filter = user_search_config.get("filter", "(sAMAccountName={username})")

        # 属性マッピング
        attributes_config = user_search_config.get("attributes", {})
        self.uid_attr = attributes_config.get("uid", "sAMAccountName")
        self.email_attr = attributes_config.get("email", "userPrincipalName")
        self.display_name_attr = attributes_config.get("display_name", "displayName")

        # タイムアウト設定
        timeout_config = config.get("timeout", {})
        self.connect_timeout = timeout_config.get("connect", 5)
        self.operation_timeout = timeout_config.get("operation", 10)

    def _get_server_uri(self) -> str:
        """LDAPサーバーURIを取得する.

        Returns:
            サーバーURI文字列

        """
        protocol = "ldaps" if self.use_ssl else "ldap"
        return f"{protocol}://{self.host}:{self.port}"

    def authenticate(self, username: str, password: str) -> ADUser | None:
        """ユーザーを認証する.

        Args:
            username: ユーザー名（sAMAccountName）
            password: パスワード

        Returns:
            認証成功時: ADUserオブジェクト
            認証失敗時: None

        """
        try:
            import ldap

            # サーバーに接続
            server_uri = self._get_server_uri()
            conn = ldap.initialize(server_uri)

            # LDAPオプション設定
            conn.set_option(ldap.OPT_PROTOCOL_VERSION, 3)
            conn.set_option(ldap.OPT_NETWORK_TIMEOUT, self.connect_timeout)
            conn.set_option(ldap.OPT_TIMEOUT, self.operation_timeout)

            if self.use_ssl:
                conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)

            # サービスアカウントでバインド
            if self.bind_dn and self.bind_password:
                conn.simple_bind_s(self.bind_dn, self.bind_password)
            else:
                # 匿名バインド
                conn.simple_bind_s()

            # ユーザーを検索
            search_filter = self.user_filter.format(username=username)
            attrs = [self.uid_attr, self.email_attr, self.display_name_attr]

            result = conn.search_s(
                self.base_dn,
                ldap.SCOPE_SUBTREE,
                search_filter,
                attrs,
            )

            if not result:
                logger.warning(f"ユーザーが見つかりません: {username}")
                conn.unbind_s()
                return None

            user_dn, user_attrs = result[0]

            # ユーザーのパスワードで再バインドして認証
            try:
                user_conn = ldap.initialize(server_uri)
                user_conn.set_option(ldap.OPT_PROTOCOL_VERSION, 3)
                if self.use_ssl:
                    user_conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
                user_conn.simple_bind_s(user_dn, password)
                user_conn.unbind_s()
            except ldap.INVALID_CREDENTIALS:
                logger.warning(f"パスワードが正しくありません: {username}")
                conn.unbind_s()
                return None

            conn.unbind_s()

            # ADUserオブジェクトを作成
            def get_attr(attrs: dict, name: str) -> str:
                """属性値を取得する."""
                values = attrs.get(name, [])
                if values:
                    val = values[0]
                    return val.decode("utf-8") if isinstance(val, bytes) else val
                return ""

            return ADUser(
                dn=user_dn,
                uid=get_attr(user_attrs, self.uid_attr),
                email=get_attr(user_attrs, self.email_attr),
                display_name=get_attr(user_attrs, self.display_name_attr),
            )

        except ImportError:
            logger.error("python-ldapがインストールされていません")
            return None
        except Exception as e:
            logger.error(f"AD認証エラー: {e}")
            return None

    def get_user_info(self, username: str) -> ADUser | None:
        """ユーザー情報を取得する（認証なし）.

        サービスアカウントを使用してユーザー情報を検索します。

        Args:
            username: ユーザー名（sAMAccountName）

        Returns:
            ユーザー情報が見つかった場合: ADUserオブジェクト
            見つからない場合: None

        """
        try:
            import ldap

            server_uri = self._get_server_uri()
            conn = ldap.initialize(server_uri)

            conn.set_option(ldap.OPT_PROTOCOL_VERSION, 3)
            conn.set_option(ldap.OPT_NETWORK_TIMEOUT, self.connect_timeout)
            conn.set_option(ldap.OPT_TIMEOUT, self.operation_timeout)

            if self.use_ssl:
                conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)

            # サービスアカウントでバインド
            if self.bind_dn and self.bind_password:
                conn.simple_bind_s(self.bind_dn, self.bind_password)
            else:
                conn.simple_bind_s()

            # ユーザーを検索
            search_filter = self.user_filter.format(username=username)
            attrs = [self.uid_attr, self.email_attr, self.display_name_attr]

            result = conn.search_s(
                self.base_dn,
                ldap.SCOPE_SUBTREE,
                search_filter,
                attrs,
            )

            conn.unbind_s()

            if not result:
                return None

            user_dn, user_attrs = result[0]

            def get_attr(attrs: dict, name: str) -> str:
                """属性値を取得する."""
                values = attrs.get(name, [])
                if values:
                    val = values[0]
                    return val.decode("utf-8") if isinstance(val, bytes) else val
                return ""

            return ADUser(
                dn=user_dn,
                uid=get_attr(user_attrs, self.uid_attr),
                email=get_attr(user_attrs, self.email_attr),
                display_name=get_attr(user_attrs, self.display_name_attr),
            )

        except ImportError:
            logger.error("python-ldapがインストールされていません")
            return None
        except Exception as e:
            logger.error(f"ユーザー情報取得エラー: {e}")
            return None

    def test_connection(self) -> bool:
        """AD接続をテストする.

        Returns:
            接続成功の場合: True
            接続失敗の場合: False

        """
        try:
            import ldap

            server_uri = self._get_server_uri()
            conn = ldap.initialize(server_uri)

            conn.set_option(ldap.OPT_PROTOCOL_VERSION, 3)
            conn.set_option(ldap.OPT_NETWORK_TIMEOUT, self.connect_timeout)

            if self.use_ssl:
                conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)

            if self.bind_dn and self.bind_password:
                conn.simple_bind_s(self.bind_dn, self.bind_password)
            else:
                conn.simple_bind_s()

            conn.unbind_s()
            return True

        except ImportError:
            logger.error("python-ldapがインストールされていません")
            return False
        except Exception as e:
            logger.error(f"AD接続テストエラー: {e}")
            return False


class MockADClient:
    """テスト・開発用のモックADクライアント.

    実際のADサーバーがない環境でのテストに使用します。
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """MockADClientを初期化する."""
        self.config = config or {}
        # テスト用のユーザーデータ
        self._mock_users: dict[str, dict[str, str]] = {
            "admin": {
                "password": "admin123",
                "email": "admin@example.com",
                "display_name": "管理者",
            },
            "testuser": {
                "password": "test123",
                "email": "testuser@example.com",
                "display_name": "テストユーザー",
            },
        }

    def add_mock_user(
        self, username: str, password: str, email: str, display_name: str,
    ) -> None:
        """モックユーザーを追加する.

        Args:
            username: ユーザー名
            password: パスワード
            email: メールアドレス
            display_name: 表示名

        """
        self._mock_users[username] = {
            "password": password,
            "email": email,
            "display_name": display_name,
        }

    def authenticate(self, username: str, password: str) -> ADUser | None:
        """モック認証を行う.

        Args:
            username: ユーザー名
            password: パスワード

        Returns:
            認証成功時: ADUserオブジェクト
            認証失敗時: None

        """
        user_data = self._mock_users.get(username)
        if not user_data:
            return None
        if user_data.get("password") != password:
            return None

        return ADUser(
            dn=f"CN={username},OU=Users,DC=example,DC=com",
            uid=username,
            email=user_data.get("email", f"{username}@example.com"),
            display_name=user_data.get("display_name", username),
        )

    def get_user_info(self, username: str) -> ADUser | None:
        """モックユーザー情報を取得する.

        Args:
            username: ユーザー名

        Returns:
            ユーザー情報が見つかった場合: ADUserオブジェクト
            見つからない場合: None

        """
        user_data = self._mock_users.get(username)
        if not user_data:
            return None

        return ADUser(
            dn=f"CN={username},OU=Users,DC=example,DC=com",
            uid=username,
            email=user_data.get("email", f"{username}@example.com"),
            display_name=user_data.get("display_name", username),
        )

    def test_connection(self) -> bool:
        """モック接続テスト.

        Returns:
            常にTrue

        """
        return True
