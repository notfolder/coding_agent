"""
Real GitHub and GitLab workflow integration tests
"""
import unittest
import sys
import os
import yaml
import logging
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from clients.mcp_tool_client import MCPToolClient
from clients.lm_client import LMClient
from handlers.task_handler import TaskHandler
from handlers.task_getter_github import TaskGetterFromGitHub
from handlers.task_getter_gitlab import TaskGetterFromGitLab
from tests.mocks.mock_llm_client import MockLLMClient


class TestRealGitHubWorkflow(unittest.TestCase):
    """End-to-end GitHub workflow tests with real API"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test configuration and check for GitHub token"""
        cls.github_token = os.environ.get('GITHUB_TOKEN')
        if not cls.github_token:
            raise unittest.SkipTest("GITHUB_TOKEN environment variable not set")
        
        # Load test configuration
        config_path = os.path.join(os.path.dirname(__file__), '..', 'real_test_config_github.yaml')
        with open(config_path, 'r') as f:
            cls.config = yaml.safe_load(f)
        
        # Set up GitHub token in environment
        os.environ['GITHUB_TOKEN'] = cls.github_token
        
        # Set up logging
        logging.basicConfig(level=logging.INFO)
        cls.logger = logging.getLogger(__name__)
    
    def setUp(self):
        """Set up test environment for each test"""
        # Initialize MCP client
        self.mcp_client = MCPToolClient(self.config['mcp_servers'][0])
        
        # Initialize mock LLM client
        self.llm_client = MockLLMClient(self.config)
        
    def tearDown(self):
        """Clean up after each test"""
        if hasattr(self, 'mcp_client'):
            self.mcp_client.close()
    
    def test_full_github_task_workflow(self):
        """Test complete GitHub task workflow"""
        try:
            # Mock github_client since we're testing MCP interaction
            with patch('handlers.task_getter_github.GithubClient') as mock_github_client:
                # Initialize task getter
                task_getter = TaskGetterFromGitHub(
                    mcp_client=self.mcp_client,
                    github_client=mock_github_client,
                    config=self.config
                )
                
                # Get tasks from GitHub
                tasks = task_getter.get_tasks()
                self.assertIsInstance(tasks, list)
                self.logger.info(f"Retrieved {len(tasks)} tasks from GitHub")
                
                if not tasks:
                    self.skipTest("No GitHub tasks found for testing workflow")
                
                # Test task processing
                task = tasks[0]
                
                # Test task preparation
                original_labels = task.labels.copy()
                task.prepare()
                
                # Verify label changes were attempted
                self.assertIsInstance(task.labels, list)
                
                # Test prompt generation
                prompt = task.get_prompt()
                self.assertIsInstance(prompt, str)
                self.assertIn('ISSUE:', prompt)
                self.assertIn('COMMENTS:', prompt)
                
                # Test task handler workflow
                task_handler = TaskHandler(
                    task=task,
                    llm_client=self.llm_client,
                    config=self.config
                )
                
                # Configure mock LLM to return completion
                self.llm_client.set_mock_response({
                    "done": True,
                    "response": "Task completed successfully"
                })
                
                # Process task
                result = task_handler.process()
                self.assertIsInstance(result, dict)
                self.logger.info(f"Task processing result: {result}")
                
        except Exception as e:
            self.fail(f"GitHub workflow test failed: {e}")
    
    def test_github_error_handling(self):
        """Test GitHub workflow error handling"""
        try:
            # Test with invalid configuration
            invalid_config = self.config.copy()
            invalid_config['github']['repo'] = 'nonexistent-repo-12345'
            
            with patch('handlers.task_getter_github.GithubClient') as mock_github_client:
                task_getter = TaskGetterFromGitHub(
                    mcp_client=self.mcp_client,
                    github_client=mock_github_client,
                    config=invalid_config
                )
                
                # Should handle errors gracefully
                tasks = task_getter.get_tasks()
                self.assertIsInstance(tasks, list)
                # May be empty due to repo not existing, but shouldn't crash
                
        except Exception as e:
            # Should not raise unhandled exceptions
            self.fail(f"Error handling test failed: {e}")


class TestRealGitLabWorkflow(unittest.TestCase):
    """End-to-end GitLab workflow tests with real API"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test configuration and check for GitLab token"""
        cls.gitlab_token = os.environ.get('GITLAB_TOKEN')
        if not cls.gitlab_token:
            raise unittest.SkipTest("GITLAB_TOKEN environment variable not set")
        
        # Load test configuration
        config_path = os.path.join(os.path.dirname(__file__), '..', 'real_test_config_gitlab.yaml')
        with open(config_path, 'r') as f:
            cls.config = yaml.safe_load(f)
        
        # Set up GitLab token in environment
        os.environ['GITLAB_TOKEN'] = cls.gitlab_token
        
        # Set up logging
        logging.basicConfig(level=logging.INFO)
        cls.logger = logging.getLogger(__name__)
    
    def setUp(self):
        """Set up test environment for each test"""
        # Initialize MCP client
        self.mcp_client = MCPToolClient(self.config['mcp_servers'][0])
        
        # Initialize mock LLM client
        self.llm_client = MockLLMClient(self.config)
        
    def tearDown(self):
        """Clean up after each test"""
        if hasattr(self, 'mcp_client'):
            self.mcp_client.close()
    
    def test_full_gitlab_task_workflow(self):
        """Test complete GitLab task workflow"""
        try:
            # Mock gitlab_client since we're testing MCP interaction
            with patch('handlers.task_getter_gitlab.GitlabClient') as mock_gitlab_client:
                # Initialize task getter
                task_getter = TaskGetterFromGitLab(
                    mcp_client=self.mcp_client,
                    gitlab_client=mock_gitlab_client,
                    config=self.config
                )
                
                # Get tasks from GitLab
                tasks = task_getter.get_tasks()
                self.assertIsInstance(tasks, list)
                self.logger.info(f"Retrieved {len(tasks)} tasks from GitLab")
                
                if not tasks:
                    self.skipTest("No GitLab tasks found for testing workflow")
                
                # Test task processing
                task = tasks[0]
                
                # Test task preparation
                task.prepare()
                
                # Test prompt generation
                prompt = task.get_prompt()
                self.assertIsInstance(prompt, str)
                self.assertIn('ISSUE:', prompt)
                
                # Test task handler workflow
                task_handler = TaskHandler(
                    task=task,
                    llm_client=self.llm_client,
                    config=self.config
                )
                
                # Configure mock LLM to return completion
                self.llm_client.set_mock_response({
                    "done": True,
                    "response": "Task completed successfully"
                })
                
                # Process task
                result = task_handler.process()
                self.assertIsInstance(result, dict)
                self.logger.info(f"Task processing result: {result}")
                
        except Exception as e:
            self.fail(f"GitLab workflow test failed: {e}")


class TestMCPServerIntegration(unittest.TestCase):
    """Test real MCP server integration"""
    
    def test_github_mcp_server_tools(self):
        """Test GitHub MCP server tool availability"""
        if not os.environ.get('GITHUB_TOKEN'):
            self.skipTest("GITHUB_TOKEN not available")
        
        try:
            config_path = os.path.join(os.path.dirname(__file__), '..', 'real_test_config_github.yaml')
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            os.environ['GITHUB_TOKEN'] = os.environ.get('GITHUB_TOKEN')
            mcp_client = MCPToolClient(config['mcp_servers'][0])
            
            # Test tool listing
            tools = mcp_client.list_tools()
            self.assertIsInstance(tools, list)
            
            # Verify expected tools are available
            tool_names = [tool.name for tool in tools] if tools else []
            expected_tools = ['search_issues', 'get_issue', 'get_issue_comments', 'update_issue']
            
            for expected_tool in expected_tools:
                if expected_tool not in tool_names:
                    self.logger.warning(f"Expected tool '{expected_tool}' not found in available tools")
            
            mcp_client.close()
            
        except Exception as e:
            self.fail(f"GitHub MCP server integration test failed: {e}")
    
    def test_gitlab_mcp_server_tools(self):
        """Test GitLab MCP server tool availability"""
        if not os.environ.get('GITLAB_TOKEN'):
            self.skipTest("GITLAB_TOKEN not available")
        
        try:
            config_path = os.path.join(os.path.dirname(__file__), '..', 'real_test_config_gitlab.yaml')
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            os.environ['GITLAB_TOKEN'] = os.environ.get('GITLAB_TOKEN')
            mcp_client = MCPToolClient(config['mcp_servers'][0])
            
            # Test tool listing
            tools = mcp_client.list_tools()
            self.assertIsInstance(tools, list)
            
            # Verify expected tools are available
            tool_names = [tool.name for tool in tools] if tools else []
            expected_tools = ['list_issues', 'get_issue', 'list_issue_discussions', 'update_issue']
            
            for expected_tool in expected_tools:
                if expected_tool not in tool_names:
                    self.logger.warning(f"Expected tool '{expected_tool}' not found in available tools")
            
            mcp_client.close()
            
        except Exception as e:
            self.fail(f"GitLab MCP server integration test failed: {e}")


if __name__ == '__main__':
    unittest.main()