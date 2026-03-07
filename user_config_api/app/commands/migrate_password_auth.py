"""パスワード認証機能マイグレーションスクリプト.

既存のusersテーブルにパスワード認証用カラムを追加します。

新規インストールでは init_db() が全カラムを自動作成するため、
このスクリプトは既存環境のアップグレード時にのみ使用してください。

使用方法:
    cd user_config_api
    python app/commands/migrate_password_auth.py

    # データベースURLを指定する場合:
    DATABASE_URL=sqlite:///./data/users.db python app/commands/migrate_password_auth.py

    # PostgreSQLの場合:
    DATABASE_URL=postgresql://user:pass@localhost/dbname python app/commands/migrate_password_auth.py

    # 確認のみ（ドライラン）:
    python app/commands/migrate_password_auth.py --dry-run
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# 親ディレクトリをPythonパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import inspect as sa_inspect, text

from app.database import create_db_engine, get_database_url

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# 追加するカラムの定義（カラム名: DDL文）
_MIGRATION_COLUMNS: dict[str, str] = {
    "auth_type": "auth_type VARCHAR(20) NOT NULL DEFAULT 'ldap'",
    "password_hash": "password_hash VARCHAR(255) NULL",
    "password_must_change": "password_must_change BOOLEAN NOT NULL DEFAULT FALSE",
    "password_updated_at": "password_updated_at DATETIME NULL",
}

# PostgreSQLではBOOLEAN, SQLiteではINTEGERを使用
_SQLITE_MIGRATION_COLUMNS: dict[str, str] = {
    "auth_type": "auth_type VARCHAR(20) NOT NULL DEFAULT 'ldap'",
    "password_hash": "password_hash VARCHAR(255) NULL",
    "password_must_change": "password_must_change INTEGER NOT NULL DEFAULT 0",
    "password_updated_at": "password_updated_at DATETIME NULL",
}


def get_existing_columns(engine: object, table_name: str) -> list[str]:
    """既存のテーブルカラム一覧を取得する.

    Args:
        engine: SQLAlchemyエンジン
        table_name: テーブル名

    Returns:
        カラム名のリスト

    """
    inspector = sa_inspect(engine)
    columns = inspector.get_columns(table_name)
    return [col["name"] for col in columns]


def run_migration(database_url: str, *, dry_run: bool = False) -> bool:
    """マイグレーションを実行する.

    usersテーブルにパスワード認証用のカラムを追加します。
    既に存在するカラムはスキップします。

    Args:
        database_url: データベース接続URL
        dry_run: Trueの場合、実際の変更は行わず確認のみ

    Returns:
        成功の場合True

    """
    logger.info(f"マイグレーション開始: {database_url}")
    if dry_run:
        logger.info("ドライランモード: 実際の変更は行いません")

    engine = create_db_engine(database_url)
    is_sqlite = database_url.startswith("sqlite")

    try:
        # 既存カラムを確認
        existing_columns = get_existing_columns(engine, "users")
        logger.info(f"既存カラム: {existing_columns}")

        # 追加するカラムを選択（DBの種類に応じてDDL文を切り替え）
        columns_to_add = _SQLITE_MIGRATION_COLUMNS if is_sqlite else _MIGRATION_COLUMNS

        # 不足しているカラムだけ追加
        missing_columns = {
            col: ddl
            for col, ddl in columns_to_add.items()
            if col not in existing_columns
        }

        if not missing_columns:
            logger.info("全てのカラムが既に存在しています。マイグレーションは不要です。")
            return True

        logger.info(f"追加するカラム: {list(missing_columns.keys())}")

        if dry_run:
            for col, ddl in missing_columns.items():
                logger.info(f"  [ドライラン] ALTER TABLE users ADD COLUMN {ddl}")
            return True

        # カラムを追加
        with engine.connect() as conn:
            for col, ddl in missing_columns.items():
                sql = f"ALTER TABLE users ADD COLUMN {ddl}"
                logger.info(f"実行: {sql}")
                conn.execute(text(sql))
            conn.commit()

        logger.info("マイグレーションが完了しました。")
        return True

    except Exception as e:
        logger.error(f"マイグレーションに失敗しました: {e}")
        return False
    finally:
        engine.dispose()


def main() -> None:
    """メインエントリポイント."""
    parser = argparse.ArgumentParser(
        description="usersテーブルにパスワード認証用カラムを追加します",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="データベースURL（省略時は環境変数DATABASE_URLまたはデフォルト値を使用）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="実際の変更は行わず、実行内容を確認するだけ",
    )
    args = parser.parse_args()

    database_url = args.database_url or get_database_url()
    success = run_migration(database_url, dry_run=args.dry_run)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
