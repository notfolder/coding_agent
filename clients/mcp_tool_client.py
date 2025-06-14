import subprocess
import threading
import queue
import json

class MCPToolClient:
    def __init__(self, server_config):
        self.server_config = server_config
        self.proc = None
        self.lock = threading.Lock()
        self._start_process()

    def _start_process(self):
        cmd = self.server_config['command']
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)

    def call_tool(self, tool, args):
        # MCP stdioプロトコルに従いコマンド送信・応答取得
        req = json.dumps({"tool": tool, "args": args}) + "\n"
        with self.lock:
            self.proc.stdin.write(req)
            self.proc.stdin.flush()
            resp = self.proc.stdout.readline()
        return json.loads(resp)

    def close(self):
        if self.proc:
            self.proc.terminate()
