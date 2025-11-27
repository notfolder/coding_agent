"""Userモデル定義.

ユーザーの基本情報を管理するテーブル。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user_config import UserConfig


class User(Base):
    """ユーザー情報を管理するモデル.

    Attributes:
        id: ユーザーID（主キー）
        username: GitHub/GitLabユーザー名（ユニーク、必須）
        ldap_uid: Active DirectoryのUID（ユニーク、オプション）
        ldap_email: Active Directoryのメールアドレス（ユニーク、オプション）
        display_name: 表示名（オプション）
        is_admin: 管理者フラグ（デフォルト: False）
        is_active: 有効フラグ（デフォルト: True）
        created_at: 作成日時
        updated_at: 更新日時
        config: ユーザー設定（1対1リレーション）

    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    ldap_uid: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    ldap_email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False,
    )

    # UserConfigとの1対1リレーション
    config: Mapped[UserConfig | None] = relationship(
        "UserConfig", back_populates="user", uselist=False, cascade="all, delete-orphan",
    )

    # インデックス定義
    __table_args__ = (
        Index("idx_users_username", "username"),
        Index("idx_users_ldap_uid", "ldap_uid"),
        Index("idx_users_ldap_email", "ldap_email"),
    )

    def __repr__(self) -> str:
        """ユーザーの文字列表現を返す."""
        return f"<User(id={self.id}, username='{self.username}', is_admin={self.is_admin})>"
