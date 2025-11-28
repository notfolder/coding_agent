"""トークン使用量APIルーター.

ユーザー毎のトークン使用量を取得するAPIエンドポイントを提供します。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated, Any

from app.services.token_usage_service import TokenUsageService
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from api.dependencies import APIKey

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/token-usage", tags=["token-usage"])


def get_token_usage_service() -> TokenUsageService:
    """TokenUsageServiceのインスタンスを取得する.

    Returns:
        TokenUsageServiceインスタンス

    """
    return TokenUsageService()


@router.get("/summary")
async def get_all_users_token_usage(
    _token: APIKey,
) -> JSONResponse:
    """全ユーザーのトークン使用量サマリーを取得する (管理者用).

    トークン使用量が多い順でソートして上位20人を返却します。

    Returns:
        全ユーザーのトークン使用量リスト

    """
    service = get_token_usage_service()
    usage_list = service.get_all_users_token_usage()

    response_data: dict[str, Any] = {
        "status": "success",
        "data": {
            "users": usage_list,
            "total_count": len(usage_list),
            "last_updated": datetime.now(tz=timezone.utc).isoformat(),
        },
    }

    logger.info("全ユーザートークン使用量を取得しました")
    return JSONResponse(content=response_data)


@router.get("/{username}")
async def get_user_token_usage(
    username: str,
    _token: APIKey,
) -> JSONResponse:
    """指定ユーザーのトークン使用量を取得する.

    Args:
        username: ユーザー名
        _token: 認証トークン (Dependencyで検証済み)

    Returns:
        ユーザーの期間別トークン使用量

    """
    service = get_token_usage_service()
    usage = service.get_user_token_usage(username)

    response_data: dict[str, Any] = {
        "status": "success",
        "data": usage,
    }

    logger.info("トークン使用量を取得しました: username=%s", username)
    return JSONResponse(content=response_data)


@router.get("/{username}/history")
async def get_user_token_usage_history(
    username: str,
    _token: APIKey,
    days: Annotated[int, Query(ge=1, le=365, description="取得日数 (1-365)")] = 30,
) -> JSONResponse:
    """指定ユーザーの日別トークン使用履歴を取得する.

    Args:
        username: ユーザー名
        _token: 認証トークン (Dependencyで検証済み)
        days: 取得日数 (デフォルト30日、1-365の範囲)

    Returns:
        日別トークン使用量のリスト

    """
    service = get_token_usage_service()
    history = service.get_user_daily_history(username, days)

    response_data: dict[str, Any] = {
        "status": "success",
        "data": history,
    }

    logger.info("トークン使用履歴を取得しました: username=%s, days=%d", username, days)
    return JSONResponse(content=response_data)
