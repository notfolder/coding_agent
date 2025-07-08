"""
Integration tests for the coding agent framework (simplified, no external dependencies)
"""
import unittest
import sys
import os
import yaml
import json

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from tests.mocks import MockMCPToolClient, MockLLMClient


class TestBasicIntegration(unittest.TestCase):
    """Basic integration tests without external dependencies"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Load test config
        config_path = os.path.join(os.path.dirname(__file__), '..', 'test_config.yaml')
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
    
    def test_mock_llm_client_integration(self):
        """Test mock LLM client integration"""
        llm_client = MockLLMClient(self.config)
        
        # Test conversation flow
        llm_client.send_system_prompt("Test system prompt")
        llm_client.send_user_message("Test user message")
        
        # Get response
        response, tools = llm_client.get_response()
        
        # Verify response structure
        self.assertIsInstance(response, str)
        self.assertIsInstance(tools, list)
        
        # Parse JSON response
        parsed = json.loads(response)
        self.assertIn('done', parsed)
    
    def test_mock_mcp_client_integration(self):
        """Test mock MCP client integration"""
        server_config = {
            'mcp_server_name': 'test_server',
            'command': ['mock_test_server']
        }
        mcp_client = MockMCPToolClient(server_config)
        
        # Test basic operations
        mcp_client.call_initialize()
        tools = mcp_client.list_tools()
        self.assertIsInstance(tools, list)
        
        # Test tool call
        result = mcp_client.call_tool('test_tool', {'param': 'value'})
        self.assertEqual(result, {})
        
        # Test properties
        self.assertIsInstance(mcp_client.system_prompt, str)
        
        # Test cleanup
        mcp_client.close()
    
    def test_config_loading(self):
        """Test configuration loading"""
        self.assertIn('llm', self.config)
        self.assertIn('provider', self.config['llm'])
        self.assertEqual(self.config['llm']['provider'], 'mock')


if __name__ == '__main__':
    unittest.main()