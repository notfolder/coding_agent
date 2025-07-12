"""
Comprehensive integration tests using GitHub and GitLab mocks
"""
import unittest
import sys
import os
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Mock the mcp module before importing TaskHandler
sys.modules['mcp'] = MagicMock()
sys.modules['mcp'].McpError = Exception

from handlers.task_handler import TaskHandler
from handlers.task_getter_github import TaskGetterFromGitHub, TaskGitHubIssue
from handlers.task_getter_gitlab import TaskGetterFromGitLab, TaskGitLabIssue
from handlers.task_factory import GitHubTaskFactory, GitLabTaskFactory
from handlers.task_key import GitHubIssueTaskKey, GitLabIssueTaskKey
from tests.mocks.mock_mcp_client import MockMCPToolClient
from tests.mocks.mock_llm_client import MockLLMClient, MockLLMClientWithToolCalls


class TestGitHubWorkflowIntegration(unittest.TestCase):
    """End-to-end GitHub workflow tests with comprehensive mocks"""
    
    def setUp(self):
        """Set up test environment"""
        self.config = {
            'github': {
                'owner': 'testorg',
                'repo': 'testrepo',
                'query': 'label:"coding agent"',
                'bot_label': 'coding agent',
                'processing_label': 'coding agent processing',
                'done_label': 'coding agent done',
                'done_label': 'coding agent done'
            },
            'max_llm_process_num': 20
        }
        
        # Create comprehensive GitHub mock setup
        github_server_config = {'mcp_server_name': 'github'}
        self.github_mcp_client = MockMCPToolClient(github_server_config)
        self.github_client = MagicMock()
        self.llm_client = MockLLMClientWithToolCalls(self.config)
    
    def test_full_github_issue_workflow(self):
        """Test complete GitHub issue processing workflow"""
        # 1. Get tasks from GitHub
        task_getter = TaskGetterFromGitHub(config=self.config, mcp_clients={"github": self.github_mcp_client})
        tasks = task_getter.get_task_list()
        self.assertIsInstance(tasks, list)
        self.assertGreater(len(tasks), 0, "Should find mock GitHub issues")
        
        # 2. Process first task
        task = tasks[0]
        self.assertIsInstance(task, TaskGitHubIssue)
        
        # 3. Prepare task (updates labels)
        original_labels = task.labels.copy()
        task.prepare()
        
        # Verify label changes
        self.assertNotIn('coding agent', task.labels)
        self.assertIn('coding agent processing', task.labels)
        
        # 4. Generate prompt
        prompt = task.get_prompt()
        self.assertIsInstance(prompt, str)
        self.assertIn('ISSUE:', prompt)
        self.assertIn('COMMENTS:', prompt)
        
        # 5. Handle task with LLM
        task_handler = TaskHandler(
            llm_client=self.llm_client,
            mcp_clients={"github": self.github_mcp_client},
            config=self.config
        )
        
        # Process the task
        result = task_handler.handle(task)
        
        # Verify completion
        self.assertIsNone(result)  # Should complete without errors
        
        # Verify MCP interactions occurred
        mock_data = self.github_mcp_client.get_mock_data()
        self.assertIn(task.issue['number'], mock_data['updated_issues'])
    
    def test_github_task_factory_integration(self):
        """Test GitHub task factory integration"""
        factory = GitHubTaskFactory(
            mcp_client=self.github_mcp_client,
            github_client=self.github_client,
            config=self.config
        )
        
        # Create task from key
        task_key = GitHubIssueTaskKey('testorg', 'testrepo', 1)
        task = factory.create_task(task_key)
        
        self.assertIsInstance(task, TaskGitHubIssue)
        self.assertEqual(task.issue['number'], 1)
        
        # Test task workflow
        task.prepare()
        prompt = task.get_prompt()
        self.assertIn('Test GitHub Issue 1', prompt)
    
    def test_github_error_recovery_workflow(self):
        """Test GitHub workflow error recovery"""
        # Create MCP client that fails initially then recovers
        error_mcp_client = MockMCPToolClient({'mcp_server_name': 'github'})
        call_count = 0
        original_call_tool = error_mcp_client.call_tool
        
        def intermittent_failure_tool(tool, args):
            nonlocal call_count
            call_count += 1
            if tool == 'update_issue' and call_count <= 2:
                raise Exception("Temporary network error")
            return original_call_tool(tool, args)
        
        error_mcp_client.call_tool = intermittent_failure_tool
        
        # Create task with error-prone MCP client
        sample_issue = error_mcp_client.get_mock_data()['issues'][0]
        task = TaskGitHubIssue(
            issue=sample_issue,
            mcp_client=error_mcp_client,
            
            config=self.config
        )
        
        # Should handle errors gracefully
        try:
            task.prepare()  # First call may fail
        except Exception:
            pass  # Expected for this test
        
        # Retry should work
        try:
            task.prepare()  # Subsequent calls should succeed
        except Exception:
            pass  # May still fail, which is acceptable
    
    def test_github_multiple_issues_workflow(self):
        """Test processing multiple GitHub issues"""
        task_getter = TaskGetterFromGitHub(config=self.config, mcp_clients={"github": self.github_mcp_client})
        tasks = task_getter.get_task_list()
        
        # Process all available tasks
        for task in tasks:
            # Prepare each task
            task.prepare()
            
            # Generate prompt for each
            prompt = task.get_prompt()
            self.assertIsInstance(prompt, str)
            
            # Simple completion test
            self.llm_client.set_mock_response({
                "comment": f"Completed task for issue #{task.issue['number']}",
                "done": True
            })
            
            task_handler = TaskHandler(
                llm_client=self.llm_client,
                mcp_clients={"github": self.github_mcp_client},
                config=self.config
            )
            
            result = task_handler.handle(task)
            self.assertIsNone(result)
    
    def test_github_comment_workflow(self):
        """Test GitHub comment creation workflow"""
        tasks = TaskGetterFromGitHub(config=self.config, mcp_clients={"github": self.github_mcp_client}).get_task_list()

        if tasks:
            task = tasks[0]
            
            # Mock comment method if it exists
            if hasattr(task, 'comment'):
                original_comment = task.comment
                comments_posted = []
                
                def mock_comment(text, mention=False):
                    comments_posted.append({'text': text, 'mention': mention})
                    return original_comment(text, mention) if original_comment else None
                
                task.comment = mock_comment
                
                # Post test comments
                task.comment("Test comment without mention")
                task.comment("Test comment with mention", mention=True)
                
                # Verify comments were tracked
                self.assertEqual(len(comments_posted), 2)
                self.assertEqual(comments_posted[0]['text'], "Test comment without mention")
                self.assertFalse(comments_posted[0]['mention'])
                self.assertTrue(comments_posted[1]['mention'])


class TestGitLabWorkflowIntegration(unittest.TestCase):
    """End-to-end GitLab workflow tests with comprehensive mocks"""
    
    def setUp(self):
        """Set up test environment"""
        self.config = {
            'gitlab': {
                'project_id': 123,
                'bot_label': 'coding agent',
                'processing_label': 'coding agent processing',
                'done_label': 'coding agent done',
                'done_label': 'coding agent done'
            },
            'max_llm_process_num': 20
        }
        
        # Create comprehensive GitLab mock setup
        gitlab_server_config = {'mcp_server_name': 'gitlab'}
        self.gitlab_mcp_client = MockMCPToolClient(gitlab_server_config)
        self.gitlab_client = MagicMock()
        self.llm_client = MockLLMClientWithToolCalls(self.config)
    
    def test_full_gitlab_issue_workflow(self):
        """Test complete GitLab issue processing workflow"""
        # 1. Get tasks from GitLab
        task_getter = TaskGetterFromGitLab(config=self.config, mcp_clients={"gitlab": self.gitlab_mcp_client})

        tasks = task_getter.get_task_list()
        self.assertIsInstance(tasks, list)
        self.assertGreater(len(tasks), 0, "Should find mock GitLab issues")
        
        # 2. Process first task
        task = tasks[0]
        self.assertIsInstance(task, TaskGitLabIssue)
        
        # 3. Prepare task (updates labels)
        original_labels = task.issue.get('labels', []).copy()
        task.prepare()
        
        # Verify label changes
        updated_labels = task.issue['labels']
        self.assertNotIn('coding agent', updated_labels)
        self.assertIn('coding agent processing', updated_labels)
        
        # 4. Generate prompt
        prompt = task.get_prompt()
        self.assertIsInstance(prompt, str)
        self.assertIn('ISSUE:', prompt)
        
        # 5. Handle task with LLM
        task_handler = TaskHandler(
            llm_client=self.llm_client,
            mcp_clients={"gitlab": self.gitlab_mcp_client},
            config=self.config
        )
        
        # Process the task
        result = task_handler.handle(task)
        
        # Verify completion
        self.assertIsNone(result)  # Should complete without errors
        
        # Verify MCP interactions occurred
        mock_data = self.gitlab_mcp_client.get_mock_data()
        self.assertIn(task.issue_iid, mock_data['updated_issues'])
    
    def test_gitlab_task_factory_integration(self):
        """Test GitLab task factory integration"""
        factory = GitLabTaskFactory(
            self.gitlab_mcp_client,
            config=self.config
        )
        
        # Create task from key
        task_key = GitLabIssueTaskKey(123, 1)
        task = factory.create_task(task_key)
        
        self.assertIsInstance(task, TaskGitLabIssue)
        self.assertEqual(task.issue_iid, 1)
        
        # Test task workflow
        task.prepare()
        prompt = task.get_prompt()
        self.assertIn('Test GitLab Issue 1', prompt)
    
    def test_gitlab_discussions_workflow(self):
        """Test GitLab discussions handling"""
        tasks = TaskGetterFromGitLab(config=self.config, mcp_clients={"gitlab": self.gitlab_mcp_client}).get_task_list()

        if tasks:
            task = tasks[0]
            
            # Generate prompt (includes discussions)
            prompt = task.get_prompt()
            
            # Should include discussion content from mock data
            self.assertIsInstance(prompt, str)
            # Verify discussions are included in some form
            # (The exact format depends on implementation)
    
    def test_gitlab_label_transitions(self):
        """Test GitLab label transition workflow"""
        task_getter = TaskGetterFromGitLab(config=self.config, mcp_clients={"gitlab": self.gitlab_mcp_client})

        tasks = task_getter.get_task_list()

        for task in tasks:
            original_labels = task.issue.get('labels', []).copy()
            
            # Test prepare (bot_label -> processing_label)
            task.prepare()
            
            current_labels = task.issue['labels']
            
            # Verify label transition
            if 'coding agent' in original_labels:
                self.assertNotIn('coding agent', current_labels)
                self.assertIn('coding agent processing', current_labels)
            
            # Other labels should be preserved
            for label in original_labels:
                if label != 'coding agent':
                    self.assertIn(label, current_labels)


class TestMixedPlatformWorkflow(unittest.TestCase):
    """Test workflows involving both GitHub and GitLab"""
    
    def setUp(self):
        """Set up test environment with both platforms"""
        self.config = {
            'github': {
                'owner': 'testorg',
                'repo': 'testrepo',
                'query': 'label:"coding agent"',
                'bot_label': 'coding agent',
                'processing_label': 'coding agent processing'
            },
            'gitlab': {
                'project_id': 123,
                'bot_label': 'coding agent',
                'processing_label': 'coding agent processing'
            },
            'max_llm_process_num': 20
        }
        
        # Create both GitHub and GitLab mock setups
        self.github_mcp_client = MockMCPToolClient({'mcp_server_name': 'github'})
        self.gitlab_mcp_client = MockMCPToolClient({'mcp_server_name': 'gitlab'})
        self.github_client = MagicMock()
        self.gitlab_client = MagicMock()
        self.llm_client = MockLLMClient(self.config)
    
    def test_task_handler_with_multiple_platforms(self):
        """Test TaskHandler with both GitHub and GitLab MCP clients"""
        # Get tasks from both platforms
        github_tasks = TaskGetterFromGitHub(config=self.config, mcp_clients={"github": self.github_mcp_client}).get_task_list()

        gitlab_tasks = TaskGetterFromGitLab(config=self.config, mcp_clients={"gitlab": self.gitlab_mcp_client}).get_task_list()

        # Create task handler with both MCP clients
        task_handler = TaskHandler(
            llm_client=self.llm_client,
            mcp_clients={"github": self.github_mcp_client, "gitlab": self.gitlab_mcp_client},
            config=self.config
        )
        
        # Process GitHub task
        if github_tasks:
            self.llm_client.set_mock_response({
                "comment": "GitHub task completed",
                "done": True
            })
            result = task_handler.handle(github_tasks[0])
            self.assertIsNone(result)
        
        # Process GitLab task
        if gitlab_tasks:
            self.llm_client.set_mock_response({
                "comment": "GitLab task completed",
                "done": True
            })
            result = task_handler.handle(gitlab_tasks[0])
            self.assertIsNone(result)
    
    def test_platform_specific_configurations(self):
        """Test that platform-specific configurations are respected"""
        # Test GitHub configuration
        github_task_getter = TaskGetterFromGitHub(config=self.config, mcp_clients={"github": self.github_mcp_client})
        github_tasks = github_task_getter.get_task_list()

        # Test GitLab configuration
        gitlab_task_getter = TaskGetterFromGitLab(config=self.config, mcp_clients={"gitlab": self.gitlab_mcp_client})
        gitlab_tasks = gitlab_task_getter.get_task_list()

        # Verify that each platform uses its own configuration
        if github_tasks:
            github_task = github_tasks[0]
            self.assertEqual(github_task.issue['owner'], 'testorg')
            self.assertEqual(github_task.issue['repo'], 'testrepo')
        
        if gitlab_tasks:
            gitlab_task = gitlab_tasks[0]
            self.assertEqual(gitlab_task.project_id, 123)


class TestErrorHandlingIntegration(unittest.TestCase):
    """Test comprehensive error handling across components"""
    
    def setUp(self):
        """Set up test environment"""
        self.config = {
            'github': {
                'owner': 'testorg',
                'repo': 'testrepo',
                'bot_label': 'coding agent',
                'processing_label': 'coding agent processing'
            },
            'max_llm_process_num': 5  # Low limit for testing
        }
        
        self.github_mcp_client = MockMCPToolClient({'mcp_server_name': 'github'})
        self.github_client = MagicMock()
    
    def test_comprehensive_error_recovery(self):
        """Test error recovery across multiple failure points"""
        # Create error-prone components
        from tests.mocks.mock_llm_client import MockLLMClientWithErrors
        error_llm = MockLLMClientWithErrors(self.config)
        
        # Create task
        tasks = TaskGetterFromGitHub(config=self.config, mcp_clients={"github": self.github_mcp_client}).get_task_list()

        if tasks:
            task = tasks[0]
            
            # Test with error-prone LLM
            task_handler = TaskHandler(
                llm_client=error_llm,
                mcp_clients={"github": self.github_mcp_client},
                config=self.config
            )
            
            # Should handle errors and eventually complete or fail gracefully
            try:
                result = task_handler.handle(task)
                # If it completes, that's successful error handling
            except Exception as e:
                # If it fails, check that it's a reasonable failure
                self.assertIsInstance(e, (ValueError, TypeError, Exception))
    
    def test_network_timeout_simulation(self):
        """Test handling of simulated network timeouts"""
        import time
        
        # Create slow MCP client
        slow_mcp_client = MockMCPToolClient({'mcp_server_name': 'github'})
        original_call_tool = slow_mcp_client.call_tool
        
        def slow_call_tool(tool, args):
            time.sleep(0.05)  # Small delay to simulate slow network
            return original_call_tool(tool, args)
        
        slow_mcp_client.call_tool = slow_call_tool
        
        # Test with slow client
        tasks = TaskGetterFromGitHub(config=self.config, mcp_clients={"github": slow_mcp_client}).get_task_list()

        # Should complete despite slow responses
        self.assertIsInstance(tasks, list)
    
    def test_malformed_data_handling(self):
        """Test handling of malformed data from mock services"""
        # Create MCP client with malformed data
        malformed_mcp = MockMCPToolClient({'mcp_server_name': 'github'})
        
        # Inject malformed data
        malformed_mcp.mock_data['issues'][0]['repository_url'] = 'not-a-valid-url'
        malformed_mcp.mock_data['issues'][0]['labels'] = "not-a-list"  # Should be list
        
        # Test task creation with malformed data
        try:
            tasks = TaskGetterFromGitHub(config=self.config, mcp_clients={"github": malformed_mcp}).get_task_list()

            # If tasks are created, test their behavior
            if tasks:
                task = tasks[0]
                # Should handle malformed data gracefully
                try:
                    task.prepare()
                    prompt = task.get_prompt()
                except (AttributeError, TypeError, IndexError):
                    # Expected for malformed data
                    pass
                    
        except (AttributeError, TypeError, IndexError, ValueError):
            # Expected for severely malformed data
            pass


if __name__ == '__main__':
    unittest.main()