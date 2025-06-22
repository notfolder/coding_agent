import os
import subprocess
import threading
import queue
import json
import uuid
import logging

class MCPToolClient:
    def __init__(self, server_config):
        self.server_config = server_config
        self.proc = None
        self.lock = threading.Lock()
        self._id_counter = 0
        self._start_process()

    def _start_process(self):
        cmd = self.server_config['command']
        env = self.server_config.get('env', {})
        os.environ.update(env)
        try:
            self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)

            if self.proc.poll() is not None:
                raise RuntimeError("MCP process exited prematurely")
            
            # self.call_initialize()

        except Exception as e:
            logging.error(f"Failed to start MCP server process: {cmd}\nError: {e}")
            raise

    def call_tool(self, tool, args):
        # toolがmcp_server/tool_name形式ならtool_nameだけにする
        if '/' in tool:
            tool = tool.split('/', 1)[1]
        self._id_counter += 1
        params = {
            "name": tool,
            "arguments": args
        }
        req_obj = {
            "jsonrpc": "2.0",
            "id": self._id_counter,
            "method": "tools/call",
            "params": params
        }
        req = json.dumps(req_obj) + "\n"
        with self.lock:
            self.proc.stdin.write(req)
            self.proc.stdin.flush()
            while True:
                resp = self.proc.stdout.readline()
                if not resp:
                    raise RuntimeError("MCP server closed pipe")
                try:
                    resp_obj = json.loads(resp)
                except Exception:
                    continue
                if resp_obj.get("id") == self._id_counter:
                    if "error" in resp_obj:
                        raise RuntimeError(f"MCP error: {resp_obj['error']}")
                    result = resp_obj.get("result", resp_obj)
                    # contentフィールドがあれば0番目のtextをパースして返す
                    if (
                        isinstance(result, dict)
                        and "content" in result
                        and isinstance(result["content"], list)
                        and len(result["content"]) > 0
                        and "text" in result["content"][0]
                    ):
                        try:
                            return json.loads(result["content"][0]["text"])
                        except Exception:
                            return result["content"][0]["text"]
                    return result

    def call_initialize(self):
        """MCPサーバー初期化用の専用メソッド。id管理・ロック・エラー処理はcall_toolと同様。"""
        self._id_counter += 1
        req_obj = {
            "jsonrpc": "2.0",
            "id": self._id_counter,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "roots": {
                        "listChanged": True
                    }
                }
            },
            "clientInfo": {
                "name": "mcp_tool_client",
                "version": "1.0.0"
            }
        }
        req = json.dumps(req_obj) + "\n"
        with self.lock:
            self.proc.stdin.write(req)
            self.proc.stdin.flush()
            while True:
                resp = self.proc.stdout.readline()
                if not resp:
                    raise RuntimeError("MCP server closed pipe during initialize")
                try:
                    resp_obj = json.loads(resp)
                except Exception:
                    continue
                if resp_obj.get("id") == self._id_counter:
                    if "error" in resp_obj:
                        raise RuntimeError(f"MCP error (initialize): {resp_obj['error']}")
                    return resp_obj.get("result", resp_obj)

    def close(self):
        if self.proc:
            self.proc.terminate()
