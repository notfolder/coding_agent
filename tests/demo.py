#!/usr/bin/env python3
"""
Example usage of the coding agent test automation framework
"""
import os
import sys

# Add the parent directory to path so we can import the test modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tests.mocks import MockMCPToolClient, MockLLMClient
from tests.run_tests import run_tests, run_unit_tests, run_integration_tests
import yaml


def demonstrate_mock_mcp_client():
    """Demonstrate mock MCP client usage"""
    print("=== Mock MCP Client Demo ===")
    
    # Create GitHub mock client
    github_config = {'mcp_server_name': 'github', 'command': ['mock']}
    github_client = MockMCPToolClient(github_config)
    
    # Show available tools
    tools = github_client.list_tools()
    print(f"GitHub tools: {[tool['name'] for tool in tools]}")
    
    # Search for issues
    issues = github_client.call_tool('search_issues', {'q': 'label:"coding agent"'})
    print(f"Found {len(issues['items'])} mock issues")
    
    # Get issue details
    issue = github_client.call_tool('get_issue', {'issue_number': 1})
    print(f"Issue: {issue['title']}")
    
    # Add comment
    comment = github_client.call_tool('add_issue_comment', {
        'issue_number': 1, 
        'body': 'This is a test comment'
    })
    print(f"Added comment: {comment['body']}")
    print()


def demonstrate_mock_llm_client():
    """Demonstrate mock LLM client usage"""
    print("=== Mock LLM Client Demo ===")
    
    config = {'llm': {'provider': 'mock'}}
    llm_client = MockLLMClient(config)
    
    # Send system prompt
    llm_client.send_system_prompt("You are a helpful coding assistant.")
    
    # Send user message
    llm_client.send_user_message("Please help me with issue #1")
    
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
    """Demonstrate the complete test workflow"""
    print("=== Test Workflow Demo ===")
    
    # Load test config
    config_path = os.path.join(os.path.dirname(__file__), 'test_config.yaml')
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    print("Test configuration loaded:")
    print(f"  LLM Provider: {config['llm']['provider']}")
    print(f"  GitHub Bot Label: {config['github']['bot_label']}")
    print(f"  GitLab Bot Label: {config['gitlab']['bot_label']}")
    print()
    
    # Create mock clients
    github_client = MockMCPToolClient({'mcp_server_name': 'github', 'command': ['mock']})
    gitlab_client = MockMCPToolClient({'mcp_server_name': 'gitlab', 'command': ['mock']})
    llm_client = MockLLMClient(config)
    
    print("Mock clients created successfully!")
    print(f"  GitHub client has {len(github_client.mock_data['issues'])} mock issues")
    print(f"  GitLab client has {len(gitlab_client.mock_data['issues'])} mock issues")
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
        
    except Exception as e:
        print(f"❌ Demo failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()