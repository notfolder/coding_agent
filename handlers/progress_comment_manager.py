"""タスク実行の進捗コメントを管理するモジュール.

タスク実行中に1つの進捗コメントを更新し続けることで、
Issue/MRのコメント数を削減し、可読性を向上させる。
"""

import logging
from datetime import datetime
from typing import Any


class ProgressCommentManager:
    """タスク実行の進捗コメントを管理するクラス.
    
    責務:
    - 進捗コメントの初期作成
    - 進捗情報の追記・更新
    - フォーマット管理（Markdown形式）
    - コメントIDの管理
    """

    def __init__(
        self,
        task: Any,
        logger: logging.Logger,
        enabled: bool = True,
        max_history_entries: int = 100,
    ) -> None:
        """初期化.
        
        Args:
            task: Taskオブジェクト（comment/update_commentメソッドを持つ）
            logger: ロガー
            enabled: 進捗コメント機能の有効/無効
            max_history_entries: 履歴エントリの最大保持数
        """
        self.task = task
        self.logger = logger
        self.enabled = enabled
        self.max_history_entries = max_history_entries

        # 状態管理
        self.comment_id: int | str | None = None
        self.start_time: datetime | None = None
        self.last_update_time: datetime | None = None
        self.current_phase: str = ""
        self.current_status: str = ""
        self.action_counter: int = 0
        self.total_actions: int = 0
        self.llm_call_count: int = 0
        self.llm_comment: str | None = None
        self.latest_understanding: dict[str, Any] | None = None
        self.latest_verification: dict[str, Any] | None = None
        self.history_entries: list[dict[str, Any]] = []
        self.checklist_items: list[dict[str, Any]] = []

    def create_initial_comment(self, task_info: str = "") -> int | str | None:
        """タスク開始時の初期コメントを作成.
        
        Args:
            task_info: タスク情報（省略可能）
            
        Returns:
            作成したコメントのID（機能無効時はNone）
        """
        if not self.enabled:
            return None

        self.start_time = datetime.now()
        self.last_update_time = self.start_time
        self.current_phase = "Initializing"
        self.current_status = "started"

        # 初期コメント作成
        content = self._build_comment_content(task_info)
        try:
            result = self.task.comment(content)
            self.comment_id = result.get("id")
            self.logger.info(f"進捗コメントを作成しました: ID={self.comment_id}")
            return self.comment_id
        except Exception as e:
            self.logger.error(f"進捗コメントの作成に失敗しました: {e}")
            return None

    def update_status(
        self,
        phase: str = "",
        status: str = "",
        action_counter: int | None = None,
        total_actions: int | None = None,
        llm_call_count: int | None = None,
    ) -> None:
        """実行状態セクションを更新.
        
        Args:
            phase: 現在フェーズ名（空文字の場合は変更なし）
            status: ステータス（空文字の場合は変更なし）
            action_counter: 完了アクション数（Noneの場合は変更なし）
            total_actions: 総アクション数（Noneの場合は変更なし）
            llm_call_count: LLM呼び出し回数（Noneの場合は変更なし）
        """
        if not self.enabled or self.comment_id is None:
            return

        # 状態更新
        if phase:
            self.current_phase = phase
        if status:
            self.current_status = status
        if action_counter is not None:
            self.action_counter = action_counter
        if total_actions is not None:
            self.total_actions = total_actions
        if llm_call_count is not None:
            self.llm_call_count = llm_call_count

        self.last_update_time = datetime.now()
        self._update_comment()

    def add_history_entry(
        self,
        entry_type: str,
        title: str,
        details: str = "",
        timestamp: datetime | None = None,
    ) -> None:
        """実行履歴にエントリを追加.
        
        Args:
            entry_type: エントリタイプ（phase/llm_call/tool_call/error/assumption等）
            title: エントリタイトル
            details: 詳細情報
            timestamp: タイムスタンプ（Noneの場合は現在時刻）
        """
        if not self.enabled or self.comment_id is None:
            return

        if timestamp is None:
            timestamp = datetime.now()

        entry = {
            "type": entry_type,
            "title": title,
            "details": details,
            "timestamp": timestamp,
        }

        self.history_entries.append(entry)

        # 履歴エントリ数上限チェック
        if len(self.history_entries) > self.max_history_entries:
            removed = self.history_entries.pop(0)
            self.logger.debug(f"履歴エントリが上限を超えたため削除: {removed['title']}")

        self.last_update_time = datetime.now()
        self._update_comment()

    def set_llm_comment(self, comment: str | None) -> None:
        """LLMからのコメントを設定.
        
        LLM応答にcommentフィールドがある場合のみ呼び出される。
        実行状態セクションの「最新コメント」に反映される。
        
        Args:
            comment: LLM応答のcommentフィールドの内容（Noneの場合は以前のコメントを維持）
        """
        if not self.enabled or self.comment_id is None:
            return

        # commentがNoneまたは空文字列の場合は以前のコメントを維持
        if comment:
            self.llm_comment = comment
        
        self.last_update_time = datetime.now()
        self._update_comment()

    def set_understanding_result(self, understanding_result: dict[str, Any]) -> None:
        """最新の依頼内容理解結果を設定.
        
        Pre-planningフェーズのUnderstanding完了時に呼び出され、
        実行状態セクションの「依頼内容理解」に反映される。
        
        Args:
            understanding_result: 理解結果の辞書
                - request_understanding: dict
                    - task_type: str
                    - primary_goal: str
                    - understanding_confidence: float
        """
        if not self.enabled or self.comment_id is None:
            return

        self.latest_understanding = understanding_result
        self.last_update_time = datetime.now()
        self._update_comment()

    def set_verification_result(self, verification_result: dict[str, Any]) -> None:
        """最新の検証結果を設定.
        
        Verificationフェーズ完了時に呼び出され、
        実行状態セクションの「最新検証結果」に反映される。
        
        Args:
            verification_result: 検証結果の辞書
                - verification_passed: bool
                - completion_confidence: float
                - comment: str (optional)
                - issues_found: list (optional)
                - additional_actions: list (optional)
        """
        if not self.enabled or self.comment_id is None:
            return

        self.latest_verification = verification_result
        self.last_update_time = datetime.now()
        self._update_comment()

    def update_checklist(
        self,
        checklist_items: list[dict[str, Any]],
    ) -> None:
        """チェックリストセクションを更新.
        
        Args:
            checklist_items: チェックリスト項目のリスト
                各項目は {"id": str, "description": str, "completed": bool} 形式
        """
        if not self.enabled or self.comment_id is None:
            return

        self.checklist_items = checklist_items
        self.last_update_time = datetime.now()
        self._update_comment()

    def finalize(
        self,
        final_status: str,
        summary: str = "",
    ) -> None:
        """タスク完了/失敗時の最終更新.
        
        Args:
            final_status: 最終ステータス（completed/failed）
            summary: サマリー情報
        """
        if not self.enabled or self.comment_id is None:
            return

        self.current_status = final_status
        if summary:
            # サマリーを履歴に追加
            self.add_history_entry(
                entry_type="summary",
                title=f"🏁 Task {final_status.capitalize()}",
                details=summary,
            )
        else:
            self.last_update_time = datetime.now()
            self._update_comment()

        self.logger.info(f"タスク終了 - 最終ステータス: {final_status}")

    def _build_comment_content(self, task_info: str = "") -> str:
        """コメント全体を構築.
        
        Args:
            task_info: タスク情報（初回のみ）
            
        Returns:
            Markdown形式のコメント内容
        """
        sections = []

        # ヘッダー
        sections.append("# 🤖 タスク実行進捗")
        
        if task_info:
            sections.append(f"\n{task_info}")

        # 実行状態セクション
        sections.append(self._format_status_section())

        # チェックリストセクション
        if self.checklist_items:
            sections.append(self._format_checklist_section())

        # 実行履歴セクション
        if self.history_entries:
            sections.append(self._format_history_section())

        # フッター
        sections.append(self._format_footer())

        return "\n\n".join(sections)

    def _format_understanding_detail(self) -> list[str]:
        """依頼内容理解の詳細を複数行で生成.
        
        Returns:
            理解結果の詳細表示行のリスト
        """
        if not self.latest_understanding:
            return []
        
        request_understanding = self.latest_understanding.get("request_understanding", {})
        task_type = request_understanding.get("task_type", "不明")
        primary_goal = request_understanding.get("primary_goal", "")
        confidence = request_understanding.get("understanding_confidence", 0.0)
        deliverables = request_understanding.get("expected_deliverables", [])
        
        lines = [
            "- **依頼内容理解**:",
            f"  - タスク種別: {task_type}",
            f"  - 理解の確信度: {confidence * 100:.0f}%",
        ]
        
        if primary_goal:
            lines.append(f"  - 主目的: {primary_goal}")
        
        if deliverables:
            lines.append("  - 成果物:")
            for deliverable in deliverables[:3]:  # 最大3件まで表示
                lines.append(f"    - {deliverable}")
            if len(deliverables) > 3:
                lines.append(f"    - ... 他{len(deliverables) - 3}件")
        
        return lines

    def _format_verification_detail(self) -> list[str]:
        """最新検証結果の詳細を複数行で生成.
        
        Returns:
            検証結果の詳細表示行のリスト
        """
        if not self.latest_verification:
            return []
        
        verification_passed = self.latest_verification.get("verification_passed", False)
        confidence = self.latest_verification.get("completion_confidence", 0)
        comment = self.latest_verification.get("comment", "")
        issues_found = self.latest_verification.get("issues_found", [])
        additional_actions = self.latest_verification.get("additional_actions", [])
        
        # 絵文字とステータス
        emoji = "✅" if verification_passed else "⚠️"
        status = "Passed" if verification_passed else "Issues Found"
        
        lines = [
            "- **最新検証結果**:",
            f"  - ステータス: {emoji} {status}",
            f"  - 確信度: {confidence * 100:.0f}%",
        ]
        
        if comment:
            lines.append(f"  - コメント: {comment}")
        
        if issues_found:
            lines.append(f"  - 問題数: {len(issues_found)}件")
            for issue in issues_found[:2]:  # 最大2件まで表示
                lines.append(f"    - {issue}")
            if len(issues_found) > 2:
                lines.append(f"    - ... 他{len(issues_found) - 2}件")
        
        if additional_actions:
            lines.append(f"  - 追加作業: {len(additional_actions)}件")
        
        return lines

    def _format_status_section(self) -> str:
        """実行状態セクションのMarkdown生成.
        
        Returns:
            実行状態セクションのMarkdown
        """
        lines = ["## 📊 実行状態"]

        # フェーズとステータス
        lines.append(f"- **現在フェーズ**: {self.current_phase}")
        lines.append(f"- **ステータス**: {self.current_status}")

        # LLMコメント（複数行、省略なし）
        if self.llm_comment:
            lines.append("- **最新コメント**:")
            # 改行で分割して各行をインデントして表示
            comment_lines = self.llm_comment.split('\n')
            for comment_line in comment_lines:
                lines.append(f"  {comment_line}")
        # コメントがない場合は項目自体を表示しない（初期状態）

        # 進捗情報
        if self.total_actions > 0:
            lines.append(f"- **進捗**: {self.action_counter}/{self.total_actions} アクション完了")

        # LLM呼び出し回数
        lines.append(f"- **LLM呼び出し回数**: {self.llm_call_count}")

        # タイムスタンプ
        if self.start_time:
            start_str = self.start_time.strftime("%Y-%m-%d %H:%M:%S")
            lines.append(f"- **開始時刻**: {start_str}")

        if self.last_update_time:
            update_str = self.last_update_time.strftime("%Y-%m-%d %H:%M:%S")
            lines.append(f"- **最終更新**: {update_str}")

        # 依頼内容理解（複数行、省略なし）
        if self.latest_understanding:
            understanding_lines = self._format_understanding_detail()
            lines.extend(understanding_lines)

        # 最新検証結果（複数行、省略なし）
        if self.latest_verification:
            verification_lines = self._format_verification_detail()
            lines.extend(verification_lines)

        return "\n".join(lines)

    def _format_checklist_section(self) -> str:
        """チェックリストセクションのMarkdown生成.
        
        Returns:
            チェックリストセクションのMarkdown
        """
        lines = ["## 🎯 チェックリスト"]

        for item in self.checklist_items:
            item_id = item.get("id", "unknown")
            description = item.get("description", "")
            completed = item.get("completed", False)
            
            checkbox = "[x]" if completed else "[ ]"
            lines.append(f"- {checkbox} **{item_id}**: {description}")

        return "\n".join(lines)

    def _format_history_section(self) -> str:
        """実行履歴セクションのMarkdown生成.
        
        Returns:
            実行履歴セクションのMarkdown
        """
        lines = ["## 📝 実行履歴"]
        lines.append("")
        lines.append("<details>")
        lines.append("<summary>ここをクリックして詳細を表示</summary>")
        lines.append("")

        for entry in self.history_entries:
            timestamp = entry["timestamp"]
            title = entry["title"]
            details = entry["details"]
            
            time_str = timestamp.strftime("%H:%M:%S")
            lines.append(f"### [{time_str}] {title}")
            
            if details:
                lines.append(details)
            
            lines.append("")

        lines.append("</details>")

        return "\n".join(lines)

    def _format_footer(self) -> str:
        """フッターのMarkdown生成.
        
        Returns:
            フッターのMarkdown
        """
        parts = []
        
        if self.start_time:
            start_str = self.start_time.strftime("%Y-%m-%d %H:%M:%S")
            parts.append(f"タスク開始: {start_str}")
        
        if self.last_update_time:
            update_str = self.last_update_time.strftime("%Y-%m-%d %H:%M:%S")
            parts.append(f"最終更新: {update_str}")
        
        footer_text = " | ".join(parts)
        return f"---\n*{footer_text}*"

    def _update_comment(self) -> None:
        """コメントをIssue/MRに反映.
        
        task.update_comment()を呼び出して、進捗コメントを更新する。
        """
        if not self.enabled or self.comment_id is None:
            return

        content = self._build_comment_content()
        try:
            self.task.update_comment(self.comment_id, content)
            self.logger.debug(f"進捗コメントを更新しました: ID={self.comment_id}")
        except Exception as e:
            self.logger.error(f"進捗コメントの更新に失敗しました: {e}")
