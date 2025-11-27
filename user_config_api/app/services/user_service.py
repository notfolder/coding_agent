"""ユーザーサービス.

ユーザー管理のビジネスロジックを提供します。
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.user_config import UserConfig
from app.utils.encryption import decrypt_value, encrypt_value

logger = logging.getLogger(__name__)


class UserService:
    """ユーザー管理サービス.

    ユーザーの作成・取得・更新・削除を行います。
    """

    def __init__(self, db: Session) -> None:
        """UserServiceを初期化する.

        Args:
            db: データベースセッション

        """
        self.db = db

    def get_user_by_id(self, user_id: int) -> User | None:
        """IDでユーザーを取得する.

        Args:
            user_id: ユーザーID

        Returns:
            ユーザーオブジェクト、または None

        """
        return self.db.get(User, user_id)

    def get_user_by_username(self, username: str) -> User | None:
        """ユーザー名でユーザーを取得する.

        Args:
            username: GitHub/GitLabユーザー名

        Returns:
            ユーザーオブジェクト、または None

        """
        stmt = select(User).where(User.username == username)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_user_by_ldap_uid(self, ldap_uid: str) -> User | None:
        """LDAP UIDでユーザーを取得する.

        Args:
            ldap_uid: Active DirectoryのUID

        Returns:
            ユーザーオブジェクト、または None

        """
        stmt = select(User).where(User.ldap_uid == ldap_uid)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_user_by_ldap_email(self, ldap_email: str) -> User | None:
        """LDAPメールアドレスでユーザーを取得する.

        Args:
            ldap_email: Active Directoryのメールアドレス

        Returns:
            ユーザーオブジェクト、または None

        """
        stmt = select(User).where(User.ldap_email == ldap_email)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_all_users(
        self,
        *,
        active_only: bool = False,
        search: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[User]:
        """全ユーザーを取得する.

        Args:
            active_only: アクティブなユーザーのみ取得する場合True
            search: 検索文字列（ユーザー名・表示名に部分一致）
            limit: 取得件数の上限
            offset: オフセット

        Returns:
            ユーザーのリスト

        """
        stmt = select(User)

        if active_only:
            stmt = stmt.where(User.is_active == True)  # noqa: E712

        if search:
            search_pattern = f"%{search}%"
            stmt = stmt.where(
                (User.username.ilike(search_pattern))
                | (User.display_name.ilike(search_pattern)),
            )

        stmt = stmt.order_by(User.username).limit(limit).offset(offset)
        return list(self.db.execute(stmt).scalars().all())

    def count_users(self, *, active_only: bool = False) -> int:
        """ユーザー数をカウントする.

        Args:
            active_only: アクティブなユーザーのみカウントする場合True

        Returns:
            ユーザー数

        """
        from sqlalchemy import func

        stmt = select(func.count(User.id))
        if active_only:
            stmt = stmt.where(User.is_active == True)  # noqa: E712
        result = self.db.execute(stmt).scalar_one()
        return int(result)

    def count_users_with_config(self) -> int:
        """設定済みユーザー数をカウントする.

        Returns:
            設定済みユーザー数

        """
        from sqlalchemy import func

        stmt = (
            select(func.count(User.id))
            .join(UserConfig, User.id == UserConfig.user_id)
            .where(User.is_active == True)  # noqa: E712
        )
        result = self.db.execute(stmt).scalar_one()
        return int(result)

    def create_user(
        self,
        username: str,
        *,
        ldap_uid: str | None = None,
        ldap_email: str | None = None,
        display_name: str | None = None,
        is_admin: bool = False,
        is_active: bool = True,
    ) -> User:
        """新規ユーザーを作成する.

        Args:
            username: GitHub/GitLabユーザー名
            ldap_uid: Active DirectoryのUID
            ldap_email: Active Directoryのメールアドレス
            display_name: 表示名
            is_admin: 管理者フラグ
            is_active: 有効フラグ

        Returns:
            作成されたユーザーオブジェクト

        Raises:
            ValueError: ユーザー名が既に存在する場合

        """
        # 重複チェック
        existing = self.get_user_by_username(username)
        if existing:
            raise ValueError(f"ユーザー名 '{username}' は既に使用されています")

        user = User(
            username=username,
            ldap_uid=ldap_uid,
            ldap_email=ldap_email,
            display_name=display_name,
            is_admin=is_admin,
            is_active=is_active,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)

        logger.info(f"ユーザーを作成しました: {username}")
        return user

    def update_user(
        self,
        user_id: int,
        *,
        username: str | None = None,
        ldap_uid: str | None = None,
        ldap_email: str | None = None,
        display_name: str | None = None,
        is_admin: bool | None = None,
        is_active: bool | None = None,
    ) -> User | None:
        """ユーザーを更新する.

        Args:
            user_id: ユーザーID
            username: 新しいユーザー名
            ldap_uid: 新しいLDAP UID
            ldap_email: 新しいLDAPメールアドレス
            display_name: 新しい表示名
            is_admin: 新しい管理者フラグ
            is_active: 新しい有効フラグ

        Returns:
            更新されたユーザーオブジェクト、または None

        Raises:
            ValueError: ユーザー名が既に存在する場合

        """
        user = self.get_user_by_id(user_id)
        if not user:
            return None

        # ユーザー名の重複チェック
        if username and username != user.username:
            existing = self.get_user_by_username(username)
            if existing:
                raise ValueError(f"ユーザー名 '{username}' は既に使用されています")
            user.username = username

        if ldap_uid is not None:
            user.ldap_uid = ldap_uid
        if ldap_email is not None:
            user.ldap_email = ldap_email
        if display_name is not None:
            user.display_name = display_name
        if is_admin is not None:
            user.is_admin = is_admin
        if is_active is not None:
            user.is_active = is_active

        self.db.commit()
        self.db.refresh(user)

        logger.info(f"ユーザーを更新しました: {user.username}")
        return user

    def delete_user(self, user_id: int, *, soft_delete: bool = True) -> bool:
        """ユーザーを削除する.

        Args:
            user_id: ユーザーID
            soft_delete: 論理削除の場合True（is_active=Falseにする）

        Returns:
            削除成功の場合True

        """
        user = self.get_user_by_id(user_id)
        if not user:
            return False

        if soft_delete:
            user.is_active = False
            self.db.commit()
            logger.info(f"ユーザーを無効化しました: {user.username}")
        else:
            self.db.delete(user)
            self.db.commit()
            logger.info(f"ユーザーを削除しました: {user.username}")

        return True

    def get_or_create_user(
        self,
        username: str,
        *,
        ldap_uid: str | None = None,
        ldap_email: str | None = None,
        display_name: str | None = None,
    ) -> tuple[User, bool]:
        """ユーザーを取得または作成する.

        Args:
            username: GitHub/GitLabユーザー名
            ldap_uid: Active DirectoryのUID
            ldap_email: Active Directoryのメールアドレス
            display_name: 表示名

        Returns:
            (ユーザーオブジェクト, 新規作成の場合True)

        """
        # まずLDAP UIDで検索
        if ldap_uid:
            user = self.get_user_by_ldap_uid(ldap_uid)
            if user:
                return user, False

        # 次にLDAPメールで検索
        if ldap_email:
            user = self.get_user_by_ldap_email(ldap_email)
            if user:
                return user, False

        # ユーザー名で検索
        user = self.get_user_by_username(username)
        if user:
            return user, False

        # 新規作成
        user = self.create_user(
            username,
            ldap_uid=ldap_uid,
            ldap_email=ldap_email,
            display_name=display_name,
        )
        return user, True

    def get_user_config(self, user_id: int) -> UserConfig | None:
        """ユーザー設定を取得する.

        Args:
            user_id: ユーザーID

        Returns:
            ユーザー設定オブジェクト、または None

        """
        stmt = select(UserConfig).where(UserConfig.user_id == user_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def update_user_config(
        self,
        user_id: int,
        *,
        llm_api_key: str | None = None,
        llm_model: str | None = None,
        additional_system_prompt: str | None = None,
    ) -> UserConfig | None:
        """ユーザー設定を更新する.

        Args:
            user_id: ユーザーID
            llm_api_key: LLM APIキー（暗号化して保存）
            llm_model: LLMモデル名
            additional_system_prompt: 追加のシステムプロンプト

        Returns:
            更新されたユーザー設定オブジェクト、または None

        """
        user = self.get_user_by_id(user_id)
        if not user:
            return None

        config = self.get_user_config(user_id)

        if not config:
            # 新規作成
            config = UserConfig(user_id=user_id)
            self.db.add(config)

        if llm_api_key is not None:
            # APIキーを暗号化して保存
            config.llm_api_key = encrypt_value(llm_api_key) if llm_api_key else None
        if llm_model is not None:
            config.llm_model = llm_model
        if additional_system_prompt is not None:
            config.additional_system_prompt = additional_system_prompt

        self.db.commit()
        self.db.refresh(config)

        logger.info(f"ユーザー設定を更新しました: user_id={user_id}")
        return config

    def get_decrypted_api_key(self, user_id: int) -> str | None:
        """復号化されたAPIキーを取得する.

        Args:
            user_id: ユーザーID

        Returns:
            復号化されたAPIキー、または None

        """
        config = self.get_user_config(user_id)
        if not config or not config.llm_api_key:
            return None

        try:
            return decrypt_value(config.llm_api_key)
        except ValueError:
            logger.warning(f"APIキーの復号化に失敗しました: user_id={user_id}")
            return None

    def delete_user_config(self, user_id: int) -> bool:
        """ユーザー設定を削除する.

        Args:
            user_id: ユーザーID

        Returns:
            削除成功の場合True

        """
        config = self.get_user_config(user_id)
        if not config:
            return False

        self.db.delete(config)
        self.db.commit()

        logger.info(f"ユーザー設定を削除しました: user_id={user_id}")
        return True
