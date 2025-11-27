"""UserConfigモデル定義.

ユーザーごとのLLM設定を管理するテーブル。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class UserConfig(Base):
    """ユーザー設定を管理するモデル.

    Attributes:
        id: 設定ID（主キー）
        user_id: ユーザーID（外部キー、ユニーク）
        llm_api_key: LLM APIキー（暗号化保存、オプション）
        llm_model: LLMモデル名（オプション）
        additional_system_prompt: 追加のシステムプロンプト（オプション）
        created_at: 作成日時
        updated_at: 更新日時
        user: ユーザー（多対1リレーション）

    """

    __tablename__ = "user_configs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False,
    )
    llm_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    additional_system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False,
    )

    # Userとのリレーション
    user: Mapped[User] = relationship("User", back_populates="config")

    # インデックス定義
    __table_args__ = (Index("idx_user_configs_user_id", "user_id"),)

    def __repr__(self) -> str:
        """ユーザー設定の文字列表現を返す."""
        return f"<UserConfig(id={self.id}, user_id={self.user_id}, llm_model='{self.llm_model}')>"
