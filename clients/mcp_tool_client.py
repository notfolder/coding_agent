import hashlib
from mcp import StdioServerParameters
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client
from mcp.types import TextContent, Tool, ClientNotification, InitializedNotification,EmbeddedResource,TextResourceContents
import threading
import logging
import json
import os
import asyncio

class MCPToolClient:
    def __init__(self, server_config, function_calling=True):
        self.server_config = server_config
        self.lock = threading.Lock()
        self._system_prompt = None
        self.function_calling = function_calling

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

    def _git_blob_sha1_from_str(self, s: str, encoding: str = 'utf-8') -> str:
        """
        Git blob SHA‑1 を文字列から計算する。
        - s: テキスト文字列（例："Hello\n"）
        - encoding: バイト化に使用するエンコーディング
        """
        data = s.encode(encoding)
        header = f"blob {len(data)}\0".encode('utf-8')
        full = header + data
        return hashlib.sha1(full).hexdigest()

    def _call_tool_sync(self, tool, args):
        # tool_name = tool.split('_', 1)[1]
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
            elif isinstance(content, EmbeddedResource):
                resource = content.resource
                if isinstance(resource, TextResourceContents):
                    text = resource.text
                    sha = self._git_blob_sha1_from_str(text)
                    results.append({'text': text, 'sha': sha})
                else:
                    results.append(result)
            else:
                results.append(content)

        return results[0] if len(results) == 1 else results

    def _list_tools_sync(self):
        async def coro_fn(session):
            return await session.list_tools()
        return self._run_with_session(coro_fn)

    def _get_tools_sync(self):
        mcp_name = self.server_config.get('mcp_server_name', '')
        tools = self.list_tools().tools
        return mcp_name, tools

    def get_function_calling_tools(self):
        mcp_name, tools = self._get_tools_sync()
        return [{
            "type": "function",
            "function": {
                "name": f"{mcp_name}_{tool.name}",
                "description": tool.description or '',
                "parameters": tool.inputSchema
            }
            } for tool in tools]

    def get_function_calling_functions(self):
        mcp_name, tools = self._get_tools_sync()
        return [{
            "name": f"{mcp_name}_{tool.name}",
            "description": tool.description or '',
            "parameters": tool.inputSchema
            } for tool in tools]

    def _get_system_prompt_sync(self):
        mcp_name, tools = self._get_tools_sync()
        prompt_lines = [f"### {mcp_name} mcp tools"]
        for tool in tools:
            if isinstance(tool, Tool):
                tool = {
                    'name': tool.name,
                    'description': tool.description,
                    'inputSchema': tool.inputSchema if isinstance(tool.inputSchema, dict) else {},
                    'required': tool.inputSchema.get('required', [])
                }
            if not isinstance(tool, dict):
                continue
            tool_name = f"{mcp_name}_{tool.get('name', '')}"
            desc = tool.get('description', '') or ''
            desc = desc.replace('\n', ' ').replace('\r', ' ').strip()
            input_schema = tool.get('inputSchema', {})
            params = input_schema.get('properties', {}) if isinstance(input_schema, dict) else {}
            required = tool.get('required', []) or []
            param_str = '{ ' + ', '.join(
                (f'"{k}"' if k in required else f'"{k}"?') +
                (f': {v.get("type", "any")}' if k in required else f': [{v.get("type", "any")}]')
                for k, v in params.items()
            ) + ' }'
            prompt_lines.append(f"* `{tool_name}` → `{param_str}` --- {desc}")

        return '\n'.join(prompt_lines)
