"""コンフィグAPIルーター.

ユーザー設定を取得するAPIエンドポイントを提供します。
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import get_llm_config, get_system_prompt, load_config
from app.services.user_service import UserService
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from api.dependencies import APIKey, DBSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/{platform}/{username}")
async def get_user_config(
    platform: str,
    username: str,
    request: Request,
    db: DBSession,
    _token: APIKey,
) -> JSONResponse:
    """ユーザー設定を取得する.

    コーディングエージェントから呼び出され、ユーザーのLLM設定を返します。
    ユーザー固有の設定がある場合はそれを、ない場合はデフォルト設定を返します。

    Args:
        platform: "github" または "gitlab"
        username: GitHub/GitLabユーザー名
        request: FastAPIリクエスト
        db: データベースセッション
        _token: 認証トークン（Dependencyで検証済み）

    Returns:
        LLM設定を含むJSONレスポンス

    """
    # 設定を取得
    config = getattr(request.app.state, "config", None) or load_config()

    # デフォルトLLM設定
    llm_config = get_llm_config(config)
    system_prompt = get_system_prompt(config)
    max_llm_process_num = config.get("max_llm_process_num", 1000)

    # ユーザー固有の設定を取得
    user_service = UserService(db)
    user = user_service.get_user_by_username(username)

    if user and user.is_active:
        user_config = user_service.get_user_config(user.id)
        if user_config:
            # ユーザー設定でオーバーライド
            llm_config = _merge_user_config(llm_config, user_config, user_service, user.id)

            if user_config.additional_system_prompt:
                system_prompt = f"{system_prompt}\n\n{user_config.additional_system_prompt}"

    # レスポンスデータの構築
    response_data = {
        "status": "success",
        "data": {
            "llm": llm_config,
            "system_prompt": system_prompt,
            "max_llm_process_num": max_llm_process_num,
        },
    }

    logger.info(f"設定を取得: platform={platform}, username={username}")
    return JSONResponse(content=response_data)


def _merge_user_config(
    base_config: dict[str, Any],
    user_config: Any,
    user_service: UserService,
    user_id: int,
) -> dict[str, Any]:
    """ユーザー設定をベース設定にマージする.

    Args:
        base_config: ベースのLLM設定
        user_config: ユーザー設定オブジェクト
        user_service: ユーザーサービス
        user_id: ユーザーID

    Returns:
        マージされたLLM設定

    """
    result = base_config.copy()

    # モデル名のオーバーライド
    if user_config.llm_model:
        provider = result.get("provider", "openai")
        if provider in result:
            result[provider] = result[provider].copy()
            result[provider]["model"] = user_config.llm_model

    # APIキーのオーバーライド（復号化して設定）
    decrypted_api_key = user_service.get_decrypted_api_key(user_id)
    if decrypted_api_key:
        provider = result.get("provider", "openai")
        if provider in result:
            result[provider] = result[provider].copy()
            result[provider]["api_key"] = decrypted_api_key

    return result
