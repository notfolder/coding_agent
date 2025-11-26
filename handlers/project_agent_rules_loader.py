"""プロジェクト固有エージェントルールローダー.

このモジュールは、プロジェクトディレクトリ内に配置されたLLMエージェント向けの
ルールファイル(AGENT.md、CLAUDE.md等)を自動的に検出し、読み込む機能を提供します。

ローカルファイルシステムまたはMCPツール経由でファイルアクセスをサポートします。
"""
from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

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
        project_root: str | Path | None = None,
        config: dict[str, Any] | None = None,
        *,
        mcp_client: MCPToolClient | None = None,
        owner: str | None = None,
        repo: str | None = None,
    ) -> None:
        """ローダーを初期化する.

        Args:
            project_root: プロジェクトルートディレクトリのパス (ローカルモード用)
            config: 設定情報 (Noneの場合はデフォルト値を使用)
            mcp_client: MCPツールクライアント (MCPモード用)
            owner: リポジトリオーナー (MCPモード用)
            repo: リポジトリ名 (MCPモード用)

        """
        self.project_root = Path(project_root) if project_root else None
        self.config = config or {}
        self.logger = logging.getLogger(__name__)

        # MCPモード用の設定
        self.mcp_client = mcp_client
        self.owner = owner
        self.repo = repo
        self.use_mcp = mcp_client is not None and owner is not None and repo is not None

        # 設定から制限値を読み込み
        rules_config = self.config.get("project_agent_rules", {})
        limits = rules_config.get("limits", {})

        self.max_file_size = limits.get("max_file_size", self.DEFAULT_MAX_FILE_SIZE)
        self.max_total_size = limits.get("max_total_size", self.DEFAULT_MAX_TOTAL_SIZE)
        self.max_agent_files = limits.get("max_agent_files", self.DEFAULT_MAX_AGENT_FILES)
        self.max_prompt_files = limits.get("max_prompt_files", self.DEFAULT_MAX_PROMPT_FILES)
        self.max_depth = limits.get("max_depth", self.DEFAULT_MAX_DEPTH)

        # 検索設定
        search_config = rules_config.get("search", {})
        self.search_root_files = search_config.get("root_files", True)
        self.search_agent_files = search_config.get("agent_files", True)
        self.search_prompt_files = search_config.get("prompt_files", True)
        self.case_insensitive = search_config.get("case_insensitive", True)

    def find_rule_files(self) -> list[dict[str, Any]]:
        """すべての種類のルールファイルを検索する(ローカルモード用).

        優先順位順にファイルリストを作成し、各ファイルの情報を返します。

        Returns:
            ファイル情報の辞書リスト(path, type, sizeを含む)

        """
        if self.project_root is None:
            return []

        files: list[dict[str, Any]] = []

        # 優先順位順にファイルを検索
        if self.search_root_files:
            self._add_files_info(files, self._find_root_files(), "root")

        if self.search_agent_files:
            agent_files = self._find_agent_files()[: self.max_agent_files]
            self._add_files_info(files, agent_files, "agent")

        if self.search_prompt_files:
            prompt_files = self._find_prompt_files()[: self.max_prompt_files]
            self._add_files_info(files, prompt_files, "prompt")

        return files

    def _add_files_info(
        self,
        result: list[dict[str, Any]],
        file_paths: list[Path],
        file_type: str,
    ) -> None:
        """ファイルパスリストからファイル情報を抽出してリストに追加する."""
        for file_path in file_paths:
            file_info = self._get_file_info(file_path, file_type)
            if file_info:
                result.append(file_info)

    def _get_file_info(self, file_path: Path, file_type: str) -> dict[str, Any] | None:
        """ファイル情報を取得する.

        Args:
            file_path: ファイルパス
            file_type: ファイルタイプ(root, agent, prompt)

        Returns:
            ファイル情報の辞書、無効な場合はNone

        """
        try:
            if not file_path.exists():
                return None

            size = file_path.stat().st_size
        except OSError as e:
            self.logger.warning("ファイル情報取得エラー: %s - %s", file_path, e)
            return None
        else:
            return {
                "path": file_path,
                "type": file_type,
                "size": size,
            }

    def validate_file(self, filepath: Path) -> bool:
        """ファイルがルールファイルとして有効か検証する.

        マークダウン形式の判定とサイズ制限のチェックを実行します。

        Args:
            filepath: 検証対象のファイルパス

        Returns:
            ファイルが有効な場合True

        """
        if not filepath.exists():
            return False

        # サイズチェック
        try:
            size = filepath.stat().st_size
            if size > self.max_file_size:
                self.logger.info(
                    "ファイルサイズが上限を超えています: %s (%d bytes)",
                    filepath,
                    size,
                )
                return False
        except OSError as e:
            self.logger.warning("ファイルサイズ取得エラー: %s - %s", filepath, e)
            return False

        # マークダウン形式の判定
        return self._is_markdown_file(filepath)

    def load_rules(self) -> str:
        """ルールファイルを検索して読み込み、結合されたルールテキストを返す.

        Returns:
            結合フォーマットで整形されたルールテキスト

        """
        # 機能が無効の場合は空文字列を返す
        rules_config = self.config.get("project_agent_rules", {})
        if not rules_config.get("enabled", True):
            return ""

        # MCPモードの場合
        if self.use_mcp:
            return self._load_rules_via_mcp()

        # ローカルモードの場合
        return self._load_rules_local()

    def _load_rules_local(self) -> str:
        """ローカルファイルシステムからルールを読み込む.

        Returns:
            結合フォーマットで整形されたルールテキスト

        """
        # プロジェクトディレクトリの存在確認
        if self.project_root is None or not self.project_root.exists():
            self.logger.warning(
                "プロジェクトディレクトリが存在しません: %s",
                self.project_root,
            )
            return ""

        # ルールファイルを検索
        rule_files = self.find_rule_files()

        if not rule_files:
            self.logger.debug("ルールファイルが見つかりませんでした")
            return ""

        # ファイル内容を読み込み
        files_content: list[tuple[str, str]] = []
        total_size = 0

        for file_info in rule_files:
            filepath = file_info["path"]

            # 妥当性検証
            if not self.validate_file(filepath):
                continue

            # 合計サイズチェック
            file_size = file_info.get("size", 0)
            if total_size + file_size > self.max_total_size:
                self.logger.info(
                    "合計サイズ上限に達しました。以降のファイルをスキップします。",
                )
                break

            # ファイル内容を読み込み
            content = self._read_file_content(filepath)
            if content:
                # プロジェクトルートからの相対パスを使用
                try:
                    relative_path = filepath.relative_to(self.project_root)
                except ValueError:
                    relative_path = filepath

                files_content.append((str(relative_path), content))
                total_size += file_size

        # 内容を結合してフォーマット
        return self._format_rules(files_content)

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

        # 2. .github/agents/*.agent.md
        if self.search_agent_files:
            total_size = self._load_agent_files_via_mcp(files_content, total_size)

        # 3. **/*.prompt.md は再帰検索が複雑なためMCPモードではスキップ

        return self._format_rules(files_content)

    def _load_root_files_via_mcp(
        self,
        files_content: list[tuple[str, str]],
        total_size: int,
    ) -> int:
        """MCPツール経由でルート直下のファイルを読み込む."""
        for filename in ["AGENT.md", "CLAUDE.md"]:
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

    def _load_agent_files_via_mcp(
        self,
        files_content: list[tuple[str, str]],
        total_size: int,
    ) -> int:
        """MCPツール経由で.github/agents/ディレクトリのファイルを読み込む."""
        agent_files = self._list_agent_files_via_mcp()
        for filepath in agent_files[: self.max_agent_files]:
            if total_size >= self.max_total_size:
                break
            content = self._get_file_content_via_mcp(filepath)
            if content:
                content_size = len(content.encode("utf-8"))
                if (
                    content_size <= self.max_file_size
                    and total_size + content_size <= self.max_total_size
                ):
                    files_content.append((filepath, content))
                    total_size += content_size
        return total_size

    def _get_file_content_via_mcp(self, path: str) -> str | None:
        """MCPツール経由でファイル内容を取得する.

        Args:
            path: リポジトリ内のファイルパス

        Returns:
            ファイル内容、エラー時はNone

        """
        if self.mcp_client is None:
            return None

        try:
            result = self.mcp_client.call_tool(
                "get_file_contents",
                {"owner": self.owner, "repo": self.repo, "path": path},
            )
            return self._parse_mcp_file_result(result)
        except (OSError, ValueError, TypeError) as e:
            self.logger.debug("ファイル取得エラー: %s - %s", path, e)
            return None

    def _parse_mcp_file_result(self, result: object) -> str | None:
        """MCP get_file_contentsの結果を解析する."""
        if isinstance(result, dict):
            # text フィールドがある場合
            if "text" in result:
                return result["text"]
            # content フィールドがある場合(Base64エンコードの可能性)
            if "content" in result:
                try:
                    return base64.b64decode(result["content"]).decode("utf-8")
                except (ValueError, UnicodeDecodeError):
                    return result["content"]
        elif isinstance(result, str):
            return result
        return None

    def _list_agent_files_via_mcp(self) -> list[str]:
        """MCPツール経由で.github/agents/ディレクトリのファイルを取得する.

        Returns:
            .agent.mdで終わるファイルパスのリスト

        """
        if self.mcp_client is None:
            return []

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

    def _find_root_files(self) -> list[Path]:
        """AGENT.mdとCLAUDE.mdを検索する.

        Returns:
            検出されたファイルパスのリスト

        """
        if self.project_root is None:
            return []

        files: list[Path] = []
        target_names = ["agent.md", "claude.md"]

        try:
            for item in self.project_root.iterdir():
                if not item.is_file():
                    continue

                name_lower = item.name.lower()
                if name_lower in target_names:
                    files.append(item)
        except OSError as e:
            self.logger.warning(
                "ルートディレクトリの読み取りエラー: %s - %s",
                self.project_root,
                e,
            )

        # AGENT.mdを先に、CLAUDE.mdを後にソート
        def sort_key(path: Path) -> int:
            name_lower = path.name.lower()
            if name_lower == "agent.md":
                return 0
            if name_lower == "claude.md":
                return 1
            return 2

        return sorted(files, key=sort_key)

    def _find_agent_files(self) -> list[Path]:
        """.github/agents/*.agent.mdを検索する.

        Returns:
            検出されたファイルパスのリスト(ファイル名でソート)

        """
        if self.project_root is None:
            return []

        agents_dir = self.project_root / ".github" / "agents"

        if not agents_dir.exists():
            return []

        try:
            files = [
                item
                for item in agents_dir.iterdir()
                if item.is_file() and item.name.endswith(".agent.md")
            ]
        except OSError as e:
            self.logger.warning(
                ".github/agentsディレクトリの読み取りエラー: %s",
                e,
            )
            return []

        # ファイル名でソート
        return sorted(files, key=lambda p: p.name.lower())

    def _find_prompt_files(self, current_dir: Path | None = None, depth: int = 0) -> list[Path]:
        """**/*.prompt.mdを再帰的に検索する.

        Args:
            current_dir: 現在のディレクトリ(Noneの場合はプロジェクトルート)
            depth: 現在の検索深度

        Returns:
            検出されたファイルパスのリスト(パスでソート)

        """
        if self.project_root is None:
            return []

        if current_dir is None:
            current_dir = self.project_root

        if depth > self.max_depth:
            return []

        files: list[Path] = []

        try:
            for item in current_dir.iterdir():
                # 隠しディレクトリをスキップ
                if item.name.startswith("."):
                    continue

                if item.is_dir():
                    # 再帰的に検索
                    files.extend(self._find_prompt_files(item, depth + 1))
                elif item.is_file() and item.name.endswith(".prompt.md"):
                    files.append(item)

        except OSError as e:
            self.logger.warning("ディレクトリの読み取りエラー: %s - %s", current_dir, e)

        # 最上位レベルでのみソート
        if depth == 0:
            return sorted(files, key=lambda p: str(p).lower())

        return files

    def _is_markdown_file(self, filepath: Path) -> bool:
        """ファイルがマークダウン形式か判定する.

        Args:
            filepath: 判定対象のファイルパス

        Returns:
            マークダウン形式の場合True

        """
        # 拡張子チェック
        if filepath.suffix.lower() != ".md":
            return False

        try:
            # Check if file is binary by looking for null bytes
            with filepath.open("rb") as f:
                header = f.read(1024)
                if b"\x00" in header:
                    return False

            # UTF-8デコードテスト
            with filepath.open(encoding="utf-8") as f:
                content = f.read()
                # 空ファイルチェック
                if not content.strip():
                    self.logger.debug("空のファイルです: %s", filepath)
                    return False

        except UnicodeDecodeError:
            self.logger.warning("UTF-8でデコードできません: %s", filepath)
            return False
        except OSError as e:
            self.logger.warning("ファイル読み取りエラー: %s - %s", filepath, e)
            return False

        return True

    def _read_file_content(self, filepath: Path) -> str | None:
        """ファイル内容をUTF-8で読み込む.

        Args:
            filepath: 読み込むファイルのパス

        Returns:
            読み込んだ内容、失敗時はNone

        """
        try:
            with filepath.open(encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return None
                return content
        except UnicodeDecodeError:
            self.logger.warning("UTF-8でデコードできません: %s", filepath)
            return None
        except OSError as e:
            self.logger.warning("ファイル読み取りエラー: %s - %s", filepath, e)
            return None

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
