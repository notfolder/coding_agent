"""FastAPI依存関係注入.

APIエンドポイントで使用する依存関係を定義します。
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Annotated

from app.database import get_db
from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session


def get_database_session() -> Generator[Session, None, None]:
    """データベースセッションを取得する.

    FastAPIのDependencyとして使用します。

    Yields:
        SQLAlchemyセッション

    """
    yield from get_db()


def verify_api_key(
    request: Request,
    authorization: str | None = Header(None),
) -> str:
    """APIキー認証を検証する.

    Args:
        request: FastAPIリクエスト
        authorization: Authorizationヘッダーの値

    Returns:
        認証成功時のトークン

    Raises:
        HTTPException: 認証失敗の場合

    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="認証に失敗しました",
        )

    # Bearer トークンの検証
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="認証に失敗しました",
        )

    token = parts[1]

    # app.stateからAPIキーを取得して検証
    expected_api_key = getattr(request.app.state, "api_key", None)
    if not expected_api_key or token != expected_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="認証に失敗しました",
        )

    return token


# 型エイリアス
DBSession = Annotated[Session, Depends(get_database_session)]
APIKey = Annotated[str, Depends(verify_api_key)]
