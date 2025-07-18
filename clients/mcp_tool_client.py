from __future__ import annotations

import asyncio
import hashlib
import json
import os
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

from mcp import StdioServerParameters
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client
from mcp.types import (
    ClientNotification,
    EmbeddedResource,
    InitializedNotification,
    TextContent,
    TextResourceContents,
    Tool,
)


class MCPToolClient:
    def __init__(self, server_config: dict[str, Any], *, function_calling: bool = True) -> None:
        self.server_config = server_config
        self.lock = threading.Lock()
        self._system_prompt = None
        self.function_calling = function_calling

    def call_tool(self, tool: str, args: dict[str, Any]) -> object:
        with self.lock:
            return self._call_tool_sync(tool, args)

    def call_initialize(self) -> None:
        # MCPのClientSessionは自動でinitializeを呼ぶので何もしない
        return None

    def list_tools(self) -> list[Tool]:
        with self.lock:
            return self._list_tools_sync()

    @property
    def system_prompt(self) -> str:
        return self._get_system_prompt_sync()

    def close(self) -> None:
        pass  # クライアントの状態管理が不要になったため何もしない

    def _run_async(self, coro: Awaitable[object]) -> object:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def _run_with_session(self, coro_fn: Callable[[ClientSession], Awaitable[object]]) -> object:
        async def wrapper() -> object:
            cmd = self.server_config["command"][0]
            args = self.server_config["command"][1:]
            env = self.server_config.get("env", {})
            merged_env = dict(os.environ)
            merged_env.update(env)
            server_params = StdioServerParameters(command=cmd, args=args, env=merged_env)
            async with (
                stdio_client(server_params) as (read_stream, write_stream),
                ClientSession(read_stream, write_stream) as session,
            ):
                await session.initialize()
                # notifications/initialized送信
                notification = ClientNotification(
                    InitializedNotification(method="notifications/initialized"),
                )
                await session.send_notification(notification)
                return await coro_fn(session)

        return self._run_async(wrapper())

    def _git_blob_sha1_from_str(self, s: str, encoding: str = "utf-8") -> str:
        r"""Git blob SHA-1 を文字列から計算する.

        - s: テキスト文字列(例:"Hello\n")
        - encoding: バイト化に使用するエンコーディング.
        """
        data = s.encode(encoding)
        header = f"blob {len(data)}\0".encode()
        full = header + data
        return hashlib.sha1(full, usedforsecurity=False).hexdigest()

    def _call_tool_sync(self, tool: str, args: dict[str, Any]) -> object:
        tool_name = tool

        async def coro_fn(session: ClientSession) -> object:
            return await session.call_tool(tool_name, args)

        result = self._run_with_session(coro_fn)

        results = []
        for content in result.content:
            if isinstance(content, TextContent):
                try:
                    obj = json.loads(content.text)
                    results.append(obj)
                except (json.JSONDecodeError, ValueError):
                    results.append(content.text)
            elif isinstance(content, EmbeddedResource):
                resource = content.resource
                if isinstance(resource, TextResourceContents):
                    text = resource.text
                    sha = self._git_blob_sha1_from_str(text)
                    results.append({"text": text, "sha": sha})
                else:
                    results.append(result)
            else:
                results.append(content)

        return results[0] if len(results) == 1 else results

    def _list_tools_sync(self) -> object:
        async def coro_fn(session: ClientSession) -> object:
            return await session.list_tools()

        return self._run_with_session(coro_fn)

    def _get_tools_sync(self) -> tuple[str, list[Tool]]:
        mcp_name = self.server_config.get("mcp_server_name", "")
        tools = self.list_tools().tools
        return mcp_name, tools

    def get_function_calling_tools(self) -> list[dict[str, Any]]:
        mcp_name, tools = self._get_tools_sync()
        return [
            {
                "type": "function",
                "function": {
                    "name": f"{mcp_name}_{tool.name}",
                    "description": tool.description or "",
                    "parameters": tool.inputSchema,
                },
            }
            for tool in tools
        ]

    def get_function_calling_functions(self) -> list[dict[str, Any]]:
        mcp_name, tools = self._get_tools_sync()
        return [
            {
                "name": f"{mcp_name}_{tool.name}",
                "description": tool.description or "",
                "parameters": tool.inputSchema,
            }
            for tool in tools
        ]

    def _get_system_prompt_sync(self) -> str:
        mcp_name, tools = self._get_tools_sync()
        prompt_lines = [f"### {mcp_name} mcp tools"]
        for tool_obj in tools:
            if isinstance(tool_obj, Tool):
                tool_dict = {
                    "name": tool_obj.name,
                    "description": tool_obj.description,
                    "inputSchema": (
                        tool_obj.inputSchema
                        if isinstance(tool_obj.inputSchema, dict)
                        else {}
                    ),
                    "required": tool_obj.inputSchema.get("required", []),
                }
            else:
                tool_dict = tool_obj
            if not isinstance(tool_dict, dict):
                continue
            tool_name = f"{mcp_name}_{tool_dict.get('name', '')}"
            desc = tool_dict.get("description", "") or ""
            desc = desc.replace("\n", " ").replace("\r", " ").strip()
            input_schema = tool_dict.get("inputSchema", {})
            params = input_schema.get("properties", {}) if isinstance(input_schema, dict) else {}
            required = tool_dict.get("required", []) or []
            param_str = (
                "{ "
                + ", ".join(
                    (f'"{k}"' if k in required else f'"{k}"?')
                    + (
                        f": {v.get('type', 'any')}"
                        if k in required
                        else f": [{v.get('type', 'any')}]"
                    )
                    for k, v in params.items()
                )
                + " }"
            )
            prompt_lines.append(f"* `{tool_name}` → `{param_str}` --- {desc}")

        return "\n".join(prompt_lines)
