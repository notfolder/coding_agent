from mcp import StdioServerParameters
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client
from mcp.types import TextContent, Tool, ClientNotification, InitializedNotification
import threading
import logging
import json
import os
import asyncio

class MCPToolClient:
    def __init__(self, server_config):
        self.server_config = server_config
        self.lock = threading.Lock()
        self._system_prompt = None

    def call_tool(self, tool, args):
        with self.lock:
            return self._call_tool_sync(tool, args)

    def call_initialize(self):
        # MCPのClientSessionは自動でinitializeを呼ぶので何もしない
        return None

    def list_tools(self):
        with self.lock:
            return self._list_tools_sync()

    @property
    def system_prompt(self):
        return self._get_system_prompt_sync()

    def close(self):
        pass  # クライアントの状態管理が不要になったため何もしない

    def _run_async(self, coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def _run_with_session(self, coro_fn):
        async def wrapper():
            cmd = self.server_config['command'][0]
            args = self.server_config['command'][1:]
            env = self.server_config.get('env', {})
            merged_env = dict(os.environ)
            merged_env.update(env)
            server_params = StdioServerParameters(command=cmd, args=args, env=merged_env)
            async with stdio_client(server_params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    # notifications/initialized送信
                    notification = ClientNotification(
                        InitializedNotification(
                            method="notifications/initialized"
                        )
                    )
                    await session.send_notification(notification)
                    return await coro_fn(session)
        return self._run_async(wrapper())

    def _call_tool_sync(self, tool, args):
        if '/' in tool:
            tool_name = tool.split('/', 1)[1]
        else:
            tool_name = tool

        async def coro_fn(session):
            return await session.call_tool(tool_name, args)

        result = self._run_with_session(coro_fn)

        results = []
        for content in result.content:
            if isinstance(content, TextContent):
                try:
                    obj = json.loads(content.text)
                    results.append(obj)
                except Exception:
                    results.append(content.text)
            else:
                results.append(content)

        return results[0] if len(results) == 1 else results

    def _list_tools_sync(self):
        async def coro_fn(session):
            return await session.list_tools()
        return self._run_with_session(coro_fn)

    def _get_system_prompt_sync(self):
        mcp_name = self.server_config.get('mcp_server_name', '')
        tools = self.list_tools().tools

        prompt_lines = [f"### {mcp_name} mcp tools"]
        for tool in tools:
            if isinstance(tool, Tool):
                tool = {
                    'name': tool.name,
                    'description': tool.description,
                    'inputSchema': tool.inputSchema if isinstance(tool.inputSchema, dict) else {},
                }
            if not isinstance(tool, dict):
                continue
            tool_name = f"{mcp_name}/{tool.get('name', '')}"
            desc = tool.get('description', '') or ''
            desc = desc.replace('\n', ' ').replace('\r', ' ').strip()
            input_schema = tool.get('inputSchema', {})
            params = input_schema.get('properties', {}) if isinstance(input_schema, dict) else {}
            param_str = '{ ' + ', '.join(f'"{k}": {v.get("type", "any")}' for k, v in params.items()) + ' }'
            prompt_lines.append(f"* `{tool_name}` → `{param_str}` --- {desc}")

        return '\n'.join(prompt_lines)
