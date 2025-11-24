"""Unit tests for PlanningCoordinator."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from handlers.planning_coordinator import PlanningCoordinator


class MockTask:
    """Mock task object for testing."""

    def __init__(self, task_uuid="test-uuid", title="Test Task", body="Test task body", number=123):
        self.uuid = task_uuid
        self.title = title
        self.body = body
        self.number = number
        
    def comment(self, text):
        """Mock comment method."""
        return {"id": 123, "body": text}
        
    def update_comment(self, comment_id, text):
        """Mock update_comment method."""
        return {"id": comment_id, "body": text}


class MockContextManager:
    """Mock TaskContextManager for testing."""
    
    def __init__(self, task_uuid, temp_dir):
        from handlers.planning_history_store import PlanningHistoryStore
        from context_storage.message_store import MessageStore
        
        self.task_uuid = task_uuid
        temp_path = Path(temp_dir)
        self.context_dir = temp_path
        self.planning_dir = temp_path / "planning"
        self.planning_dir.mkdir(parents=True, exist_ok=True)
        
        # Create minimal config for MessageStore
        config = {"llm": {"context_length": 8000}}
        
        self.planning_store = PlanningHistoryStore(task_uuid, self.planning_dir)
        self.message_store = MessageStore(temp_path, config)
        
    def get_planning_store(self):
        return self.planning_store
        
    def get_message_store(self):
        return self.message_store


class MockLLMClient:
    """Mock LLM client for testing."""

    def __init__(self, responses=None):
        self.responses = responses or []
        self.call_count = 0

    def process(self, prompt):
        """Return pre-configured response."""
        if self.call_count < len(self.responses):
            response = self.responses[self.call_count]
            self.call_count += 1
            return response
        return {"done": True}


class TestPlanningCoordinator(unittest.TestCase):
    """Test PlanningCoordinator functionality."""

    def setUp(self) -> None:
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.task_uuid = "test-uuid"
        self.config = {
            "enabled": True,
            "strategy": "chain_of_thought",
            "max_subtasks": 100,
            "reflection": {
                "enabled": True,
                "trigger_on_error": True,
                "trigger_interval": 3,
            },
            "revision": {
                "max_revisions": 3,
            },
            "main_config": {
                "llm": {
                    "provider": "openai",
                    "model": "gpt-4",
                    "context_length": 8000,
                    "function_calling": False,
                    "openai": {
                        "api_key": "test-key",
                        "model": "gpt-4",
                    },
                },
            },
        }
        self.task = MockTask(task_uuid=self.task_uuid)
        self.mcp_clients = {"github": MagicMock()}
        self.context_manager = MockContextManager(self.task_uuid, self.temp_dir)

    def tearDown(self) -> None:
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_coordinator_creation(self) -> None:
        """Test PlanningCoordinator object creation."""
        llm_client = MockLLMClient()
        coordinator = PlanningCoordinator(
            config=self.config,
            llm_client=llm_client,
            mcp_clients=self.mcp_clients,
            task=self.task,
            context_manager=self.context_manager,
        )

        assert coordinator.config == self.config
        assert coordinator.llm_client == llm_client  # Should use provided client
        assert coordinator.mcp_clients == self.mcp_clients
        assert coordinator.task == self.task
        assert coordinator.current_phase == "planning"
        assert coordinator.action_counter == 0
        assert coordinator.revision_counter == 0

    def test_coordinator_creation_without_llm_client(self) -> None:
        """Test PlanningCoordinator creation when llm_client is None."""
        coordinator = PlanningCoordinator(
            config=self.config,
            llm_client=None,
            mcp_clients=self.mcp_clients,
            task=self.task,
            context_manager=self.context_manager,
        )

        assert coordinator.config == self.config
        assert coordinator.llm_client is not None  # Should auto-create client
        assert coordinator.mcp_clients == self.mcp_clients
        assert coordinator.task == self.task

    @unittest.skip("Requires LLM client mocking - needs refactoring")
    def test_planning_phase_execution(self) -> None:
        """Test execution of planning phase."""
        plan = {
            "goal_understanding": {
                "main_objective": "Test objective",
                "success_criteria": ["Criterion 1"],
            },
            "task_decomposition": {
                "reasoning": "Test reasoning",
                "subtasks": [
                    {
                        "id": "task_1",
                        "description": "First task",
                        "dependencies": [],
                    }
                ],
            },
            "action_plan": {
                "execution_order": ["task_1"],
                "actions": [
                    {
                        "task_id": "task_1",
                        "action_type": "tool_call",
                        "tool": "test_tool",
                    }
                ],
            },
        }

        llm_client = MockLLMClient(responses=[plan])
        coordinator = PlanningCoordinator(
            config=self.config,
            llm_client=llm_client,
            mcp_clients=self.mcp_clients,
            task=self.task,
            context_manager=self.context_manager,
        )

        result = coordinator._execute_planning_phase()
        assert result is not None
        assert result["goal_understanding"]["main_objective"] == "Test objective"

    def test_should_reflect_on_error(self) -> None:
        """Test that reflection is triggered on error."""
        llm_client = MockLLMClient()
        coordinator = PlanningCoordinator(
            config=self.config,
            llm_client=llm_client,
            mcp_clients=self.mcp_clients,
            task=self.task,
            context_manager=self.context_manager,
        )

        # Error result should trigger reflection
        error_result = {"status": "error", "error": "Test error"}
        assert coordinator._should_reflect(error_result) is True

        # Success result initially (action_counter=0, 0 % 3 == 0, so True)
        # Set action counter to 1 first to avoid interval trigger
        coordinator.action_counter = 1
        success_result = {"status": "success"}
        assert coordinator._should_reflect(success_result) is False

    def test_should_reflect_at_interval(self) -> None:
        """Test that reflection is triggered at configured intervals."""
        llm_client = MockLLMClient()
        coordinator = PlanningCoordinator(
            config=self.config,
            llm_client=llm_client,
            mcp_clients=self.mcp_clients,
            task=self.task,
            context_manager=self.context_manager,
        )

        success_result = {"status": "success"}

        # Set action counter to interval
        coordinator.action_counter = 3
        assert coordinator._should_reflect(success_result) is True

        # Not at interval
        coordinator.action_counter = 2
        assert coordinator._should_reflect(success_result) is False

    def test_revision_limit(self) -> None:
        """Test that plan revisions are limited."""
        llm_client = MockLLMClient()
        coordinator = PlanningCoordinator(
            config=self.config,
            llm_client=llm_client,
            mcp_clients=self.mcp_clients,
            task=self.task,
            context_manager=self.context_manager,
        )

        reflection = {
            "status": "error",
            "reason": "Test error",
            "changes": ["Change 1"],
        }

        # First three revisions should succeed
        for i in range(3):
            result = coordinator._revise_plan(reflection)
            # Result may be None if LLM returns invalid JSON, but counter should increment
            assert coordinator.revision_counter == i + 1

        # Fourth revision should fail (exceeds limit)
        result = coordinator._revise_plan(reflection)
        assert result is None
        assert coordinator.revision_counter == 3  # Counter should not increment when limit exceeded

    def test_is_complete(self) -> None:
        """Test completion check."""
        llm_client = MockLLMClient()
        coordinator = PlanningCoordinator(
            config=self.config,
            llm_client=llm_client,
            mcp_clients=self.mcp_clients,
            task=self.task,
            context_manager=self.context_manager,
        )

        # No plan - not complete
        assert coordinator._is_complete() is False

        # Set a plan with one action
        coordinator.current_plan = {
            "action_plan": {
                "actions": [{"task_id": "task_1"}]
            }
        }

        # Action counter = 0, not complete
        assert coordinator._is_complete() is False

        # Action counter = 1, complete
        coordinator.action_counter = 1
        assert coordinator._is_complete() is True

    def test_parse_planning_response(self) -> None:
        """Test parsing of planning response."""
        llm_client = MockLLMClient()
        coordinator = PlanningCoordinator(
            config=self.config,
            llm_client=llm_client,
            mcp_clients=self.mcp_clients,
            task=self.task,
            context_manager=self.context_manager,
        )

        # Dict response
        dict_response = {"plan": "test"}
        assert coordinator._parse_planning_response(dict_response) == dict_response

        # JSON string response
        json_response = '{"plan": "test"}'
        assert coordinator._parse_planning_response(json_response) == {"plan": "test"}

        # Invalid JSON
        invalid_response = "not json"
        assert coordinator._parse_planning_response(invalid_response) is None

    def test_build_planning_prompt(self) -> None:
        """Test building of planning prompt."""
        llm_client = MockLLMClient()
        coordinator = PlanningCoordinator(
            config=self.config,
            llm_client=llm_client,
            mcp_clients=self.mcp_clients,
            task=self.task,
            context_manager=self.context_manager,
        )

        prompt = coordinator._build_planning_prompt([])
        assert "Test Task" in prompt
        assert "Test task body" in prompt
        assert "plan" in prompt.lower()

    @unittest.skip("Requires LLM client mocking - needs refactoring")
    def test_execute_with_planning_basic_flow(self) -> None:
        """Test basic execution flow with planning."""
        plan = {
            "goal_understanding": {"main_objective": "Test"},
            "task_decomposition": {"subtasks": []},
            "action_plan": {
                "execution_order": [],
                "actions": [],
            },
        }

        llm_client = MockLLMClient(responses=[plan])
        coordinator = PlanningCoordinator(
            config=self.config,
            llm_client=llm_client,
            mcp_clients=self.mcp_clients,
            task=self.task,
            context_manager=self.context_manager,
        )

        result = coordinator.execute_with_planning()
        assert result is True


if __name__ == "__main__":
    unittest.main()
