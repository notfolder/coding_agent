"""プロジェクト固有エージェントルールローダー.

このモジュールは、プロジェクトディレクトリ内に配置されたLLMエージェント向けの
ルールファイル(AGENTS.md、CLAUDE.md等)を自動的に検出し、読み込む機能を提供します。

MCP経由でファイルアクセスを行います。
"""
from __future__ import annotations

import base64
import logging
import os
from typing import TYPE_CHECKING, Any

from mcp import McpError

if TYPE_CHECKING:
    from clients.mcp_tool_client import MCPToolClient


class ProjectAgentRulesLoader:
    """プロジェクト固有エージェントルールローダー.

    プロジェクトディレクトリからルールファイルを検索し、
    ファイルの妥当性検証、内容の読み込みと結合を行います。

    ローカルファイルシステムまたはMCPツール経由でファイルアクセスをサポートします。
    """

    # デフォルト設定値
    DEFAULT_MAX_FILE_SIZE = 102400  # 100KB
    DEFAULT_MAX_TOTAL_SIZE = 512000  # 500KB
    DEFAULT_MAX_AGENT_FILES = 10
    DEFAULT_MAX_PROMPT_FILES = 50
    DEFAULT_MAX_DEPTH = 10

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        mcp_client: MCPToolClient,
        owner: str | None = None,
        repo: str | None = None,
        project_id: str | None = None,
    ) -> None:
        """ローダーを初期化する.

        Args:
            config: 設定情報 (Noneの場合はデフォルト値を使用)
            mcp_client: MCPツールクライアント (必須)
            owner: リポジトリオーナー (GitHub用)
            repo: リポジトリ名 (GitHub用)
            project_id: プロジェクトID (GitLab用)

        """
        self.config = config or {}
        self.logger = logging.getLogger(__name__)

        # MCP設定
        self.mcp_client = mcp_client
        self.owner = owner
        self.repo = repo
        self.project_id = project_id

        # 設定から制限値を読み込み
        rules_config = self.config.get("project_agent_rules", {})
        limits = rules_config.get("limits", {})

        # 環境変数による設定上書きをサポート
        self.max_file_size = int(
            os.getenv(
                "PROJECT_AGENT_RULES_MAX_FILE_SIZE",
                limits.get("max_file_size", self.DEFAULT_MAX_FILE_SIZE),
            ),
        )
        self.max_total_size = int(
            os.getenv(
                "PROJECT_AGENT_RULES_MAX_TOTAL_SIZE",
                limits.get("max_total_size", self.DEFAULT_MAX_TOTAL_SIZE),
            ),
        )
        self.max_agent_files = limits.get("max_agent_files", self.DEFAULT_MAX_AGENT_FILES)
        self.max_prompt_files = limits.get("max_prompt_files", self.DEFAULT_MAX_PROMPT_FILES)
        self.max_depth = limits.get("max_depth", self.DEFAULT_MAX_DEPTH)

        # 検索設定
        search_config = rules_config.get("search", {})
        self.search_root_files = search_config.get("root_files", True)
        self.search_agent_files = search_config.get("agent_files", True)
        self.search_prompt_files = search_config.get("prompt_files", True)
        self.case_insensitive = search_config.get("case_insensitive", True)



    def load_rules(self) -> str:
        """ルールファイルを検索して読み込み、結合されたルールテキストを返す.

        Returns:
            結合フォーマットで整形されたルールテキスト

        """
        # 環境変数による有効/無効チェック
        env_enabled = os.getenv("PROJECT_AGENT_RULES_ENABLED")
        if env_enabled is not None:
            if env_enabled.lower() in ("false", "0", "no"):
                return ""
        else:
            # 環境変数が設定されていない場合は設定ファイルをチェック
            rules_config = self.config.get("project_agent_rules", {})
            if not rules_config.get("enabled", True):
                return ""

        return self._load_rules_via_mcp()



    def _load_rules_via_mcp(self) -> str:
        """MCPツール経由でルールを読み込む.

        Returns:
            結合フォーマットで整形されたルールテキスト

        """
        files_content: list[tuple[str, str]] = []
        total_size = 0

        # 1. AGENT.md, CLAUDE.md (ルート直下)
        if self.search_root_files:
            total_size = self._load_root_files_via_mcp(files_content, total_size)

        return self._format_rules(files_content)

    def _load_root_files_via_mcp(
        self,
        files_content: list[tuple[str, str]],
        total_size: int,
    ) -> int:
        """MCP経由でルート直下のファイルを読み込む."""
        for filename in ["AGENTS.md", "CLAUDE.md", "AGENT.md"]:
            content = self._get_file_content_via_mcp(filename)
            if content:
                content_size = len(content.encode("utf-8"))
                if (
                    content_size <= self.max_file_size
                    and total_size + content_size <= self.max_total_size
                ):
                    files_content.append((filename, content))
                    total_size += content_size
        return total_size

    def _check_file_not_found_error(self, exception: BaseException) -> bool:
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
        if hasattr(exception, "exceptions"):
            for e in exception.exceptions:  # type: ignore[attr-defined]
                if self._check_file_not_found_error(e):
                    return True

        return False

    def _get_file_content_via_mcp(self, path: str) -> str | None:
        """MCP経由でファイル内容を取得する.

        Args:
            path: リポジトリ内のファイルパス

        Returns:
            ファイル内容、ファイルが存在しない場合はNone

        Raises:
            McpError: MCP通信エラー (File not found以外)
            Exception: その他の予期しないエラー

        """
        file_not_found = False
        try:
            # GitHubの場合
            if self.owner and self.repo:
                result = self.mcp_client.call_tool(
                    "get_file_contents",
                    {"owner": self.owner, "repo": self.repo, "path": path},
                )
            # GitLabの場合
            elif self.project_id:
                result = self.mcp_client.call_tool(
                    "get_file_contents",
                    {"project_id": self.project_id, "file_path": path},
                )
            else:
                return None

            return self._parse_mcp_file_result(result)
        except* McpError as eg:
            # ExceptionGroupから再帰的にFile not foundエラーをチェック
            if self._check_file_not_found_error(eg):
                self.logger.debug("ファイルが見つかりません: %s", path)
                file_not_found = True
            else:
                # それ以外のMcpErrorは再送出
                raise

        if file_not_found:
            return None

        return None  # 通常はここには到達しない

    def _parse_mcp_file_result(self, result: object) -> str | None:
        """MCP get_file_contentsの結果を解析する."""
        if isinstance(result, dict):
            # text フィールドがある場合
            if "text" in result:
                return result["text"]
            # content フィールドがある場合
            if "content" in result:
                content = result["content"]
                if not isinstance(content, str):
                    return str(content)

                # ASCII文字のみで構成されている場合はBase64の可能性
                try:
                    content.encode("ascii")
                    return base64.b64decode(content).decode("utf-8")
                except (UnicodeEncodeError, ValueError, UnicodeDecodeError, AttributeError):
                    # デコードに失敗したら元の文字列を返す
                    return content

        if isinstance(result, str):
            return result

        return None

    def _list_agent_files_via_mcp(self) -> list[str]:
        """MCP経由で.github/agents/ディレクトリのファイルを取得する.

        Returns:
            .agent.mdで終わるファイルパスのリスト

        """
        try:
            result = self.mcp_client.call_tool(
                "get_file_contents",
                {"owner": self.owner, "repo": self.repo, "path": ".github/agents/"},
            )

            files: list[str] = []
            if isinstance(result, list):
                for item in result:
                    if isinstance(item, dict):
                        name = item.get("name", "")
                        if name.endswith(".agent.md"):
                            files.append(f".github/agents/{name}")

            return sorted(files)

        except (OSError, ValueError, TypeError) as e:
            self.logger.debug(".github/agentsディレクトリの取得エラー: %s", e)

        return []



    def _format_rules(self, files_content: list[tuple[str, str]]) -> str:
        """複数ファイルの内容を結合フォーマットで整形する.

        Args:
            files_content: (ファイルパス, 内容) のタプルリスト

        Returns:
            整形されたルールテキスト

        """
        if not files_content:
            return ""

        sections: list[str] = [
            "---",
            "",
            "## Project-Specific Agent Rules",
            "",
            "The following rules are defined in the project and should be followed:",
            "",
        ]

        for filepath, content in files_content:
            sections.append(f"### From: {filepath}")
            sections.append("")
            sections.append(content)
            sections.append("")

        sections.append("---")

        return "\n".join(sections)
