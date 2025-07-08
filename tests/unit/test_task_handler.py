"""
Unit tests for task handler and LLM integration
"""
import unittest
import sys
import os
import yaml
import json

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from handlers.task_handler import TaskHandler
from handlers.task_getter_github import TaskGitHubIssue
from tests.mocks import MockMCPToolClient, MockLLMClient, MockLLMClientWithErrors


class TestTaskHandler(unittest.TestCase):
    """Test cases for task handler"""
    
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
        self.mcp_clients = {
            'github': MockMCPToolClient(github_server_config)
        }
        
        # Create mock LLM client
        self.llm_client = MockLLMClient(self.config)
        
        # Create task handler
        self.task_handler = TaskHandler(self.llm_client, self.mcp_clients, self.config)
        
        # Create test task
        self.issue_data = {
            'number': 1,
            'title': 'Test Issue',
            'body': 'This is a test issue for automation',
            'repository_url': 'https://github.com/test-owner/test-repo',
            'labels': [{'name': 'coding agent processing'}],
            'state': 'open'
        }
        self.test_task = TaskGitHubIssue(
            self.issue_data, 
            self.mcp_clients['github'], 
            None,
            self.config
        )
    
    def test_sanitize_arguments_dict(self):
        """Test sanitizing arguments when they are already a dict"""
        args = {'test': 'value', 'number': 123}
        result = self.task_handler.sanitize_arguments(args)
        self.assertEqual(result, args)
    
    def test_sanitize_arguments_json_string(self):
        """Test sanitizing arguments when they are a JSON string"""
        args = '{"test": "value", "number": 123}'
        result = self.task_handler.sanitize_arguments(args)
        expected = {'test': 'value', 'number': 123}
        self.assertEqual(result, expected)
    
    def test_sanitize_arguments_invalid_json(self):
        """Test sanitizing arguments with invalid JSON"""
        args = '{"test": "value", invalid}'
        with self.assertRaises(ValueError):
            self.task_handler.sanitize_arguments(args)
    
    def test_sanitize_arguments_invalid_type(self):
        """Test sanitizing arguments with invalid type"""
        args = 123
        with self.assertRaises(TypeError):
            self.task_handler.sanitize_arguments(args)
    
    def test_handle_task_basic_flow(self):
        """Test basic task handling flow"""
        # Set up specific responses for this test
        responses = [
            (json.dumps({
                "command": {"tool": "github_get_issue", "args": {"issue_number": 1}},
                "comment": "Starting to analyze the issue",
                "done": False
            }), []),
            (json.dumps({
                "comment": "Task completed successfully",
                "done": True
            }), [])
        ]
        self.llm_client.set_custom_responses(responses)
        
        # Handle the task
        self.task_handler.handle(self.test_task)
        
        # Verify that system and user prompts were sent
        self.assertIsNotNone(self.llm_client.system_prompt)
        self.assertGreaterEqual(len(self.llm_client.user_messages), 1)
        
        # Verify the user message contains the task prompt
        user_message = self.llm_client.user_messages[0]
        self.assertIn('Test Issue', user_message)
    
    def test_handle_task_with_tool_calls(self):
        """Test task handling with tool calls"""
        # Set up responses that include tool calls
        responses = [
            (json.dumps({
                "command": {"tool": "github_get_issue_comments", "args": {"issue_number": 1}},
                "comment": "Getting issue comments",
                "done": False
            }), []),
            (json.dumps({
                "command": {"tool": "github_add_issue_comment", "args": {"body": "Working on this issue"}},
                "comment": "Adding progress comment",
                "done": False
            }), []),
            (json.dumps({
                "comment": "All done!",
                "done": True
            }), [])
        ]
        self.llm_client.set_custom_responses(responses)
        
        # Handle the task
        self.task_handler.handle(self.test_task)
        
        # Verify multiple interactions occurred
        self.assertGreaterEqual(len(self.llm_client.user_messages), 1)  # At least initial prompt
        self.assertEqual(self.llm_client.current_response_index, 3)  # All responses consumed
    
    def test_handle_task_with_think_blocks(self):
        """Test task handling with <think> blocks in responses"""
        # Set up response with think block
        responses = [
            ('<think>Let me analyze this issue step by step...</think>' + json.dumps({
                "comment": "Analysis complete",
                "done": True
            }), [])
        ]
        self.llm_client.set_custom_responses(responses)
        
        # Handle the task
        self.task_handler.handle(self.test_task)
        
        # Verify think content was added as comment
        # Check that a comment with the think content was added
        comments = self.mcp_clients['github'].mock_data['comments']
        think_comment_found = any(
            'Let me analyze this issue step by step...' in comment['body'] 
            for comment in comments
        )
        self.assertTrue(think_comment_found)
    
    def test_handle_task_max_iterations(self):
        """Test that task handling respects max iterations"""
        # Set a low max count
        self.config['max_llm_process_num'] = 2
        
        # Set up responses that never complete
        responses = [
            (json.dumps({
                "command": {"tool": "github_get_issue", "args": {"issue_number": 1}},
                "comment": "Still working...",
                "done": False
            }), [])
        ] * 10  # More responses than max count
        
        self.llm_client.set_custom_responses(responses)
        
        # Handle the task
        self.task_handler.handle(self.test_task)
        
        # Should not have consumed all responses due to max count
        self.assertLessEqual(self.llm_client.current_response_index, 2)


class TestTaskHandlerErrorHandling(unittest.TestCase):
    """Test error handling in task handler"""
    
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
        self.mcp_clients = {
            'github': MockMCPToolClient(github_server_config)
        }
        
        # Create error-prone LLM client
        self.llm_client = MockLLMClientWithErrors(self.config)
        
        # Create task handler
        self.task_handler = TaskHandler(self.llm_client, self.mcp_clients, self.config)
        
        # Create test task
        self.issue_data = {
            'number': 1,
            'title': 'Test Issue',
            'body': 'This is a test issue for error handling',
            'repository_url': 'https://github.com/test-owner/test-repo',
            'labels': [{'name': 'coding agent processing'}],
            'state': 'open'
        }
        self.test_task = TaskGitHubIssue(
            self.issue_data, 
            self.mcp_clients['github'], 
            None,
            self.config
        )
    
    def test_handle_task_with_json_errors(self):
        """Test task handling with JSON parsing errors"""
        # This should not raise an exception, but handle errors gracefully
        try:
            self.task_handler.handle(self.test_task)
            # Verify the handler attempted to process responses
            self.assertGreaterEqual(self.llm_client.error_count, 1)
        except Exception as e:
            self.fail(f"Task handler should handle JSON errors gracefully, but raised: {e}")


if __name__ == '__main__':
    unittest.main()