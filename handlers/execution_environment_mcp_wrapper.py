"""ExecutionEnvironmentManagerをMCPToolClientインターフェースでラップするモジュール.

このモジュールは、ExecutionEnvironmentManagerを通常のMCPToolClientとして扱えるようにするための
ラッパークラスを提供します。これにより、PrePlanningManagerなど他のコンポーネントから
command-executorとtext-editorツールに統一的にアクセスできるようになります。
"""
from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from handlers.execution_environment_manager import ExecutionEnvironmentManager
    from mcp.types import Tool


class ExecutionEnvironmentMCPWrapper:
    """ExecutionEnvironmentManagerをMCPToolClientインターフェースでラップするクラス.

    ExecutionEnvironmentManagerが提供するcommand-executorとtext-editor機能を
    MCPToolClientと同じインターフェースで利用できるようにするラッパークラス。
    """

    def __init__(
        self,
        execution_manager: ExecutionEnvironmentManager,
        mcp_server_name: str,
    ) -> None:
        """ExecutionEnvironmentMCPWrapperを初期化する.

        Args:
            execution_manager: ラップ対象のExecutionEnvironmentManagerインスタンス
            mcp_server_name: MCPサーバー名("command-executor" or "text")

        """
        self.execution_manager = execution_manager
        self.mcp_server_name = mcp_server_name
        self.lock = threading.Lock()  # MCPToolClientと同様のスレッドセーフ実装
        self.logger = logging.getLogger(__name__)

    def call_tool(self, tool: str, args: dict[str, Any]) -> object:
        """ツール呼び出しをExecutionEnvironmentManagerにルーティングする.

        Args:
            tool: ツール名(execute_commandまたはtext_editor)
            args: ツール引数

        Returns:
            実行結果(辞書形式)

        Raises:
            ValueError: 未知のツール名の場合
            RuntimeError: 実行環境が準備されていない場合

        """
        with self.lock:
            # コンテナ準備状況をチェック
            if self.execution_manager._current_task is None:
                msg = "Current task not set in execution manager"
                raise RuntimeError(msg)

            task_uuid = self.execution_manager._current_task.uuid
            container_info = self.execution_manager.get_container_info(task_uuid)

            if container_info is None or container_info.status != "ready":
                msg = (
                    f"Execution environment not ready for task {task_uuid}. "
                    "Please ensure prepare() is called before using tools."
                )
                raise RuntimeError(msg)

            # ツール実行
            result = self._execute_tool_internal(tool, args)

            # ExecutionEnvironmentManagerがエラー辞書を返した場合
            if isinstance(result, dict) and result.get("exit_code", 0) != 0:
                # 警告ログは出すが例外は投げない(LLMにエラー結果を返す)
                self.logger.warning(
                    "Tool execution returned error: %s",
                    result.get("stderr"),
                )

            return result

    def _execute_tool_internal(self, tool: str, args: dict[str, Any]) -> object:
        """ツール実行の内部処理.

        Args:
            tool: ツール名
            args: ツール引数

        Returns:
            実行結果

        Raises:
            ValueError: 未知のツール名の場合

        """
        if self.mcp_server_name == "command-executor":
            if tool == "execute_command":
                return self.execution_manager.execute_command(
                    command=args.get("command", ""),
                    working_directory=args.get("working_directory"),
                )
            msg = f"Unknown command-executor tool: {tool}"
            raise ValueError(msg)

        if self.mcp_server_name == "text":
            # text_editorツールは単一ツール、commandパラメータで動作切替
            return self.execution_manager.call_text_editor_tool(tool="text_editor", arguments=args)

        msg = f"Unknown MCP server: {self.mcp_server_name}"
        raise ValueError(msg)

    def get_function_calling_functions(self) -> list[dict[str, Any]]:
        """Function calling用の関数定義を返す.

        Returns:
            サーバー種別に応じた関数定義リスト

        """
        if self.mcp_server_name == "command-executor":
            return self.execution_manager.get_function_calling_functions()
        if self.mcp_server_name == "text":
            return self.execution_manager.get_text_editor_functions()
        return []

    def get_function_calling_tools(self) -> list[dict[str, Any]]:
        """OpenAI形式のツール定義を返す.

        Returns:
            サーバー種別に応じたツール定義リスト

        """
        if self.mcp_server_name == "command-executor":
            return self.execution_manager.get_function_calling_tools()
        if self.mcp_server_name == "text":
            return self.execution_manager.get_text_editor_tools()
        return []

    @property
    def system_prompt(self) -> str:
        """システムプロンプト文字列を返す.

        Returns:
            サーバー種別に応じたシステムプロンプト

        """
        if self.mcp_server_name == "command-executor":
            return self._generate_command_executor_system_prompt()
        if self.mcp_server_name == "text":
            return self._generate_text_editor_system_prompt()
        return ""

    def _generate_command_executor_system_prompt(self) -> str:
        """command-executor用のシステムプロンプトを生成する.

        Returns:
            許可コマンドリスト等を含むプロンプト文字列

        """
        allowed_commands = self.execution_manager.get_allowed_commands_text()
        return f"""### command-executor mcp tools
コンテナ化された隔離環境でコマンドを実行できます。プロジェクトは既にクローン済みです。

許可されているコマンド:
{allowed_commands}

* `command-executor_execute_command` → {{ "command": string, "working_directory"?: string }} --- Execute a command in an isolated Docker execution environment"""

    def _generate_text_editor_system_prompt(self) -> str:
        """text-editor用のシステムプロンプトを生成する.

        Returns:
            テキストエディタ機能説明を含むプロンプト文字列

        """
        return """### text-editor mcp tools
プロジェクトワークスペース内のファイル表示・作成・編集が可能です。

* `text_editor` → { "command": enum["view","create","str_replace","insert","undo_edit"], "path": string, ... } --- ファイル操作ツール"""

    def call_initialize(self) -> None:
        """初期化処理.

        ExecutionEnvironmentManagerでは不要なのでパススルー。
        """
        pass

    def list_tools(self) -> list[Tool]:
        """ツールリストを取得する.

        MCPToolClientとの互換性のために実装。

        Returns:
            mcp.types.Tool形式のツールリスト

        """
        from mcp.types import Tool

        functions = self.get_function_calling_functions()
        return [
            Tool(
                name=f["name"],
                description=f.get("description", ""),
                inputSchema=f.get("parameters", {}),
            )
            for f in functions
        ]

    def close(self) -> None:
        """クライアントをクローズする.

        ExecutionEnvironmentManagerはTaskHandler側でcleanupされるため、ここでは何もしない。
        """
        pass
