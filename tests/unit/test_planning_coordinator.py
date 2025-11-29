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
    
    def get_prompt(self):
        """Mock get_prompt method."""
        return f"TASK: {self.title}\nDESCRIPTION: {self.body}\nNUMBER: {self.number}"


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


class TestVerificationPhase(unittest.TestCase):
    """検証フェーズ機能のテスト."""

    def setUp(self) -> None:
        """テスト環境をセットアップ."""
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
            "verification": {
                "enabled": True,
                "max_rounds": 2,
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
        """テスト環境をクリーンアップ."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_build_executed_actions_summary_with_actions(self) -> None:
        """アクションがある場合の実行済みアクションサマリーのテスト."""
        llm_client = MagicMock()
        coordinator = PlanningCoordinator(
            config=self.config,
            llm_client=llm_client,
            mcp_clients=self.mcp_clients,
            task=self.task,
            context_manager=self.context_manager,
        )

        # テスト用の計画を設定
        coordinator.current_plan = {
            "action_plan": {
                "actions": [
                    {"task_id": "task_1", "purpose": "Read file", "tool": "read_file"},
                    {"task_id": "task_2", "purpose": "Write code", "tool": "write_file"},
                ]
            }
        }

        summary = coordinator._build_executed_actions_summary()
        assert "task_1" in summary
        assert "task_2" in summary
        assert "Read file" in summary
        assert "Write code" in summary
        assert "read_file" in summary
        assert "write_file" in summary

    def test_build_executed_actions_summary_no_plan(self) -> None:
        """計画がない場合の実行済みアクションサマリーのテスト."""
        llm_client = MagicMock()
        coordinator = PlanningCoordinator(
            config=self.config,
            llm_client=llm_client,
            mcp_clients=self.mcp_clients,
            task=self.task,
            context_manager=self.context_manager,
        )

        coordinator.current_plan = None
        summary = coordinator._build_executed_actions_summary()
        assert "No plan available" in summary

    def test_build_executed_actions_summary_no_actions(self) -> None:
        """アクションがない場合の実行済みアクションサマリーのテスト."""
        llm_client = MagicMock()
        coordinator = PlanningCoordinator(
            config=self.config,
            llm_client=llm_client,
            mcp_clients=self.mcp_clients,
            task=self.task,
            context_manager=self.context_manager,
        )

        coordinator.current_plan = {"action_plan": {"actions": []}}
        summary = coordinator._build_executed_actions_summary()
        assert "No actions were executed" in summary

    def test_extract_success_criteria_with_criteria(self) -> None:
        """成功基準がある場合の抽出テスト."""
        llm_client = MagicMock()
        coordinator = PlanningCoordinator(
            config=self.config,
            llm_client=llm_client,
            mcp_clients=self.mcp_clients,
            task=self.task,
            context_manager=self.context_manager,
        )

        coordinator.current_plan = {
            "goal_understanding": {
                "success_criteria": [
                    "All tests pass",
                    "Code compiles without errors",
                ]
            }
        }

        criteria = coordinator._extract_success_criteria()
        assert "All tests pass" in criteria
        assert "Code compiles without errors" in criteria

    def test_extract_success_criteria_no_plan(self) -> None:
        """計画がない場合の成功基準抽出テスト."""
        llm_client = MagicMock()
        coordinator = PlanningCoordinator(
            config=self.config,
            llm_client=llm_client,
            mcp_clients=self.mcp_clients,
            task=self.task,
            context_manager=self.context_manager,
        )

        coordinator.current_plan = None
        criteria = coordinator._extract_success_criteria()
        assert "No success criteria available" in criteria

    def test_extract_success_criteria_no_criteria(self) -> None:
        """成功基準がない場合の抽出テスト."""
        llm_client = MagicMock()
        coordinator = PlanningCoordinator(
            config=self.config,
            llm_client=llm_client,
            mcp_clients=self.mcp_clients,
            task=self.task,
            context_manager=self.context_manager,
        )

        coordinator.current_plan = {"goal_understanding": {}}
        criteria = coordinator._extract_success_criteria()
        assert "No explicit success criteria" in criteria

    def test_build_verification_prompt(self) -> None:
        """検証プロンプトの構築テスト."""
        llm_client = MagicMock()
        coordinator = PlanningCoordinator(
            config=self.config,
            llm_client=llm_client,
            mcp_clients=self.mcp_clients,
            task=self.task,
            context_manager=self.context_manager,
        )

        coordinator.current_plan = {
            "goal_understanding": {
                "success_criteria": ["Test criterion"]
            },
            "action_plan": {
                "actions": [
                    {"task_id": "task_1", "purpose": "Test", "tool": "test_tool"}
                ]
            }
        }

        prompt = coordinator._build_verification_prompt()
        
        # プロンプトに必要な要素が含まれているか確認
        assert "Verification Phase" in prompt
        assert "Success Criteria" in prompt
        assert "Placeholder Detection" in prompt
        assert "TODO" in prompt
        assert "FIXME" in prompt
        assert "verification_passed" in prompt
        assert "additional_actions" in prompt

    def test_post_verification_result_passed(self) -> None:
        """検証成功時の結果投稿テスト."""
        llm_client = MagicMock()
        coordinator = PlanningCoordinator(
            config=self.config,
            llm_client=llm_client,
            mcp_clients=self.mcp_clients,
            task=self.task,
            context_manager=self.context_manager,
        )

        verification_result = {
            "verification_passed": True,
            "issues_found": [],
            "placeholder_detected": {"count": 0, "locations": []},
            "additional_work_needed": False,
            "additional_actions": [],
            "completion_confidence": 0.95,
            "comment": "All implementations are complete."
        }

        # task.commentがMockになっていることを確認
        coordinator.task.comment = MagicMock(return_value={"id": 456})
        
        coordinator._post_verification_result(verification_result)
        
        # commentが呼ばれたことを確認
        coordinator.task.comment.assert_called_once()
        call_args = coordinator.task.comment.call_args[0][0]
        assert "✅" in call_args
        assert "Passed" in call_args
        assert "95%" in call_args

    def test_post_verification_result_failed(self) -> None:
        """検証失敗時の結果投稿テスト."""
        llm_client = MagicMock()
        coordinator = PlanningCoordinator(
            config=self.config,
            llm_client=llm_client,
            mcp_clients=self.mcp_clients,
            task=self.task,
            context_manager=self.context_manager,
        )

        verification_result = {
            "verification_passed": False,
            "issues_found": ["Missing implementation", "TODO found"],
            "placeholder_detected": {"count": 2, "locations": ["file.py:10", "file.py:20"]},
            "additional_work_needed": True,
            "additional_actions": [
                {"task_id": "fix_1", "purpose": "Complete implementation"}
            ],
            "completion_confidence": 0.5,
            "comment": "Issues found in implementation."
        }

        coordinator.task.comment = MagicMock(return_value={"id": 456})
        
        coordinator._post_verification_result(verification_result)
        
        coordinator.task.comment.assert_called_once()
        call_args = coordinator.task.comment.call_args[0][0]
        assert "⚠️" in call_args
        assert "Issues Found" in call_args
        assert "Missing implementation" in call_args
        assert "file.py:10" in call_args
        assert "1 actions" in call_args

    def test_update_checklist_for_additional_work(self) -> None:
        """追加作業用チェックリスト更新のテスト."""
        llm_client = MagicMock()
        coordinator = PlanningCoordinator(
            config=self.config,
            llm_client=llm_client,
            mcp_clients=self.mcp_clients,
            task=self.task,
            context_manager=self.context_manager,
        )

        coordinator.current_plan = {
            "action_plan": {
                "actions": [
                    {"task_id": "task_1", "purpose": "Original task 1"},
                    {"task_id": "task_2", "purpose": "Original task 2"},
                ]
            }
        }

        verification_result = {"issues_found": ["Issue 1"]}
        additional_actions = [
            {"task_id": "verification_fix_1", "purpose": "Fix issue 1"},
        ]

        coordinator.checklist_comment_id = 123
        coordinator.task.update_comment = MagicMock()

        coordinator._update_checklist_for_additional_work(verification_result, additional_actions)

        coordinator.task.update_comment.assert_called_once()
        call_args = coordinator.task.update_comment.call_args[0]
        assert call_args[0] == 123  # comment_id
        checklist_content = call_args[1]
        
        # 元の計画が完了済みとして表示されていることを確認
        assert "Original Plan (Completed)" in checklist_content
        assert "[x]" in checklist_content
        assert "task_1" in checklist_content
        
        # 追加作業が未完了として表示されていることを確認
        assert "Additional Work (From Verification)" in checklist_content
        assert "[ ]" in checklist_content
        assert "verification_fix_1" in checklist_content


if __name__ == "__main__":
    unittest.main()
