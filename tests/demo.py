#!/usr/bin/env python3
"""
Interactive demo for real GitHub and GitLab integration testing
"""
import sys
import os
import yaml
import logging

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from clients.mcp_tool_client import MCPToolClient
from tests.mocks.mock_llm_client import MockLLMClient
from handlers.task_getter_github import TaskGetterFromGitHub
from handlers.task_getter_gitlab import TaskGetterFromGitLab
from unittest.mock import patch

class RealIntegrationDemo:
    """Interactive demonstration of real GitHub and GitLab integration"""
    
    def __init__(self):
        self.setup_logging()
        self.github_token = os.environ.get('GITHUB_TOKEN')
        self.gitlab_token = os.environ.get('GITLAB_TOKEN')
        
    def setup_logging(self):
        """Set up logging for the demo"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
    
    def check_prerequisites(self):
        """Check if API tokens are available"""
        print("🔍 Checking prerequisites...")
        
        if not self.github_token and not self.gitlab_token:
            print("❌ No API tokens found!")
            print("   Please set GITHUB_TOKEN and/or GITLAB_TOKEN environment variables")
            print("   Example:")
            print("   export GITHUB_TOKEN='your_github_token_here'")
            print("   export GITLAB_TOKEN='your_gitlab_token_here'")
            return False
        
        if self.github_token:
            print("✅ GitHub token found")
        else:
            print("⚠️  No GitHub token - GitHub demos will be skipped")
        
        if self.gitlab_token:
            print("✅ GitLab token found")
        else:
            print("⚠️  No GitLab token - GitLab demos will be skipped")
        
        return True
    
    def load_config(self, service):
        """Load configuration for a service"""
        config_path = os.path.join(
            os.path.dirname(__file__),
            f'real_test_config_{service}.yaml'
        )
        
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    
    def demo_github_mcp_connection(self):
        """Demonstrate GitHub MCP server connection"""
        if not self.github_token:
            print("⏭️  Skipping GitHub demo (no token)")
            return
        
        print("\n🔗 Testing GitHub MCP Connection...")
        
        try:
            # Set up environment
            os.environ['GITHUB_TOKEN'] = self.github_token
            
            # Load configuration
            config = self.load_config('github')
            
            # Initialize MCP client
            mcp_client = MCPToolClient(config['mcp_servers'][0])
            
            # Test connection
            print("   Initializing MCP client...")
            mcp_client.call_initialize()
            
            # List available tools
            print("   Listing available tools...")
            tools = mcp_client.list_tools()
            
            print(f"   ✅ Connected successfully! Found {len(tools)} tools:")
            for tool in tools[:5]:  # Show first 5 tools
                print(f"      - {tool.name}")
            if len(tools) > 5:
                print(f"      ... and {len(tools) - 5} more")
            
            # Test a simple tool call
            print("   Testing issue search...")
            query = config['github']['query']
            result = mcp_client.call_tool('search_issues', {'q': query})
            
            if isinstance(result, dict) and 'items' in result:
                issues = result['items']
                print(f"   ✅ Found {len(issues)} issues matching query")
                
                if issues:
                    issue = issues[0]
                    print(f"      Example: #{issue['number']} - {issue['title'][:50]}...")
            else:
                print("   ℹ️  No issues found (this is normal for test repositories)")
            
            # Clean up
            mcp_client.close()
            print("   ✅ GitHub MCP demo completed successfully")
            
        except Exception as e:
            print(f"   ❌ GitHub MCP demo failed: {e}")
            self.logger.error(f"GitHub MCP demo error: {e}", exc_info=True)
    
    def demo_gitlab_mcp_connection(self):
        """Demonstrate GitLab MCP server connection"""
        if not self.gitlab_token:
            print("⏭️  Skipping GitLab demo (no token)")
            return
        
        print("\n🔗 Testing GitLab MCP Connection...")
        
        try:
            # Set up environment
            os.environ['GITLAB_TOKEN'] = self.gitlab_token
            
            # Load configuration
            config = self.load_config('gitlab')
            
            # Initialize MCP client
            mcp_client = MCPToolClient(config['mcp_servers'][0])
            
            # Test connection
            print("   Initializing MCP client...")
            mcp_client.call_initialize()
            
            # List available tools
            print("   Listing available tools...")
            tools = mcp_client.list_tools()
            
            print(f"   ✅ Connected successfully! Found {len(tools)} tools:")
            for tool in tools[:5]:  # Show first 5 tools
                print(f"      - {tool.name}")
            if len(tools) > 5:
                print(f"      ... and {len(tools) - 5} more")
            
            # Test a simple tool call
            print("   Testing issue listing...")
            project_id = config['gitlab']['project_id']
            result = mcp_client.call_tool('list_issues', {
                'project_id': project_id,
                'state': 'opened',
                'labels': config['gitlab']['bot_label']
            })
            
            if isinstance(result, dict) and 'items' in result:
                issues = result['items']
                print(f"   ✅ Found {len(issues)} issues in project")
                
                if issues:
                    issue = issues[0]
                    print(f"      Example: !{issue['iid']} - {issue['title'][:50]}...")
            else:
                print("   ℹ️  No issues found (this is normal for test projects)")
            
            # Clean up
            mcp_client.close()
            print("   ✅ GitLab MCP demo completed successfully")
            
        except Exception as e:
            print(f"   ❌ GitLab MCP demo failed: {e}")
            self.logger.error(f"GitLab MCP demo error: {e}", exc_info=True)
    
    def demo_github_task_workflow(self):
        """Demonstrate GitHub task workflow"""
        if not self.github_token:
            print("⏭️  Skipping GitHub workflow demo (no token)")
            return
        
        print("\n🔄 Testing GitHub Task Workflow...")
        
        try:
            # Set up environment
            os.environ['GITHUB_TOKEN'] = self.github_token
            
            # Load configuration
            config = self.load_config('github')
            
            # Initialize clients
            mcp_client = MCPToolClient(config['mcp_servers'][0])
            llm_client = MockLLMClient(config)
            
            # Mock github_client since we're testing MCP interaction
            with patch('handlers.task_getter_github.GithubClient') as mock_github_client:
                print("   Initializing task getter...")
                task_getter = TaskGetterFromGitHub(
                    mcp_client=mcp_client,
                    github_client=mock_github_client,
                    config=config
                )
                
                print("   Retrieving tasks from GitHub...")
                tasks = task_getter.get_tasks()
                
                print(f"   ✅ Retrieved {len(tasks)} tasks")
                
                if tasks:
                    task = tasks[0]
                    print(f"      Processing task: {task.issue.get('title', 'Unknown')[:50]}...")
                    
                    # Test task preparation
                    print("      Testing task preparation...")
                    task.prepare()
                    print("      ✅ Task preparation completed")
                    
                    # Test prompt generation
                    print("      Testing prompt generation...")
                    prompt = task.get_prompt()
                    print(f"      ✅ Generated prompt ({len(prompt)} characters)")
                    
                else:
                    print("   ℹ️  No tasks found - this is normal if no issues match criteria")
            
            # Clean up
            mcp_client.close()
            print("   ✅ GitHub workflow demo completed successfully")
            
        except Exception as e:
            print(f"   ❌ GitHub workflow demo failed: {e}")
            self.logger.error(f"GitHub workflow demo error: {e}", exc_info=True)
    
    def demo_gitlab_task_workflow(self):
        """Demonstrate GitLab task workflow"""
        if not self.gitlab_token:
            print("⏭️  Skipping GitLab workflow demo (no token)")
            return
        
        print("\n🔄 Testing GitLab Task Workflow...")
        
        try:
            # Set up environment
            os.environ['GITLAB_TOKEN'] = self.gitlab_token
            
            # Load configuration
            config = self.load_config('gitlab')
            
            # Initialize clients
            mcp_client = MCPToolClient(config['mcp_servers'][0])
            llm_client = MockLLMClient(config)
            
            # Mock gitlab_client since we're testing MCP interaction
            with patch('handlers.task_getter_gitlab.GitlabClient') as mock_gitlab_client:
                print("   Initializing task getter...")
                task_getter = TaskGetterFromGitLab(
                    mcp_client=mcp_client,
                    gitlab_client=mock_gitlab_client,
                    config=config
                )
                
                print("   Retrieving tasks from GitLab...")
                tasks = task_getter.get_tasks()
                
                print(f"   ✅ Retrieved {len(tasks)} tasks")
                
                if tasks:
                    task = tasks[0]
                    print(f"      Processing task: {task.issue.get('title', 'Unknown')[:50]}...")
                    
                    # Test task preparation
                    print("      Testing task preparation...")
                    task.prepare()
                    print("      ✅ Task preparation completed")
                    
                    # Test prompt generation
                    print("      Testing prompt generation...")
                    prompt = task.get_prompt()
                    print(f"      ✅ Generated prompt ({len(prompt)} characters)")
                    
                else:
                    print("   ℹ️  No tasks found - this is normal if no issues match criteria")
            
            # Clean up
            mcp_client.close()
            print("   ✅ GitLab workflow demo completed successfully")
            
        except Exception as e:
            print(f"   ❌ GitLab workflow demo failed: {e}")
            self.logger.error(f"GitLab workflow demo error: {e}", exc_info=True)
    
    def run_interactive_demo(self):
        """Run the interactive demo"""
        print("🚀 Real GitHub and GitLab Integration Demo")
        print("==========================================")
        
        if not self.check_prerequisites():
            return
        
        print("\nThis demo will test real API integration with GitHub and GitLab.")
        print("The tests are designed to be non-destructive and safe to run.")
        print()
        
        # Run demonstrations
        self.demo_github_mcp_connection()
        self.demo_gitlab_mcp_connection()
        self.demo_github_task_workflow()
        self.demo_gitlab_task_workflow()
        
        print("\n🎉 Demo completed!")
        print("\nTo run the full test suite:")
        print("  python3 -m tests.run_tests --real")
        print("\nTo run individual test types:")
        print("  python3 -m tests.run_tests --unit")
        print("  python3 -m tests.run_tests --integration")


def main():
    """Main function"""
    try:
        demo = RealIntegrationDemo()
        demo.run_interactive_demo()
    except KeyboardInterrupt:
        print("\n\n👋 Demo interrupted by user")
    except Exception as e:
        print(f"\n❌ Demo failed with error: {e}")
        logging.exception("Demo error")


if __name__ == '__main__':
    main()
    print(f"Tool call result: {result}")
    
    # Test system prompt
    prompt = test_client.system_prompt
    print(f"System prompt: {prompt}")
    print()


def demonstrate_mock_llm_client():
    """Demonstrate mock LLM client usage"""
    print("=== Mock LLM Client Demo ===")
    
    config = {'llm': {'provider': 'mock'}}
    llm_client = MockLLMClient(config)
    
    # Send system prompt
    llm_client.send_system_prompt("You are a helpful coding assistant.")
    
    # Send user message
    llm_client.send_user_message("Please help me with a test task")
    
    # Get responses
    response1, _ = llm_client.get_response()
    print(f"Response 1: {response1}")
    
    response2, _ = llm_client.get_response()
    print(f"Response 2: {response2}")
    
    # Show interaction history
    print(f"System prompt: {llm_client.system_prompt}")
    print(f"User messages: {llm_client.user_messages}")
    print()


def demonstrate_test_workflow():
    """Demonstrate the basic test workflow without GitHub/GitLab specifics"""
    print("=== Test Workflow Demo ===")
    
    # Load test config
    config_path = os.path.join(os.path.dirname(__file__), 'test_config.yaml')
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    print("Test configuration loaded:")
    print(f"  LLM Provider: {config['llm']['provider']}")
    # Note: GitHub/GitLab specific config removed per user request
    print()
    
    # Create mock clients (generic, not service-specific)
    test_client = MockMCPToolClient({'mcp_server_name': 'test_server', 'command': ['mock']})
    llm_client = MockLLMClient(config)
    
    print("Mock clients created successfully!")
    print(f"  Test MCP client initialized with server: {test_client.server_name}")
    print(f"  LLM client has {len(llm_client.response_queue)} default responses")
    print()


def run_sample_tests():
    """Run sample tests to show the framework in action"""
    print("=== Running Sample Tests ===")
    
    # Run unit tests
    print("Running unit tests...")
    unit_success = run_unit_tests()
    print(f"Unit tests: {'PASSED' if unit_success else 'FAILED'}")
    
    # Run integration tests
    print("Running integration tests...")
    integration_success = run_integration_tests()
    print(f"Integration tests: {'PASSED' if integration_success else 'FAILED'}")
    
    # Overall result
    overall_success = unit_success and integration_success
    print(f"Overall result: {'PASSED' if overall_success else 'FAILED'}")
    print()


def main():
    """Main demo function"""
    print("Coding Agent Test Automation Framework Demo")
    print("(GitHub/GitLab mocking removed per user request)")
    print("=" * 50)
    print()
    
    try:
        demonstrate_mock_mcp_client()
        demonstrate_mock_llm_client()
        demonstrate_test_workflow()
        run_sample_tests()
        
        print("✅ Demo completed successfully!")
        print()
        print("To run the full test suite manually:")
        print("  python3 -m tests.run_tests")
        print("  python3 -m tests.run_tests --unit")
        print("  python3 -m tests.run_tests --integration")
        print()
        print("Note: GitHub and GitLab mocking has been removed per user request.")
        print("Tests now focus on LLM client mocking and general framework functionality.")
        
    except Exception as e:
        print(f"❌ Demo failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()