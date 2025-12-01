"""TextEditorMCPClientのユニットテスト.

TextEditorMCPClientクラスの単体テストを提供します。
"""
from __future__ import annotations

import json
from unittest import mock

import pytest

from clients.text_editor_mcp_client import (
    TextEditorMCPClient,
    TextEditorToolResult,
)


class TestTextEditorToolResult:
    """TextEditorToolResultデータクラスのテスト."""

    def test_result_creation_success(self) -> None:
        """成功結果の作成をテストする."""
        result = TextEditorToolResult(
            success=True,
            content="file content",
            error="",
        )
        assert result.success is True
        assert result.content == "file content"
        assert result.error == ""

    def test_result_creation_error(self) -> None:
        """エラー結果の作成をテストする."""
        result = TextEditorToolResult(
            success=False,
            content="",
            error="File not found",
        )
        assert result.success is False
        assert result.content == ""
        assert result.error == "File not found"

    def test_result_default_error(self) -> None:
        """デフォルトエラー値をテストする."""
        result = TextEditorToolResult(
            success=True,
            content="content",
        )
        assert result.error == ""


class TestTextEditorMCPClient:
    """TextEditorMCPClientのテスト."""

    def test_client_creation(self) -> None:
        """クライアント作成をテストする."""
        client = TextEditorMCPClient(
            container_id="test-container",
            workspace_path="/workspace/project",
            timeout_seconds=30,
        )
        assert client.container_id == "test-container"
        assert client.workspace_path == "/workspace/project"
        assert client.timeout_seconds == 30
        assert client._process is None
        assert client._initialized is False

    def test_client_creation_defaults(self) -> None:
        """デフォルト値でのクライアント作成をテストする."""
        client = TextEditorMCPClient(container_id="test-container")
        assert client.container_id == "test-container"
        assert client.workspace_path == "/workspace/project"
        assert client.timeout_seconds == 30

    def test_get_next_request_id(self) -> None:
        """リクエストID生成をテストする."""
        client = TextEditorMCPClient(container_id="test-container")
        initial_id = client._get_next_request_id()
        next_id = client._get_next_request_id()
        assert next_id == initial_id + 1

    def test_is_running_not_started(self) -> None:
        """未起動時のis_runningをテストする."""
        client = TextEditorMCPClient(container_id="test-container")
        assert client.is_running() is False

    @mock.patch("subprocess.Popen")
    def test_is_running_started(self, mock_popen: mock.Mock) -> None:
        """起動時のis_runningをテストする."""
        mock_process = mock.Mock()
        mock_process.poll.return_value = None  # プロセスは実行中
        mock_popen.return_value = mock_process

        client = TextEditorMCPClient(container_id="test-container")
        client._process = mock_process
        assert client.is_running() is True

    @mock.patch("subprocess.Popen")
    def test_is_running_stopped(self, mock_popen: mock.Mock) -> None:
        """停止時のis_runningをテストする."""
        mock_process = mock.Mock()
        mock_process.poll.return_value = 0  # プロセスは終了
        mock_popen.return_value = mock_process

        client = TextEditorMCPClient(container_id="test-container")
        client._process = mock_process
        assert client.is_running() is False

    def test_call_tool_not_initialized(self) -> None:
        """未初期化時のツール呼び出しエラーをテストする."""
        client = TextEditorMCPClient(container_id="test-container")
        with pytest.raises(RuntimeError, match="not initialized"):
            client.call_tool("view", {"path": "/test"})


class TestTextEditorMCPClientFunctions:
    """TextEditorMCPClientの関数定義テスト."""

    def test_get_function_calling_functions(self) -> None:
        """Function calling関数定義取得をテストする."""
        client = TextEditorMCPClient(container_id="test-container")
        functions = client.get_function_calling_functions()

        assert len(functions) == 5
        function_names = [f["name"] for f in functions]
        assert "text_editor_view" in function_names
        assert "text_editor_create" in function_names
        assert "text_editor_str_replace" in function_names
        assert "text_editor_insert" in function_names
        assert "text_editor_undo_edit" in function_names

    def test_get_function_calling_tools(self) -> None:
        """Function callingツール定義取得をテストする."""
        client = TextEditorMCPClient(container_id="test-container")
        tools = client.get_function_calling_tools()

        assert len(tools) == 5
        for tool in tools:
            assert tool["type"] == "function"
            assert "function" in tool

    def test_view_function_schema(self) -> None:
        """view関数のスキーマをテストする."""
        client = TextEditorMCPClient(container_id="test-container")
        functions = client.get_function_calling_functions()
        view_func = next(f for f in functions if f["name"] == "text_editor_view")

        params = view_func["parameters"]
        assert params["type"] == "object"
        assert "path" in params["properties"]
        assert "view_range" in params["properties"]
        assert params["required"] == ["path"]

    def test_create_function_schema(self) -> None:
        """create関数のスキーマをテストする."""
        client = TextEditorMCPClient(container_id="test-container")
        functions = client.get_function_calling_functions()
        create_func = next(f for f in functions if f["name"] == "text_editor_create")

        params = create_func["parameters"]
        assert params["type"] == "object"
        assert "path" in params["properties"]
        assert "file_text" in params["properties"]
        assert set(params["required"]) == {"path", "file_text"}

    def test_str_replace_function_schema(self) -> None:
        """str_replace関数のスキーマをテストする."""
        client = TextEditorMCPClient(container_id="test-container")
        functions = client.get_function_calling_functions()
        replace_func = next(
            f for f in functions if f["name"] == "text_editor_str_replace"
        )

        params = replace_func["parameters"]
        assert params["type"] == "object"
        assert "path" in params["properties"]
        assert "old_str" in params["properties"]
        assert "new_str" in params["properties"]
        assert set(params["required"]) == {"path", "old_str", "new_str"}


class TestTextEditorMCPClientConvenienceMethods:
    """TextEditorMCPClientの便利メソッドのテスト."""

    @mock.patch.object(TextEditorMCPClient, "call_tool")
    def test_view_method(self, mock_call_tool: mock.Mock) -> None:
        """viewメソッドをテストする."""
        mock_call_tool.return_value = TextEditorToolResult(
            success=True,
            content="file content",
        )
        client = TextEditorMCPClient(container_id="test-container")
        result = client.view("/test/path.py")

        mock_call_tool.assert_called_once_with("view", {"path": "/test/path.py"})
        assert result.success is True
        assert result.content == "file content"

    @mock.patch.object(TextEditorMCPClient, "call_tool")
    def test_view_method_with_range(self, mock_call_tool: mock.Mock) -> None:
        """範囲指定でのviewメソッドをテストする."""
        mock_call_tool.return_value = TextEditorToolResult(
            success=True,
            content="partial content",
        )
        client = TextEditorMCPClient(container_id="test-container")
        result = client.view("/test/path.py", view_range=[1, 10])

        mock_call_tool.assert_called_once_with(
            "view", {"path": "/test/path.py", "view_range": [1, 10]},
        )
        assert result.success is True

    @mock.patch.object(TextEditorMCPClient, "call_tool")
    def test_create_method(self, mock_call_tool: mock.Mock) -> None:
        """createメソッドをテストする."""
        mock_call_tool.return_value = TextEditorToolResult(
            success=True,
            content="File created",
        )
        client = TextEditorMCPClient(container_id="test-container")
        result = client.create("/test/new.py", "print('hello')")

        mock_call_tool.assert_called_once_with(
            "create", {"path": "/test/new.py", "file_text": "print('hello')"},
        )
        assert result.success is True

    @mock.patch.object(TextEditorMCPClient, "call_tool")
    def test_str_replace_method(self, mock_call_tool: mock.Mock) -> None:
        """str_replaceメソッドをテストする."""
        mock_call_tool.return_value = TextEditorToolResult(
            success=True,
            content="Replacement done",
        )
        client = TextEditorMCPClient(container_id="test-container")
        result = client.str_replace("/test/file.py", "old", "new")

        mock_call_tool.assert_called_once_with(
            "str_replace", {"path": "/test/file.py", "old_str": "old", "new_str": "new"},
        )
        assert result.success is True

    @mock.patch.object(TextEditorMCPClient, "call_tool")
    def test_insert_method(self, mock_call_tool: mock.Mock) -> None:
        """insertメソッドをテストする."""
        mock_call_tool.return_value = TextEditorToolResult(
            success=True,
            content="Insertion done",
        )
        client = TextEditorMCPClient(container_id="test-container")
        result = client.insert("/test/file.py", 5, "# comment")

        mock_call_tool.assert_called_once_with(
            "insert", {"path": "/test/file.py", "insert_line": 5, "new_str": "# comment"},
        )
        assert result.success is True

    @mock.patch.object(TextEditorMCPClient, "call_tool")
    def test_undo_edit_method(self, mock_call_tool: mock.Mock) -> None:
        """undo_editメソッドをテストする."""
        mock_call_tool.return_value = TextEditorToolResult(
            success=True,
            content="Undo done",
        )
        client = TextEditorMCPClient(container_id="test-container")
        result = client.undo_edit("/test/file.py")

        mock_call_tool.assert_called_once_with("undo_edit", {"path": "/test/file.py"})
        assert result.success is True


class TestTextEditorMCPInExecutionEnvironmentManager:
    """ExecutionEnvironmentManagerのtext-editor MCP関連機能のテスト."""

    def test_text_editor_enabled_default(self) -> None:
        """デフォルトでtext_editor有効をテストする."""
        from handlers.execution_environment_manager import ExecutionEnvironmentManager

        config: dict = {}
        manager = ExecutionEnvironmentManager(config)
        # デフォルトはTrue
        assert manager.is_text_editor_enabled() is True

    def test_text_editor_enabled_from_config_true(self) -> None:
        """設定ファイルからのtext_editor有効化をテストする."""
        from handlers.execution_environment_manager import ExecutionEnvironmentManager

        config = {"text_editor_mcp": {"enabled": True}}
        manager = ExecutionEnvironmentManager(config)
        assert manager.is_text_editor_enabled() is True

    def test_text_editor_enabled_from_config_false(self) -> None:
        """設定ファイルからのtext_editor無効化をテストする."""
        from handlers.execution_environment_manager import ExecutionEnvironmentManager

        config = {"text_editor_mcp": {"enabled": False}}
        manager = ExecutionEnvironmentManager(config)
        assert manager.is_text_editor_enabled() is False

    def test_text_editor_enabled_from_env_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """環境変数からのtext_editor有効化をテストする."""
        from handlers.execution_environment_manager import ExecutionEnvironmentManager

        monkeypatch.setenv("TEXT_EDITOR_MCP_ENABLED", "true")
        config = {"text_editor_mcp": {"enabled": False}}
        manager = ExecutionEnvironmentManager(config)
        # 環境変数が優先される
        assert manager.is_text_editor_enabled() is True

    def test_text_editor_enabled_from_env_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """環境変数からのtext_editor無効化をテストする."""
        from handlers.execution_environment_manager import ExecutionEnvironmentManager

        monkeypatch.setenv("TEXT_EDITOR_MCP_ENABLED", "false")
        config = {"text_editor_mcp": {"enabled": True}}
        manager = ExecutionEnvironmentManager(config)
        # 環境変数が優先される
        assert manager.is_text_editor_enabled() is False

    def test_get_text_editor_functions(self) -> None:
        """text-editor関数定義取得をテストする."""
        from handlers.execution_environment_manager import ExecutionEnvironmentManager

        config = {"text_editor_mcp": {"enabled": True}}
        manager = ExecutionEnvironmentManager(config)
        functions = manager.get_text_editor_functions()

        assert len(functions) == 5
        function_names = [f["name"] for f in functions]
        assert "text_editor_view" in function_names
        assert "text_editor_create" in function_names

    def test_get_text_editor_functions_disabled(self) -> None:
        """無効時のtext-editor関数定義取得をテストする."""
        from handlers.execution_environment_manager import ExecutionEnvironmentManager

        config = {"text_editor_mcp": {"enabled": False}}
        manager = ExecutionEnvironmentManager(config)
        functions = manager.get_text_editor_functions()

        assert len(functions) == 0

    def test_get_text_editor_tools(self) -> None:
        """text-editorツール定義取得をテストする."""
        from handlers.execution_environment_manager import ExecutionEnvironmentManager

        config = {"text_editor_mcp": {"enabled": True}}
        manager = ExecutionEnvironmentManager(config)
        tools = manager.get_text_editor_tools()

        assert len(tools) == 5
        for tool in tools:
            assert tool["type"] == "function"

    def test_get_text_editor_client_not_started(self) -> None:
        """未起動時のtext-editorクライアント取得をテストする."""
        from handlers.execution_environment_manager import ExecutionEnvironmentManager

        config = {"text_editor_mcp": {"enabled": True}}
        manager = ExecutionEnvironmentManager(config)
        client = manager.get_text_editor_client("test-uuid")

        assert client is None

    def test_call_text_editor_tool_no_task(self) -> None:
        """タスク未設定時のツール呼び出しエラーをテストする."""
        from handlers.execution_environment_manager import ExecutionEnvironmentManager

        config = {"text_editor_mcp": {"enabled": True}}
        manager = ExecutionEnvironmentManager(config)

        with pytest.raises(RuntimeError, match="Current task not set"):
            manager.call_text_editor_tool("view", {"path": "/test"})
