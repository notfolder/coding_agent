"""APIルーターパッケージ.

各種APIエンドポイントを定義するルーターを提供します。
"""

from api.routers.config import router as config_router

__all__ = ["config_router"]
