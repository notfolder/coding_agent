"""
Integration tests for the complete coding agent workflow
"""
import unittest
import sys
import os
import yaml
import json
from unittest.mock import patch

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from handlers.task_getter import TaskGetter
from handlers.task_handler import TaskHandler
from handlers.task_factory import GitHubTaskFactory, GitLabTaskFactory
from queueing import InMemoryTaskQueue
from tests.mocks import MockMCPToolClient, MockLLMClient


class TestWorkflowIntegration(unittest.TestCase):
    """Integration tests for complete coding agent workflow"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Load test config
        config_path = os.path.join(os.path.dirname(__file__), '..', 'test_config.yaml')
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Create mock MCP clients
        github_server_config = {
            'mcp_server_name': 'github',
            'command': ['mock_github_server']
        }
        gitlab_server_config = {
            'mcp_server_name': 'gitlab',
            'command': ['mock_gitlab_server']
        }
        
        self.mcp_clients = {
            'github': MockMCPToolClient(github_server_config),
            'gitlab': MockMCPToolClient(gitlab_server_config)
        }
        
        # Create mock LLM client
        self.llm_client = MockLLMClient(self.config)
        
        # Create task queue
        self.task_queue = InMemoryTaskQueue()
    
    def test_github_workflow_end_to_end(self):
        """Test complete GitHub workflow from task discovery to completion"""
        # 1. Get tasks from GitHub
        task_getter = TaskGetter.factory(self.config, self.mcp_clients, 'github')
        tasks = task_getter.get_task_list()
        
        self.assertGreater(len(tasks), 0, "Should discover some tasks")
        
        # 2. Prepare first task (changes label to processing)
        task = tasks[0]
        original_labels = task.labels.copy()
        task.prepare()
        
        # Verify label change
        self.assertNotIn('coding agent', task.labels)
        self.assertIn('coding agent processing', task.labels)
        
        # 3. Add task to queue
        task_key = task.get_task_key()
        self.task_queue.put(task_key.to_dict())
        
        # 4. Process task with handler
        task_handler = TaskHandler(self.llm_client, self.mcp_clients, self.config)
        
        # Set up completion response
        responses = [
            (json.dumps({
                "command": {"tool": "add_issue_comment", "args": {"body": "Starting work on this issue"}},
                "comment": "Beginning task execution",
                "done": False
            }), []),
            (json.dumps({
                "comment": "Task completed successfully",
                "done": True
            }), [])
        ]
        self.llm_client.set_custom_responses(responses)
        
        # Handle the task
        task_handler.handle(task)
        
        # 5. Finish task (changes label to done)
        task.finish()
        
        # Verify final label change
        self.assertNotIn('coding agent processing', task.labels)
        self.assertIn('coding agent done', task.labels)
        
        # Verify LLM was called
        self.assertGreater(len(self.llm_client.user_messages), 0)
    
    def test_gitlab_workflow_end_to_end(self):
        """Test complete GitLab workflow from task discovery to completion"""
        # 1. Get tasks from GitLab
        task_getter = TaskGetter.factory(self.config, self.mcp_clients, 'gitlab')
        tasks = task_getter.get_task_list()
        
        self.assertGreater(len(tasks), 0, "Should discover some tasks")
        
        # 2. Prepare first task
        task = tasks[0]
        original_labels = task.issue.get('labels', []).copy()
        task.prepare()
        
        # Verify label change
        current_labels = task.issue.get('labels', [])
        self.assertNotIn('coding agent', current_labels)
        self.assertIn('coding agent processing', current_labels)
        
        # 3. Process task
        task_handler = TaskHandler(self.llm_client, self.mcp_clients, self.config)
        
        # Reset LLM client for fresh test
        self.llm_client.reset()
        responses = [
            (json.dumps({
                "comment": "Analyzing GitLab issue",
                "done": True
            }), [])
        ]
        self.llm_client.set_custom_responses(responses)
        
        task_handler.handle(task)
        
        # 4. Finish task
        task.finish()
        
        # Verify final state
        final_labels = task.issue.get('labels', [])
        self.assertNotIn('coding agent processing', final_labels)
        self.assertIn('coding agent done', final_labels)
    
    def test_task_queue_operations(self):
        """Test task queue put and get operations"""
        # Get a task
        task_getter = TaskGetter.factory(self.config, self.mcp_clients, 'github')
        tasks = task_getter.get_task_list()
        task = tasks[0]
        
        # Put task in queue
        task_key_dict = task.get_task_key().to_dict()
        self.task_queue.put(task_key_dict)
        
        # Get task from queue
        retrieved_task_dict = self.task_queue.get()
        
        # Verify it's the same task
        self.assertEqual(task_key_dict, retrieved_task_dict)
    
    def test_task_factory_github(self):
        """Test GitHub task factory"""
        factory = GitHubTaskFactory(self.config, self.mcp_clients)
        
        # Create task key
        task_key_dict = {
            'type': 'github_issue',
            'owner': 'test-owner',
            'repo': 'test-repo',
            'issue_number': 1
        }
        
        # Recreate task from key
        task = factory.create_task_from_key(task_key_dict)
        
        self.assertIsNotNone(task)
        self.assertEqual(task.issue['number'], 1)
        self.assertEqual(task.issue['owner'], 'test-owner')
        self.assertEqual(task.issue['repo'], 'test-repo')
    
    def test_task_factory_gitlab(self):
        """Test GitLab task factory"""
        factory = GitLabTaskFactory(self.config, self.mcp_clients)
        
        # Create task key
        task_key_dict = {
            'type': 'gitlab_issue',
            'project_id': 'test-project',
            'issue_iid': 1
        }
        
        # Recreate task from key
        task = factory.create_task_from_key(task_key_dict)
        
        self.assertIsNotNone(task)
        self.assertEqual(task.issue['iid'], 1)
        self.assertEqual(task.issue['project_id'], 'test-project')
    
    def test_error_recovery_workflow(self):
        """Test that workflow can recover from errors"""
        # Get a task
        task_getter = TaskGetter.factory(self.config, self.mcp_clients, 'github')
        tasks = task_getter.get_task_list()
        task = tasks[0]
        task.prepare()
        
        # Create handler with error-prone LLM
        from tests.mocks import MockLLMClientWithErrors
        error_llm = MockLLMClientWithErrors(self.config)
        task_handler = TaskHandler(error_llm, self.mcp_clients, self.config)
        
        # Should handle errors gracefully
        try:
            task_handler.handle(task)
        except Exception as e:
            self.fail(f"Workflow should handle errors gracefully: {e}")
        
        # Task should still be completable
        task.finish()
        self.assertIn('coding agent done', task.labels)


class TestMCPServerInteraction(unittest.TestCase):
    """Test MCP server interaction patterns"""
    
    def setUp(self):
        """Set up test fixtures"""
        config_path = os.path.join(os.path.dirname(__file__), '..', 'test_config.yaml')
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
    
    def test_github_mcp_tool_coverage(self):
        """Test that mock GitHub MCP server covers required tools"""
        github_server_config = {
            'mcp_server_name': 'github',
            'command': ['mock_github_server']
        }
        mock_client = MockMCPToolClient(github_server_config)
        
        # Test required tools
        required_tools = [
            'search_issues', 'get_issue', 'get_issue_comments', 
            'update_issue', 'add_issue_comment'
        ]
        
        available_tools = [tool['name'] for tool in mock_client.list_tools()]
        
        for tool in required_tools:
            self.assertIn(tool, available_tools, f"Required tool {tool} not available")
    
    def test_gitlab_mcp_tool_coverage(self):
        """Test that mock GitLab MCP server covers required tools"""
        gitlab_server_config = {
            'mcp_server_name': 'gitlab',
            'command': ['mock_gitlab_server']
        }
        mock_client = MockMCPToolClient(gitlab_server_config)
        
        # Test required tools
        required_tools = [
            'list_issues', 'get_issue', 'list_issue_discussions',
            'update_issue', 'add_issue_comment'
        ]
        
        available_tools = [tool['name'] for tool in mock_client.list_tools()]
        
        for tool in required_tools:
            self.assertIn(tool, available_tools, f"Required tool {tool} not available")
    
    def test_mcp_tool_call_error_handling(self):
        """Test MCP tool call error handling"""
        github_server_config = {
            'mcp_server_name': 'github',
            'command': ['mock_github_server']
        }
        mock_client = MockMCPToolClient(github_server_config)
        
        # Test calling non-existent tool
        result = mock_client.call_tool('non_existent_tool', {})
        self.assertEqual(result, {})  # Should return empty dict for unknown tools
        
        # Test calling with missing args
        result = mock_client.call_tool('get_issue', {})
        self.assertIsNone(result)  # Should return None when issue not found


if __name__ == '__main__':
    unittest.main()