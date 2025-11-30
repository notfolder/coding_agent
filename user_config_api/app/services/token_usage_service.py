"""トークン使用量サービス.

ユーザー毎のトークン使用量を集計・取得するサービスを提供します。
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterator, List

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, create_engine, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

_METADATA = MetaData()
tasks_table = Table(
    "tasks",
    _METADATA,
    Column("uuid", String(36), primary_key=True),
    Column("user", String(255)),
    Column("total_tokens", Integer),
    Column("created_at", DateTime(timezone=True)),
)


class TokenUsageService:
    """トークン使用量サービス.

    PostgreSQLなどのSQLデータベース上に保存されたtasksテーブルを参照します。
    """

    MAX_USERS_LIMIT = 20

    def __init__(
        self,
        tasks_db_path: str | Path | None = None,
        *,
        database_url: str | None = None,
        engine: Engine | None = None,
    ) -> None:
        """TokenUsageServiceを初期化する."""

        self._tasks_db_path = Path(tasks_db_path) if tasks_db_path else None
        self._database_url = self._resolve_database_url(database_url)
        self._engine = engine or self._create_engine()
        self._session_factory = sessionmaker(bind=self._engine, autoflush=False, expire_on_commit=False)

    @contextmanager
    def _get_session(self) -> Iterator[Session]:
        """SQLAlchemyセッションを取得する."""

        session = self._session_factory()
        try:
            yield session
        except SQLAlchemyError:
            session.rollback()
            raise
        finally:
            session.close()

    def _get_now(self) -> datetime:
        """現在時刻をUTC基準で取得する."""

        return datetime.now(tz=UTC).astimezone()

    def get_user_token_usage(self, username: str) -> Dict[str, Any]:
        """指定ユーザーの期間別トークン使用量を取得する."""

        try:
            with self._get_session() as session:
                now = self._get_now()
                # 日時の基準ポイントを算出
                today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                week_start = today_start - timedelta(days=today_start.weekday())
                month_start = today_start.replace(day=1)

                today_tokens = self._get_tokens_since(session, username, today_start)
                week_tokens = self._get_tokens_since(session, username, week_start)
                month_tokens = self._get_tokens_since(session, username, month_start)

                total_stmt = select(func.coalesce(func.sum(tasks_table.c.total_tokens), 0)).where(
                    tasks_table.c.user == username
                )
                total_tokens = session.execute(total_stmt).scalar() or 0

                return {
                    "username": username,
                    "today": today_tokens,
                    "this_week": week_tokens,
                    "this_month": month_tokens,
                    "total": max(0, int(total_tokens)),
                    "last_updated": now.isoformat(),
                }

        except SQLAlchemyError:
            logger.exception("Database error while getting token usage")
        except Exception:
            logger.exception("Unexpected error while getting token usage")

        return {
            "username": username,
            "today": 0,
            "this_week": 0,
            "this_month": 0,
            "total": 0,
            "last_updated": self._get_now().isoformat(),
        }

    def get_user_daily_history(self, username: str, days: int = 30) -> Dict[str, Any]:
        """指定ユーザーの日別トークン履歴を取得する."""

        days = max(1, min(365, days))

        try:
            with self._get_session() as session:
                now = self._get_now()
                # 表示期間の開始・終了日を決定
                end_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
                start_date = end_date - timedelta(days=days - 1)

                stmt = (
                    select(
                        func.date(tasks_table.c.created_at).label("date"),
                        func.coalesce(func.sum(tasks_table.c.total_tokens), 0).label("tokens"),
                    )
                    .where(
                        tasks_table.c.user == username,
                        tasks_table.c.created_at.is_not(None),
                        tasks_table.c.created_at >= start_date,
                    )
                    .group_by(func.date(tasks_table.c.created_at))
                    .order_by(func.date(tasks_table.c.created_at))
                )

                rows = session.execute(stmt).all()
                db_results = {
                    (
                        mapping["date"].strftime("%Y-%m-%d")
                        if hasattr(mapping["date"], "strftime")
                        else str(mapping["date"])
                    ): max(0, int(mapping["tokens"] or 0))
                    for mapping in (row._mapping for row in rows)
                }

                history: List[Dict[str, Any]] = []
                current_date = start_date
                while current_date <= end_date:
                    date_str = current_date.strftime("%Y-%m-%d")
                    tokens = db_results.get(date_str, 0)
                    history.append({"date": date_str, "tokens": tokens})
                    current_date += timedelta(days=1)

                return {
                    "username": username,
                    "history": history,
                    "period_start": start_date.strftime("%Y-%m-%d"),
                    "period_end": end_date.strftime("%Y-%m-%d"),
                    "last_updated": now.isoformat(),
                }

        except SQLAlchemyError:
            logger.exception("Database error while getting daily history")
        except Exception:
            logger.exception("Unexpected error while getting daily history")

        return self._empty_history(username, days)

    def get_all_users_token_usage(self) -> List[Dict[str, Any]]:
        """全ユーザーのトークン使用量を取得する (上位20件)."""

        try:
            with self._get_session() as session:
                now = self._get_now()
                # 期間別に集計するための基準日時を準備
                today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                week_start = today_start - timedelta(days=today_start.weekday())
                month_start = today_start.replace(day=1)

                month_stmt = (
                    select(
                        tasks_table.c.user.label("user"),
                        func.coalesce(func.sum(tasks_table.c.total_tokens), 0).label("this_month"),
                    )
                    .where(
                        tasks_table.c.user.is_not(None),
                        tasks_table.c.created_at.is_not(None),
                        tasks_table.c.created_at >= month_start,
                    )
                    .group_by(tasks_table.c.user)
                )
                month_results = {
                    mapping["user"]: max(0, int(mapping["this_month"] or 0))
                    for mapping in (row._mapping for row in session.execute(month_stmt).all())
                    if mapping["user"]
                }

                if not month_results:
                    return []

                total_stmt = (
                    select(
                        tasks_table.c.user.label("user"),
                        func.coalesce(func.sum(tasks_table.c.total_tokens), 0).label("total"),
                    )
                    .where(tasks_table.c.user.is_not(None))
                    .group_by(tasks_table.c.user)
                )
                total_results = {
                    mapping["user"]: max(0, int(mapping["total"] or 0))
                    for mapping in (row._mapping for row in session.execute(total_stmt).all())
                    if mapping["user"]
                }

                users_sorted = sorted(
                    month_results.items(),
                    key=lambda item: item[1],
                    reverse=True,
                )[: self.MAX_USERS_LIMIT]

                results: List[Dict[str, Any]] = []
                for user, month_tokens in users_sorted:
                    today_tokens = self._get_tokens_since(session, user, today_start)
                    week_tokens = self._get_tokens_since(session, user, week_start)
                    total_tokens = total_results.get(user, 0)

                    results.append(
                        {
                            "username": user,
                            "today": today_tokens,
                            "this_week": week_tokens,
                            "this_month": month_tokens,
                            "total": total_tokens,
                        }
                    )

                return results

        except SQLAlchemyError:
            logger.exception("Database error while getting all users token usage")
        except Exception:
            logger.exception("Unexpected error while getting all users token usage")

        return []

    def _get_tokens_since(self, session: Session, username: str, since: datetime) -> int:
        """指定日時以降のトークン数を取得する."""

        if not username:
            return 0

        stmt = (
            select(func.coalesce(func.sum(tasks_table.c.total_tokens), 0))
            .where(
                tasks_table.c.user == username,
                tasks_table.c.total_tokens.is_not(None),
                tasks_table.c.total_tokens > 0,
                tasks_table.c.created_at.is_not(None),
                tasks_table.c.created_at >= since,
            )
        )
        total = session.execute(stmt).scalar()
        if total is None:
            return 0
        return max(0, int(total))

    def _empty_history(self, username: str, days: int) -> Dict[str, Any]:
        """空の履歴を作成する."""

        now = self._get_now()
        end_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_date = end_date - timedelta(days=days - 1)

        history: List[Dict[str, Any]] = []
        current_date = start_date
        while current_date <= end_date:
            history.append({"date": current_date.strftime("%Y-%m-%d"), "tokens": 0})
            current_date += timedelta(days=1)

        return {
            "username": username,
            "history": history,
            "period_start": start_date.strftime("%Y-%m-%d"),
            "period_end": end_date.strftime("%Y-%m-%d"),
            "last_updated": now.isoformat(),
        }

    def _resolve_database_url(self, override_url: str | None) -> str:
        """接続先データベースURLを決定する."""

        if override_url:
            return override_url

        # 環境変数で直接URLが渡されている場合は最優先で利用
        env_url = os.environ.get("TASK_DB_URL") or os.environ.get("TASKS_DATABASE_URL")
        if env_url:
            return env_url

        # 個別の接続情報（ホスト等）が与えられている場合はURLを組み立てる
        host = os.environ.get("TASK_DB_HOST")
        if host:
            port = os.environ.get("TASK_DB_PORT", "5432")
            name = os.environ.get("TASK_DB_NAME", "coding_agent")
            user = os.environ.get("TASK_DB_USER", "")
            password = os.environ.get("TASK_DB_PASSWORD", "")

            auth = ""
            if user and password:
                auth = f"{user}:{password}@"
            elif user:
                auth = f"{user}@"
            elif password:
                auth = f":{password}@"

            return f"postgresql://{auth}{host}:{port}/{name}"

        # 引数でパスが指定されている場合はSQLite接続として扱う
        if self._tasks_db_path:
            return f"sqlite:///{self._tasks_db_path}"

        default_sqlite = Path("./contexts/tasks.db")
        return f"sqlite:///{default_sqlite}"

    def _create_engine(self) -> Engine:
        """SQLAlchemy Engineを生成する."""

        connect_args: Dict[str, Any] = {}
        if self._database_url.startswith("sqlite"):
            # SQLiteはスレッド毎に接続を共有できないため、この引数で緩和する
            connect_args = {"check_same_thread": False}

        try:
            return create_engine(
                self._database_url,
                pool_pre_ping=True,
                future=True,
                connect_args=connect_args,
            )
        except SQLAlchemyError:
            logger.exception("Failed to initialize SQLAlchemy engine; falling back to in-memory database")
            return create_engine("sqlite:///:memory:", future=True)
