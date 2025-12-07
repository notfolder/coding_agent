"""Playwright MCPクライアントモジュール.

@executeautomation/playwright-mcp-serverとの通信を管理するクラスを提供します。
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
class PlaywrightToolResult:
    """Playwrightツール実行結果を保持するデータクラス.

    Attributes:
        success: 実行が成功したかどうか
        content: 成功時のコンテンツ
        error: 失敗時のエラーメッセージ

    """

    success: bool
    content: str
    error: str = ""


class PlaywrightMCPClient:
    """Playwright MCPサーバーとの通信を管理するクラス.

    コンテナ内でMCPサーバープロセスを起動し、JSON-RPCで通信します。
    ブラウザ操作、スクリーンショット撮影、要素操作などをサポートします。
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
        """PlaywrightMCPClientを初期化する.

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
            PlaywrightMCPClient._request_id_counter += 1
            return PlaywrightMCPClient._request_id_counter

    def start(self) -> None:
        """MCPサーバープロセスを起動する.

        コンテナ内で@executeautomation/playwright-mcp-serverを起動し、初期化を行います。

        Raises:
            RuntimeError: サーバー起動に失敗した場合

        """
        if self._process is not None:
            self.logger.warning("Playwright MCPサーバーは既に起動しています")
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
                "@executeautomation/playwright-mcp-server",
            ]

            self.logger.info("Playwright MCPサーバーを起動します: %s", " ".join(cmd))

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

            self.logger.info("Playwright MCPサーバーが起動しました")

        except Exception as e:
            self.logger.exception("Playwright MCPサーバーの起動に失敗しました")
            self.stop()
            msg = f"Failed to start Playwright MCP server: {e}"
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
                    "name": "coding-agent-playwright",
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

        self.logger.debug("Playwright MCPサーバーの初期化が完了しました")

    def stop(self) -> None:
        """MCPサーバープロセスを停止する."""
        if self._process is None:
            return

        try:
            self.logger.info("Playwright MCPサーバーを停止します")

            # 正常終了を試みる
            if self._process.stdin:
                self._process.stdin.close()

            self._process.terminate()

            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()

            self.logger.info("Playwright MCPサーバーが停止しました")

        except Exception as e:
            self.logger.warning("Playwright MCPサーバー停止中にエラー発生: %s", e)
        finally:
            self._process = None
            self._initialized = False

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> PlaywrightToolResult:
        """Playwrightツールを呼び出す.

        Args:
            tool_name: ツール名（playwright_navigate等）
            arguments: ツールの引数

        Returns:
            ツール実行結果

        Raises:
            RuntimeError: サーバーが起動していない場合

        """
        if not self._initialized or self._process is None:
            msg = "Playwright MCP server not initialized. Call start() first."
            raise RuntimeError(msg)

        # ツール呼び出しリクエスト
        request = {
            "jsonrpc": "2.0",
            "id": self._get_next_request_id(),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }

        self.logger.debug("Playwrightツール呼び出し: %s, args: %s", tool_name, arguments)

        try:
            response = self._send_request(request)

            if "error" in response:
                error_msg = response["error"].get("message", str(response["error"]))
                self.logger.warning("Playwrightツールエラー: %s", error_msg)
                return PlaywrightToolResult(
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
                return PlaywrightToolResult(
                    success=False,
                    content="",
                    error=content,
                )

            return PlaywrightToolResult(
                success=True,
                content=content,
                error="",
            )

        except Exception as e:
            self.logger.exception("Playwrightツール呼び出し中にエラー発生")
            return PlaywrightToolResult(
                success=False,
                content="",
                error=str(e),
            )

    def _ensure_process_available(self) -> bool:
        """MCPサーバープロセスが利用可能かどうかを確認する.

        Returns:
            プロセスとstdin/stdoutが利用可能な場合True

        """
        return (
            self._process is not None
            and self._process.stdin is not None
            and self._process.stdout is not None
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
        if not self._ensure_process_available():
            msg = "Playwright MCP server process not available"
            raise RuntimeError(msg)

        try:
            # リクエストを送信
            request_json = json.dumps(request) + "\n"
            self._process.stdin.write(request_json)
            self._process.stdin.flush()

            # レスポンスを受信
            response_line = self._process.stdout.readline()

            if not response_line:
                msg = "No response from Playwright MCP server"
                raise RuntimeError(msg)

            return json.loads(response_line.strip())

        except json.JSONDecodeError as e:
            msg = f"Failed to parse Playwright MCP response: {e}"
            raise RuntimeError(msg) from e
        except Exception as e:
            msg = f"Playwright MCP communication error: {e}"
            raise RuntimeError(msg) from e

    def _send_notification(self, notification: dict[str, Any]) -> None:
        """JSON-RPC通知を送信する(レスポンスなし).

        Args:
            notification: JSON-RPC通知辞書

        """
        if not self._ensure_process_available():
            return

        try:
            notification_json = json.dumps(notification) + "\n"
            self._process.stdin.write(notification_json)
            self._process.stdin.flush()
        except Exception as e:
            self.logger.warning("Playwright通知送信中にエラー発生: %s", e)

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
                "name": "playwright_navigate",
                "description": "Navigate to a URL in the browser",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "The URL to navigate to (e.g., 'http://localhost:3000' or 'https://example.com')",
                        },
                    },
                    "required": ["url"],
                },
            },
            {
                "name": "playwright_screenshot",
                "description": "Take a screenshot of the current page or a specific element",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name for the screenshot file (without extension)",
                        },
                        "width": {
                            "type": "integer",
                            "description": "Viewport width in pixels (optional, default: 1280)",
                        },
                        "height": {
                            "type": "integer",
                            "description": "Viewport height in pixels (optional, default: 720)",
                        },
                    },
                    "required": ["name"],
                },
            },
            {
                "name": "playwright_click",
                "description": "Click an element on the page",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "selector": {
                            "type": "string",
                            "description": "CSS selector for the element to click (e.g., '#submit-button', '.login-link')",
                        },
                    },
                    "required": ["selector"],
                },
            },
            {
                "name": "playwright_fill",
                "description": "Fill a form input field with text",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "selector": {
                            "type": "string",
                            "description": "CSS selector for the input field",
                        },
                        "value": {
                            "type": "string",
                            "description": "Text to fill into the input field",
                        },
                    },
                    "required": ["selector", "value"],
                },
            },
            {
                "name": "playwright_select",
                "description": "Select an option from a dropdown/select element",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "selector": {
                            "type": "string",
                            "description": "CSS selector for the select element",
                        },
                        "value": {
                            "type": "string",
                            "description": "Value of the option to select",
                        },
                    },
                    "required": ["selector", "value"],
                },
            },
            {
                "name": "playwright_hover",
                "description": "Hover over an element",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "selector": {
                            "type": "string",
                            "description": "CSS selector for the element to hover over",
                        },
                    },
                    "required": ["selector"],
                },
            },
            {
                "name": "playwright_evaluate",
                "description": "Execute JavaScript code in the page context",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "script": {
                            "type": "string",
                            "description": "JavaScript code to execute",
                        },
                    },
                    "required": ["script"],
                },
            },
            {
                "name": "playwright_get_content",
                "description": "Get the HTML content of the current page",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
            {
                "name": "playwright_get_console_logs",
                "description": "Get browser console logs",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
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
