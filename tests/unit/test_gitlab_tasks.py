"""
Unit tests for GitLab task getter and task management
"""
import unittest
import sys
import os
import yaml
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from handlers.task_getter_gitlab import TaskGetterFromGitLab, TaskGitLabIssue
from handlers.task_key import GitLabIssueTaskKey
from tests.mocks import MockMCPToolClient


class TestTaskGetterFromGitLab(unittest.TestCase):
    """Test cases for GitLab task getter"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Load test config
        config_path = os.path.join(os.path.dirname(__file__), '..', 'test_config.yaml')
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Create mock MCP clients
        gitlab_server_config = {
            'mcp_server_name': 'gitlab',
            'command': ['mock_gitlab_server']
        }
        self.mcp_clients = {
            'gitlab': MockMCPToolClient(gitlab_server_config)
        }
    
    @patch('handlers.task_getter_gitlab.GitlabClient')
    def test_get_task_list(self, mock_gitlab_client):
        """Test getting list of tasks from GitLab"""
        # Mock the GitLab client to return empty lists  
        mock_gitlab_instance = MagicMock()
        mock_gitlab_instance.search_issues.return_value = []
        mock_gitlab_instance.search_merge_requests.return_value = []
        mock_gitlab_client.return_value = mock_gitlab_instance
        
        # Create task getter
        task_getter = TaskGetterFromGitLab(self.config, self.mcp_clients)
        
        # Override the search to use our mock data with proper filtering
        def mock_search_issues(query):
            # Return issues that match the label filtering
            all_issues = self.mcp_clients['gitlab'].mock_data['issues']
            # Add assignee field to match the filtering logic
            for issue in all_issues:
                issue['assignee'] = {'username': self.config['gitlab']['owner']}
            return all_issues
        
        task_getter.gitlab_client.search_issues = mock_search_issues
        task_getter.gitlab_client.search_merge_requests = lambda q: []
        
        tasks = task_getter.get_task_list()
        
        # Should return tasks for issues with 'coding agent' label
        self.assertIsInstance(tasks, list)
        self.assertGreater(len(tasks), 0)
        
        # All tasks should be TaskGitLabIssue instances
        for task in tasks:
            self.assertIsInstance(task, TaskGitLabIssue)
    
    @patch('handlers.task_getter_gitlab.GitlabClient')
    def test_task_filtering_by_label(self, mock_gitlab_client):
        """Test that only issues with correct label are returned"""
        # Mock the GitLab client to return empty lists
        mock_gitlab_instance = MagicMock()
        mock_gitlab_instance.search_issues.return_value = []
        mock_gitlab_instance.search_merge_requests.return_value = []
        mock_gitlab_client.return_value = mock_gitlab_instance
        
        # Create task getter
        task_getter = TaskGetterFromGitLab(self.config, self.mcp_clients)
        
        # Override the search to use our mock data with proper filtering
        def mock_search_issues(query):
            # Return issues that match the label filtering
            all_issues = self.mcp_clients['gitlab'].mock_data['issues']
            # Add assignee field to match the filtering logic
            for issue in all_issues:
                issue['assignee'] = {'username': self.config['gitlab']['owner']}
            return all_issues
        
        task_getter.gitlab_client.search_issues = mock_search_issues
        task_getter.gitlab_client.search_merge_requests = lambda q: []
        
        tasks = task_getter.get_task_list()
        
        for task in tasks:
            # Check that the task has the bot label
            issue_labels = task.issue.get('labels', [])
            self.assertIn(self.config['gitlab']['bot_label'], issue_labels)


class TestTaskGitLabIssue(unittest.TestCase):
    """Test cases for GitLab issue task"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Load test config
        config_path = os.path.join(os.path.dirname(__file__), '..', 'test_config.yaml')
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Create mock MCP client
        gitlab_server_config = {
            'mcp_server_name': 'gitlab',
            'command': ['mock_gitlab_server']
        }
        self.mcp_client = MockMCPToolClient(gitlab_server_config)
        
        # Mock issue data
        self.issue_data = {
            'iid': 1,
            'title': 'GitLab Test Issue',
            'description': 'This is a test issue for automation',
            'project_id': 'test-project',
            'labels': ['coding agent'],
            'state': 'opened'
        }
        
        # Create task
        self.task = TaskGitLabIssue(
            self.issue_data, 
            self.mcp_client, 
            None,  # gitlab_client not needed for our tests
            self.config
        )
    
    def test_prepare_label_change(self):
        """Test that prepare() changes labels correctly"""
        # Initial state should have 'coding agent' label
        initial_labels = self.task.issue.get('labels', [])
        self.assertIn('coding agent', initial_labels)
        self.assertNotIn('coding agent processing', initial_labels)
        
        # Call prepare
        self.task.prepare()
        
        # Should now have processing label and not bot label
        updated_labels = self.task.issue.get('labels', [])
        self.assertNotIn('coding agent', updated_labels)
        self.assertIn('coding agent processing', updated_labels)
    
    def test_get_prompt_format(self):
        """Test that get_prompt returns properly formatted prompt"""
        prompt = self.task.get_prompt()
        
        # Should contain issue information
        self.assertIn('ISSUE:', prompt)
        self.assertIn('GitLab Test Issue', prompt)
        self.assertIn('This is a test issue for automation', prompt)
        # Note: GitLab uses 'description' instead of 'body'
    
    def test_finish_label_change(self):
        """Test that finish() changes labels correctly"""
        # Start with processing label
        self.task.issue['labels'] = ['coding agent processing']
        
        # Call finish
        self.task.finish()
        
        # Should now have done label and not processing label
        updated_labels = self.task.issue.get('labels', [])
        self.assertNotIn('coding agent processing', updated_labels)
        self.assertIn('coding agent done', updated_labels)
    
    def test_get_task_key(self):
        """Test task key generation"""
        task_key = self.task.get_task_key()
        
        self.assertIsInstance(task_key, GitLabIssueTaskKey)
        self.assertEqual(task_key.project_id, 'test-project')
        self.assertEqual(task_key.issue_iid, 1)
    
    def test_check_task_state(self):
        """Test checking if task is in processing state"""
        # Initially should not be in processing state
        self.assertFalse(self.task.check())
        
        # Add processing label
        current_labels = self.task.issue.get('labels', [])
        current_labels.append('coding agent processing')
        self.task.issue['labels'] = current_labels
        
        # Now should be in processing state
        self.assertTrue(self.task.check())


if __name__ == '__main__':
    unittest.main()