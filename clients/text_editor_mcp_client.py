"""テキスト編集MCPクライアントモジュール.

bhouston/mcp-server-text-editorとの通信を管理するクラスを提供します。
コンテナ内でMCPサーバープロセスを起動し、標準入出力を介してJSON-RPCで通信します。
"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from handlers.task import Task  # noqa: F401 - Type hint import


@dataclass
class TextEditorToolResult:
    """テキストエディタツール実行結果を保持するデータクラス.

    Attributes:
        success: 実行が成功したかどうか
        content: 成功時のコンテンツ
        error: 失敗時のエラーメッセージ

    """

    success: bool
    content: str
    error: str = ""


class TextEditorMCPClient:
    """text-editor MCPサーバーとの通信を管理するクラス.

    コンテナ内でMCPサーバープロセスを起動し、JSON-RPCで通信します。
    ファイルの表示、作成、編集、取り消し操作をサポートします。
    """

    # MCP JSON-RPC リクエストID管理
    _request_id_counter: int = 0
    _id_lock: threading.Lock = threading.Lock()

    def __init__(
        self,
        container_id: str,
        workspace_path: str = "/workspace/project",
        timeout_seconds: int = 30,
    ) -> None:
        """TextEditorMCPClientを初期化する.

        Args:
            container_id: DockerコンテナID
            workspace_path: コンテナ内の作業ディレクトリパス
            timeout_seconds: コマンド実行タイムアウト(秒)

        """
        self.container_id = container_id
        self.workspace_path = workspace_path
        self.timeout_seconds = timeout_seconds
        self.logger = logging.getLogger(__name__)

        # MCPサーバープロセス
        self._process: subprocess.Popen | None = None
        self._initialized = False

    def _get_next_request_id(self) -> int:
        """次のリクエストIDを取得する.

        Returns:
            ユニークなリクエストID

        """
        with self._id_lock:
            TextEditorMCPClient._request_id_counter += 1
            return TextEditorMCPClient._request_id_counter

    def start(self) -> None:
        """MCPサーバープロセスを起動する.

        コンテナ内でmcp-server-text-editorを起動し、初期化を行います。

        Raises:
            RuntimeError: サーバー起動に失敗した場合

        """
        if self._process is not None:
            self.logger.warning("MCPサーバーは既に起動しています")
            return

        try:
            # コンテナ内でMCPサーバーを起動
            cmd = [
                "docker",
                "exec",
                "-i",
                "-w",
                self.workspace_path,
                self.container_id,
                "npx",
                "-y",
                "mcp-server-text-editor",
            ]

            self.logger.info("text-editor MCPサーバーを起動します: %s", " ".join(cmd))

            self._process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # 行バッファリング
            )

            # MCPサーバーの初期化
            self._initialize_server()
            self._initialized = True

            self.logger.info("text-editor MCPサーバーが起動しました")

        except Exception as e:
            self.logger.exception("text-editor MCPサーバーの起動に失敗しました")
            self.stop()
            msg = f"Failed to start text-editor MCP server: {e}"
            raise RuntimeError(msg) from e

    def _initialize_server(self) -> None:
        """MCPサーバーを初期化する.

        MCP初期化リクエストを送信し、サーバーの準備完了を確認します。

        Raises:
            RuntimeError: 初期化に失敗した場合

        """
        # MCPの初期化リクエスト
        init_request = {
            "jsonrpc": "2.0",
            "id": self._get_next_request_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "coding-agent-text-editor",
                    "version": "1.0.0",
                },
            },
        }

        response = self._send_request(init_request)

        if "error" in response:
            msg = f"MCP initialization failed: {response['error']}"
            raise RuntimeError(msg)

        # 初期化完了通知を送信
        initialized_notification = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        }
        self._send_notification(initialized_notification)

        self.logger.debug("MCPサーバーの初期化が完了しました")

    def stop(self) -> None:
        """MCPサーバープロセスを停止する."""
        if self._process is None:
            return

        try:
            self.logger.info("text-editor MCPサーバーを停止します")

            # 正常終了を試みる
            if self._process.stdin:
                self._process.stdin.close()

            self._process.terminate()

            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()

            self.logger.info("text-editor MCPサーバーが停止しました")

        except Exception as e:
            self.logger.warning("MCPサーバー停止中にエラー発生: %s", e)
        finally:
            self._process = None
            self._initialized = False

    def call_tool(self, command: str, arguments: dict[str, Any]) -> TextEditorToolResult:
        """テキストエディタツールを呼び出す.

        Args:
            command: 実行するコマンド(view, create, str_replace, insert, undo_edit)
            arguments: コマンドの引数

        Returns:
            ツール実行結果

        Raises:
            RuntimeError: サーバーが起動していない場合

        """
        if not self._initialized or self._process is None:
            msg = "MCP server not initialized. Call start() first."
            raise RuntimeError(msg)

        # コマンドを引数に追加
        tool_arguments = {"command": command, **arguments}

        # ツール呼び出しリクエスト
        request = {
            "jsonrpc": "2.0",
            "id": self._get_next_request_id(),
            "method": "tools/call",
            "params": {
                "name": "text_editor",
                "arguments": tool_arguments,
            },
        }

        self.logger.debug("text_editorツール呼び出し: %s %s", command, arguments)

        try:
            response = self._send_request(request)

            if "error" in response:
                error_msg = response["error"].get("message", str(response["error"]))
                self.logger.warning("text_editorツールエラー: %s", error_msg)
                return TextEditorToolResult(
                    success=False,
                    content="",
                    error=error_msg,
                )

            # 結果を取得
            result = response.get("result", {})
            content_list = result.get("content", [])

            # コンテンツを文字列として結合
            content_parts = []
            for item in content_list:
                if isinstance(item, dict) and "text" in item:
                    content_parts.append(item["text"])
                elif isinstance(item, str):
                    content_parts.append(item)

            content = "\n".join(content_parts)

            # エラーチェック(isError フラグ)
            is_error = result.get("isError", False)
            if is_error:
                return TextEditorToolResult(
                    success=False,
                    content="",
                    error=content,
                )

            return TextEditorToolResult(
                success=True,
                content=content,
                error="",
            )

        except Exception as e:
            self.logger.exception("text_editorツール呼び出し中にエラー発生")
            return TextEditorToolResult(
                success=False,
                content="",
                error=str(e),
            )

    def _send_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """JSON-RPCリクエストを送信し、レスポンスを受信する.

        Args:
            request: JSON-RPCリクエスト辞書

        Returns:
            JSON-RPCレスポンス辞書

        Raises:
            RuntimeError: 通信エラーの場合

        """
        if self._process is None or self._process.stdin is None or self._process.stdout is None:
            msg = "MCP server process not available"
            raise RuntimeError(msg)

        try:
            # リクエストを送信
            request_json = json.dumps(request) + "\n"
            self._process.stdin.write(request_json)
            self._process.stdin.flush()

            # レスポンスを受信
            response_line = self._process.stdout.readline()

            if not response_line:
                msg = "No response from MCP server"
                raise RuntimeError(msg)

            return json.loads(response_line.strip())

        except json.JSONDecodeError as e:
            msg = f"Failed to parse MCP response: {e}"
            raise RuntimeError(msg) from e
        except Exception as e:
            msg = f"MCP communication error: {e}"
            raise RuntimeError(msg) from e

    def _send_notification(self, notification: dict[str, Any]) -> None:
        """JSON-RPC通知を送信する(レスポンスなし).

        Args:
            notification: JSON-RPC通知辞書

        """
        if self._process is None or self._process.stdin is None:
            return

        try:
            notification_json = json.dumps(notification) + "\n"
            self._process.stdin.write(notification_json)
            self._process.stdin.flush()
        except Exception as e:
            self.logger.warning("通知送信中にエラー発生: %s", e)

    # ---- 便利メソッド: 各コマンドをラップ ----

    def view(
        self,
        path: str,
        view_range: list[int] | None = None,
    ) -> TextEditorToolResult:
        """ファイルまたはディレクトリの内容を表示する.

        Args:
            path: 表示対象のパス
            view_range: 表示する行範囲 [開始行, 終了行](オプション)

        Returns:
            ツール実行結果

        """
        args: dict[str, Any] = {"path": path}
        if view_range is not None:
            args["view_range"] = view_range
        return self.call_tool("view", args)

    def create(self, path: str, file_text: str) -> TextEditorToolResult:
        """新しいファイルを作成する.

        Args:
            path: 作成するファイルのパス
            file_text: ファイルの内容

        Returns:
            ツール実行結果

        """
        return self.call_tool("create", {"path": path, "file_text": file_text})

    def str_replace(
        self,
        path: str,
        old_str: str,
        new_str: str,
    ) -> TextEditorToolResult:
        """ファイル内の文字列を置換する.

        Args:
            path: 編集対象のファイルパス
            old_str: 置換対象の文字列
            new_str: 置換後の文字列

        Returns:
            ツール実行結果

        """
        return self.call_tool(
            "str_replace",
            {"path": path, "old_str": old_str, "new_str": new_str},
        )

    def insert(
        self,
        path: str,
        insert_line: int,
        new_str: str,
    ) -> TextEditorToolResult:
        """指定した行に新しいテキストを挿入する.

        Args:
            path: 編集対象のファイルパス
            insert_line: 挿入位置の行番号
            new_str: 挿入するテキスト

        Returns:
            ツール実行結果

        """
        return self.call_tool(
            "insert",
            {"path": path, "insert_line": insert_line, "new_str": new_str},
        )

    def undo_edit(self, path: str) -> TextEditorToolResult:
        """直前のファイル編集を取り消す.

        Args:
            path: 取り消し対象のファイルパス

        Returns:
            ツール実行結果

        """
        return self.call_tool("undo_edit", {"path": path})

    def is_running(self) -> bool:
        """MCPサーバーが実行中かどうかを確認する.

        Returns:
            実行中の場合True

        """
        if self._process is None:
            return False
        return self._process.poll() is None

    def get_function_calling_functions(self) -> list[dict[str, Any]]:
        """Return function definitions for function calling.

        Returns:
            関数定義のリスト

        """
        return [
            {
                "name": "text_editor_view",
                "description": "View the content of a file or list directory contents.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "File or directory path to view",
                        },
                        "view_range": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "Optional line range [start, end] for files",
                        },
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "text_editor_create",
                "description": "Create a new file with specified content. The file must not already exist.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path for the new file",
                        },
                        "file_text": {
                            "type": "string",
                            "description": "Content for the new file",
                        },
                    },
                    "required": ["path", "file_text"],
                },
            },
            {
                "name": "text_editor_str_replace",
                "description": "Replace a specific string in a file. The old_str must match exactly one location.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "File path to edit",
                        },
                        "old_str": {
                            "type": "string",
                            "description": "Exact string to replace",
                        },
                        "new_str": {
                            "type": "string",
                            "description": "Replacement string",
                        },
                    },
                    "required": ["path", "old_str", "new_str"],
                },
            },
            {
                "name": "text_editor_insert",
                "description": "Insert new text at the specified line number.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "File path to edit",
                        },
                        "insert_line": {
                            "type": "integer",
                            "description": "Line number to insert at",
                        },
                        "new_str": {
                            "type": "string",
                            "description": "Text to insert",
                        },
                    },
                    "required": ["path", "insert_line", "new_str"],
                },
            },
            {
                "name": "text_editor_undo_edit",
                "description": "Revert the most recent edit to a file.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "File path to undo",
                        },
                    },
                    "required": ["path"],
                },
            },
        ]

    def get_function_calling_tools(self) -> list[dict[str, Any]]:
        """Return tool definitions for function calling (OpenAI format).

        Returns:
            ツール定義のリスト

        """
        functions = self.get_function_calling_functions()
        return [
            {
                "type": "function",
                "function": func,
            }
            for func in functions
        ]
