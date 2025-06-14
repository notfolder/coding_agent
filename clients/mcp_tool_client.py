import subprocess
import threading
import queue
import json
import uuid

class MCPToolClient:
    def __init__(self, server_config):
        self.server_config = server_config
        self.proc = None
        self.lock = threading.Lock()
        self._start_process()
        self._id_counter = 0

    def _start_process(self):
        cmd = self.server_config['command']
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)

    def call_tool(self, tool, args):
        # toolがmcp_server/tool_name形式ならtool_nameだけにする
        if '/' in tool:
            tool = tool.split('/', 1)[1]
        self._id_counter += 1
        req_obj = {
            "jsonrpc": "2.0",
            "id": self._id_counter,
            "method": tool,
            "params": args
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
                    return resp_obj.get("result", resp_obj)

    def close(self):
        if self.proc:
            self.proc.terminate()
