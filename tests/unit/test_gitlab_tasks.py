"""
Real GitLab integration tests - requires GITLAB_TOKEN environment variable
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
from handlers.task_getter_gitlab import TaskGetterFromGitLab, TaskGitLabIssue
from handlers.task_key import GitLabIssueTaskKey


class TestRealGitLabIntegration(unittest.TestCase):
    """Real GitLab integration tests using actual GitLab API"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test configuration and check for GitLab token"""
        # Check if GitLab token is available
        cls.gitlab_token = os.environ.get('GITLAB_TOKEN')
        if not cls.gitlab_token:
            raise unittest.SkipTest("GITLAB_TOKEN environment variable not set")
        
        # Load test configuration
        config_path = os.path.join(os.path.dirname(__file__), '..', 'real_test_config_gitlab.yaml')
        with open(config_path, 'r') as f:
            cls.config = yaml.safe_load(f)
        
        # Set up GitLab token in environment for MCP server
        os.environ['GITLAB_TOKEN'] = cls.gitlab_token
        
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
    
    def test_gitlab_mcp_connection(self):
        """Test that we can connect to GitLab MCP server"""
        try:
            self.mcp_client.call_initialize()
            tools = self.mcp_client.list_tools()
            self.assertIsInstance(tools, list)
            self.logger.info(f"Available GitLab tools: {len(tools)}")
        except Exception as e:
            self.fail(f"Failed to connect to GitLab MCP server: {e}")
    
    def test_list_gitlab_issues(self):
        """Test listing GitLab issues with real API"""
        try:
            # List issues in test project
            project_id = self.config['gitlab']['project_id']
            result = self.mcp_client.call_tool('list_issues', {
                'project_id': project_id,
                'state': 'opened',
                'labels': self.config['gitlab']['bot_label']
            })
            
            self.assertIsInstance(result, dict)
            issues = result.get('items', [])
            self.logger.info(f"Found {len(issues)} issues in project {project_id}")
            
            # If we found issues, verify they have expected structure
            if issues:
                issue = issues[0]
                self.assertIn('iid', issue)
                self.assertIn('title', issue)
                self.assertIn('labels', issue)
                self.assertIn('project_id', issue)
                
        except Exception as e:
            self.fail(f"Failed to list GitLab issues: {e}")
    
    def test_get_gitlab_issue_details(self):
        """Test getting GitLab issue details"""
        try:
            # First list issues
            project_id = self.config['gitlab']['project_id']
            list_result = self.mcp_client.call_tool('list_issues', {
                'project_id': project_id,
                'state': 'opened',
                'labels': self.config['gitlab']['bot_label']
            })
            
            issues = list_result.get('items', [])
            if not issues:
                self.skipTest("No issues found in test project")
                
            # Get details for first issue
            issue = issues[0]
            issue_detail = self.mcp_client.call_tool('get_issue', {
                'project_id': project_id,
                'issue_iid': issue['iid']
            })
            
            self.assertIsInstance(issue_detail, dict)
            self.assertIn('iid', issue_detail)
            self.assertIn('title', issue_detail)
            self.assertIn('description', issue_detail)
            self.logger.info(f"Got issue !{issue_detail['iid']}: {issue_detail['title']}")
            
        except Exception as e:
            self.fail(f"Failed to get GitLab issue details: {e}")
    
    def test_get_issue_discussions(self):
        """Test getting GitLab issue discussions"""
        try:
            # First list issues
            project_id = self.config['gitlab']['project_id']
            list_result = self.mcp_client.call_tool('list_issues', {
                'project_id': project_id,
                'state': 'opened',
                'labels': self.config['gitlab']['bot_label']
            })
            
            issues = list_result.get('items', [])
            if not issues:
                self.skipTest("No issues found in test project")
                
            # Get discussions for first issue
            issue = issues[0]
            discussions = self.mcp_client.call_tool('list_issue_discussions', {
                'project_id': project_id,
                'issue_iid': issue['iid']
            })
            
            self.assertIsInstance(discussions, dict)
            discussion_items = discussions.get('items', [])
            self.logger.info(f"Found {len(discussion_items)} discussions on issue !{issue['iid']}")
            
        except Exception as e:
            self.fail(f"Failed to get GitLab issue discussions: {e}")
    
    def test_task_gitlab_issue_creation(self):
        """Test creating TaskGitLabIssue objects with real GitLab data"""
        try:
            # List issues first
            project_id = self.config['gitlab']['project_id']
            list_result = self.mcp_client.call_tool('list_issues', {
                'project_id': project_id,
                'state': 'opened',
                'labels': self.config['gitlab']['bot_label']
            })
            
            issues = list_result.get('items', [])
            if not issues:
                self.skipTest("No issues found in test project")
            
            # Create TaskGitLabIssue with real data
            issue_data = issues[0]
            
            # Mock gitlab_client since we're testing MCP interaction
            with patch('handlers.task_getter_gitlab.GitlabClient') as mock_gitlab_client:
                task = TaskGitLabIssue(
                    issue=issue_data,
                    mcp_client=self.mcp_client,
                    gitlab_client=mock_gitlab_client,
                    config=self.config
                )
                
                # Test task properties
                self.assertIsInstance(task.issue, dict)
                self.assertIsInstance(task.project_id, int)
                self.assertIsInstance(task.issue_iid, int)
                
                # Test get_prompt method (reads real data)
                prompt = task.get_prompt()
                self.assertIsInstance(prompt, str)
                self.assertIn('ISSUE:', prompt)
                self.logger.info(f"Generated prompt for issue !{task.issue_iid}")
                
        except Exception as e:
            self.fail(f"Failed to create TaskGitLabIssue: {e}")
    
    def test_task_getter_from_gitlab(self):
        """Test TaskGetterFromGitLab with real GitLab API"""
        try:
            # Mock gitlab_client since we're testing MCP interaction
            with patch('handlers.task_getter_gitlab.GitlabClient') as mock_gitlab_client:
                task_getter = TaskGetterFromGitLab(
                    mcp_client=self.mcp_client,
                    gitlab_client=mock_gitlab_client,
                    config=self.config
                )
                
                # Test getting tasks
                tasks = task_getter.get_tasks()
                self.assertIsInstance(tasks, list)
                
                if tasks:
                    # Verify task structure
                    task = tasks[0]
                    self.assertIsInstance(task, TaskGitLabIssue)
                    self.assertIsInstance(task.issue, dict)
                    self.logger.info(f"Found {len(tasks)} GitLab tasks")
                else:
                    self.logger.info("No GitLab tasks found (this is normal if no issues match criteria)")
                
        except Exception as e:
            self.fail(f"Failed to get tasks from GitLab: {e}")


class TestGitLabTaskKey(unittest.TestCase):
    """Test GitLab task key functionality"""
    
    def test_gitlab_issue_task_key(self):
        """Test GitLab issue task key creation and parsing"""
        # Test data
        project_id = "test-group/test-project"
        issue_iid = 123
        
        # Create task key
        task_key = GitLabIssueTaskKey(project_id, issue_iid)
        
        # Test properties
        self.assertEqual(task_key.project_id, project_id)
        self.assertEqual(task_key.issue_iid, issue_iid)
        
        # Test string representation
        key_str = str(task_key)
        self.assertIn(str(project_id), key_str)
        self.assertIn(str(issue_iid), key_str)


if __name__ == '__main__':
    unittest.main()
    
    def test_label_manipulation(self):
        """Test label list manipulation without GitLab API calls"""
        # Test basic label operations (GitLab uses string arrays for labels)
        labels = ['coding agent', 'bug', 'enhancement']
        
        # Test removing a label
        if 'coding agent' in labels:
            labels.remove('coding agent')
        labels.append('coding agent processing')
        
        self.assertNotIn('coding agent', labels)
        self.assertIn('coding agent processing', labels)
        self.assertIn('bug', labels)
        self.assertIn('enhancement', labels)
    
    def test_description_formatting(self):
        """Test description formatting without GitLab-specific data"""
        # Test basic description template formatting
        title = "Test GitLab Issue"
        description = "This is a test GitLab issue for automation"
        
        prompt = f"ISSUE: {title}\n\n{description}\n\nDISCUSSIONS:\n"
        
        self.assertIn('ISSUE:', prompt)
        self.assertIn(title, prompt)
        self.assertIn(description, prompt)
        self.assertIn('DISCUSSIONS:', prompt)


if __name__ == '__main__':
    unittest.main()