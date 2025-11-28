"""プロジェクトファイル一覧コンテキストローダー.

このモジュールは、Issue/MR/PRの処理時に対象プロジェクトのファイル一覧を
初期コンテキストに含める機能を提供します。

GitHub MCPサーバーでは`get_file_contents`ツール、
GitLab MCPサーバーでは`get_repository_tree`ツールを使用してファイル一覧を取得します。
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from mcp import McpError

if TYPE_CHECKING:
    from clients.mcp_tool_client import MCPToolClient
    from handlers.task import Task


class FileListContextLoader:
    """プロジェクトファイル一覧コンテキストローダー.

    プロジェクトディレクトリからファイル一覧を取得し、
    フラットリスト形式に整形してシステムプロンプト用のコンテキストを生成します。

    GitHub MCPまたはGitLab MCP経由でファイルアクセスをサポートします。
    """

    # デフォルト設定値
    DEFAULT_ENABLED = True
    DEFAULT_MAX_DEPTH = -1  # 無制限

    def __init__(
        self,
        config: dict[str, Any],
        mcp_clients: dict[str, MCPToolClient],
    ) -> None:
        """ローダーを初期化する.

        Args:
            config: アプリケーション設定辞書
            mcp_clients: MCPツールクライアントの辞書(キー: "github"または"gitlab")

        """
        self.config = config
        self.mcp_clients = mcp_clients
        self.logger = logging.getLogger(__name__)

        # file_list_context設定を読み込み
        file_list_config = config.get("file_list_context", {})
        self.enabled = file_list_config.get("enabled", self.DEFAULT_ENABLED)
        self.max_depth = file_list_config.get("max_depth", self.DEFAULT_MAX_DEPTH)

    def load_file_list(self, task: Task) -> str:
        """タスクに関連するプロジェクトのファイル一覧を取得して整形する.

        Args:
            task: タスクオブジェクト

        Returns:
            整形済みファイル一覧文字列。取得失敗時または無効時は空文字列

        """
        # 機能が無効の場合は空文字列を返す
        if not self.enabled:
            self.logger.debug("ファイル一覧コンテキストが無効です")
            return ""

        try:
            # タスクからリポジトリ情報を取得
            task_key = task.get_task_key()
            owner = getattr(task_key, "owner", None)
            repo = getattr(task_key, "repo", None)
            project_id = getattr(task_key, "project_id", None)

            # GitHub の場合
            if owner and repo and "github" in self.mcp_clients:
                self.logger.info("GitHub リポジトリからファイル一覧を取得: %s/%s", owner, repo)
                file_list = self._fetch_file_list_from_github(owner, repo)
                if file_list:
                    # 階層制限を適用
                    file_list = self._apply_depth_limit(file_list, self.max_depth)
                    # フォーマットして返す
                    return self._format_file_list(file_list, owner, repo)
                self.logger.warning("GitHub からファイル一覧を取得できませんでした")
                return ""

            # GitLab の場合
            if project_id and "gitlab" in self.mcp_clients:
                self.logger.info("GitLab プロジェクトからファイル一覧を取得: %s", project_id)
                file_list = self._fetch_file_list_from_gitlab(str(project_id))
                if file_list:
                    file_list = self._apply_depth_limit(file_list, self.max_depth)
                    return self._format_file_list(file_list, "", str(project_id))
                self.logger.warning("GitLab からファイル一覧を取得できませんでした")
                return ""

            self.logger.warning("ファイル一覧取得に必要な情報が不足しています")
            return ""

        except Exception:
            self.logger.exception("ファイル一覧の取得中にエラーが発生しました")
            return ""

    def _fetch_file_list_from_github(self, owner: str, repo: str) -> list[str]:
        """GitHub MCPクライアントを使用してファイル一覧を取得する.

        Args:
            owner: リポジトリオーナー
            repo: リポジトリ名

        Returns:
            ファイルパスのリスト

        """
        try:
            mcp_client = self.mcp_clients["github"]
            file_list: list[str] = []
            self._fetch_github_directory_contents(mcp_client, owner, repo, "", file_list)
            return file_list

        except Exception:
            self.logger.exception("GitHub ファイル一覧取得エラー")
            return []

    def _fetch_github_directory_contents(
        self,
        mcp_client: MCPToolClient,
        owner: str,
        repo: str,
        path: str,
        file_list: list[str],
        current_depth: int = 0,
    ) -> None:
        """GitHub MCPを使用してディレクトリ内容を再帰的に取得する.

        Args:
            mcp_client: GitHub MCPクライアント
            owner: リポジトリオーナー
            repo: リポジトリ名
            path: ディレクトリパス
            file_list: 結果を格納するリスト
            current_depth: 現在の階層深度

        """
        # max_depthが0以上の場合は深度制限を適用
        # current_depth = 0 はルートディレクトリ
        if self.max_depth >= 0 and current_depth >= self.max_depth:
            return

        try:
            result = mcp_client.call_tool(
                "get_file_contents",
                {"owner": owner, "repo": repo, "path": path},
            )

            if isinstance(result, list):
                for item in result:
                    if isinstance(item, dict):
                        item_type = item.get("type", "")
                        item_path = item.get("path", "")

                        if item_type == "file":
                            # ファイルの場合はリストに追加
                            file_list.append(item_path)
                        elif item_type == "dir":
                            # ディレクトリの場合は再帰的に取得
                            self._fetch_github_directory_contents(
                                mcp_client, owner, repo, item_path, file_list, current_depth + 1,
                            )
            elif isinstance(result, dict) and result.get("type") == "dir":
                # 単一ディレクトリの情報が返された場合
                dir_entries = result.get("entries", [])
                for entry in dir_entries:
                    if isinstance(entry, dict):
                        entry_type = entry.get("type", "")
                        entry_path = entry.get("path", "")

                        if entry_type == "file":
                            file_list.append(entry_path)
                        elif entry_type == "dir":
                            self._fetch_github_directory_contents(
                                mcp_client, owner, repo, entry_path, file_list, current_depth + 1,
                            )

        except* McpError as eg:
            # ExceptionGroupからエラーをチェック
            error_is_not_found = self._check_not_found_error(eg)
            if not error_is_not_found:
                self.logger.warning("GitHub ディレクトリ取得エラー (path=%s): %s", path, eg)

    def _fetch_file_list_from_gitlab(self, project_id: str) -> list[str]:
        """GitLab MCPクライアントを使用してファイル一覧を取得する.

        Args:
            project_id: GitLabプロジェクトID

        Returns:
            ファイルパスのリスト

        """
        try:
            mcp_client = self.mcp_clients["gitlab"]
            file_list: list[str] = []

            # get_repository_tree でファイルツリーを取得
            result = mcp_client.call_tool(
                "get_repository_tree",
                {"project_id": project_id, "path": "", "recursive": True},
            )

            if isinstance(result, list):
                for item in result:
                    if isinstance(item, dict):
                        item_type = item.get("type", "")
                        item_path = item.get("path", "")
                        if item_type == "blob":
                            file_list.append(item_path)
            elif isinstance(result, dict):
                tree_items = result.get("tree", result.get("items", []))
                for item in tree_items:
                    if isinstance(item, dict):
                        item_type = item.get("type", "")
                        item_path = item.get("path", "")
                        if item_type == "blob":
                            file_list.append(item_path)

            return file_list

        except Exception:
            self.logger.exception("GitLab ファイル一覧取得エラー")
            return []

    def _apply_depth_limit(self, file_list: list[str], max_depth: int) -> list[str]:
        """ファイルリストに階層制限を適用する.

        Args:
            file_list: ファイルパスのリスト
            max_depth: 最大深度。-1の場合は無制限

        Returns:
            深度制限適用後のファイルパスのリスト

        """
        # max_depthが-1の場合は無制限
        if max_depth < 0:
            return file_list

        filtered: list[str] = []
        for file_path in file_list:
            depth = file_path.count("/")
            if depth <= max_depth:
                filtered.append(file_path)

        return filtered

    def _format_file_list(self, file_list: list[str], owner: str, repo: str) -> str:
        """ファイルリストをフラットリスト形式に整形する.

        Args:
            file_list: ファイルパスのリスト
            owner: リポジトリオーナー
            repo: リポジトリ名

        Returns:
            整形済みファイル一覧文字列

        """
        if not file_list:
            return ""

        # アルファベット順にソート
        sorted_files = sorted(file_list)

        # プロジェクト名を作成
        project_name = f"{owner}/{repo}" if owner else repo

        # ヘッダー行を生成
        lines: list[str] = [
            "---",
            "",
            "## Project File List",
            "",
            f"Repository: {project_name}",
            "",
            "```",
        ]

        # ファイルパスをリストに追加
        lines.extend(sorted_files)

        # フッター行を生成
        lines.extend([
            "```",
            "",
            f"Total: {len(sorted_files)} files",
            "",
            "---",
        ])

        return "\n".join(lines)

    def _check_not_found_error(self, exception: BaseException) -> bool:
        """例外がFile not foundエラーかどうかを再帰的にチェックする.

        Args:
            exception: チェックする例外

        Returns:
            File not foundエラーの場合True

        """
        # McpErrorの場合、メッセージをチェック
        if isinstance(exception, McpError):
            error_msg = str(exception).lower()
            if "not found" in error_msg or "404" in error_msg:
                return True

        # ExceptionGroupの場合、再帰的にチェック
        exceptions = getattr(exception, "exceptions", None)
        if exceptions is not None:
            for e in exceptions:
                if self._check_not_found_error(e):
                    return True

        return False
