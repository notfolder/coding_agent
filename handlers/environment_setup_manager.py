"""環境構築マネージャーモジュール.

環境構築サブフェーズ全体を管理するクラスを提供します。
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from handlers.environment_verifier import EnvironmentVerifier

if TYPE_CHECKING:
    from clients.llm_base import LLMClient
    from handlers.execution_environment_manager import ExecutionEnvironmentManager
    from handlers.progress_comment_manager import ProgressCommentManager
    from handlers.task import Task


class EnvironmentSetupManager:
    """環境構築サブフェーズを管理するクラス.
    
    責務:
    - 環境構築サブフェーズ全体を管理
    - 環境構築コマンドの実行
    - 検証コマンドの実行（expected_outputと完全一致確認）
    - エラー時のLLMによるコマンド再生成（最大3回）
    - エラー分類に応じた適切なリトライ処理
    - ProgressCommentManagerへの通知
    """

    # LLM修正の最大回数
    MAX_LLM_REGENERATION = 3
    
    # リトライ設定
    NETWORK_RETRY_DELAYS = [5, 10, 20]  # 指数バックオフ（秒）
    SERVER_ERROR_DELAY = 10  # 一時的なサーバーエラーの待機時間（秒）
    LOCK_CONFLICT_DELAY = 3  # ロック競合の待機時間（秒）
    MAX_LOCK_RETRIES = 5  # ロック競合の最大リトライ回数

    def __init__(
        self,
        config: dict[str, Any],
        llm_client: LLMClient,
        execution_manager: ExecutionEnvironmentManager,
        progress_manager: ProgressCommentManager,
        task: Task,
    ) -> None:
        """EnvironmentSetupManagerを初期化する.
        
        Args:
            config: 設定情報
            llm_client: LLMクライアント
            execution_manager: 実行環境マネージャー
            progress_manager: 進捗コメントマネージャー
            task: タスクオブジェクト
        """
        self.config = config
        self.llm_client = llm_client
        self.execution_manager = execution_manager
        self.progress_manager = progress_manager
        self.task = task
        self.logger = logging.getLogger(__name__)
        
        # 検証用のVerifierを初期化
        self.verifier = EnvironmentVerifier(execution_manager)
        
        # LLM修正カウンター
        self.llm_regeneration_count = 0
        
        # リトライカウンター
        self.network_retry_count = 0

    def execute(
        self,
        environment_setup_info: dict[str, Any],
    ) -> dict[str, Any]:
        """環境構築サブフェーズを実行する.
        
        Args:
            environment_setup_info: 計画フェーズで生成された環境構築情報
            
        Returns:
            環境構築結果の辞書
        """
        self.logger.info("環境構築サブフェーズを開始します")
        
        # フェーズ開始を通知
        self.progress_manager.set_active_phase("environment_setup")
        
        # 環境構築情報を取得
        environment_name = environment_setup_info.get("name", "python")
        setup_commands = environment_setup_info.get("setup_commands", [])
        verification_commands = environment_setup_info.get("verification", [])
        
        self.logger.info("選択された環境: %s", environment_name)
        self.logger.info("セットアップコマンド数: %d", len(setup_commands))
        self.logger.info("検証コマンド数: %d", len(verification_commands))
        
        # Docker環境を起動（実行ループ外で1回のみ）
        try:
            container_info = self.execution_manager.create_container(
                self.task,
                environment_name=environment_name,
            )
            container_id = container_info.container_id
            self.logger.info("コンテナを作成しました: %s", container_id)
        except Exception as e:
            self.logger.error("コンテナ作成失敗: %s", e, exc_info=True)
            return self._handle_fatal_error(
                "Container creation failed",
                str(e),
                environment_name,
            )
        
        # プロジェクトをクローン
        try:
            self.execution_manager.clone_project(self.task, container_id)
            self.logger.info("プロジェクトをクローンしました")
        except Exception as e:
            self.logger.error("プロジェクトクローン失敗: %s", e, exc_info=True)
            return self._handle_fatal_error(
                "Project clone failed",
                str(e),
                environment_name,
            )
        
        # セットアップコマンドを実行（エラー時は再試行）
        setup_result = self._execute_setup_commands_with_retry(
            setup_commands,
            container_id,
            environment_setup_info,
        )
        
        if not setup_result["success"]:
            # セットアップ失敗
            self.logger.error("環境構築に失敗しました")
            return self._handle_fatal_error(
                "Environment setup failed",
                setup_result.get("error", "Unknown error"),
                environment_name,
            )
        
        # 環境検証を実行
        verification_result = self._verify_environment_with_retry(
            verification_commands,
            container_id,
            environment_setup_info,
        )
        
        if not verification_result["success"]:
            # 検証失敗
            self.logger.error("環境検証に失敗しました")
            return self._handle_fatal_error(
                "Environment verification failed",
                verification_result.get("message", "Unknown error"),
                environment_name,
            )
        
        # 成功
        self.logger.info("環境構築サブフェーズが完了しました")
        self.progress_manager.mark_phase_completed("environment_setup")
        
        return {
            "overall_status": "success",
            "environment_name": environment_name,
            "setup_result": setup_result,
            "verification_result": verification_result,
            "errors": [],
        }

    def _execute_setup_commands_with_retry(
        self,
        setup_commands: list[str],
        container_id: str,
        environment_setup_info: dict[str, Any],
    ) -> dict[str, Any]:
        """セットアップコマンドをリトライ付きで実行する.
        
        Args:
            setup_commands: セットアップコマンドのリスト
            container_id: コンテナID
            environment_setup_info: 環境構築情報（LLM修正時に使用）
            
        Returns:
            実行結果の辞書
        """
        current_commands = setup_commands
        
        while self.llm_regeneration_count <= self.MAX_LLM_REGENERATION:
            result = self._execute_setup_commands(current_commands, container_id)
            
            if result["success"]:
                return result
            
            # エラー分類
            error_type = self._classify_error(result)
            
            if error_type == "retryable":
                # リトライ可能エラー
                if self._handle_retryable_error(result):
                    # リトライ成功、再度実行
                    continue
                # リトライ失敗、修正可能エラーとして扱う
                error_type = "fixable"
            
            if error_type == "fixable" and self.llm_regeneration_count < self.MAX_LLM_REGENERATION:
                # 修正可能エラー、LLMに修正依頼
                self.logger.info(
                    "LLMに修正依頼します（%d/%d回目）",
                    self.llm_regeneration_count + 1,
                    self.MAX_LLM_REGENERATION,
                )
                new_setup_info = self._regenerate_setup_commands(
                    current_commands,
                    result,
                    environment_setup_info,
                )
                if new_setup_info:
                    current_commands = new_setup_info.get("setup_commands", current_commands)
                    self.llm_regeneration_count += 1
                    continue
            
            # 致命的エラーまたはLLM修正回数超過
            return result
        
        return result

    def _execute_setup_commands(
        self,
        setup_commands: list[str],
        container_id: str,
    ) -> dict[str, Any]:
        """セットアップコマンドを実行する.
        
        Args:
            setup_commands: セットアップコマンドのリスト
            container_id: コンテナID
            
        Returns:
            実行結果の辞書
        """
        if not setup_commands:
            self.logger.info("セットアップコマンドが指定されていません")
            return {
                "success": True,
                "message": "No setup commands specified",
                "results": [],
            }
        
        results = []
        
        for i, command in enumerate(setup_commands):
            self.logger.info("セットアップコマンド%d実行: %s", i + 1, command)
            
            try:
                exec_result = self.execution_manager.execute_command(
                    container_id=container_id,
                    command=command,
                )
                
                result_info = {
                    "command": command,
                    "exit_code": exec_result.exit_code,
                    "stdout": exec_result.stdout,
                    "stderr": exec_result.stderr,
                }
                
                if exec_result.exit_code != 0:
                    # コマンド失敗
                    self.logger.error(
                        "セットアップコマンド%d失敗: exit_code=%d",
                        i + 1,
                        exec_result.exit_code,
                    )
                    result_info["success"] = False
                    results.append(result_info)
                    return {
                        "success": False,
                        "error": f"Command failed: {command}",
                        "results": results,
                        "failed_command": command,
                        "exit_code": exec_result.exit_code,
                        "stderr": exec_result.stderr,
                    }
                
                result_info["success"] = True
                results.append(result_info)
                self.logger.info("セットアップコマンド%d: 成功", i + 1)
                
            except Exception as e:
                self.logger.error("セットアップコマンド%d実行エラー: %s", i + 1, e, exc_info=True)
                return {
                    "success": False,
                    "error": str(e),
                    "results": results,
                    "failed_command": command,
                }
        
        return {
            "success": True,
            "message": "All setup commands completed successfully",
            "results": results,
        }

    def _verify_environment_with_retry(
        self,
        verification_commands: list[dict[str, str]],
        container_id: str,
        environment_setup_info: dict[str, Any],
    ) -> dict[str, Any]:
        """環境検証をリトライ付きで実行する.
        
        Args:
            verification_commands: 検証コマンドのリスト
            container_id: コンテナID
            environment_setup_info: 環境構築情報（LLM修正時に使用）
            
        Returns:
            検証結果の辞書
        """
        current_verification = verification_commands
        
        while self.llm_regeneration_count <= self.MAX_LLM_REGENERATION:
            result = self.verifier.verify_setup(current_verification, container_id)
            
            if result["success"]:
                return result
            
            # 検証失敗、LLMに修正依頼
            if self.llm_regeneration_count < self.MAX_LLM_REGENERATION:
                self.logger.info(
                    "検証失敗、LLMに修正依頼します（%d/%d回目）",
                    self.llm_regeneration_count + 1,
                    self.MAX_LLM_REGENERATION,
                )
                new_setup_info = self._regenerate_setup_commands(
                    environment_setup_info.get("setup_commands", []),
                    {"error": "Verification failed", "verification_result": result},
                    environment_setup_info,
                )
                if new_setup_info:
                    # セットアップコマンドを再実行
                    setup_result = self._execute_setup_commands(
                        new_setup_info.get("setup_commands", []),
                        container_id,
                    )
                    if not setup_result["success"]:
                        return {
                            "success": False,
                            "message": "Setup failed after regeneration",
                            "results": [],
                        }
                    # 検証コマンドを更新
                    current_verification = new_setup_info.get("verification", current_verification)
                    self.llm_regeneration_count += 1
                    continue
            
            # LLM修正回数超過
            return result
        
        return result

    def _classify_error(self, error_result: dict[str, Any]) -> str:
        """エラーを分類する.
        
        Args:
            error_result: エラー結果の辞書
            
        Returns:
            エラータイプ（"retryable", "fixable", "fatal"）
        """
        error_msg = error_result.get("error", "").lower()
        stderr = error_result.get("stderr", "").lower()
        exit_code = error_result.get("exit_code", 0)
        
        combined_error = f"{error_msg} {stderr}"
        
        # リトライ可能エラー
        if any(keyword in combined_error for keyword in [
            "timeout", "connection", "network", "dns", "temporary failure",
            "503", "502", "504", "could not resolve host",
        ]):
            return "retryable"
        
        # ロック競合
        if any(keyword in combined_error for keyword in [
            "lock", "locked", "waiting for lock",
        ]):
            return "retryable"
        
        # 修正可能エラー
        if any(keyword in combined_error for keyword in [
            "not found", "no such", "invalid", "version conflict",
            "dependency", "syntax error", "parse error",
        ]):
            return "fixable"
        
        # 致命的エラー
        if any(keyword in combined_error for keyword in [
            "permission denied", "out of memory", "disk full",
            "no space left", "cannot allocate memory",
        ]):
            return "fatal"
        
        # デフォルトは修正可能
        return "fixable"

    def _handle_retryable_error(self, error_result: dict[str, Any]) -> bool:
        """リトライ可能エラーを処理する.
        
        Args:
            error_result: エラー結果の辞書
            
        Returns:
            リトライ成功の場合True
        """
        error_msg = error_result.get("error", "").lower()
        stderr = error_result.get("stderr", "").lower()
        combined_error = f"{error_msg} {stderr}"
        
        # ネットワークエラー
        if any(keyword in combined_error for keyword in [
            "timeout", "connection", "network", "dns", "503", "502", "504",
        ]):
            if self.network_retry_count < len(self.NETWORK_RETRY_DELAYS):
                delay = self.NETWORK_RETRY_DELAYS[self.network_retry_count]
                self.logger.info("ネットワークエラー、%d秒待機してリトライします", delay)
                time.sleep(delay)
                self.network_retry_count += 1
                return True
            return False
        
        # ロック競合
        if any(keyword in combined_error for keyword in ["lock", "locked"]):
            if self.network_retry_count < self.MAX_LOCK_RETRIES:
                self.logger.info("ロック競合、%d秒待機してリトライします", self.LOCK_CONFLICT_DELAY)
                time.sleep(self.LOCK_CONFLICT_DELAY)
                self.network_retry_count += 1
                return True
            return False
        
        # その他の一時的エラー
        self.logger.info("一時的エラー、%d秒待機してリトライします", self.SERVER_ERROR_DELAY)
        time.sleep(self.SERVER_ERROR_DELAY)
        return True

    def _regenerate_setup_commands(
        self,
        original_commands: list[str],
        error_info: dict[str, Any],
        environment_setup_info: dict[str, Any],
    ) -> dict[str, Any] | None:
        """LLMに修正を依頼してセットアップコマンドを再生成する.
        
        Args:
            original_commands: 元のセットアップコマンド
            error_info: エラー情報
            environment_setup_info: 環境構築情報
            
        Returns:
            修正されたセットアップ情報（失敗時はNone）
        """
        # プロンプトを構築
        prompt = self._build_regeneration_prompt(
            original_commands,
            error_info,
            environment_setup_info,
        )
        
        try:
            # LLMに修正依頼
            self.llm_client.send_user_message(prompt)
            response, _, _ = self.llm_client.get_response()
            
            # レスポンスをパース
            import json
            import re
            
            # JSONブロックを抽出
            json_match = re.search(r"```json\s*(\{.*?\})\s*```", response, re.DOTALL)
            if not json_match:
                json_match = re.search(r"(\{.*?\})", response, re.DOTALL)
            
            if json_match:
                json_str = json_match.group(1)
                result = json.loads(json_str)
                self.logger.info("LLMによるコマンド再生成成功")
                return result
            
            self.logger.warning("LLM応答からJSONを抽出できませんでした")
            return None
            
        except Exception as e:
            self.logger.error("LLMによるコマンド再生成失敗: %s", e, exc_info=True)
            return None

    def _build_regeneration_prompt(
        self,
        original_commands: list[str],
        error_info: dict[str, Any],
        environment_setup_info: dict[str, Any],
    ) -> str:
        """LLM修正用のプロンプトを構築する.
        
        Args:
            original_commands: 元のセットアップコマンド
            error_info: エラー情報
            environment_setup_info: 環境構築情報
            
        Returns:
            プロンプト文字列
        """
        error_msg = error_info.get("error", "Unknown error")
        stderr = error_info.get("stderr", "")
        
        prompt = f"""An error occurred during environment setup:

Error: {error_msg}

Standard Error Output:
```
{stderr}
```

Original setup commands:
{chr(10).join(f"{i+1}. {cmd}" for i, cmd in enumerate(original_commands))}

Environment: {environment_setup_info.get("name", "unknown")}

Please generate corrected setup commands to fix this error.

Important: For verification commands, ensure that:
- Commands produce deterministic, exact outputs
- expected_output matches the actual command output exactly (complete string match)
- Use simple commands with predictable outputs

Return the response in JSON format:
{{
  "setup_commands": ["corrected command 1", "corrected command 2"],
  "verification": [
    {{
      "command": "verification command 1",
      "expected_output": "exact expected output"
    }}
  ]
}}
"""
        return prompt

    def _handle_fatal_error(
        self,
        error_type: str,
        error_message: str,
        environment_name: str,
    ) -> dict[str, Any]:
        """致命的エラーを処理する.
        
        Args:
            error_type: エラータイプ
            error_message: エラーメッセージ
            environment_name: 環境名
            
        Returns:
            エラー結果の辞書
        """
        # エラーコメントを投稿
        self._post_error_comment(error_type, error_message, environment_name)
        
        # 警告付きで実行フェーズに移行
        return {
            "overall_status": "failed",
            "environment_name": environment_name,
            "setup_result": {
                "success": False,
                "error": error_message,
            },
            "verification_result": {
                "success": False,
            },
            "errors": [{"type": error_type, "message": error_message}],
        }

    def _post_error_comment(
        self,
        error_type: str,
        error_message: str,
        environment_name: str,
    ) -> None:
        """エラーコメントを投稿する.
        
        Args:
            error_type: エラータイプ
            error_message: エラーメッセージ
            environment_name: 環境名
        """
        comment = f"""## 環境構築失敗

**ステータス**: 警告付きで失敗 ⚠
**環境**: {environment_name}

環境構築中にエラーが発生しました。制限付きで実行フェーズに進みます。

**エラー詳細**:
```
{error_message}
```

**試行した対応**:
- ネットワークリトライ回数: {self.network_retry_count}
- LLM再生成回数: {self.llm_regeneration_count}/{self.MAX_LLM_REGENERATION}
- エラー分類: {error_type}

実行フェーズに進みますが、環境構築が不完全なため一部機能が利用できない可能性があります。
"""
        
        try:
            self.task.comment(comment)
            self.logger.info("エラーコメントを投稿しました")
        except Exception as e:
            self.logger.error("エラーコメント投稿失敗: %s", e, exc_info=True)
