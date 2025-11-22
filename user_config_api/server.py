"""ユーザー設定API モックアップサーバー.

このモジュールは、config.yamlからLLM設定を読み込み、
REST API経由で設定を提供するモックアップサーバーです。
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import JSONResponse

# ロガーの設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPIアプリケーションの初期化
app = FastAPI(
    title="User Config API",
    description="ユーザー設定API（モックアップ版）",
    version="1.0.0",
)

# グローバル変数として設定を保持
CONFIG: dict[str, Any] = {}
API_KEY: str = ""


def load_config() -> dict[str, Any]:
    """config.yamlを読み込む."""
    config_path = Path("/app/config.yaml")
    if not config_path.exists():
        # Dockerコンテナ外での実行時のフォールバック
        config_path = Path("config.yaml")
    
    try:
        with config_path.open() as f:
            config = yaml.safe_load(f)
        logger.info(f"設定ファイルを読み込みました: {config_path}")
        return config
    except Exception as e:
        logger.error(f"設定ファイルの読み込みに失敗: {e}")
        return {}


def get_api_key() -> str:
    """APIキーを取得する（環境変数 > config.yaml）."""
    # 環境変数から取得
    env_api_key = os.environ.get("API_SERVER_KEY")
    if env_api_key:
        return env_api_key
    
    # config.yamlから取得
    config = load_config()
    config_api_key = config.get("api_server", {}).get("api_key", "")
    if config_api_key:
        return config_api_key
    
    # デフォルト値
    logger.warning("APIキーが設定されていません。デフォルト値を使用します。")
    return "default-api-key"


def verify_token(authorization: str | None = Header(None)) -> bool:
    """Bearer トークン認証を検証する.
    
    Args:
        authorization: Authorizationヘッダーの値
    
    Returns:
        認証成功の場合True
    
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
    if token != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="認証に失敗しました",
        )
    
    return True


@app.on_event("startup")
async def startup_event() -> None:
    """アプリケーション起動時の処理."""
    global CONFIG, API_KEY
    CONFIG = load_config()
    API_KEY = get_api_key()
    logger.info("APIサーバーを起動しました")


@app.get("/health")
async def health_check() -> dict[str, str]:
    """ヘルスチェックエンドポイント（認証不要）.
    
    Returns:
        ステータス情報
    """
    return {"status": "ok"}


@app.get("/config/{platform}/{username}")
async def get_config(
    platform: str,
    username: str,
    authorized: bool = Depends(verify_token),
) -> JSONResponse:
    """ユーザー設定を取得する.
    
    Args:
        platform: "github" または "gitlab"
        username: ユーザー名（現在は無視される）
        authorized: 認証済みフラグ（Dependencyで検証）
    
    Returns:
        LLM設定を含むJSONレスポンス
    """
    if not CONFIG:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "status": "error",
                "message": "設定ファイルの読み込みに失敗しました",
            },
        )
    
    # レスポンスデータの構築
    response_data = {
        "status": "success",
        "data": {
            "llm": CONFIG.get("llm", {}),
            "system_prompt": _get_system_prompt(CONFIG),
            "max_llm_process_num": CONFIG.get("max_llm_process_num", 1000),
        },
    }
    
    logger.info(f"設定を取得: platform={platform}, username={username}")
    return JSONResponse(content=response_data)


def _get_system_prompt(config: dict[str, Any]) -> str:
    """システムプロンプトを取得する.
    
    Args:
        config: 設定辞書
    
    Returns:
        システムプロンプトの文字列
    """
    # config.yamlから直接取得
    if "system_prompt" in config:
        return config["system_prompt"]
    
    # system_prompt.txtから読み込み
    prompt_path = Path("/app/system_prompt.txt")
    if not prompt_path.exists():
        prompt_path = Path("system_prompt.txt")
    
    try:
        if prompt_path.exists():
            with prompt_path.open() as f:
                return f.read().strip()
    except Exception as e:
        logger.warning(f"システムプロンプトの読み込みに失敗: {e}")
    
    return "あなたは優秀なコーディングアシスタントです。"


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
