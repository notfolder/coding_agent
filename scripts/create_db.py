#!/usr/bin/env python
"""データベース作成ツール.

PostgreSQLにtasksテーブルとインデックスを作成します。

使用方法:
    python scripts/create_db.py

環境変数:
    DATABASE_URL: 完全な接続URL（他設定を上書き）
    DATABASE_HOST: PostgreSQLホスト（デフォルト: localhost）
    DATABASE_PORT: PostgreSQLポート（デフォルト: 5432）
    DATABASE_NAME: データベース名（デフォルト: coding_agent）
    DATABASE_USER: ユーザー名
    DATABASE_PASSWORD: パスワード
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import yaml

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from db.task_db import TaskDBManager  # noqa: E402

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def load_config(config_path: Path | None = None) -> dict:
    """設定ファイルを読み込む.

    Args:
        config_path: 設定ファイルのパス（Noneの場合はデフォルト）

    Returns:
        dict: 設定辞書

    """
    if config_path is None:
        config_path = project_root / "config.yaml"

    if config_path.exists():
        with config_path.open() as f:
            return yaml.safe_load(f)

    logger.warning("設定ファイルが見つかりません: %s", config_path)
    return {}


def main() -> int:
    """メイン関数.

    Returns:
        int: 終了コード（0: 成功、1: 失敗）

    """
    parser = argparse.ArgumentParser(
        description="PostgreSQLにtasksテーブルとインデックスを作成します",
    )
    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        help="設定ファイルのパス（デフォルト: config.yaml）",
    )
    args = parser.parse_args()

    try:
        # 設定を読み込み
        config = load_config(args.config)
        logger.info("設定を読み込みました")

        # TaskDBManagerを初期化
        db_manager = TaskDBManager(config)

        # テーブルを作成
        db_manager.create_tables()

        logger.info("データベースの作成が完了しました")
        return 0

    except Exception as e:
        logger.exception("データベースの作成に失敗しました: %s", e)
        return 1

    finally:
        # クリーンアップ
        if "db_manager" in locals():
            db_manager.close()


if __name__ == "__main__":
    sys.exit(main())
