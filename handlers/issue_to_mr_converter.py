"""Issue から MR/PR への変換モジュール.

このモジュールは、GitHub/GitLab の Issue で依頼された内容を
自動的に Merge Request (MR) / Pull Request (PR) として作成する機能を提供します。
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from clients.github_client import GithubClient
from clients.gitlab_client import GitlabClient

if TYPE_CHECKING:
    from clients.llm_base import LLMClient
    from handlers.task import Task


# 転記するコメントの最大件数
MAX_TRANSFER_COMMENTS = 50

# ブランチ名の最大長
MAX_BRANCH_NAME_LENGTH = 50

# 予約されたブランチ名（使用禁止）
RESERVED_BRANCH_NAMES = frozenset({"main", "master", "develop", "release", "feature", "hotfix"})

# ブランチ名生成のリトライ回数
MAX_BRANCH_NAME_RETRIES = 5


@dataclass
class ConversionResult:
    """変換結果を保持するデータクラス.

    Attributes:
        success: 変換が成功したかどうか
        mr_number: 作成されたマージリクエスト/プルリクエスト番号
        mr_url: マージリクエスト/プルリクエストのURL
        branch_name: 作成されたブランチ名
        error_message: エラーメッセージ（失敗時）

    """

    success: bool
    mr_number: int | None = None
    mr_url: str | None = None
    branch_name: str | None = None
    error_message: str | None = None


class BranchNameGenerator:
    """LLM を使用してブランチ名を生成するクラス.

    Issue の内容を分析し、Git の命名規則に従った適切なブランチ名を生成します。
    """

    # ブランチ名生成用のシステムプロンプト
    SYSTEM_PROMPT = """You are a branch name and base branch selector for Git repositories.
Your task is to analyze GitHub/GitLab issue content and generate:
1. An appropriate branch name for the feature/fix
2. The most appropriate base branch to merge into

Branch naming rules (Git-flow compliant):
1. Use one of these prefixes based on issue type:
   - feature/ : for new features (merges to develop)
   - fix/ : for bug fixes (merges to develop)
   - hotfix/ : for critical production fixes (merges to master/main)
   - release/ : for release preparation (merges from develop to master)
   - docs/ : for documentation updates
   - refactor/ : for code refactoring
   - test/ : for test additions/updates
   - task/ : for other tasks or chores
2. MUST include bot name and issue number in format: {prefix}{bot_name}-{issue_number}-{description}
3. Use only lowercase letters, numbers, and hyphens
4. Maximum length is 50 characters
5. Do not use spaces or special characters
6. Choose prefix based on urgency and target:
   - Use hotfix/ for critical production issues requiring immediate fix
   - Use feature/ for new functionality
   - Use fix/ for non-critical bug fixes
   - Use release/ when preparing a new release

Base branch selection criteria (Git-flow):
1. For new features (feature/ prefix): select "develop" branch
2. For bug fixes (fix/ prefix): select "develop" branch for normal fixes
3. For hotfixes (hotfix/ prefix): select "master" or "main" (production branch)
4. For release preparation (release/ prefix): select "develop" branch
5. For documentation (docs/ prefix): select "develop" or "main" based on urgency
6. For refactoring/tests (refactor/, test/ prefix): select "develop" branch
7. Priority order when selecting base branch:
   - If hotfix: master > main
   - If feature/fix/refactor/test: develop > main > master
   - If release exists: newest release/* branch > develop
8. Default to "develop" if exists, otherwise "main"

Output format: JSON with "branch_name", "base_branch", and "reasoning" fields.

Examples:
{
  "branch_name": "feature/codingagent-123-add-user-authentication",
  "base_branch": "develop",
  "reasoning": "Issue #123 requests adding user authentication feature. Using feature/ prefix with bot name and issue number. Targeting develop branch as this is a new feature that should be integrated before release."
}

{
  "branch_name": "fix/codingagent-456-login-error",
  "base_branch": "main",
  "reasoning": "Issue #456 reports a login bug. Using fix/ prefix. Targeting main branch as this is a critical bug fix for production."
}"""

    def __init__(
        self,
        llm_client: LLMClient,
        config: dict[str, Any],
    ) -> None:
        """BranchNameGeneratorを初期化する.

        Args:
            llm_client: LLMクライアントのインスタンス
            config: アプリケーション設定辞書

        """
        self.llm_client = llm_client
        self.config = config
        self.logger = logging.getLogger(__name__)

    def generate(
        self,
        issue_info: dict[str, Any],
        existing_branches: list[str] | None = None,
        available_branches: list[str] | None = None,
    ) -> tuple[str, str]:
        """Issue情報からブランチ名とベースブランチを生成する.

        Args:
            issue_info: Issue情報（number, title, body, labels等）
            existing_branches: 既存のブランチ名リスト（重複チェック用）
            available_branches: 利用可能なブランチリスト（ベースブランチ選択用）

        Returns:
            (ブランチ名, ベースブランチ名)のタプル

        Raises:
            ValueError: 有効なブランチ名を生成できない場合

        """
        if existing_branches is None:
            existing_branches = []
        if available_branches is None:
            available_branches = ["main", "develop"]  # デフォルト候補

        # Bot名を取得（設定から、またはデフォルト値）
        bot_name = self._get_bot_name()

        # LLMへのメッセージを構築
        message = self._build_message(issue_info, bot_name, existing_branches, available_branches)

        # LLMに問い合わせ
        try:
            branch_name, base_branch = self._request_branch_info(message)
        except Exception as e:
            self.logger.warning("LLMによる生成に失敗: %s", e)
            # フォールバック: デフォルトのブランチ名を生成
            branch_name = self._generate_fallback_name(bot_name, issue_info.get("number", 0))
            base_branch = "main"

        # ブランチ名の検証と修正
        validated_name = self._validate_and_fix(branch_name, bot_name, issue_info, existing_branches)
        
        # ベースブランチの検証
        validated_base = self._validate_base_branch(base_branch, available_branches)

        return validated_name, validated_base

    def _get_bot_name(self) -> str:
        """ボット名を取得する."""
        # 設定から取得
        github_config = self.config.get("github", {})
        gitlab_config = self.config.get("gitlab", {})
        bot_name = github_config.get("bot_name") or gitlab_config.get("bot_name")
        if bot_name:
            return self._sanitize_for_branch(bot_name)

        # デフォルト値
        return "codingagent"

    def _build_message(
        self,
        issue_info: dict[str, Any],
        bot_name: str,
        existing_branches: list[str],
        available_branches: list[str],
    ) -> str:
        """LLMへのメッセージを構築する."""
        labels_str = ", ".join(issue_info.get("labels", [])) or "None"
        existing_str = ", ".join(existing_branches[:20]) if existing_branches else "None"
        available_str = ", ".join(available_branches) if available_branches else "main, develop"

        return f"""Generate a branch name and select base branch for this issue:

**Issue #{issue_info.get("number", "Unknown")}**
**Title**: {issue_info.get("title", "")}

**Description**:
{issue_info.get("body", "")[:500]}

**Labels**: {labels_str}

**Bot name to use**: {bot_name}
**Issue number to use**: {issue_info.get("number", "Unknown")}

**Existing branches** (avoid duplicates): {existing_str}
**Available base branches**: {available_str}

Please respond with JSON containing branch_name, base_branch, and reasoning."""

    def _request_branch_info(self, message: str) -> tuple[str, str]:
        """LLMにブランチ名とベースブランチを問い合わせる."""
        # システムプロンプトを送信
        self.llm_client.send_system_prompt(self.SYSTEM_PROMPT)
        self.llm_client.send_user_message(message)

        # レスポンスを取得
        response, _, _ = self.llm_client.get_response()

        # JSONを解析
        try:
            # JSONブロックを抽出
            json_match = re.search(r"\{[^}]+\}", response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                branch_name = data.get("branch_name", "")
                base_branch = data.get("base_branch", "main")
                reasoning = data.get("reasoning", "")
                
                if branch_name:
                    self.logger.info(
                        "LLM選択: branch=%s, base=%s, reasoning=%s",
                        branch_name, base_branch, reasoning,
                    )
                    return branch_name, base_branch
        except json.JSONDecodeError:
            self.logger.warning("LLMレスポンスのJSONパースに失敗")

        # JSONでない場合、直接ブランチ名を抽出（ベースはデフォルト）
        lines = response.strip().split("\n")
        for line in lines:
            line = line.strip()
            if "/" in line and not line.startswith("#"):
                return line, "main"

        error_msg = "LLMから有効なブランチ名を取得できませんでした"
        raise ValueError(error_msg)

    def _validate_and_fix(
        self,
        branch_name: str,
        bot_name: str,
        issue_info: dict[str, Any],
        existing_branches: list[str],
    ) -> str:
        """ブランチ名を検証し、必要に応じて修正する."""
        issue_number = issue_info.get("number", 0)

        # 基本のサニタイズ
        branch_name = self._sanitize_for_branch(branch_name)

        # プレフィックスの確認と追加
        valid_prefixes = ("feature/", "fix/", "docs/", "refactor/", "test/", "task/")
        if not any(branch_name.startswith(p) for p in valid_prefixes):
            branch_name = f"task/{branch_name}"

        # Bot名とIssue番号が含まれているか確認
        if bot_name.lower() not in branch_name.lower():
            # プレフィックス部分を分離
            parts = branch_name.split("/", 1)
            prefix = parts[0] + "/"
            rest = parts[1] if len(parts) > 1 else ""
            branch_name = f"{prefix}{bot_name}-{issue_number}-{rest}"

        # 長さ制限
        if len(branch_name) > MAX_BRANCH_NAME_LENGTH:
            branch_name = branch_name[:MAX_BRANCH_NAME_LENGTH].rstrip("-")

        # 予約語チェック
        base_name = branch_name.split("/")[-1] if "/" in branch_name else branch_name
        if base_name.lower() in RESERVED_BRANCH_NAMES:
            branch_name = f"task/{bot_name}-{issue_number}-auto-generated"

        # 重複チェックとサフィックス追加
        original_name = branch_name
        suffix = 2
        while branch_name in existing_branches and suffix <= MAX_BRANCH_NAME_RETRIES:
            # 長さ制限を考慮してサフィックスを追加
            base = original_name[:MAX_BRANCH_NAME_LENGTH - 3]
            branch_name = f"{base}-{suffix}"
            suffix += 1

        return branch_name

    def _validate_base_branch(self, base_branch: str, available_branches: list[str]) -> str:
        """ベースブランチを検証する."""
        # 利用可能なブランチに存在するか確認
        if base_branch in available_branches:
            return base_branch
        
        # 存在しない場合は候補から選択
        if "develop" in available_branches:
            self.logger.warning("ベースブランチ %s が存在しないためdevelopを使用", base_branch)
            return "develop"
        if "main" in available_branches:
            self.logger.warning("ベースブランチ %s が存在しないためmainを使用", base_branch)
            return "main"
        if "master" in available_branches:
            self.logger.warning("ベースブランチ %s が存在しないためmasterを使用", base_branch)
            return "master"
        
        # どれも無い場合は最初の候補またはデフォルト
        fallback = available_branches[0] if available_branches else "main"
        self.logger.warning("ベースブランチ %s が存在しないため %s を使用", base_branch, fallback)
        return fallback

    def _sanitize_for_branch(self, text: str) -> str:
        """テキストをブランチ名として使用可能な形式に変換する."""
        # 小文字に変換
        text = text.lower()
        # 許可されない文字を置換
        text = re.sub(r"[^a-z0-9/-]", "-", text)
        # 連続するハイフンを1つに
        text = re.sub(r"-+", "-", text)
        # 先頭・末尾のハイフンを除去
        text = text.strip("-")
        # 連続するスラッシュを1つに
        text = re.sub(r"/+", "/", text)
        # 末尾のスラッシュを除去
        text = text.rstrip("/")
        return text

    def _generate_fallback_name(self, bot_name: str, issue_number: int) -> str:
        """フォールバック用のブランチ名を生成する."""
        return f"task/{bot_name}-{issue_number}-auto-generated"


class ContentTransferManager:
    """Issue の内容とコメントをマージリクエスト/プルリクエストに転記するクラス."""

    def __init__(
        self,
        config: dict[str, Any],
    ) -> None:
        """ContentTransferManagerを初期化する.

        Args:
            config: アプリケーション設定辞書

        """
        self.config = config
        self.logger = logging.getLogger(__name__)

    def format_mr_body(
        self,
        issue_info: dict[str, Any],
        comments: list[dict[str, Any]],
    ) -> str:
        """マージリクエスト/プルリクエストの本文を生成する.

        Args:
            issue_info: Issue情報
            comments: コメントリスト

        Returns:
            フォーマットされたマージリクエスト/プルリクエスト本文

        """
        # Issue情報セクション
        issue_section = self._format_issue_section(issue_info)

        # コメントセクション
        comments_section = self._format_comments_section(comments)

        # 自動生成情報セクション
        auto_section = self._format_auto_section(issue_info.get("number", 0))

        return f"{issue_section}\n{comments_section}\n{auto_section}"

    def _format_issue_section(self, issue_info: dict[str, Any]) -> str:
        """Issue情報セクションをフォーマットする."""
        number = issue_info.get("number", "")
        author = issue_info.get("author", "")
        created_at = issue_info.get("created_at", "")
        body = issue_info.get("body", "")

        return f"""## 📋 元 Issue からの転記

### Issue 情報
- **Issue 番号**: #{number}
- **作成者**: @{author}
- **作成日時**: {created_at}

### Issue 内容
{body}

---"""

    def _format_comments_section(self, comments: list[dict[str, Any]]) -> str:
        """コメントセクションをフォーマットする."""
        if not comments:
            return "## 💬 Issue コメント\n\nコメントはありません。\n\n---"

        # 最新のコメントを取得（最大50件）
        recent_comments = comments[-MAX_TRANSFER_COMMENTS:]

        lines = ["## 💬 Issue コメント\n"]

        for i, comment in enumerate(recent_comments, 1):
            author = comment.get("author", "unknown")
            created_at = comment.get("created_at", "")
            body = comment.get("body", "")

            # ボットコメントを除外するオプション
            exclude_bot = self.config.get("issue_to_mr_conversion", {}).get(
                "exclude_bot_comments", True,
            )
            if exclude_bot and self._is_bot_comment(author):
                continue

            lines.append(f"### コメント {i}")
            lines.append(f"- **投稿者**: @{author}")
            lines.append(f"- **投稿日時**: {created_at}")
            lines.append("")
            lines.append(body)
            lines.append("")

        lines.append("---")
        return "\n".join(lines)

    def _format_auto_section(self, issue_number: int) -> str:
        """自動生成情報セクションをフォーマットする."""
        return f"""## 🤖 自動生成情報
このマージリクエスト/プルリクエストは Issue #{issue_number} から自動生成されました。"""

    def _is_bot_comment(self, author: str) -> bool:
        """コメントがボットによるものかどうかを判定する."""
        # ボット名を取得
        bot_names = []

        github_bot = self.config.get("github", {}).get("bot_name")
        if github_bot:
            bot_names.append(github_bot.lower())

        gitlab_bot = self.config.get("gitlab", {}).get("bot_name")
        if gitlab_bot:
            bot_names.append(gitlab_bot.lower())

        # 一般的なボットパターン
        bot_patterns = ["bot", "automation", "ci-", "github-actions"]

        author_lower = author.lower()
        return author_lower in bot_names or any(p in author_lower for p in bot_patterns)


class IssueToMRConverter:
    """Issue からマージリクエスト/プルリクエストへの変換を制御するメインクラス."""

    def __init__(
        self,
        task: Task,
        llm_client: LLMClient,
        config: dict[str, Any],
        platform: str,
        task_uuid: str | None = None,
        gitlab_client: GitlabClient = None,
        github_client: GithubClient = None,
    ) -> None:
        """IssueToMRConverterを初期化する.

        Args:
            task: Issueタスクオブジェクト
            llm_client: LLMクライアント
            config: アプリケーション設定
            platform: プラットフォーム名 ("github" または "gitlab")
            task_uuid: タスクのUUID（記録・追跡用）
            gitlab_client: GitLabClientインスタンス (GitLabの場合)
            github_client: GithubClientインスタンス (GitHubの場合)

        """
        self.task = task
        self.llm_client = llm_client
        self.config = config
        self.platform = platform
        self.task_uuid = task_uuid
        self.gitlab_client = gitlab_client
        self.github_client = github_client
        self.logger = logging.getLogger(__name__)

        # 機能が有効かどうかをチェック
        self._conversion_config = config.get("issue_to_mr_conversion", {})

        # サブコンポーネントの初期化
        self.branch_generator = BranchNameGenerator(llm_client, config)
        self.content_manager = ContentTransferManager(config)

    def is_enabled(self) -> bool:
        """Issue→マージリクエスト/プルリクエスト変換機能が有効かどうかを確認する."""
        # 設定ファイルによる有効/無効チェック
        return self._conversion_config.get("enabled", True)

    def convert(self) -> ConversionResult:
        """Issueをマージリクエスト/プルリクエストに変換する.

        Returns:
            変換結果

        """
        if not self.is_enabled():
            return ConversionResult(
                success=False,
                error_message="Issue to MR conversion is disabled",
            )

        self.logger.info("Issue #%s をマージリクエスト/プルリクエストに変換を開始します", self._get_issue_number())

        try:
            # 1. Issue情報を収集
            issue_info = self._collect_issue_info()

            # 2. ブランチ名とベースブランチを生成
            existing_branches = self._get_existing_branches()
            available_branches = self._get_existing_branches()  # 既存ブランチ=利用可能ブランチ
            branch_name, base_branch = self.branch_generator.generate(
                issue_info,
                existing_branches,
                available_branches,
            )
            self.logger.info("ブランチ名とベースブランチを生成しました: %s <- %s", branch_name, base_branch)
            
            # ベースブランチをインスタンス変数に保存（_create_mr_prで使用）
            self._base_branch = base_branch

            # 3. ブランチを作成
            if not self._create_branch(branch_name):
                return ConversionResult(
                    success=False,
                    error_message=f"Failed to create branch: {branch_name}",
                )

            # 4. 空コミットを作成
            if not self._create_empty_commit(branch_name, issue_info):
                self._cleanup_branch(branch_name)
                return ConversionResult(
                    success=False,
                    error_message="Failed to create initial commit",
                )

            # 5. マージリクエスト/プルリクエストを作成
            mr_result = self._create_mr_pr(branch_name, issue_info)
            if not mr_result:
                self._cleanup_branch(branch_name)
                return ConversionResult(
                    success=False,
                    error_message="Failed to create MR/PR",
                )

            mr_number = mr_result.get("number") or mr_result.get("iid")
            mr_url = mr_result.get("html_url") or mr_result.get("web_url")

            # 6. コメントを転記（Issue内のコメントをマージリクエスト/プルリクエスト本文に含める）
            comments = self._get_issue_comments()
            mr_body = self.content_manager.format_mr_body(issue_info, comments)
            self._update_mr_body(mr_result, mr_body)

            # 7. ボットへのアサインとラベル付与
            self._setup_auto_task(mr_result)

            # 8. 元Issueに作成報告
            self._notify_source_issue(mr_number, branch_name, mr_url, base_branch)

            # 9. 元Issueのラベルを更新（processing → done）
            # Issue→MR変換後、Issueタスクは完了するため、ここでラベル更新を行う
            self._update_source_issue_labels()

            self.logger.info("Issue #%s をマージリクエスト/プルリクエスト #%s に変換しました", self._get_issue_number(), mr_number)

            return ConversionResult(
                success=True,
                mr_number=mr_number,
                mr_url=mr_url,
                branch_name=branch_name,
            )

        except Exception as e:
            self.logger.exception("Issue→マージリクエスト/プルリクエスト変換でエラーが発生しました")
            return ConversionResult(
                success=False,
                error_message=str(e),
            )

    def _get_issue_number(self) -> int:
        """Issue番号を取得する."""
        task_key = self.task.get_task_key()
        if hasattr(task_key, "number"):
            return task_key.number
        if hasattr(task_key, "issue_iid"):
            return task_key.issue_iid
        return 0

    def _collect_issue_info(self) -> dict[str, Any]:
        """Issue情報を収集する."""
        task_key = self.task.get_task_key()

        # 共通情報
        info: dict[str, Any] = {
            "number": self._get_issue_number(),
            "title": self.task.title,
            "body": self.task.body,
            "author": self.task.get_user() or "unknown",
            "labels": getattr(self.task, "labels", []),
        }

        # プラットフォーム固有の情報
        if self.platform == "github":
            info["repository"] = f"{task_key.owner}/{task_key.repo}"
            info["owner"] = task_key.owner
            info["repo"] = task_key.repo
        else:  # gitlab
            info["project_id"] = task_key.project_id
            info["repository"] = str(task_key.project_id)

        # 作成日時の取得
        if hasattr(self.task, "issue"):
            info["created_at"] = self.task.issue.get("created_at", "")
        elif hasattr(self.task, "mr"):
            info["created_at"] = self.task.mr.get("created_at", "")

        return info

    def _get_existing_branches(self) -> list[str]:
        """既存のブランチ一覧を取得する."""
        try:
            if self.platform == "github":
                # GitHubの場合 - GithubClientを使用
                task_key = self.task.get_task_key()
                branches_data = self.github_client.list_branches(
                    owner=task_key.owner,
                    repo=task_key.repo,
                )
                if isinstance(branches_data, list):
                    return [b.get("name", "") for b in branches_data if isinstance(b, dict)]
            else:
                # GitLabの場合 - GitLabClientを使用
                task_key = self.task.get_task_key()
                branches_data = self.gitlab_client.list_branches(task_key.project_id)
                if isinstance(branches_data, list):
                    return [b.get("name", "") for b in branches_data if isinstance(b, dict)]
        except Exception as e:
            self.logger.warning("ブランチ一覧の取得に失敗: %s", e)

        return []

    def _create_branch(self, branch_name: str) -> bool:
        """ブランチを作成する."""
        try:
            if self.platform == "github":
                # GitHubの場合はGithubClientを使用
                task_key = self.task.get_task_key()
                self.github_client.create_branch(
                    owner=task_key.owner,
                    repo=task_key.repo,
                    branch=branch_name,
                )
            else:
                # GitLabの場合はGitLabClientを使用
                task_key = self.task.get_task_key()
                self.gitlab_client.create_branch(
                    project_id=task_key.project_id,
                    branch_name=branch_name,
                    ref="main",
                )
            return True
        except Exception as e:
            self.logger.warning("ブランチの作成に失敗: %s", e)
            return False

    def _create_empty_commit(self, branch_name: str, issue_info: dict[str, Any]) -> bool:
        """空コミットを作成する."""
        try:
            issue_number = issue_info.get("number", 0)
            commit_message = f"chore: Initialize branch for issue #{issue_number}"

            if self.platform == "github":
                # GitHubの場合はGithubClientを使用
                task_key = self.task.get_task_key()
                self.github_client.create_or_update_file(
                    owner=task_key.owner,
                    repo=task_key.repo,
                    path=".gitkeep",
                    message=commit_message,
                    content="",
                    branch=branch_name,
                )
            else:
                # GitLabの場合はGitLabClientを使用
                task_key = self.task.get_task_key()
                self.gitlab_client.create_commit(
                    project_id=task_key.project_id,
                    branch=branch_name,
                    commit_message=commit_message,
                    actions=[],
                )
            return True
        except Exception as e:
            self.logger.warning("初期コミットの作成に失敗: %s", e)
            return False

    def _create_mr_pr(self, branch_name: str, issue_info: dict[str, Any]) -> dict[str, Any] | None:
        """マージリクエスト/プルリクエストを作成する."""
        try:
            # ベースブランチを取得（convertで設定済み、なければデフォルト）
            base_branch = getattr(self, "_base_branch", "main")
            
            title = f"{issue_info.get('title', '')}"
            issue_number = issue_info.get("number", 0)
            mr_pr_type = "マージリクエスト" if self.platform == "gitlab" else "プルリクエスト"
            body = f"この{mr_pr_type}は Issue #{issue_number} から自動生成されました。\n\nベースブランチ: `{base_branch}`"

            if self.platform == "github":
                # GitHubの場合はGithubClientを使用
                task_key = self.task.get_task_key()
                result = self.github_client.create_pull_request(
                    owner=task_key.owner,
                    repo=task_key.repo,
                    title=title,
                    body=body,
                    head=branch_name,
                    base=base_branch,
                    draft=self._conversion_config.get("auto_draft", True),
                )
                return result
            else:
                # GitLabの場合はGitLabClientを使用
                task_key = self.task.get_task_key()
                result = self.gitlab_client.create_merge_request(
                    project_id=task_key.project_id,
                    source_branch=branch_name,
                    target_branch=base_branch,
                    title=title,
                    description=body,
                    draft=self._conversion_config.get("auto_draft", True),
                )
                return result
        except Exception as e:
            self.logger.warning("マージリクエスト/プルリクエストの作成に失敗: %s", e)
            return None

    def _update_mr_body(self, mr_result: dict[str, Any], body: str) -> None:
        """マージリクエスト/プルリクエストの本文を更新する."""
        try:
            if self.platform == "github":
                # GitHubの場合はGithubClientを使用
                task_key = self.task.get_task_key()
                pr_number = mr_result.get("number")
                self.github_client.update_pull_request(
                    owner=task_key.owner,
                    repo=task_key.repo,
                    pull_number=pr_number,
                    body=body,
                )
            else:
                # GitLabの場合はGitLabClientを使用
                task_key = self.task.get_task_key()
                mr_iid = mr_result.get("iid")
                self.gitlab_client.update_merge_request(
                    project_id=task_key.project_id,
                    merge_request_iid=mr_iid,
                    description=body,
                )
        except Exception as e:
            self.logger.warning("マージリクエスト/プルリクエスト本文の更新に失敗: %s", e)

    def _get_issue_comments(self) -> list[dict[str, Any]]:
        """Issueのコメントを取得する."""
        try:
            return self.task.get_comments()
        except Exception as e:
            self.logger.warning("コメントの取得に失敗: %s", e)
            return []

    def _setup_auto_task(self, mr_result: dict[str, Any]) -> None:
        """マージリクエスト/プルリクエストに自動タスク化の設定を行う."""
        try:
            # 元Issueの作成者を取得
            original_user = self.task.get_user()
            
            if self.platform == "github":
                # GitHubの場合はGithubClientを使用
                task_key = self.task.get_task_key()
                pr_number = mr_result.get("number")
                bot_label = self.config.get("github", {}).get("bot_label", "coding agent")

                # ラベルを追加
                self.github_client.add_issue_labels(
                    owner=task_key.owner,
                    repo=task_key.repo,
                    issue_number=pr_number,
                    labels=[bot_label],
                )

                # アサインを設定（ボット名を優先）
                bot_name = (
                    self.config.get("github", {}).get("bot_name")
                    or self.config.get("github", {}).get("assignee")
                )
                if bot_name:
                    self.github_client.update_issue(
                        owner=task_key.owner,
                        repo=task_key.repo,
                        issue_number=pr_number,
                        assignees=[bot_name],
                    )
                
                # 元Issueの作成者をレビュアーとして登録
                if original_user and original_user != bot_name:
                    try:
                        self.github_client.request_pull_request_reviewers(
                            owner=task_key.owner,
                            repo=task_key.repo,
                            pull_number=pr_number,
                            reviewers=[original_user],
                        )
                        self.logger.info(
                            "元Issueの作成者 '%s' をPRレビュアーとして登録しました",
                            original_user,
                        )
                    except Exception as e:
                        self.logger.warning(
                            "PRレビュアーの登録に失敗しました（user=%s）: %s",
                            original_user, e,
                        )
            else:
                task_key = self.task.get_task_key()
                mr_iid = mr_result.get("iid")
                bot_label = self.config.get("gitlab", {}).get("bot_label", "coding agent")

                # ラベルを追加 - GitLabClientを使用
                self.gitlab_client.update_merge_request(
                    project_id=task_key.project_id,
                    merge_request_iid=mr_iid,
                    labels=[bot_label],
                )

                # アサインを設定（ボット名を優先）
                bot_name = (
                    self.config.get("gitlab", {}).get("bot_name")
                    or self.config.get("gitlab", {}).get("assignee")
                )
                if bot_name:
                    # ユーザー名からuser_idを取得
                    user_info = self.gitlab_client.get_user_by_username(bot_name)
                    if user_info and "id" in user_info:
                        self.gitlab_client.update_merge_request(
                            project_id=task_key.project_id,
                            merge_request_iid=mr_iid,
                            assignee_ids=[user_info["id"]],
                        )
                    else:
                        self.logger.warning(
                            "GitLabユーザー '%s' が見つかりませんでした",
                            bot_name,
                        )
                
                # 元Issueの作成者をレビュアーとして登録
                if original_user and original_user != bot_name:
                    try:
                        # レビュアーのuser_idを取得
                        reviewer_info = self.gitlab_client.get_user_by_username(original_user)
                        if reviewer_info and "id" in reviewer_info:
                            self.gitlab_client.update_merge_request(
                                project_id=task_key.project_id,
                                merge_request_iid=mr_iid,
                                reviewer_ids=[reviewer_info["id"]],
                            )
                            self.logger.info(
                                "元Issueの作成者 '%s' をMRレビュアーとして登録しました",
                                original_user,
                            )
                        else:
                            self.logger.warning(
                                "レビュアー登録用のGitLabユーザー '%s' が見つかりませんでした",
                                original_user,
                            )
                    except Exception as e:
                        self.logger.warning(
                            "MRレビュアーの登録に失敗しました（user=%s）: %s",
                            original_user, e,
                        )
        except Exception as e:
            self.logger.warning("自動タスク設定に失敗: %s", e)

    def _notify_source_issue(self, mr_number: int, branch_name: str, mr_url: str | None, base_branch: str) -> None:
        """元Issueに作成報告をコメントする."""
        mr_pr_type = "マージリクエスト" if self.platform == "gitlab" else "プルリクエスト"
        
        # UUID行を追加
        uuid_line = ""
        if self.task_uuid:
            uuid_line = f"\n- **Task UUID**: `{self.task_uuid}`"
        
        comment_body = f"""## 🚀 {mr_pr_type}を作成しました

この Issue の内容に基づいて、以下の{mr_pr_type}を作成しました：

- **{mr_pr_type}**: #{mr_number}
- **作業用ブランチ**: `{branch_name}`
- **ベースブランチ**: `{base_branch}`
- **リンク**: {mr_url or "N/A"}{uuid_line}

以降の処理は{mr_pr_type}上で進めます。"""

        try:
            self.task.comment(comment_body)
        except Exception as e:
            self.logger.warning("元Issueへのコメントに失敗: %s", e)

    def _update_source_issue_labels(self) -> None:
        """元Issueのラベルを更新する."""
        try:
            if self.platform == "github":
                bot_label = self.config.get("github", {}).get("bot_label", "coding agent")
                processing_label = self.config.get("github", {}).get("processing_label", "coding agent processing")
                done_label = self.config.get("github", {}).get("done_label", "coding agent done")
            else:
                bot_label = self.config.get("gitlab", {}).get("bot_label", "coding agent")
                processing_label = self.config.get("gitlab", {}).get("processing_label", "coding agent processing")
                done_label = self.config.get("gitlab", {}).get("done_label", "coding agent done")

            # bot_label と processing_label を削除
            self.task.remove_label(bot_label)
            self.task.remove_label(processing_label)
            # done_label を追加
            self.task.add_label(done_label)
        except Exception as e:
            self.logger.warning("元Issueのラベル更新に失敗: %s", e)

    def _cleanup_branch(self, branch_name: str) -> None:
        """作成したブランチを削除する（エラー時のクリーンアップ）."""
        try:
            if self.platform == "github":
                # GitHubの場合はGithubClientを使用
                task_key = self.task.get_task_key()
                self.github_client.delete_branch(
                    owner=task_key.owner,
                    repo=task_key.repo,
                    branch=branch_name,
                )
            else:
                # GitLabの場合はGitLabClientを使用
                task_key = self.task.get_task_key()
                self.gitlab_client.delete_branch(
                    project_id=task_key.project_id,
                    branch_name=branch_name,
                )
        except Exception as e:
            self.logger.warning("ブランチのクリーンアップに失敗: %s", e)
