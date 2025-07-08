"""
Real GitHub integration tests - requires GITHUB_TOKEN environment variable
"""
import unittest
import sys
import os
import yaml
import logging
from unittest.mock import patch

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from clients.mcp_tool_client import MCPToolClient
from handlers.task_getter_github import TaskGetterFromGitHub, TaskGitHubIssue
from handlers.task_key import GitHubIssueTaskKey


class TestRealGitHubIntegration(unittest.TestCase):
    """Real GitHub integration tests using actual GitHub API"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test configuration and check for GitHub token"""
        # Check if GitHub token is available
        cls.github_token = os.environ.get('GITHUB_TOKEN')
        if not cls.github_token:
            raise unittest.SkipTest("GITHUB_TOKEN environment variable not set")
        
        # Load test configuration
        config_path = os.path.join(os.path.dirname(__file__), '..', 'real_test_config_github.yaml')
        with open(config_path, 'r') as f:
            cls.config = yaml.safe_load(f)
        
        # Set up GitHub token in environment for MCP server
        os.environ['GITHUB_TOKEN'] = cls.github_token
        
        # Initialize MCP client
        cls.mcp_client = MCPToolClient(cls.config['mcp_servers'][0])
        
        # Set up logging to capture issues
        logging.basicConfig(level=logging.INFO)
        cls.logger = logging.getLogger(__name__)
    
    @classmethod
    def tearDownClass(cls):
        """Clean up after tests"""
        if hasattr(cls, 'mcp_client'):
            cls.mcp_client.close()
    
    def test_github_mcp_connection(self):
        """Test that we can connect to GitHub MCP server"""
        try:
            self.mcp_client.call_initialize()
            tools = self.mcp_client.list_tools()
            self.assertIsInstance(tools, list)
            self.logger.info(f"Available GitHub tools: {len(tools)}")
        except Exception as e:
            self.fail(f"Failed to connect to GitHub MCP server: {e}")
    
    def test_search_github_issues(self):
        """Test searching for GitHub issues with real API"""
        try:
            # Search for issues in test repository
            query = self.config['github']['query']
            result = self.mcp_client.call_tool('search_issues', {'q': query})
            
            self.assertIsInstance(result, dict)
            self.logger.info(f"Found {len(result.get('items', []))} issues matching query")
            
            # If we found issues, verify they have expected structure
            if 'items' in result and result['items']:
                issue = result['items'][0]
                self.assertIn('number', issue)
                self.assertIn('title', issue)
                self.assertIn('labels', issue)
                self.assertIn('repository_url', issue)
                
        except Exception as e:
            self.fail(f"Failed to search GitHub issues: {e}")
    
    def test_get_issue_details(self):
        """Test getting issue details from GitHub"""
        try:
            # First search for issues
            query = self.config['github']['query']
            search_result = self.mcp_client.call_tool('search_issues', {'q': query})
            
            if not search_result.get('items'):
                self.skipTest("No issues found in test repository")
                
            # Get details for first issue
            issue = search_result['items'][0]
            repo_url = issue['repository_url']
            owner = repo_url.split('/')[-2]
            repo = repo_url.split('/')[-1]
            
            issue_detail = self.mcp_client.call_tool('get_issue', {
                'owner': owner,
                'repo': repo,
                'issue_number': issue['number']
            })
            
            self.assertIsInstance(issue_detail, dict)
            self.assertIn('number', issue_detail)
            self.assertIn('title', issue_detail)
            self.assertIn('body', issue_detail)
            self.logger.info(f"Got issue #{issue_detail['number']}: {issue_detail['title']}")
            
        except Exception as e:
            self.fail(f"Failed to get issue details: {e}")
    
    def test_get_issue_comments(self):
        """Test getting issue comments from GitHub"""
        try:
            # First search for issues
            query = self.config['github']['query']
            search_result = self.mcp_client.call_tool('search_issues', {'q': query})
            
            if not search_result.get('items'):
                self.skipTest("No issues found in test repository")
                
            # Get comments for first issue
            issue = search_result['items'][0]
            repo_url = issue['repository_url']
            owner = repo_url.split('/')[-2]
            repo = repo_url.split('/')[-1]
            
            comments = self.mcp_client.call_tool('get_issue_comments', {
                'owner': owner,
                'repo': repo,
                'issue_number': issue['number']
            })
            
            self.assertIsInstance(comments, list)
            self.logger.info(f"Found {len(comments)} comments on issue #{issue['number']}")
            
        except Exception as e:
            self.fail(f"Failed to get issue comments: {e}")
    
    def test_task_github_issue_creation(self):
        """Test creating TaskGitHubIssue objects with real GitHub data"""
        try:
            # Search for issues first
            query = self.config['github']['query']
            search_result = self.mcp_client.call_tool('search_issues', {'q': query})
            
            if not search_result.get('items'):
                self.skipTest("No issues found in test repository")
            
            # Create TaskGitHubIssue with real data
            issue_data = search_result['items'][0]
            
            # Mock github_client since we're testing MCP interaction
            with patch('handlers.task_getter_github.GithubClient') as mock_github_client:
                task = TaskGitHubIssue(
                    issue=issue_data,
                    mcp_client=self.mcp_client,
                    github_client=mock_github_client,
                    config=self.config
                )
                
                # Test task properties
                self.assertIsInstance(task.issue, dict)
                self.assertIn('repo', task.issue)
                self.assertIn('owner', task.issue)
                self.assertIsInstance(task.labels, list)
                
                # Test get_prompt method (reads real data)
                prompt = task.get_prompt()
                self.assertIsInstance(prompt, str)
                self.assertIn('ISSUE:', prompt)
                self.assertIn('COMMENTS:', prompt)
                self.logger.info(f"Generated prompt for issue #{task.issue['number']}")
                
        except Exception as e:
            self.fail(f"Failed to create TaskGitHubIssue: {e}")
    
    def test_task_getter_from_github(self):
        """Test TaskGetterFromGitHub with real GitHub API"""
        try:
            # Mock github_client since we're testing MCP interaction
            with patch('handlers.task_getter_github.GithubClient') as mock_github_client:
                task_getter = TaskGetterFromGitHub(
                    mcp_client=self.mcp_client,
                    github_client=mock_github_client,
                    config=self.config
                )
                
                # Test getting tasks
                tasks = task_getter.get_tasks()
                self.assertIsInstance(tasks, list)
                
                if tasks:
                    # Verify task structure
                    task = tasks[0]
                    self.assertIsInstance(task, TaskGitHubIssue)
                    self.assertIsInstance(task.issue, dict)
                    self.logger.info(f"Found {len(tasks)} GitHub tasks")
                else:
                    self.logger.info("No GitHub tasks found (this is normal if no issues match criteria)")
                
        except Exception as e:
            self.fail(f"Failed to get tasks from GitHub: {e}")


class TestGitHubTaskKey(unittest.TestCase):
    """Test GitHub task key functionality"""
    
    def test_github_issue_task_key(self):
        """Test GitHub issue task key creation and parsing"""
        # Test data
        owner = "test-owner"
        repo = "test-repo"
        issue_number = 123
        
        # Create task key
        task_key = GitHubIssueTaskKey(owner, repo, issue_number)
        
        # Test properties
        self.assertEqual(task_key.owner, owner)
        self.assertEqual(task_key.repo, repo)
        self.assertEqual(task_key.issue_number, issue_number)
        
        # Test string representation
        key_str = str(task_key)
        self.assertIn(owner, key_str)
        self.assertIn(repo, key_str)
        self.assertIn(str(issue_number), key_str)


if __name__ == '__main__':
    unittest.main()