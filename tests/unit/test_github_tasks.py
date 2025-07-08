"""
Unit tests for GitHub task getter and task management
"""
import unittest
import sys
import os
import yaml
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from handlers.task_getter_github import TaskGetterFromGitHub, TaskGitHubIssue
from handlers.task_key import GitHubIssueTaskKey
from tests.mocks import MockMCPToolClient


class TestTaskGetterFromGitHub(unittest.TestCase):
    """Test cases for GitHub task getter"""
    
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
    
    @patch('handlers.task_getter_github.GithubClient')
    def test_get_task_list(self, mock_github_client):
        """Test getting list of tasks from GitHub"""
        # Mock the GitHub client to return empty lists (we'll use MCP client instead)
        mock_github_instance = MagicMock()
        mock_github_instance.search_issues.return_value = []
        mock_github_instance.search_pull_requests.return_value = []
        mock_github_client.return_value = mock_github_instance
        
        # Create task getter
        task_getter = TaskGetterFromGitHub(self.config, self.mcp_clients)
        
        # Override the search to use our mock data
        task_getter.github_client.search_issues = lambda q: self.mcp_clients['github'].mock_data['issues']
        task_getter.github_client.search_pull_requests = lambda q: []
        
        tasks = task_getter.get_task_list()
        
        # Should return tasks for issues with 'coding agent' label
        self.assertIsInstance(tasks, list)
        self.assertGreater(len(tasks), 0)
        
        # All tasks should be TaskGitHubIssue instances
        for task in tasks:
            self.assertIsInstance(task, TaskGitHubIssue)
    
    @patch('handlers.task_getter_github.GithubClient')
    def test_task_filtering_by_label(self, mock_github_client):
        """Test that only issues with correct label are returned"""
        # Mock the GitHub client to return empty lists
        mock_github_instance = MagicMock()
        mock_github_instance.search_issues.return_value = []
        mock_github_instance.search_pull_requests.return_value = []
        mock_github_client.return_value = mock_github_instance
        
        # Create task getter
        task_getter = TaskGetterFromGitHub(self.config, self.mcp_clients)
        
        # Override the search to use our mock data
        task_getter.github_client.search_issues = lambda q: self.mcp_clients['github'].mock_data['issues']
        task_getter.github_client.search_pull_requests = lambda q: []
        
        tasks = task_getter.get_task_list()
        
        for task in tasks:
            # Check that the task has the bot label
            self.assertIn(self.config['github']['bot_label'], task.labels)


class TestTaskGitHubIssue(unittest.TestCase):
    """Test cases for GitHub issue task"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Load test config
        config_path = os.path.join(os.path.dirname(__file__), '..', 'test_config.yaml')
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Create mock MCP client
        github_server_config = {
            'mcp_server_name': 'github',
            'command': ['mock_github_server']
        }
        self.mcp_client = MockMCPToolClient(github_server_config)
        
        # Mock issue data with proper GitHub format
        self.issue_data = {
            'number': 1,
            'title': 'Test Issue',
            'body': 'This is a test issue for automation',
            'repository_url': 'https://github.com/test-owner/test-repo',
            'labels': [{'name': 'coding agent'}],
            'state': 'open'
        }
        
        # Create task
        self.task = TaskGitHubIssue(
            self.issue_data, 
            self.mcp_client, 
            None,  # github_client not needed for our tests
            self.config
        )
    
    def test_prepare_label_change(self):
        """Test that prepare() changes labels correctly"""
        # Initial state should have 'coding agent' label
        self.assertIn('coding agent', self.task.labels)
        self.assertNotIn('coding agent processing', self.task.labels)
        
        # Call prepare
        self.task.prepare()
        
        # Should now have processing label and not bot label
        self.assertNotIn('coding agent', self.task.labels)
        self.assertIn('coding agent processing', self.task.labels)
    
    def test_get_prompt_format(self):
        """Test that get_prompt returns properly formatted prompt"""
        prompt = self.task.get_prompt()
        
        # Should contain issue information
        self.assertIn('ISSUE:', prompt)
        self.assertIn('Test Issue', prompt)
        self.assertIn('This is a test issue for automation', prompt)
        self.assertIn('COMMENTS:', prompt)
    
    def test_comment_functionality(self):
        """Test adding comments to issue"""
        test_comment = "This is a test comment"
        
        # Should not raise any errors
        self.task.comment(test_comment)
        
        # Verify comment was added to mock data
        comments = self.mcp_client.mock_data['comments']
        self.assertTrue(any(comment['body'] == test_comment for comment in comments))
    
    def test_finish_label_change(self):
        """Test that finish() changes labels correctly"""
        # Start with processing label
        self.task.labels = ['coding agent processing']
        self.task.issue['labels'] = self.task.labels
        
        # Call finish
        self.task.finish()
        
        # Should now have done label and not processing label
        self.assertNotIn('coding agent processing', self.task.labels)
        self.assertIn('coding agent done', self.task.labels)
    
    def test_get_task_key(self):
        """Test task key generation"""
        task_key = self.task.get_task_key()
        
        self.assertIsInstance(task_key, GitHubIssueTaskKey)
        self.assertEqual(task_key.owner, 'test-owner')
        self.assertEqual(task_key.repo, 'test-repo')
        self.assertEqual(task_key.number, 1)
    
    def test_check_task_state(self):
        """Test checking if task is in processing state"""
        # Initially should not be in processing state
        self.assertFalse(self.task.check())
        
        # Add processing label
        self.task.labels.append('coding agent processing')
        self.task.issue['labels'] = self.task.labels
        
        # Now should be in processing state
        self.assertTrue(self.task.check())


if __name__ == '__main__':
    unittest.main()