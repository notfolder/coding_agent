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
        # タスク固有の設定を取得
        task_config = self._get_task_config(task)
        
        # Check if planning is enabled
        planning_config = task_config.get("planning", {})
        planning_enabled = planning_config.get("enabled", True)
        
        if planning_enabled and task.uuid:
            # Use planning-based task handling
            self._handle_with_planning(task, task_config)
        else:
            # Check if context storage is enabled
            context_storage_enabled = task_config.get("context_storage", {}).get("enabled", False)
            
            if context_storage_enabled and task.uuid:
                # Use file-based context storage
                self._handle_with_context_storage(task, task_config)
            else:
                # Use legacy in-memory handling
                self._handle_legacy(task, task_config)

    def _handle_with_context_storage(self, task: Task, task_config: dict[str, Any]) -> None:
        """Handle task with file-based context storage.

        Args:
            task: Task object
            task_config: Task configuration

        """
        from clients.lm_client import get_llm_client
        from context_storage import ContextCompressor, TaskContextManager
        from pause_resume_manager import PauseResumeManager
        from task_stop_manager import TaskStopManager
        
        # Initialize pause/resume manager
        pause_manager = PauseResumeManager(task_config)
        
        # Initialize task stop manager
        stop_manager = TaskStopManager(task_config)
        
        # Check if this is a resumed task
        is_resumed = getattr(task, "is_resumed", False)
        if is_resumed:
            # Restore task context from paused state
            planning_state = pause_manager.restore_task_context(task, task.uuid)
            self.logger.info("一時停止タスクを復元しました: %s", task.uuid)
        
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
            
            # Get functions and tools from MCP clients
            functions = []
            tools = []
            if task_config.get("llm", {}).get("function_calling", True):
                for mcp_client in self.mcp_clients.values():
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
            
            # Processing loop
            count = 0
            max_count = task_config.get("max_llm_process_num", 1000)
            error_state = {"last_tool": None, "tool_error_count": 0}
            
            while count < max_count:
                # Check for pause signal
                if pause_manager.check_pause_signal():
                    self.logger.info("一時停止シグナルを検出、タスクを一時停止します")
                    pause_manager.pause_task(task, task.uuid, planning_state=None)
                    return  # Exit without calling finish()
                
                # Check for assignee removal (task stop)
                if stop_manager.should_check_now() and not stop_manager.check_assignee_status(task):
                    self.logger.info("アサイン解除を検出、タスクを停止します")
                    stop_manager.stop_task(task, task.uuid, llm_call_count=count)
                    return  # Exit without calling finish()
                
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
                context_manager.update_statistics(llm_calls=1)
            
            # Task completed successfully
            task.finish()
            context_manager.complete()
            
        except Exception as e:
            self.logger.exception("Task processing failed")
            context_manager.fail(str(e))
            raise

    def _handle_with_planning(self, task: Task, task_config: dict[str, Any]) -> None:
        """Handle task with planning-based approach.

        Args:
            task: Task object
            task_config: Task configuration

        """
        from context_storage import TaskContextManager
        from handlers.planning_coordinator import PlanningCoordinator
        from pause_resume_manager import PauseResumeManager
        from task_stop_manager import TaskStopManager
        
        # Initialize pause/resume manager
        pause_manager = PauseResumeManager(task_config)
        
        # Initialize task stop manager
        stop_manager = TaskStopManager(task_config)
        
        # Check if this is a resumed task
        is_resumed = getattr(task, "is_resumed", False)
        planning_state = None
        if is_resumed:
            # Restore task context from paused state
            planning_state = pause_manager.restore_task_context(task, task.uuid)
            self.logger.info("一時停止タスクを復元しました（Planning実行中）: %s", task.uuid)
        
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

    def _get_task_config(self, task: Task) -> dict[str, Any]:
        """タスクに応じた設定を取得する.
        
        USE_USER_CONFIG_API環境変数がtrueの場合、タスクのユーザーに基づいて
        API経由で設定を取得します。
        
        Args:
            task: タスクオブジェクト
        
        Returns:
            タスク用の設定辞書
        """
        import os
        
        # API使用フラグをチェック
        use_api = os.environ.get("USE_USER_CONFIG_API", "false").lower() == "true"
        if not use_api:
            return self.config
        
        # main.pyのfetch_user_configを使用
        try:
            from main import fetch_user_config
            return fetch_user_config(task, self.config)
        except Exception as e:
            self.logger.warning(f"ユーザー設定の取得に失敗しました: {e}。デフォルト設定を使用します。")
            return self.config

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
        resp, functions = self.llm_client.get_response()
        self.logger.info("LLM応答: %s", resp)

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

        # レスポンスデータの処理
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

        # プロジェクト固有のエージェントルールを取得して追加
        project_rules = self._load_project_agent_rules(task_config, task)
        if project_rules:
            prompt = prompt + "\n" + project_rules

        return prompt

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
        resp = llm_client.get_response()
        self.logger.info("LLM応答: %s", resp)
        
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
            task, data, error_state, llm_client, tool_store, context_manager
        )

    def _process_response_data_with_context(
        self,
        task: Task,
        data: dict,
        error_state: dict,
        llm_client: Any,
        tool_store: Any,
        context_manager: Any,
    ) -> bool:
        """レスポンスデータを解析し、適切な処理を実行する（file-based mode用）.

        Returns:
            処理を終了する場合はTrue、継続する場合はFalse

        """
        import time
        
        # 終了条件のチェック
        if data.get("done", False):
            task.comment("タスク完了")
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
            return self._process_command_field(task, data, error_state)

        return False
