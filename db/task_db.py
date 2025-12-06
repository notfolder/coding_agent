"""タスクデータベース層.

このモジュールはDBTaskモデルとTaskDBManagerクラスを提供し、
タスク情報のPostgreSQLへの永続化を担当します。

主要コンポーネント:
- DBTask: SQLAlchemy ORMモデル（tasksテーブル定義）
- TaskDBManager: データベースアクセスロジック
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    DateTime,
    Index,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    sessionmaker,
)

if TYPE_CHECKING:
    from handlers.task_key import TaskKey

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """SQLAlchemy宣言的ベースクラス."""

    pass


class DBTask(Base):
    """タスク情報を格納するORMモデル.

    tasksテーブルに対応し、タスクの全情報を永続化します。
    """

    __tablename__ = "tasks"

    # プライマリキー
    uuid: Mapped[str] = mapped_column(String(36), primary_key=True)

    # TaskKey分解フィールド
    task_source: Mapped[str] = mapped_column(String(50), nullable=False)
    task_type: Mapped[str] = mapped_column(String(50), nullable=False)
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    repo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    number: Mapped[int] = mapped_column(Integer, nullable=False)

    # タスク状態
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # 実行環境情報
    process_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hostname: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # LLM設定
    llm_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    context_length: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 統計情報
    llm_call_count: Mapped[int] = mapped_column(Integer, default=0)
    tool_call_count: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    compression_count: Mapped[int] = mapped_column(Integer, default=0)

    # エラー情報
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ユーザー情報
    user: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # インデックス定義
    __table_args__ = (
        Index("ix_tasks_status", "status"),
        Index("ix_tasks_created_at", "created_at"),
        Index("ix_tasks_user", "user"),
        Index(
            "ix_tasks_task_key",
            "task_source",
            "task_type",
            "owner",
            "repo",
            "project_id",
            "number",
        ),
    )

    def get_task_key(self) -> TaskKey:
        """TaskKeyオブジェクトを復元する.

        task_keyの分解フィールドから適切なTaskKeyサブクラスのインスタンスを生成します。

        Returns:
            TaskKey: 復元されたTaskKeyオブジェクト

        Raises:
            ValueError: 不明なtask_source/task_typeの組み合わせの場合

        """
        # 遅延インポート（循環参照回避）
        from handlers.task_key import (
            GitHubIssueTaskKey,
            GitHubPullRequestTaskKey,
            GitLabIssueTaskKey,
            GitLabMergeRequestTaskKey,
        )

        if self.task_source == "github":
            if self.task_type == "issue":
                return GitHubIssueTaskKey(
                    owner=self.owner or "",
                    repo=self.repo or "",
                    number=self.number,
                )
            if self.task_type == "pull_request":
                return GitHubPullRequestTaskKey(
                    owner=self.owner or "",
                    repo=self.repo or "",
                    number=self.number,
                )
        elif self.task_source == "gitlab":
            if self.task_type == "issue":
                return GitLabIssueTaskKey(
                    project_id=self.project_id or 0,
                    issue_iid=self.number,
                )
            if self.task_type == "merge_request":
                return GitLabMergeRequestTaskKey(
                    project_id=self.project_id or 0,
                    mr_iid=self.number,
                )

        msg = f"不明なtask_source/task_typeの組み合わせ: {self.task_source}/{self.task_type}"
        raise ValueError(msg)


def _parse_task_key_dict(task_dict: dict[str, Any]) -> tuple[str, str, str | None, str | None, int | None, int]:
    """TaskKeyのto_dict()結果をデータベース形式に変換するヘルパー関数.

    Args:
        task_dict: TaskKey.to_dict()の結果

    Returns:
        tuple: (task_source, task_type, owner, repo, project_id, number)

    """
    # type: "github_issue" -> task_source: "github", task_type: "issue"
    task_type_full = task_dict.get("type", "unknown")
    if "_" in task_type_full:
        parts = task_type_full.split("_", 1)
        task_source = parts[0]
        task_type = parts[1]
    else:
        task_source = task_type_full
        task_type = task_type_full

    # フィールドの抽出
    owner = task_dict.get("owner")
    repo = task_dict.get("repo")
    project_id = task_dict.get("project_id")
    number = 0

    if task_source == "gitlab":
        # issue_iid または mr_iid を取得（Noneの場合は0）
        issue_iid = task_dict.get("issue_iid")
        mr_iid = task_dict.get("mr_iid")
        number = int(issue_iid if issue_iid is not None else (mr_iid if mr_iid is not None else 0))
    else:
        number = int(task_dict.get("number", 0))

    return task_source, task_type, owner, repo, int(project_id) if project_id is not None else None, number


class TaskDBManager:
    """タスクのDB操作を行うマネージャークラス.

    PostgreSQLへのタスク情報の登録・取得・更新を担当します。
    セッション管理とトランザクション制御を提供します。
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """TaskDBManagerを初期化する.

        Args:
            config: 設定辞書。database セクションを参照します。
                   設定がない場合は環境変数から接続情報を取得します。

        """
        self.config = config or {}
        self._engine = self._create_engine()
        self._session_factory = sessionmaker(bind=self._engine)

    def _create_engine(self) -> Any:
        """SQLAlchemyエンジンを作成する.

        環境変数またはconfig.yamlから接続情報を取得してエンジンを作成します。
        config.database.urlが設定されている場合はそれを使用し、
        そうでない場合は個別の設定から接続URLを構築します。

        Returns:
            Engine: SQLAlchemyエンジン

        """
        # config.yamlから取得
        db_config = self.config.get("database", {})

        # urlが設定されている場合は優先（環境変数DATABASE_URLで上書き可能）
        database_url = db_config.get("url")

        if not database_url:
            # 個別の設定から構築
            host = db_config.get("host", "localhost")
            port = db_config.get("port", 5432)
            name = db_config.get("name", "coding_agent")
            user = db_config.get("user", "")
            password = db_config.get("password", "")

            # URLを構築
            database_url = f"postgresql://{user}:{password}@{host}:{port}/{name}"

        # コネクションプール設定
        pool_size = db_config.get("pool_size", 5)
        max_overflow = db_config.get("max_overflow", 10)

        logger.info("PostgreSQLに接続します: %s", database_url.split("@")[-1])

        return create_engine(
            database_url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=True,  # 接続の生存確認
        )

    def get_session(self) -> Session:
        """新しいセッションを取得する.

        Returns:
            Session: SQLAlchemyセッション

        """
        return self._session_factory()

    def create_tables(self) -> None:
        """テーブルを作成する.

        tasksテーブルが存在しない場合は作成します。
        """
        Base.metadata.create_all(self._engine)
        logger.info("データベーステーブルを作成しました")

    def create_task(self, task_data: dict[str, Any]) -> DBTask:
        """新規タスクを作成しDBにINSERTする.

        Args:
            task_data: タスクデータの辞書

        Returns:
            DBTask: 作成されたDBTaskオブジェクト

        """
        db_task = DBTask(**task_data)

        with self.get_session() as session:
            session.add(db_task)
            session.commit()
            # セッション外でも属性にアクセスできるようにリフレッシュ
            session.refresh(db_task)
            # デタッチ状態にする
            session.expunge(db_task)

        logger.info("タスクをDBに作成しました: uuid=%s", db_task.uuid)
        return db_task

    def create_task_from_task(self, task: Any, task_uuid: str, user: str | None = None) -> DBTask:
        """Taskオブジェクトから新規タスクを作成しDBにINSERTする.

        Args:
            task: handlers.task.Taskオブジェクト
            task_uuid: タスクUUID
            user: ユーザー名

        Returns:
            DBTask: 作成されたDBTaskオブジェクト

        """
        task_key = task.task_key
        task_dict = task_key.to_dict()

        # ヘルパー関数でTaskKey情報を変換
        task_source, task_type, owner, repo, project_id, number = _parse_task_key_dict(task_dict)

        now = datetime.now(timezone.utc)

        task_data = {
            "uuid": task_uuid,
            "task_source": task_source,
            "task_type": task_type,
            "owner": owner,
            "repo": repo,
            "project_id": project_id,
            "number": number,
            "status": "pending",
            "created_at": now,
            "user": user,
        }

        return self.create_task(task_data)

    def get_task(self, uuid: str) -> DBTask | None:
        """UUIDでタスクを取得する.

        Args:
            uuid: タスクUUID

        Returns:
            DBTask | None: 見つかったDBTaskオブジェクト、または None

        """
        with self.get_session() as session:
            db_task = session.query(DBTask).filter(DBTask.uuid == uuid).first()
            if db_task:
                # デタッチ状態にする
                session.expunge(db_task)
            return db_task

    def get_task_by_key(self, task_key: TaskKey) -> DBTask | None:
        """TaskKeyでタスクを取得する.

        最新のタスク（created_at降順）を返します。

        Args:
            task_key: TaskKeyオブジェクト

        Returns:
            DBTask | None: 見つかったDBTaskオブジェクト、または None

        """
        task_dict = task_key.to_dict()

        # ヘルパー関数でTaskKey情報を変換
        task_source, task_type, owner, repo, project_id, number = _parse_task_key_dict(task_dict)

        with self.get_session() as session:
            query = session.query(DBTask).filter(
                DBTask.task_source == task_source,
                DBTask.task_type == task_type,
            )

            # GitHubの場合
            if task_source == "github":
                query = query.filter(
                    DBTask.owner == owner,
                    DBTask.repo == repo,
                    DBTask.number == number,
                )
            # GitLabの場合
            elif task_source == "gitlab":
                query = query.filter(
                    DBTask.project_id == project_id,
                    DBTask.number == number,
                )

            db_task = query.order_by(DBTask.created_at.desc()).first()
            if db_task:
                session.expunge(db_task)
            return db_task

    def find_completed_tasks_by_key(
        self,
        task_key: TaskKey,
        since: datetime | None = None,
    ) -> list[DBTask]:
        """TaskKeyで完了済みタスクを検索する.

        同じTaskKeyを持つ、statusがcompletedまたはstoppedのタスクを
        完了日時の降順で返します。

        Args:
            task_key: TaskKeyオブジェクト
            since: この日時以降に完了したタスクのみを取得（オプション）

        Returns:
            list[DBTask]: 見つかったDBTaskオブジェクトのリスト（完了日時降順）

        """
        task_dict = task_key.to_dict()

        # ヘルパー関数でTaskKey情報を変換
        task_source, task_type, owner, repo, project_id, number = _parse_task_key_dict(task_dict)

        with self.get_session() as session:
            query = session.query(DBTask).filter(
                DBTask.task_source == task_source,
                DBTask.task_type == task_type,
                DBTask.status.in_(["completed", "stopped"]),
            )

            # GitHubの場合
            if task_source == "github":
                query = query.filter(
                    DBTask.owner == owner,
                    DBTask.repo == repo,
                    DBTask.number == number,
                )
            # GitLabの場合
            elif task_source == "gitlab":
                query = query.filter(
                    DBTask.project_id == project_id,
                    DBTask.number == number,
                )

            # 日時フィルタ
            if since:
                query = query.filter(DBTask.completed_at >= since)

            # 完了日時の降順でソート
            db_tasks = query.order_by(DBTask.completed_at.desc()).all()

            # デタッチ状態にする
            for db_task in db_tasks:
                session.expunge(db_task)

            return db_tasks

    def save_task(self, db_task: DBTask) -> DBTask:
        """DBTaskオブジェクトを保存（更新）する.

        Args:
            db_task: 更新するDBTaskオブジェクト

        Returns:
            DBTask: 更新されたDBTaskオブジェクト

        """
        with self.get_session() as session:
            # マージして更新
            merged_task = session.merge(db_task)
            session.commit()
            session.refresh(merged_task)
            session.expunge(merged_task)

        logger.debug("タスクをDBに保存しました: uuid=%s", db_task.uuid)
        return merged_task

    def close(self) -> None:
        """エンジンを閉じる."""
        self._engine.dispose()
        logger.info("データベース接続を閉じました")
