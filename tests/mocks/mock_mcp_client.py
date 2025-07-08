"""
Mock MCP client for testing (GitHub and GitLab mocking removed per user request)
"""
import json
from typing import Dict, Any, List, Optional


class MockMCPToolClient:
    """Mock implementation of MCPToolClient for general testing (not GitHub/GitLab specific)"""
    
    def __init__(self, server_config, function_calling=True):
        self.server_config = server_config
        self.function_calling = function_calling
        self.server_name = server_config.get('mcp_server_name', 'unknown')
        self.mock_data = {}
        self._system_prompt = None
    
    def call_tool(self, tool: str, args: Dict[str, Any]) -> Any:
        """Mock tool call implementation - returns empty response for any tool"""
        # Note: GitHub and GitLab mocking removed per user request
        # This mock now only provides basic MCP client interface without service-specific data
        return {}
    
    def call_initialize(self):
        """Mock initialize call"""
        return None
    
    def list_tools(self):
        """Mock list tools - returns empty list"""
        # Note: GitHub and GitLab specific tools removed per user request
        return []
    
    @property
    def system_prompt(self):
        """Mock system prompt"""
        return f"Mock {self.server_name} MCP server for testing"
    
    def close(self):
        """Mock close"""
        pass
    
    def get_function_calling_functions(self):
        """Mock function calling functions"""
        return []
    
    def get_function_calling_tools(self):
        """Mock function calling tools"""
        return []