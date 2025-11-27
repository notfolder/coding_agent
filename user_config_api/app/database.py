"""データベース設定とセッション管理.

SQLAlchemyを使用したデータベース接続・セッション管理を提供します。
"""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models.base import Base


def get_database_url() -> str:
    """データベースURLを取得する.

    環境変数DATABASE_URLから取得するか、デフォルト値を使用します。

    Returns:
        データベースURL文字列

    """
    default_url = "sqlite:///./data/users.db"
    return os.environ.get("DATABASE_URL", default_url)


def create_db_engine(database_url: str | None = None, echo: bool = False) -> Any:
    """SQLAlchemyエンジンを作成する.

    Args:
        database_url: データベースURL（Noneの場合は環境変数から取得）
        echo: SQLログ出力フラグ

    Returns:
        SQLAlchemyエンジン

    """
    if database_url is None:
        database_url = get_database_url()

    # SQLiteの場合、データディレクトリを作成
    if database_url.startswith("sqlite:///"):
        db_path = database_url.replace("sqlite:///", "")
        db_path = db_path.removeprefix("./")
        db_dir = Path(db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

    # SQLite用の追加設定
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    return create_engine(database_url, echo=echo, connect_args=connect_args)


# グローバルエンジンとセッションファクトリ
_engine = None
_SessionLocal = None


def get_engine() -> Any:
    """グローバルエンジンを取得する.

    Returns:
        SQLAlchemyエンジン

    """
    global _engine
    if _engine is None:
        _engine = create_db_engine()
    return _engine


def get_session_factory() -> sessionmaker:
    """セッションファクトリを取得する.

    Returns:
        SQLAlchemyセッションファクトリ

    """
    global _SessionLocal
    if _SessionLocal is None:
        engine = get_engine()
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    """データベースセッションを取得するジェネレータ.

    FastAPIのDependencyとして使用します。

    Yields:
        SQLAlchemyセッション

    """
    session_factory = get_session_factory()
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """データベースセッションのコンテキストマネージャ.

    Streamlit等でDependency以外の方法でセッションを取得する際に使用します。

    Yields:
        SQLAlchemyセッション

    """
    session_factory = get_session_factory()
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """データベースを初期化する.

    全てのテーブルを作成します。
    """
    engine = get_engine()
    Base.metadata.create_all(bind=engine)


def reset_db() -> None:
    """データベースをリセットする.

    全てのテーブルを削除して再作成します（開発・テスト用）。
    """
    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def reset_engine() -> None:
    """グローバルエンジンをリセットする（テスト用）."""
    global _engine, _SessionLocal
    _engine = None
    _SessionLocal = None
