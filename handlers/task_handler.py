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
        llm_client: object,  # LLMClientの具象クラス
        mcp_clients: dict[str, object],  # MCPToolClientの辞書
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

        self.llm_client.send_system_prompt(self._make_system_prompt(task_config))
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
        return self._make_system_prompt(self.config)

    def _make_system_prompt(self, task_config: dict[str, Any] | None = None) -> str:
        """システムプロンプトを生成する.

        設定に基づいてfunction callingの有無を判定し、
        適切なシステムプロンプトファイルを読み込んで、
        MCPプロンプトを埋め込んで返します.
        
        Args:
            task_config: タスク固有の設定（Noneの場合はself.configを使用）

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
        return prompt.replace("{mcp_prompt}", mcp_prompt)

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
