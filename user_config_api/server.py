"""ユーザー設定API サーバー.

このモジュールは、config.yamlとデータベースからLLM設定を読み込み、
REST API経由で設定を提供するサーバーです。

ユーザー固有の設定がデータベースにある場合はそれを優先し、
ない場合はconfig.yamlのデフォルト設定を返します。
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from api.routers.config import router as config_router
from app.config import get_api_key, load_config
from app.database import init_db
from fastapi import FastAPI

# ロガーの設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """アプリケーションのライフサイクル管理.

    起動時に設定を読み込み、データベースを初期化します。
    """
    # 起動時の処理
    config = load_config()
    api_key = get_api_key(config)

    # データベースを初期化
    init_db()

    # app.stateに設定を保存（スレッドセーフ）
    app.state.config = config
    app.state.api_key = api_key

    logger.info("APIサーバーを起動しました")

    yield

    # シャットダウン時の処理（必要な場合）
    logger.info("APIサーバーをシャットダウンしました")


# FastAPIアプリケーションの初期化（lifespanを使用）
app = FastAPI(
    title="User Config API",
    description="ユーザー設定API - データベース連携版",
    version="2.0.0",
    lifespan=lifespan,
)

# ルーターを追加
app.include_router(config_router)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """ヘルスチェックエンドポイント（認証不要）.

    Returns:
        ステータス情報

    """
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
