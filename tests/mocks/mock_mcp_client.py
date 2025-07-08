"""
Mock MCP client for testing GitHub and GitLab integrations
"""
import json
from typing import Dict, Any, List, Optional


class MockMCPToolClient:
    """Mock implementation of MCPToolClient for testing"""
    
    def __init__(self, server_config, function_calling=True):
        self.server_config = server_config
        self.function_calling = function_calling
        self.server_name = server_config.get('mcp_server_name', 'unknown')
        self.mock_data = {}
        self._system_prompt = None
        self._setup_mock_data()
    
    def _setup_mock_data(self):
        """Setup mock data for different server types"""
        if self.server_name == 'github':
            self._setup_github_mock_data()
        elif self.server_name == 'gitlab':
            self._setup_gitlab_mock_data()
    
    def _setup_github_mock_data(self):
        """Setup mock data for GitHub server"""
        self.mock_data = {
            'issues': [
                {
                    'number': 1,
                    'title': 'Test Issue 1',
                    'body': 'This is a test issue',
                    'repository_url': 'https://github.com/test-owner/test-repo',
                    'labels': [{'name': 'coding agent'}],
                    'state': 'open'
                },
                {
                    'number': 2,
                    'title': 'Test Issue 2',
                    'body': 'Another test issue',
                    'repository_url': 'https://github.com/test-owner/test-repo',
                    'labels': [{'name': 'coding agent'}, {'name': 'bug'}],
                    'state': 'open'
                }
            ],
            'comments': [
                {'body': 'Test comment 1'},
                {'body': 'Test comment 2'}
            ]
        }
    
    def _setup_gitlab_mock_data(self):
        """Setup mock data for GitLab server"""
        self.mock_data = {
            'issues': [
                {
                    'iid': 1,
                    'title': 'GitLab Test Issue 1',
                    'description': 'This is a GitLab test issue',
                    'project_id': 'test-project',
                    'labels': ['coding agent'],
                    'state': 'opened'
                }
            ],
            'discussions': [
                {
                    'items': [
                        {
                            'notes': [
                                {'body': 'GitLab test comment 1'},
                                {'body': 'GitLab test comment 2'}
                            ]
                        }
                    ]
                }
            ]
        }
    
    def call_tool(self, tool: str, args: Dict[str, Any]) -> Any:
        """Mock tool call implementation"""
        if self.server_name == 'github':
            return self._handle_github_tool(tool, args)
        elif self.server_name == 'gitlab':
            return self._handle_gitlab_tool(tool, args)
        else:
            raise ValueError(f"Unknown server: {self.server_name}")
    
    def _handle_github_tool(self, tool: str, args: Dict[str, Any]) -> Any:
        """Handle GitHub tool calls"""
        if tool == 'search_issues':
            return {'items': self.mock_data['issues']}
        elif tool == 'get_issue':
            issue_number = args.get('issue_number')
            for issue in self.mock_data['issues']:
                if issue['number'] == issue_number:
                    return issue
            return None
        elif tool == 'get_issue_comments':
            return self.mock_data['comments']
        elif tool == 'update_issue':
            # Update issue labels
            issue_number = args.get('issue_number')
            labels = args.get('labels', [])
            for issue in self.mock_data['issues']:
                if issue['number'] == issue_number:
                    issue['labels'] = labels
                    return issue
            return None
        elif tool == 'add_issue_comment':
            comment = {'body': args.get('body', '')}
            self.mock_data['comments'].append(comment)
            return comment
        else:
            return {}
    
    def _handle_gitlab_tool(self, tool: str, args: Dict[str, Any]) -> Any:
        """Handle GitLab tool calls"""
        if tool == 'list_issues':
            return {'items': self.mock_data['issues']}
        elif tool == 'get_issue':
            issue_iid = args.get('issue_iid')
            for issue in self.mock_data['issues']:
                if issue['iid'] == issue_iid:
                    return issue
            return None
        elif tool == 'list_issue_discussions':
            return self.mock_data['discussions'][0]
        elif tool == 'update_issue':
            # Update issue labels
            issue_iid = args.get('issue_iid')
            labels = args.get('labels', [])
            for issue in self.mock_data['issues']:
                if issue['iid'] == issue_iid:
                    issue['labels'] = labels
                    return issue
            return None
        elif tool == 'add_issue_comment':
            comment = {'body': args.get('body', '')}
            # In real GitLab, this would be added to discussions
            return comment
        else:
            return {}
    
    def call_initialize(self):
        """Mock initialize call"""
        return None
    
    def list_tools(self):
        """Mock list tools"""
        if self.server_name == 'github':
            return [
                {'name': 'search_issues', 'description': 'Search GitHub issues'},
                {'name': 'get_issue', 'description': 'Get GitHub issue'},
                {'name': 'get_issue_comments', 'description': 'Get issue comments'},
                {'name': 'update_issue', 'description': 'Update issue'},
                {'name': 'add_issue_comment', 'description': 'Add issue comment'}
            ]
        elif self.server_name == 'gitlab':
            return [
                {'name': 'list_issues', 'description': 'List GitLab issues'},
                {'name': 'get_issue', 'description': 'Get GitLab issue'},
                {'name': 'list_issue_discussions', 'description': 'Get issue discussions'},
                {'name': 'update_issue', 'description': 'Update issue'},
                {'name': 'add_issue_comment', 'description': 'Add issue comment'}
            ]
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