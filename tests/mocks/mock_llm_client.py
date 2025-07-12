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
            
            # Response with tool call and progress update
            (json.dumps({
                "command": {"tool": "get_issue_comments", "args": {"issue_number": 1}},
                "comment": "Analyzing the issue and checking comments",
                "done": False
            }), []),
            
            # Response with thinking and solution
            ("<think>Let me analyze this issue carefully and provide a solution</think>\n" + 
             json.dumps({
                "comment": "I understand the issue. The problem is related to the configuration. I'll implement a fix.",
                "done": False
            }), []),
            
            # Response with completion
            (json.dumps({
                "comment": "Task completed successfully. The issue has been resolved by updating the configuration.",
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
    
    def set_mock_response(self, response_data: Dict[str, Any]):
        """Set a single mock response (convenience method)"""
        response_json = json.dumps(response_data)
        self.response_queue = [(response_json, [])]
        self.current_response_index = 0
    
    def add_mock_response(self, response_data: Dict[str, Any]):
        """Add a mock response to the queue"""
        response_json = json.dumps(response_data)
        self.response_queue.append((response_json, []))
    
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
        self.error_types = ['json_error', 'timeout_error', 'api_error']
        self.current_error_type = 0
    
    def get_response(self) -> Tuple[str, List]:
        """Get response with simulated errors"""
        if self.error_count < self.max_errors:
            self.error_count += 1
            error_type = self.error_types[self.current_error_type % len(self.error_types)]
            self.current_error_type += 1
            
            if error_type == 'json_error':
                # Return invalid JSON to simulate parsing errors
                return ("Invalid JSON response {", [])
            elif error_type == 'timeout_error':
                # Simulate timeout by returning incomplete response
                return ("Partial response without proper", [])
            else:  # api_error
                # Return valid JSON but with error content
                return (json.dumps({
                    "error": "API Error occurred",
                    "comment": "There was an error processing the request",
                    "done": False
                }), [])
        else:
            # After max errors, return valid completion
            return (json.dumps({
                "comment": "Finally completed after errors",
                "done": True
            }), [])


class MockLLMClientWithToolCalls(MockLLMClient):
    """Mock LLM client that simulates tool calling scenarios"""
    
    def __init__(self, config: Dict[str, Any], functions: List = None, tools: List = None):
        super().__init__(config, functions, tools)
        self._setup_tool_call_responses()
    
    def _setup_tool_call_responses(self):
        """Setup responses that include tool calls"""
        self.response_queue = [
            # Initial analysis with tool call
            (json.dumps({
                "command": {
                    "tool": "search_issues",
                    "args": {"q": "label:\"coding agent\""}
                },
                "comment": "Searching for issues to work on",
                "done": False
            }), []),
            
            # Get specific issue details
            (json.dumps({
                "command": {
                    "tool": "get_issue",
                    "args": {"owner": "testorg", "repo": "testrepo", "issue_number": 1}
                },
                "comment": "Getting issue details",
                "done": False
            }), []),
            
            # Update issue labels
            (json.dumps({
                "command": {
                    "tool": "update_issue",
                    "args": {
                        "owner": "testorg",
                        "repo": "testrepo", 
                        "issue_number": 1,
                        "labels": ["coding agent processing", "bug"]
                    }
                },
                "comment": "Updating issue status",
                "done": False
            }), []),
            
            # Complete the task
            (json.dumps({
                "comment": "Task completed successfully",
                "done": True
            }), [])
        ]


def get_mock_llm_client(config: Dict[str, Any], functions: List = None, tools: List = None):
    """Factory function to create mock LLM client"""
    provider = config.get('llm', {}).get('provider', 'mock')
    
    if provider == 'mock':
        return MockLLMClient(config, functions, tools)
    elif provider == 'mock_with_errors':
        return MockLLMClientWithErrors(config, functions, tools)
    elif provider == 'mock_with_tool_calls':
        return MockLLMClientWithToolCalls(config, functions, tools)
    else:
        return MockLLMClient(config, functions, tools)