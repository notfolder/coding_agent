"""タスクハンドラー.

このモジュールは、LLMクライアントとMCPツールクライアントを使用して
タスクを処理するハンドラークラスを提供します。
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcp import McpError

if TYPE_CHECKING:
    from clients.llm_base import LLMClient
    from clients.mcp_tool_client import MCPToolClient
    from handlers.task import Task

# 定数定義
MAX_JSON_PARSE_ERRORS = 5
MAX_CONSECUTIVE_TOOL_ERRORS = 3


class TaskHandler:
    """タスク処理ハンドラー.

    LLMクライアントとMCPツールクライアントを統合し、
    タスクに対する自動化された処理を実行します。
    """

    def __init__(
        self,
        llm_client: LLMClient,
        mcp_clients: dict[str, MCPToolClient],
        config: dict[str, Any],
    ) -> None:
        """タスクハンドラーを初期化する.

        Args:
            llm_client: LLMクライアントのインスタンス
            mcp_clients: MCPツールクライアントの辞書
            config: アプリケーション設定辞書

        """
        self.llm_client = llm_client
        self.mcp_clients = mcp_clients
        self.config = config
        self.logger = logging.getLogger(__name__)

    def sanitize_arguments(self, arguments: str | dict | list) -> dict[str, Any]:
        """引数をサニタイズして辞書形式に変換する.

        引数がdict型でない場合はJSON文字列としてパースし、
        dict型に変換します。不正な形式の場合は例外を発生させます。

        Args:
            arguments: サニタイズ対象の引数

        Returns:
            辞書形式に変換された引数

        Raises:
            ValueError: JSON文字列の解析に失敗した場合
            TypeError: サポートされていない型の場合

        """
        # 既に辞書型の場合はそのまま返す
        if isinstance(arguments, dict):
            return arguments

        # 文字列の場合はJSONとしてパース
        if isinstance(arguments, str):
            try:
                parsed = json.loads(arguments)
                if isinstance(parsed, dict):
                    return parsed
                error_msg = "Parsed JSON is not a dictionary."
                raise ValueError(error_msg)
            except json.JSONDecodeError as e:
                msg = f"Invalid JSON string for arguments: {e}"
                raise ValueError(msg) from e
        else:
            # サポートされていない型の場合はエラー
            msg = f"Unsupported type for arguments: {type(arguments)}"
            raise TypeError(msg)

    def handle(self, task: Task) -> None:
        """タスクを処理する.

        LLMに対してタスクのプロンプトを送信し、レスポンスに基づいて
        必要なツールを実行しながらタスクを完了まで処理します。

        Args:
            task: 処理対象のタスクオブジェクト

        """
        # Issue → MR/PR 変換処理のチェック
        # Issueタスクの場合、MR/PRに変換して処理を終了する（MRは次回スケジュールで処理される）
        if self._should_convert_issue_to_mr(task, self.config):
            conversion_result = self._convert_issue_to_mr(task, self.config)
            if conversion_result:
                self.logger.info(
                    "Issue #%s をMR/PR #%s に変換しました。MR/PRは次回スケジュールで処理されます。",
                    self._get_issue_number(task),
                    conversion_result.mr_number,
                )
                return
            # 変換に失敗した場合は通常処理に進む（エラーはログに記録済み）
            self.logger.warning("Issue→MR/PR変換に失敗しました。通常処理を継続します。")

        # 計画機能の有効可否を先に判定する
        planning_config = self.config.get("planning", {})
        planning_enabled = planning_config.get("enabled", True)

        # 実行環境の初期化（計画前情報収集でもツールが必要なため常に準備）
        execution_manager = self._init_execution_environment(
            task,
            self.config,
            prepare=True,
        )

        try:
            # 実行環境のMCPラッパーが登録されたので、LLMクライアントを更新
            if planning_enabled and task.uuid:
                # LLMクライアントのツール定義を更新（実行環境ラッパー含む）
                self._update_llm_client_tools()
                # Use planning-based task handling
                self._handle_with_planning(task, self.config, execution_manager)
            else:
                # Check if context storage is enabled
                context_storage_enabled = self.config.get("context_storage", {}).get("enabled", False)
                
                if context_storage_enabled and task.uuid:
                    # Use file-based context storage
                    self._handle_with_context_storage(task, self.config)
                else:
                    # Use legacy in-memory handling
                    self._handle_legacy(task, self.config)
        finally:
            # 実行環境のクリーンアップ
            self._cleanup_execution_environment(execution_manager, task)

    def _init_execution_environment(
        self,
        task: Task,
        task_config: dict[str, Any],
        *,
        prepare: bool = True,
    ) -> Any | None:
        """実行環境を初期化する.

        Command Executor機能が有効な場合、タスク用のDocker実行環境を準備します。

        Args:
            task: タスクオブジェクト
            task_config: タスク固有の設定
            prepare: 直ちにコンテナを起動するかどうか

        Returns:
            ExecutionEnvironmentManagerインスタンス（無効な場合はNone）

        """
        from handlers.execution_environment_manager import ExecutionEnvironmentManager
        from handlers.execution_environment_mcp_wrapper import ExecutionEnvironmentMCPWrapper

        try:
            # ExecutionEnvironmentManagerを初期化
            manager = ExecutionEnvironmentManager(task_config)
            
            # 機能が無効な場合はNoneを返す
            if not manager.is_enabled():
                return None
            
            # タスクにUUIDがない場合はスキップ
            # UUIDはコンテナ名の一意性確保に必要（通常はタスクキュー経由で自動付与）
            if not task.uuid:
                self.logger.warning(
                    "タスクにUUIDがないため実行環境をスキップします。"
                    "タスクキュー経由でタスクを処理することで自動的にUUIDが付与されます。"
                )
                return None
            
            if not prepare:
                # 計画フェーズ完了後にコンテナを起動する
                self.logger.info(
                    "Command Executor実行環境の準備を遅延します: %s",
                    task.uuid,
                )
            else:
                # 実行環境を準備
                self.logger.info("Command Executor実行環境を準備します: %s", task.uuid)
                container_info = manager.prepare(task)
                self.logger.info("実行環境の準備が完了しました: %s", container_info.container_id)
            
            # 現在のタスクを設定
            manager.set_current_task(task)
            
            # MCPクライアントとしてラップしてmcp_clientsに追加
            command_executor_wrapper = ExecutionEnvironmentMCPWrapper(
                execution_manager=manager,
                mcp_server_name="command-executor",
            )
            self.mcp_clients["command-executor"] = command_executor_wrapper
            
            # text-editor有効時は別途追加
            if manager.is_text_editor_enabled():
                text_editor_wrapper = ExecutionEnvironmentMCPWrapper(
                    execution_manager=manager,
                    mcp_server_name="text",
                )
                self.mcp_clients["text"] = text_editor_wrapper
            
            self.logger.info(
                "実行環境をMCPクライアントとして登録: command-executor%s",
                ", text" if manager.is_text_editor_enabled() else "",
            )
            
            return manager
            
        except Exception as e:
            self.logger.warning("実行環境の初期化に失敗しました: %s", e)
            # 実行環境の初期化失敗は警告として記録し、処理は続行
            task.comment(f"⚠️ 実行環境の初期化に失敗しました: {e}")
            return None

    def _update_llm_client_tools(self) -> None:
        """LLMクライアントのツール定義を更新する.
        
        実行環境ラッパーが登録された後に、LLMクライアントに
        最新のfunctionsとtoolsを設定します。
        """
        if not self.llm_client:
            return
        
        # function_callingが有効な場合のみ更新
        llm_config = self.config.get("llm", {})
        if not llm_config.get("function_calling", True):
            return
        
        # 全MCPクライアントからツール定義を収集
        functions = []
        tools = []
        for client_name, mcp_client in self.mcp_clients.items():
            try:
                functions.extend(mcp_client.get_function_calling_functions())
                tools.extend(mcp_client.get_function_calling_tools())
            except Exception as e:
                self.logger.warning(
                    "MCPクライアント '%s' からのツール取得に失敗: %s",
                    client_name,
                    e,
                )
        
        # LLMクライアントに再設定
        if hasattr(self.llm_client, "update_tools"):
            # update_toolsメソッドがあれば使用
            self.llm_client.update_tools(functions, tools)
            self.logger.info("LLMクライアントのツール定義を更新しました")
        else:
            # 直接プロパティを更新
            if functions:
                self.llm_client.functions = functions
            if tools:
                self.llm_client.tools = tools
            self.logger.info("LLMクライアントのツール定義を直接更新しました")

    def _cleanup_execution_environment(
        self,
        execution_manager: Any | None,
        task: Task,
    ) -> None:
        """実行環境をクリーンアップする.

        タスク終了時にDocker実行環境を削除します。

        Args:
            execution_manager: ExecutionEnvironmentManagerインスタンス
            task: タスクオブジェクト

        """
        if execution_manager is None:
            return
        
        if not task.uuid:
            return
        
        try:
            self.logger.info("Command Executor実行環境をクリーンアップします: %s", task.uuid)
            execution_manager.cleanup(task.uuid)
        except Exception as e:
            self.logger.warning("実行環境のクリーンアップに失敗しました: %s", e)

    def _handle_with_context_storage(self, task: Task, task_config: dict[str, Any]) -> None:
        """Handle task with file-based context storage.

        Args:
            task: Task object
            task_config: Task configuration

        """
        from clients.lm_client import get_llm_client
        from comment_detection_manager import CommentDetectionManager
        from context_storage import ContextCompressor, TaskContextManager
        from pause_resume_manager import PauseResumeManager
        from task_stop_manager import TaskStopManager
        
        # Initialize pause/resume manager
        pause_manager = PauseResumeManager(task_config)
        
        # Initialize task stop manager
        stop_manager = TaskStopManager(task_config)
        
        # Initialize comment detection manager
        comment_detection_manager = CommentDetectionManager(task, task_config)
        
        # Check if this is a resumed task
        is_resumed = getattr(task, "is_resumed", False)
        comment_detection_state = None
        if is_resumed:
            # Restore task context from paused state
            planning_state = pause_manager.restore_task_context(task, task.uuid)
            self.logger.info("一時停止タスクを復元しました: %s", task.uuid)
            
            # コメント検出状態の復元を試みる
            comment_detection_state = self._load_comment_detection_state(task.uuid, task_config)
        
        # Initialize context manager
        context_manager = TaskContextManager(
            task_key=task.get_task_key(),
            task_uuid=task.uuid,
            config=task_config,
            user=task.user,
        )
        
        try:
            # Get stores
            message_store = context_manager.get_message_store()
            summary_store = context_manager.get_summary_store()
            tool_store = context_manager.get_tool_store()
            
            # Check if text-editor MCP is enabled
            text_editor_enabled = False
            if hasattr(self, 'execution_manager') and self.execution_manager is not None:
                text_editor_enabled = self.execution_manager.is_text_editor_enabled()
            
            # Get functions and tools from MCP clients
            functions = []
            tools = []
            if task_config.get("llm", {}).get("function_calling", True):
                for client_name, mcp_client in self.mcp_clients.items():
                    # text-editor MCP有効時はGitHub/GitLab MCPを除外
                    if text_editor_enabled and client_name in ("github", "gitlab"):
                        self.logger.info(
                            "text-editor MCP有効のため%s MCPをLLMから除外します",
                            client_name
                        )
                        continue
                    
                    functions.extend(mcp_client.get_function_calling_functions())
                    tools.extend(mcp_client.get_function_calling_tools())
            
            # Create task-specific LLM client with message store
            task_llm_client = get_llm_client(
                task_config,
                functions=functions if functions else None,
                tools=tools if tools else None,
                message_store=message_store,
                context_dir=context_manager.context_dir,
            )
            
            # Create context compressor
            compressor = ContextCompressor(
                message_store,
                summary_store,
                task_llm_client,
                task_config,
            )
            
            # Setup task handling
            self._setup_task_handling_with_client(task, task_config, task_llm_client)
            
            # Initialize or restore comment detection
            if comment_detection_state:
                comment_detection_manager.restore_state(comment_detection_state)
            else:
                comment_detection_manager.initialize()
            
            # Processing loop
            count = 0
            max_count = task_config.get("max_llm_process_num", 1000)
            error_state = {"last_tool": None, "tool_error_count": 0}
            
            while count < max_count:
                # Check for pause signal
                if pause_manager.check_pause_signal():
                    self.logger.info("一時停止シグナルを検出、タスクを一時停止します")
                    # コメント検出状態を保存
                    self._save_comment_detection_state(
                        task.uuid, task_config, comment_detection_manager.get_state()
                    )
                    pause_manager.pause_task(task, task.uuid, planning_state=None)
                    return  # Exit without calling finish()
                
                # Check for assignee removal (task stop)
                if stop_manager.should_check_now() and not stop_manager.check_assignee_status(task):
                    self.logger.info("アサイン解除を検出、タスクを停止します")
                    # 最終要約を作成してコンテキストをcompletedに移動
                    context_manager.stop()
                    # コメントとラベル更新
                    stop_manager.post_stop_notification(task, llm_call_count=count)
                    return  # Exit without calling finish()
                
                # Check for new comments and add to context
                new_comments = comment_detection_manager.check_for_new_comments()
                if new_comments:
                    comment_detection_manager.add_to_context(task_llm_client, new_comments)
                
                # Check if compression is needed
                if compressor.should_compress():
                    self.logger.info("Context compression triggered")
                    compressor.compress()
                    context_manager.update_statistics(compressions=1)
                
                # Process LLM interaction
                if self._process_llm_interaction_with_client(
                    task, count, error_state, task_llm_client, message_store, tool_store, context_manager
                ):
                    break
                
                count += 1
                # LLM呼び出しのカウントアップはprocess内でトークン数と一緒に記録される
            
            # Task completed successfully
            task.finish()
            context_manager.complete()
            
        except Exception as e:
            self.logger.exception("Task processing failed")
            context_manager.fail(str(e))
            raise

    def _handle_with_planning(
        self,
        task: Task,
        task_config: dict[str, Any],
        execution_manager: Any | None,
    ) -> None:
        """Handle task with planning-based approach.

        Args:
            task: Task object
            task_config: Task configuration
            execution_manager: Execution environment manager instance

        """
        from comment_detection_manager import CommentDetectionManager
        from context_storage import TaskContextManager
        from handlers.planning_coordinator import PlanningCoordinator
        from pause_resume_manager import PauseResumeManager
        from task_stop_manager import TaskStopManager
        
        # Initialize pause/resume manager
        pause_manager = PauseResumeManager(task_config)
        
        # Initialize task stop manager
        stop_manager = TaskStopManager(task_config)
        
        # Initialize comment detection manager
        comment_detection_manager = CommentDetectionManager(task, task_config)
        
        # Check if this is a resumed task
        is_resumed = getattr(task, "is_resumed", False)
        planning_state = None
        comment_detection_state = None
        if is_resumed:
            # Restore task context from paused state
            planning_state = pause_manager.restore_task_context(task, task.uuid)
            self.logger.info("一時停止タスクを復元しました（Planning実行中）: %s", task.uuid)
            
            # コメント検出状態の復元を試みる
            comment_detection_state = self._load_comment_detection_state(task.uuid, task_config)
        
        # Initialize context manager for planning
        context_manager = TaskContextManager(
            task_key=task.get_task_key(),
            task_uuid=task.uuid,
            config=task_config,
            user=task.user,
            is_resumed=is_resumed,
        )
        
        try:
            # Get planning configuration
            planning_config = task_config.get("planning", {})
            # Add main config for LLM client initialization
            planning_config["main_config"] = self.config
            
            # Create planning coordinator with context_manager
            coordinator = PlanningCoordinator(
                config=planning_config,
                llm_client=self.llm_client,
                mcp_clients=self.mcp_clients,
                task=task,
                context_manager=context_manager,
            )
            
            # Restore planning state if resumed
            if is_resumed and planning_state:
                coordinator.restore_planning_state(planning_state)
            
            # Pass pause manager to coordinator
            coordinator.pause_manager = pause_manager
            
            # Pass stop manager to coordinator
            coordinator.stop_manager = stop_manager
            
            # Initialize or restore comment detection
            if comment_detection_state:
                comment_detection_manager.restore_state(comment_detection_state)
            else:
                comment_detection_manager.initialize()
            
            # Pass comment detection manager to coordinator
            coordinator.comment_detection_manager = comment_detection_manager
            
            # Pass execution environment manager to coordinator
            # (環境準備・切り替え処理で必要)
            coordinator.execution_manager = execution_manager
            
            # Execute with planning
            success = coordinator.execute_with_planning()
            
            if success:
                task.finish()
                context_manager.complete()
                self.logger.info("Task completed successfully with planning")
            else:
                context_manager.fail("Planning execution failed")
                self.logger.error("Task failed with planning")
                
        except Exception as e:
            context_manager.fail(str(e))
            self.logger.exception("Planning-based task processing failed")
            raise

    def _handle_legacy(self, task: Task, task_config: dict[str, Any]) -> None:
        """Handle task using legacy in-memory approach.

        Args:
            task: Task object
            task_config: Task configuration

        """
        # 初期設定
        self._setup_task_handling(task, task_config)

        # 処理ループの初期化
        count = 0
        max_count = task_config.get("max_llm_process_num", 1000)

        # 連続ツールエラー管理用の状態
        error_state = {"last_tool": None, "tool_error_count": 0}

        # LLMとの対話ループ
        while count < max_count:
            if self._process_llm_interaction(task, count, error_state):
                break
            count += 1

    def _setup_task_handling(self, task: Task, task_config: dict[str, Any] | None = None) -> None:
        """タスク処理の初期設定を行う.
        
        Args:
            task: タスクオブジェクト
            task_config: タスク固有の設定（Noneの場合はself.configを使用）
        """
        if task_config is None:
            task_config = self.config
            
        prompt = task.get_prompt()
        self.logger.info("LLMに送信するプロンプト: %s", prompt)

        self.llm_client.send_system_prompt(self._make_system_prompt(task_config, task))
        self.llm_client.send_user_message(prompt)

    def _process_llm_interaction(self, task: Task, count: int, error_state: dict) -> bool:
        """LLMとの単一の対話処理を実行する.

        Returns:
            処理を終了する場合はTrue、継続する場合はFalse

        """
        # LLMからレスポンスを取得
        resp, functions, tokens = self.llm_client.get_response()
        self.logger.info("LLM応答: %s (トークン数: %d)", resp, tokens)

        # レスポンスの前処理
        resp_clean = self._process_think_tags(task, resp)

        # JSON応答の解析
        try:
            data = self._extract_json(resp_clean)
        except Exception:
            self.logger.exception("LLM応答JSONパース失敗")
            if count >= MAX_JSON_PARSE_ERRORS:
                task.comment("LLM応答エラーでスキップ")
                return True
            return False

        # レスポンスデータの処理（トークン数は記録されない - レガシーモード）
        return self._process_response_data(task, data, functions, error_state)

    def _process_think_tags(self, task: Task, resp: str) -> str:
        """レスポンス内の<think>タグを処理し、クリーンなレスポンスを返す."""
        think_matches = re.findall(r"<think>(.*?)</think>", resp, flags=re.DOTALL)
        for think_content in think_matches:
            task.comment(think_content.strip())

        return re.sub(r"<think>.*?</think>", "", resp, flags=re.DOTALL).strip()

    def _process_response_data(
        self, task: Task, data: dict, functions: list, error_state: dict,
    ) -> bool:
        """レスポンスデータを解析し、適切な処理を実行する.

        Returns:
            処理を終了する場合はTrue、継続する場合はFalse

        """
        # function_callフィールドの処理
        if "function_call" in data:
            functions = data["function_call"]
            if not isinstance(functions, list):
                functions = [functions]

        # 各種処理の実行
        if len(functions) != 0 and self._execute_functions(task, functions, error_state):
            return True

        if "plan" in data:
            self._process_plan_field(task, data)

        if "command" in data and self._process_command_field(task, data, error_state):
            return True

        if data.get("done"):
            self._process_done_field(task, data)
            return True

        return False

    def _execute_functions(self, task: Task, functions: list, error_state: dict) -> bool:
        """関数呼び出しを実行する.

        Returns:
            エラーで処理を中断する場合はTrue

        """
        # 呼び出し対象の関数名をコメントとして記録
        comments = [
            function["name"]
            for function in functions
            if isinstance(function, dict) and "name" in function
        ]
        task.comment(f"関数呼び出し: {', '.join(list(comments))}")

        # 各関数を順次実行し、いずれか一つでも成功すればTrueを返す
        return any(self._execute_single_function(task, function, error_state) for function in functions)

    def _execute_single_function(self, task: Task, function: dict, error_state: dict) -> bool:
        """単一の関数を実行する.

        Returns:
            エラーで処理を中断する場合はTrue

        """
        # 関数名の取得
        name = function["name"] if isinstance(function, dict) else function.name
        mcp_server, tool_name = name.split("_", 1)

        # 引数の取得とサニタイズ
        args = function["arguments"] if isinstance(function, dict) else function.arguments
        args = self.sanitize_arguments(args)
        self.logger.info("関数呼び出し: %s with args: %s", name, args)

        # ツールの実行
        error_state["current_args"] = args
        output = self._call_mcp_tool(task, mcp_server, tool_name, name, error_state)

        # ツール実行結果をLLMに送信
        self.llm_client.send_function_result(name, output)

        return error_state["tool_error_count"] >= MAX_CONSECUTIVE_TOOL_ERRORS

    def _call_mcp_tool(
        self,
        task: Task,
        mcp_server: str,
        tool_name: str,
        full_name: str,
        error_state: dict,
    ) -> str:
        """MCPツールを呼び出し、エラーハンドリングを行う."""
        result = ""
        try:
            args = error_state.get("current_args", {})
            result = self.mcp_clients[mcp_server].call_tool(tool_name, args)
            # ツール呼び出し成功時はエラーカウントリセット
            if error_state["last_tool"] == tool_name:
                error_state["tool_error_count"] = 0
        except *(McpError, BaseException) as e:
            # 例外の種類に応じて処理を分岐
            if hasattr(e, "exceptions") and e.exceptions:
                # McpErrorの場合
                result = self._handle_mcp_error(task, e, full_name, error_state)
            # その他の例外の場合
            result = self._handle_general_error(task, e, full_name, error_state)
        return result

    def _handle_mcp_error(self, task: Task, e: Exception, name: str, error_state: dict) -> str:
        """MCPエラーを処理する."""
        error_detail = str(e.exceptions[0].exceptions[0])
        self.logger.exception("ツール呼び出し失敗: %s", error_detail)
        task.comment(f"ツール呼び出しエラー: {error_detail}")

        self._update_error_count(name, error_state)
        if error_state["tool_error_count"] >= MAX_CONSECUTIVE_TOOL_ERRORS:
            task.comment(f"同じツール({name})で3回連続エラーが発生したため処理を中止します。")

        return f"error: {error_detail}"

    def _handle_general_error(self, task: Task, e: Exception, name: str, error_state: dict) -> str:
        """一般的なエラーを処理する."""
        error_msg = str(e)
        if hasattr(e, "exceptions") and e.exceptions:
            error_msg = str(e.exceptions[0])

        self.logger.exception("ツール呼び出しエラー: %s", error_msg)
        task.comment(f"ツール呼び出しエラー: {error_msg}")

        self._update_error_count(name, error_state)
        if error_state["tool_error_count"] >= MAX_CONSECUTIVE_TOOL_ERRORS:
            task.comment(f"同じツール({name})で3回連続エラーが発生したため処理を中止します。")

        return f"error: {error_msg}"

    def _update_error_count(self, name: str, error_state: dict) -> None:
        """エラーカウントを更新する."""
        if error_state["last_tool"] == name:
            error_state["tool_error_count"] += 1
        else:
            error_state["tool_error_count"] = 1
            error_state["last_tool"] = name

    def _process_plan_field(self, task: Task, data: dict) -> None:
        """planフィールドを処理する."""
        task.comment(str(data["comment"]))
        task.comment(str(data["plan"]))
        self.llm_client.send_user_message(str(data["plan"]))

    def _process_command_field(self, task: Task, data: dict, error_state: dict) -> bool:
        """レガシー形式のcommandフィールドを処理する.

        Returns:
            エラーで処理を中断する場合はTrue

        """
        task.comment(data.get("comment", ""))
        tool = data["command"]["tool"]
        args = self.sanitize_arguments(data["command"]["args"])
        mcp_server, tool_name = tool.split("_", 1)

        should_abort = False
        try:
            output = self.mcp_clients[mcp_server].call_tool(tool_name, args)
            if error_state["last_tool"] == tool:
                error_state["tool_error_count"] = 0
        except Exception as e:
            # Handle both McpError and other exceptions
            error_detail = str(e)
            if hasattr(e, "exceptions") and hasattr(e.exceptions[0], "exceptions"):
                # Handle ExceptionGroup structure
                error_detail = str(e.exceptions[0].exceptions[0])
            self.logger.exception("ツール呼び出し失敗: %s", error_detail)
            task.comment(f"ツール呼び出しエラー: {error_detail}")
            output = f"error: {error_detail}"

            self._update_error_count(tool, error_state)
            if error_state["tool_error_count"] >= MAX_CONSECUTIVE_TOOL_ERRORS:
                task.comment(f"同じツール({tool})で3回連続エラーが発生したため処理を中止します。")
                should_abort = True

        self.llm_client.send_user_message(f"output: {output}")
        return should_abort

    def _process_done_field(self, task: Task, data: dict) -> None:
        """doneフィールドを処理する."""
        comment_text = data.get("comment", "") or "処理が完了しました。"
        task.comment(comment_text, mention=True)
        task.finish()

    def get_system_prompt(self) -> str:
        """システムプロンプトを取得する(テスト用の公開メソッド)."""
        return self._make_system_prompt(self.config, task=None)

    def _make_system_prompt(
        self,
        task_config: dict[str, Any] | None = None,
        task: Task | None = None,
    ) -> str:
        """システムプロンプトを生成する.

        設定に基づいてfunction callingの有無を判定し、
        適切なシステムプロンプトファイルを読み込んで、
        MCPプロンプトを埋め込んで返します.
        プロジェクト固有のエージェントルールがある場合は末尾に追加します。
        プロジェクトファイル一覧がある場合は末尾に追加します。
        Command Executor機能が有効な場合はその説明を追加します。
        
        Args:
            task_config: タスク固有の設定（Noneの場合はself.configを使用）
            task: タスクオブジェクト（プロジェクトルール取得用）

        Returns:
            生成されたシステムプロンプト文字列

        """
        if task_config is None:
            task_config = self.config
            
        if task_config.get("llm", {}).get("function_calling", True):
            # function callingが有効な場合
            with Path("system_prompt_function_call.txt").open() as f:
                prompt = f.read()
        else:
            # function callingが無効な場合
            with Path("system_prompt.txt").open() as f:
                prompt = f.read()

        # MCPクライアントからシステムプロンプトを取得して結合
        mcp_prompt = ""
        for client in self.mcp_clients.values():
            mcp_prompt += client.system_prompt + "\n"

        # プロンプトテンプレートのプレースホルダーを置換
        prompt = prompt.replace("{mcp_prompt}", mcp_prompt)

        # Command Executor機能が有効な場合、その説明を追加
        command_executor_prompt = self._load_command_executor_prompt(task_config)
        if command_executor_prompt:
            prompt = prompt + "\n" + command_executor_prompt

        # text-editor MCP機能が有効な場合、その説明を追加
        text_editor_prompt = self._load_text_editor_prompt(task_config)
        if text_editor_prompt:
            prompt = prompt + "\n" + text_editor_prompt

        # プロジェクト固有のエージェントルールを取得して追加
        project_rules = self._load_project_agent_rules(task_config, task)
        if project_rules:
            prompt = prompt + "\n" + project_rules

        # プロジェクトファイル一覧を取得して追加
        file_list_context = self._load_file_list_context(task_config, task)
        if file_list_context:
            prompt = prompt + "\n" + file_list_context

        return prompt

    def _load_command_executor_prompt(
        self,
        task_config: dict[str, Any],
    ) -> str:
        """Command Executor機能のシステムプロンプトを読み込む.

        Command Executor機能が有効な場合、プロンプトテンプレートを読み込み、
        許可コマンドリストを埋め込んで返します。

        Args:
            task_config: タスク固有の設定

        Returns:
            Command Executorのシステムプロンプト文字列（無効な場合は空文字列）

        """
        from handlers.execution_environment_manager import ExecutionEnvironmentManager

        # 設定ファイルによる有効/無効チェック
        executor_config = task_config.get("command_executor", {})
        if not executor_config.get("enabled", False):
            return ""

        # プロンプトテンプレートを読み込む
        prompt_path = Path("system_prompt_command_executor.txt")
        if not prompt_path.exists():
            self.logger.warning("Command Executorプロンプトファイルが見つかりません: %s", prompt_path)
            return ""

        try:
            with prompt_path.open() as f:
                prompt = f.read()

            # 許可コマンドリストを取得して埋め込む
            manager = ExecutionEnvironmentManager(task_config)
            allowed_commands_text = manager.get_allowed_commands_text()
            prompt = prompt.replace("{allowed_commands_list}", allowed_commands_text)

            return prompt

        except Exception as e:
            self.logger.warning("Command Executorプロンプトの読み込みに失敗: %s", e)
            return ""

    def _load_text_editor_prompt(
        self,
        task_config: dict[str, Any],
    ) -> str:
        """text-editor MCP機能のシステムプロンプトを読み込む.

        text-editor MCP機能が有効な場合、プロンプトテンプレートを読み込んで返します。

        Args:
            task_config: タスク固有の設定

        Returns:
            text-editorのシステムプロンプト文字列(無効な場合は空文字列)

        """
        import os

        # 設定ファイルによる有効/無効チェック
        text_editor_config = task_config.get("text_editor_mcp", {})
        if not text_editor_config.get("enabled", True):
            return ""

        # プロンプトテンプレートを読み込む
        prompt_path = Path("system_prompt_text_editor.txt")
        if not prompt_path.exists():
            self.logger.warning("text-editorプロンプトファイルが見つかりません: %s", prompt_path)
            return ""

        try:
            with prompt_path.open() as f:
                return f.read()

        except Exception as e:
            self.logger.warning("text-editorプロンプトの読み込みに失敗: %s", e)
            return ""

    def _load_project_agent_rules(
        self,
        task_config: dict[str, Any],
        task: Task | None = None,
    ) -> str:
        """プロジェクト固有のエージェントルールを読み込む.

        Args:
            task_config: タスク固有の設定
            task: タスクオブジェクト

        Returns:
            プロジェクト固有のエージェントルール文字列

        """
        import os
        
        from handlers.project_agent_rules_loader import ProjectAgentRulesLoader

        # 環境変数による有効/無効チェック
        env_enabled = os.getenv("PROJECT_AGENT_RULES_ENABLED")
        if env_enabled is not None:
            if env_enabled.lower() in ("false", "0", "no"):
                return ""
        else:
            # 環境変数が設定されていない場合は設定ファイルをチェック
            rules_config = task_config.get("project_agent_rules", {})
            if not rules_config.get("enabled", True):
                return ""

        # タスクからowner/repo (GitHub) または project_id (GitLab) を取得してMCPモードで読み込み
        if task is not None:
            try:
                task_key = task.get_task_key()
                owner = getattr(task_key, "owner", None)
                repo = getattr(task_key, "repo", None)
                project_id = getattr(task_key, "project_id", None)

                # GitHub の場合
                if owner and repo and "github" in self.mcp_clients:
                    loader = ProjectAgentRulesLoader(
                        config=task_config,
                        mcp_client=self.mcp_clients["github"],
                        owner=owner,
                        repo=repo,
                    )
                    return loader.load_rules()
                
                # GitLab の場合
                if project_id and "gitlab" in self.mcp_clients:
                    loader = ProjectAgentRulesLoader(
                        config=task_config,
                        mcp_client=self.mcp_clients["gitlab"],
                        project_id=str(project_id),
                    )
                    return loader.load_rules()
            except Exception as e:
                self.logger.warning("プロジェクトルールの読み込みに失敗しました: %s", e)

        return ""

    def _load_file_list_context(
        self,
        task_config: dict[str, Any],
        task: Task | None = None,
    ) -> str:
        """プロジェクトファイル一覧を読み込む.

        Args:
            task_config: タスク固有の設定
            task: タスクオブジェクト

        Returns:
            プロジェクトファイル一覧文字列

        """
        from handlers.file_list_context_loader import FileListContextLoader

        # タスクがない場合は空文字列を返す
        if task is None:
            return ""

        try:
            loader = FileListContextLoader(
                config=task_config,
                mcp_clients=self.mcp_clients,
            )
            return loader.load_file_list(task)
        except Exception as e:
            self.logger.warning("ファイル一覧の読み込みに失敗しました: %s", e)
            return ""

    def _extract_json(self, text: str) -> dict[str, Any]:
        """テキストから最初のJSONブロックを抽出する.

        LLMの応答テキストからJSON形式の部分を抽出し、
        パースして辞書として返します。

        Args:
            text: JSON を含む可能性があるテキスト

        Returns:
            抽出・パースされたJSONデータの辞書

        Raises:
            ValueError: JSONが見つからない場合
            json.JSONDecodeError: JSONの解析に失敗した場合

        """
        # テキストから最初の"{" と最後の "}" を見つける
        start = text.find("{")
        end = text.rfind("}")

        if start == -1 or end == -1:
            msg = "No JSON found"
            raise ValueError(msg)

        # JSON部分を抽出してパース
        return json.loads(text[start : end + 1])

    def _setup_task_handling_with_client(
        self, task: Task, task_config: dict[str, Any], llm_client: Any
    ) -> None:
        """タスク処理の初期設定を行う（カスタムLLMクライアント用）.
        
        Args:
            task: タスクオブジェクト
            task_config: タスク固有の設定
            llm_client: 使用するLLMクライアント
        """
        prompt = task.get_prompt()
        self.logger.info("LLMに送信するプロンプト: %s", prompt)

        llm_client.send_system_prompt(self._make_system_prompt(task_config, task))
        llm_client.send_user_message(prompt)

    def _process_llm_interaction_with_client(
        self,
        task: Task,
        count: int,
        error_state: dict,
        llm_client: Any,
        message_store: Any,
        tool_store: Any,
        context_manager: Any,
    ) -> bool:
        """LLMとの単一の対話処理を実行する（file-based mode用）.

        Returns:
            処理を終了する場合はTrue、継続する場合はFalse

        """
        import time
        
        # LLMからレスポンスを取得
        resp, functions, tokens = llm_client.get_response()
        self.logger.info("LLM応答: %s (トークン数: %d)", resp, tokens)
        
        # 空レスポンスのチェック
        if not resp or not resp.strip():
            self.logger.error("LLMから空の応答が返されました")
            if count >= MAX_JSON_PARSE_ERRORS:
                task.comment("LLM応答エラーでスキップ")
                return True
            return False

        # レスポンスの前処理
        resp_clean = self._process_think_tags(task, resp)
        self.logger.debug("think処理後のレスポンス: %s", resp_clean)

        # JSON応答の解析
        try:
            data = self._extract_json(resp_clean)
        except Exception:
            self.logger.exception("LLM応答JSONパース失敗 (応答内容: %s)", resp_clean[:200])
            if count >= MAX_JSON_PARSE_ERRORS:
                task.comment("LLM応答エラーでスキップ")
                return True
            return False

        # レスポンスデータの処理（ツール実行含む）
        return self._process_response_data_with_context(
            task, data, error_state, llm_client, tool_store, context_manager, tokens
        )

    def _process_response_data_with_context(
        self,
        task: Task,
        data: dict,
        error_state: dict,
        llm_client: Any,
        tool_store: Any,
        context_manager: Any,
        tokens: int = 0,
    ) -> bool:
        """レスポンスデータを解析し、適切な処理を実行する（file-based mode用）.

        Args:
            task: タスクオブジェクト
            data: LLMレスポンスデータ
            error_state: エラー状態管理用辞書
            llm_client: LLMクライアント
            tool_store: ツールストア
            context_manager: コンテキストマネージャー
            tokens: 今回のLLM呼び出しで使用したトークン数

        Returns:
            処理を終了する場合はTrue、継続する場合はFalse

        """
        import time
        
        # 終了条件のチェック
        if data.get("done", False):
            task.comment("タスク完了")
            # トークン数を記録してから終了
            context_manager.update_statistics(tokens=tokens)
            return True

        # コメントフィールドの処理
        if "comment" in data:
            task.comment(data["comment"])

        # 各フィールドの処理
        if "plan" in data:
            task.comment(str(data["plan"]))
            llm_client.send_user_message(str(data["plan"]))

        # function_call形式の処理 (OpenAI/LMStudio互換)
        if "function_call" in data:
            func_call = data["function_call"]
            tool_name = func_call["name"]
            args_str = func_call.get("arguments", "{}")
            
            # argumentsが文字列の場合はパース
            if isinstance(args_str, str):
                args = json.loads(args_str) if args_str else {}
            else:
                args = args_str
            
            args = self.sanitize_arguments(args)
            mcp_server, tool_func = tool_name.split("_", 1)
            
            start_time = time.time()
            try:
                output = self.mcp_clients[mcp_server].call_tool(tool_func, args)
                duration_ms = (time.time() - start_time) * 1000
                
                # Record tool execution
                tool_store.add_tool_call(
                    tool_name=tool_name,
                    args=args,
                    result=output,
                    status="success",
                    duration_ms=duration_ms,
                )
                context_manager.update_statistics(tool_calls=1)
                
                # Send result to LLM
                llm_client.send_function_result(tool_name, output)
                
                # Reset error count on success
                if error_state.get("last_tool") == tool_name:
                    error_state["tool_error_count"] = 0
                
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                error_msg = str(e)
                
                # Record tool error
                tool_store.add_tool_call(
                    tool_name=tool_name,
                    args=args,
                    result=None,
                    status="error",
                    duration_ms=duration_ms,
                    error=error_msg,
                )
                context_manager.update_statistics(tool_calls=1)
                
                self.logger.exception("ツール呼び出しエラー: %s", error_msg)
                llm_client.send_function_result(tool_name, {"error": error_msg})
                
                # Update error state
                self._update_error_count(tool_name, error_state)
                if error_state.get("tool_error_count", 0) >= MAX_CONSECUTIVE_TOOL_ERRORS:
                    task.comment(f"同じツール({tool_name})で3回連続エラーが発生したため処理を中止します。")
                    return True

        if "call_tool" in data:
            # ツール呼び出し処理
            for tool_call in data["call_tool"]:
                tool_name = tool_call["tool"]
                args = self.sanitize_arguments(tool_call.get("args", {}))
                mcp_server, tool_func = tool_name.split("_", 1)
                
                start_time = time.time()
                try:
                    output = self.mcp_clients[mcp_server].call_tool(tool_func, args)
                    duration_ms = (time.time() - start_time) * 1000
                    
                    # Record tool execution
                    tool_store.add_tool_call(
                        tool_name=tool_name,
                        args=args,
                        result=output,
                        status="success",
                        duration_ms=duration_ms,
                    )
                    context_manager.update_statistics(tool_calls=1)
                    
                    # Send result to LLM
                    llm_client.send_function_result(tool_name, output)
                    
                    # Reset error count on success
                    if error_state["last_tool"] == tool_name:
                        error_state["tool_error_count"] = 0
                    
                except Exception as e:
                    duration_ms = (time.time() - start_time) * 1000
                    error_msg = str(e)
                    
                    # Record tool error
                    tool_store.add_tool_call(
                        tool_name=tool_name,
                        args=args,
                        result=None,
                        status="error",
                        duration_ms=duration_ms,
                        error=error_msg,
                    )
                    context_manager.update_statistics(tool_calls=1)
                    
                    self.logger.exception("ツール呼び出しエラー: %s", error_msg)
                    llm_client.send_function_result(tool_name, {"error": error_msg})
                    
                    # Update error state
                    self._update_error_count(tool_name, error_state)
                    if error_state["tool_error_count"] >= MAX_CONSECUTIVE_TOOL_ERRORS:
                        task.comment(f"同じツール({tool_name})で3回連続エラーが発生したため処理を中止します。")
                        return True

        if "command" in data:
            # Legacy command format
            task.comment(data.get("comment", ""))
            result = self._process_command_field(task, data, error_state)
            # LLM呼び出しのトークン数を記録
            context_manager.update_statistics(llm_calls=1, tokens=tokens)
            return result

        # 通常のレスポンス処理が完了した場合もLLM統計を記録
        context_manager.update_statistics(llm_calls=1, tokens=tokens)
        return False

    def _load_comment_detection_state(
        self,
        task_uuid: str,
        task_config: dict[str, Any],
    ) -> dict[str, Any] | None:
        """一時停止されたタスクのコメント検出状態を読み込む.
        
        Args:
            task_uuid: タスクのUUID
            task_config: タスク設定
            
        Returns:
            コメント検出状態の辞書、見つからない場合はNone
        """
        import json
        from pathlib import Path
        
        context_storage_config = task_config.get("context_storage", {})
        base_dir = Path(context_storage_config.get("base_dir", "contexts"))
        running_dir = base_dir / "running" / task_uuid
        
        state_path = running_dir / "comment_detection_state.json"
        
        if not state_path.exists():
            self.logger.debug("コメント検出状態ファイルが見つかりません: %s", state_path)
            return None
        
        try:
            with state_path.open() as f:
                state = json.load(f)
            self.logger.info("コメント検出状態を読み込みました: %s", state_path)
            return state
        except Exception as e:
            self.logger.warning("コメント検出状態の読み込みに失敗: %s", e)
            return None

    def _save_comment_detection_state(
        self,
        task_uuid: str,
        task_config: dict[str, Any],
        state: dict[str, Any],
    ) -> None:
        """コメント検出状態を保存する.
        
        Args:
            task_uuid: タスクのUUID
            task_config: タスク設定
            state: 保存する状態辞書
        """
        import json
        from pathlib import Path
        
        context_storage_config = task_config.get("context_storage", {})
        base_dir = Path(context_storage_config.get("base_dir", "contexts"))
        running_dir = base_dir / "running" / task_uuid
        
        # ディレクトリが存在することを確認
        running_dir.mkdir(parents=True, exist_ok=True)
        
        state_path = running_dir / "comment_detection_state.json"
        
        try:
            with state_path.open("w") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            self.logger.info("コメント検出状態を保存しました: %s", state_path)
        except Exception as e:
            self.logger.warning("コメント検出状態の保存に失敗: %s", e)

    # =========================================
    # Issue → MR/PR 変換機能
    # =========================================

    def _is_issue_task(self, task: Task) -> bool:
        """タスクがIssueかどうかを判定する.

        GitHub Issue または GitLab Issue の場合に True を返します。
        Pull Request や Merge Request の場合は False を返します。

        Args:
            task: タスクオブジェクト

        Returns:
            Issue タスクの場合 True、それ以外は False

        """
        from handlers.task_getter_github import TaskGitHubIssue
        from handlers.task_getter_gitlab import TaskGitLabIssue

        return isinstance(task, (TaskGitHubIssue, TaskGitLabIssue))

    def _should_convert_issue_to_mr(self, task: Task, task_config: dict[str, Any]) -> bool:
        """Issue → MR/PR 変換を実行すべきかどうかを判定する.

        以下の条件がすべて満たされる場合に True を返します：
        1. タスクが Issue である
        2. issue_to_mr_conversion が有効である

        Args:
            task: タスクオブジェクト
            task_config: タスク固有の設定

        Returns:
            変換を実行すべき場合 True

        """
        # Issue タスクでない場合は変換不要
        if not self._is_issue_task(task):
            return False

        # 設定ファイルによる有効/無効チェック
        conversion_config = task_config.get("issue_to_mr_conversion", {})
        return conversion_config.get("enabled", True)

    def _get_platform_for_task(self, task: Task) -> str:
        """タスクのプラットフォームを判定する.

        Args:
            task: タスクオブジェクト

        Returns:
            "github" または "gitlab"

        """
        from handlers.task_getter_github import TaskGitHubIssue

        if isinstance(task, TaskGitHubIssue):
            return "github"
        return "gitlab"

    def _get_mcp_client_for_task(self, task: Task) -> Any:
        """タスクに対応する MCP クライアントを取得する.

        Args:
            task: タスクオブジェクト

        Returns:
            MCP クライアント

        """
        platform = self._get_platform_for_task(task)
        return self.mcp_clients.get(platform)

    def _get_issue_number(self, task: Task) -> int:
        """Issue番号を取得する.

        Args:
            task: タスクオブジェクト

        Returns:
            Issue 番号

        """
        task_key = task.get_task_key()
        # GitHub: number, GitLab: issue_iid
        if hasattr(task_key, "number"):
            return task_key.number
        if hasattr(task_key, "issue_iid"):
            return task_key.issue_iid
        return 0

    def _convert_issue_to_mr(
        self,
        task: Task,
        task_config: dict[str, Any],
    ) -> Any:
        """Issue を MR/PR に変換する.

        IssueToMRConverter を使用して Issue を MR/PR に変換します。
        変換が成功した場合、元の Issue は done ラベルに更新され、
        作成された MR/PR は次回のスケジューリングで処理されます。

        Args:
            task: Issue タスクオブジェクト
            task_config: タスク固有の設定

        Returns:
            変換結果（ConversionResult）、変換に失敗した場合は None

        """
        import tempfile
        from pathlib import Path

        from clients.lm_client import get_llm_client
        from context_storage.message_store import MessageStore
        from handlers.issue_to_mr_converter import IssueToMRConverter

        try:
            # プラットフォームの判定
            platform = self._get_platform_for_task(task)

            # MCP クライアントの取得
            mcp_client = self._get_mcp_client_for_task(task)
            if mcp_client is None:
                self.logger.error(
                    "MCP クライアントが見つかりません: platform=%s",
                    platform,
                )
                return None

            # Issue→MR変換用の一時LLMクライアントを作成
            # LLMクライアントにはmessage_storeが必要なため、一時ディレクトリを使用
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_context_dir = Path(temp_dir)

                # メッセージストアを初期化
                temp_message_store = MessageStore(temp_context_dir, task_config)

                # 変換用のLLMクライアントを作成
                conversion_llm_client = get_llm_client(
                    task_config,
                    functions=None,  # Issue→MR変換にfunctionsは不要
                    tools=None,
                    message_store=temp_message_store,
                    context_dir=temp_context_dir,
                )

                # IssueToMRConverter のインスタンス化
                if platform == "gitlab":
                    # GitLabの場合はGitLabClientを渡す
                    converter = IssueToMRConverter(
                        task=task,
                        llm_client=conversion_llm_client,
                        config=task_config,
                        platform=platform,
                        gitlab_client=task.gitlab_client if hasattr(task, "gitlab_client") else None,
                    )
                else:
                    # GitHubの場合はGithubClientを渡す
                    converter = IssueToMRConverter(
                        task=task,
                        llm_client=conversion_llm_client,
                        config=task_config,
                        platform=platform,
                        github_client=task.github_client if hasattr(task, "github_client") else None,
                    )

                # 変換の実行
                result = converter.convert()

            if result.success:
                self.logger.info(
                    "Issue→MR/PR変換が成功しました: MR/PR #%s, ブランチ: %s",
                    result.mr_number,
                    result.branch_name,
                )
                return result

            self.logger.error(
                "Issue→MR/PR変換が失敗しました: %s",
                result.error_message,
            )
            # 変換失敗時は Issue にエラーコメントを投稿
            task.comment(f"⚠️ MR/PR への変換に失敗しました: {result.error_message}")
            return None

        except Exception as e:
            self.logger.exception("Issue→MR/PR変換中に例外が発生しました")
            # 変換失敗時は Issue にエラーコメントを投稿
            task.comment(f"⚠️ MR/PR への変換中にエラーが発生しました: {e}")
            return None
