import asyncio
from typing import List, TypedDict, Optional, Dict, Any
import os
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()

class Issue(TypedDict):
    number: int
    title: str
    body: str

class GitHubMCPClient:
    def __init__(self, mcp_config: Dict[str, Any], github_config: Dict[str, Any]):
        self.server_url = mcp_config['server_url']
        self.api_key = os.environ.get(mcp_config.get('api_key_env', ''))
        self.owner = github_config['owner']
        self.repo = github_config['repo']
        self.session: Optional[ClientSession] = None
        self.exit_stack = None
        self.stdio = None
        self.write = None
        self.loop = asyncio.get_event_loop()
        self.server_script_path = mcp_config.get('server_script_path', None)

    async def _connect(self):
        if not self.server_script_path:
            raise ValueError('server_script_path must be set in mcp_config')
        self.exit_stack = asyncio.ExitStack() if hasattr(asyncio, 'ExitStack') else None
        server_params = StdioServerParameters(
            command="python" if self.server_script_path.endswith('.py') else "node",
            args=[self.server_script_path],
            env=None
        )
        stdio_transport = await stdio_client(server_params)
        self.stdio, self.write = stdio_transport
        self.session = await ClientSession(self.stdio, self.write).__aenter__()
        await self.session.initialize()

    def _ensure_connected(self):
        if self.session is None:
            self.loop.run_until_complete(self._connect())

    def get_issues(self, label: str) -> List[Issue]:
        self._ensure_connected()
        args = {
            "owner": self.owner,
            "repo": self.repo,
            "labels": [label]
        }
        result = self.loop.run_until_complete(self.session.call_tool('list_issues', args))
        return result.get('issues', [])

    def update_issue(self, number: int, remove_label: str) -> None:
        self._ensure_connected()
        args = {
            "owner": self.owner,
            "repo": self.repo,
            "issue_number": number,
            "remove_labels": [remove_label]
        }
        self.loop.run_until_complete(self.session.call_tool('update_issue', args))

    def add_issue_comment(self, number: int, comment: str) -> None:
        self._ensure_connected()
        args = {
            "owner": self.owner,
            "repo": self.repo,
            "issue_number": number,
            "body": comment
        }
        self.loop.run_until_complete(self.session.call_tool('add_issue_comment', args))

    def call_tool(self, tool: str, args: dict) -> dict:
        self._ensure_connected()
        # owner/repo自動付与
        args = {"owner": self.owner, "repo": self.repo, **args}
        return self.loop.run_until_complete(self.session.call_tool(tool, args))
