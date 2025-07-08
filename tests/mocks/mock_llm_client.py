"""
Mock LLM client for testing
"""
import json
import sys
import os
from typing import List, Tuple, Dict, Any, Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from clients.llm_base import LLMClient


class MockLLMClient(LLMClient):
    """Mock implementation of LLM client for testing"""
    
    def __init__(self, config: Dict[str, Any], functions: List = None, tools: List = None):
        self.config = config
        self.functions = functions or []
        self.tools = tools or []
        self.system_prompt = ""
        self.user_messages = []
        self.response_queue = []
        self.current_response_index = 0
        
        # Default responses for testing
        self._setup_default_responses()
    
    def _setup_default_responses(self):
        """Setup default responses for testing scenarios"""
        self.response_queue = [
            # Initial response with a simple tool call
            (json.dumps({
                "command": {"tool": "github_get_issue", "args": {"issue_number": 1}},
                "comment": "Starting to work on the issue",
                "done": False
            }), []),
            
            # Response with completion
            (json.dumps({
                "comment": "Task completed successfully",
                "done": True
            }), [])
        ]
    
    def send_system_prompt(self, prompt: str):
        """Store system prompt"""
        self.system_prompt = prompt
    
    def send_user_message(self, message: str):
        """Store user message"""
        self.user_messages.append(message)
    
    def send_function_result(self, name: str, result) -> None:
        """Store function result"""
        pass  # Not needed for current tests
    
    def get_response(self) -> Tuple[str, List]:
        """Get mock response"""
        if self.current_response_index < len(self.response_queue):
            response = self.response_queue[self.current_response_index]
            self.current_response_index += 1
            return response
        else:
            # Default completion response
            return (json.dumps({"comment": "No more responses", "done": True}), [])
    
    def set_custom_responses(self, responses: List[Tuple[str, List]]):
        """Set custom response queue for specific tests"""
        self.response_queue = responses
        self.current_response_index = 0
    
    def reset(self):
        """Reset client state"""
        self.system_prompt = ""
        self.user_messages = []
        self.current_response_index = 0
        self._setup_default_responses()


class MockLLMClientWithErrors(MockLLMClient):
    """Mock LLM client that simulates errors for testing error handling"""
    
    def __init__(self, config: Dict[str, Any], functions: List = None, tools: List = None):
        super().__init__(config, functions, tools)
        self.error_count = 0
        self.max_errors = 3
    
    def get_response(self) -> Tuple[str, List]:
        """Get response with simulated errors"""
        if self.error_count < self.max_errors:
            self.error_count += 1
            # Return invalid JSON to simulate parsing errors
            return ("Invalid JSON response {", [])
        else:
            # After max errors, return valid completion
            return (json.dumps({"comment": "Finally completed after errors", "done": True}), [])


def get_mock_llm_client(config: Dict[str, Any], functions: List = None, tools: List = None):
    """Factory function to create mock LLM client"""
    provider = config.get('llm', {}).get('provider', 'mock')
    
    if provider == 'mock':
        return MockLLMClient(config, functions, tools)
    elif provider == 'mock_with_errors':
        return MockLLMClientWithErrors(config, functions, tools)
    else:
        return MockLLMClient(config, functions, tools)