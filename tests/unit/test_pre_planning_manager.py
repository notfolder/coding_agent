"""PrePlanningManagerのユニットテスト.

計画前情報収集フェーズの機能をテストします。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from handlers.pre_planning_manager import PrePlanningManager


class MockTask:
    """テスト用のモックタスク."""

    def __init__(self, title: str = "Test Task", body: str = "Test task body") -> None:
        """モックタスクを初期化."""
        self.title = title
        self.body = body
        self.comments: list[str] = []

    def get_prompt(self) -> str:
        """タスクプロンプトを取得."""
        return f"TASK: {self.title}\nDESCRIPTION: {self.body}"

    def comment(self, text: str) -> dict:
        """コメントを投稿."""
        self.comments.append(text)
        return {"id": len(self.comments)}


class MockLLMClient:
    """テスト用のモックLLMクライアント."""

    def __init__(self, responses: list[tuple[str, None, int]] | None = None) -> None:
        """モックLLMクライアントを初期化."""
        self.responses = responses or []
        self.call_count = 0
        self.messages: list[str] = []

    def send_user_message(self, message: str) -> None:
        """ユーザーメッセージを送信."""
        self.messages.append(message)

    def get_response(self) -> tuple[str, None, int]:
        """レスポンスを取得."""
        if self.call_count < len(self.responses):
            response = self.responses[self.call_count]
            self.call_count += 1
            return response
        return ('{"error": "no more responses"}', None, 0)


class TestPrePlanningManager(unittest.TestCase):
    """PrePlanningManagerのテストクラス."""

    def setUp(self) -> None:
        """テスト環境をセットアップ."""
        self.temp_dir = tempfile.mkdtemp()
        self.config = {
            "enabled": True,
            "understanding": {
                "confidence_threshold": 0.7,
            },
            "collection": {
                "enabled": True,
                "max_retries_per_tool": 2,
            },
            "assumption": {
                "enabled": True,
                "confidence_threshold": 0.5,
            },
            "notification": {
                "notify_on_start": True,
                "notify_on_understanding_complete": True,
                "notify_on_collection_complete": True,
                "notify_on_assumption": False,
            },
        }
        self.task = MockTask()
        self.mcp_clients = {"github": MagicMock()}

    def tearDown(self) -> None:
        """テスト環境をクリーンアップ."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_manager_creation(self) -> None:
        """PrePlanningManagerのオブジェクト作成をテスト."""
        llm_client = MockLLMClient()
        manager = PrePlanningManager(
            config=self.config,
            llm_client=llm_client,
            mcp_clients=self.mcp_clients,
            task=self.task,
        )

        assert manager.config == self.config
        assert manager.llm_client == llm_client
        assert manager.mcp_clients == self.mcp_clients
        assert manager.task == self.task
        assert manager.current_subphase == "understanding"
        assert manager.understanding_result is None
        assert manager.collection_plan is None
        assert manager.collection_results == []
        assert manager.assumptions == []

    def test_execute_understanding_success(self) -> None:
        """依頼内容の理解フェーズの成功ケースをテスト."""
        understanding_response = """{
            "phase": "request_understanding",
            "request_understanding": {
                "task_type": "feature_development",
                "primary_goal": "新機能の実装",
                "expected_deliverables": ["コード", "テスト"],
                "constraints": ["Python 3.12"],
                "scope": {
                    "in_scope": ["バックエンド"],
                    "out_of_scope": ["フロントエンド"]
                },
                "understanding_confidence": 0.85,
                "ambiguities": []
            }
        }"""

        llm_client = MockLLMClient(responses=[(understanding_response, None, 100)])
        manager = PrePlanningManager(
            config=self.config,
            llm_client=llm_client,
            mcp_clients=self.mcp_clients,
            task=self.task,
        )

        result = manager.execute_understanding()

        assert result is not None
        assert result.get("phase") == "request_understanding"
        understanding = result.get("request_understanding", {})
        assert understanding.get("task_type") == "feature_development"
        assert understanding.get("primary_goal") == "新機能の実装"
        assert understanding.get("understanding_confidence") == 0.85

    def test_execute_understanding_parse_failure(self) -> None:
        """依頼内容の理解でパース失敗時のフォールバックをテスト."""
        llm_client = MockLLMClient(responses=[("invalid json", None, 100)])
        manager = PrePlanningManager(
            config=self.config,
            llm_client=llm_client,
            mcp_clients=self.mcp_clients,
            task=self.task,
        )

        result = manager.execute_understanding()

        # パース失敗時は最小限の理解結果が返される
        assert result is not None
        assert result.get("phase") == "request_understanding"
        understanding = result.get("request_understanding", {})
        assert understanding.get("task_type") == "unknown"
        assert understanding.get("understanding_confidence") == 0.3

    def test_execute_collection_planning_skip(self) -> None:
        """情報収集をスキップするケースをテスト."""
        collection_response = """{
            "phase": "information_planning",
            "information_needs": {
                "required_information": [],
                "collection_order": [],
                "skip_collection": true,
                "skip_reason": "シンプルなタスクのため追加情報不要"
            }
        }"""

        llm_client = MockLLMClient(responses=[(collection_response, None, 100)])
        manager = PrePlanningManager(
            config=self.config,
            llm_client=llm_client,
            mcp_clients=self.mcp_clients,
            task=self.task,
        )
        manager.understanding_result = {"request_understanding": {"task_type": "simple"}}

        result = manager.execute_collection_planning()

        assert result is not None
        info_needs = result.get("information_needs", {})
        assert info_needs.get("skip_collection") is True

    def test_execute_collection_empty_plan(self) -> None:
        """空の収集計画でexecute_collectionを実行するテスト."""
        llm_client = MockLLMClient()
        manager = PrePlanningManager(
            config=self.config,
            llm_client=llm_client,
            mcp_clients=self.mcp_clients,
            task=self.task,
        )
        manager.collection_plan = {"information_needs": {"required_information": []}}

        results = manager.execute_collection()

        assert results == []

    def test_get_result(self) -> None:
        """get_resultメソッドのテスト."""
        llm_client = MockLLMClient()
        manager = PrePlanningManager(
            config=self.config,
            llm_client=llm_client,
            mcp_clients=self.mcp_clients,
            task=self.task,
        )

        # 理解結果を設定
        manager.understanding_result = {
            "request_understanding": {
                "task_type": "feature_development",
                "primary_goal": "テスト機能",
                "understanding_confidence": 0.8,
            }
        }

        result = manager.get_result()

        assert "pre_planning_result" in result
        pre_planning = result["pre_planning_result"]
        assert "request_understanding" in pre_planning
        assert "collected_information" in pre_planning
        assert "assumptions" in pre_planning
        assert "information_gaps" in pre_planning
        assert "recommendations_for_planning" in pre_planning

    def test_get_pre_planning_state(self) -> None:
        """一時停止用の状態取得をテスト."""
        llm_client = MockLLMClient()
        manager = PrePlanningManager(
            config=self.config,
            llm_client=llm_client,
            mcp_clients=self.mcp_clients,
            task=self.task,
        )

        manager.current_subphase = "collection"
        manager.understanding_result = {"test": "data"}
        manager.collection_plan = {"plan": "data"}
        manager.collection_results = [{"id": "info_1", "status": "collected"}]
        manager.assumptions = [{"id": "info_2", "assumed_value": "test"}]

        state = manager.get_pre_planning_state()

        assert state["current_subphase"] == "collection"
        assert state["understanding_result"] == {"test": "data"}
        assert state["collection_plan"] == {"plan": "data"}
        assert len(state["collection_results"]) == 1
        assert len(state["assumptions"]) == 1

    def test_restore_pre_planning_state(self) -> None:
        """一時停止からの復元をテスト."""
        llm_client = MockLLMClient()
        manager = PrePlanningManager(
            config=self.config,
            llm_client=llm_client,
            mcp_clients=self.mcp_clients,
            task=self.task,
        )

        saved_state = {
            "current_subphase": "assumption",
            "understanding_result": {"restored": True},
            "collection_plan": {"plan": "restored"},
            "collection_results": [{"id": "info_1"}],
            "assumptions": [{"id": "info_2"}],
            "information_gaps": [{"description": "gap"}],
        }

        manager.restore_pre_planning_state(saved_state)

        assert manager.current_subphase == "assumption"
        assert manager.understanding_result == {"restored": True}
        assert manager.collection_plan == {"plan": "restored"}
        assert len(manager.collection_results) == 1
        assert len(manager.assumptions) == 1
        assert len(manager.information_gaps) == 1

    def test_is_non_assumable(self) -> None:
        """推測不可項目の判定をテスト."""
        llm_client = MockLLMClient()
        manager = PrePlanningManager(
            config=self.config,
            llm_client=llm_client,
            mcp_clients=self.mcp_clients,
            task=self.task,
        )

        # 推測不可の項目
        assert manager._is_non_assumable("api_key_config") is True
        assert manager._is_non_assumable("database_password") is True
        assert manager._is_non_assumable("security_settings") is True
        assert manager._is_non_assumable("user_token") is True

        # 推測可能な項目
        assert manager._is_non_assumable("project_structure") is False
        assert manager._is_non_assumable("code_style") is False
        assert manager._is_non_assumable("test_framework") is False

    def test_parse_tool_name(self) -> None:
        """ツール名のパースをテスト."""
        llm_client = MockLLMClient()
        manager = PrePlanningManager(
            config=self.config,
            llm_client=llm_client,
            mcp_clients=self.mcp_clients,
            task=self.task,
        )

        # 通常のケース
        mcp_server, tool = manager._parse_tool_name("github_get_file_contents")
        assert mcp_server == "github"
        assert tool == "get_file_contents"

        # アンダースコアなしのケース
        mcp_server, tool = manager._parse_tool_name("simpletool")
        assert mcp_server == "default"
        assert tool == "simpletool"

    def test_order_by_collection_order(self) -> None:
        """収集順序による並び替えをテスト."""
        llm_client = MockLLMClient()
        manager = PrePlanningManager(
            config=self.config,
            llm_client=llm_client,
            mcp_clients=self.mcp_clients,
            task=self.task,
        )

        required_info = [
            {"id": "info_3"},
            {"id": "info_1"},
            {"id": "info_2"},
        ]
        collection_order = ["info_2", "info_1", "info_3"]

        ordered = manager._order_by_collection_order(required_info, collection_order)

        assert ordered[0]["id"] == "info_2"
        assert ordered[1]["id"] == "info_1"
        assert ordered[2]["id"] == "info_3"

    def test_notifications_posted(self) -> None:
        """通知が正しく投稿されることをテスト."""
        understanding_response = """{
            "phase": "request_understanding",
            "request_understanding": {
                "task_type": "feature_development",
                "primary_goal": "テスト",
                "expected_deliverables": [],
                "constraints": [],
                "scope": {"in_scope": [], "out_of_scope": []},
                "understanding_confidence": 0.9,
                "ambiguities": []
            }
        }"""
        collection_response = """{
            "phase": "information_planning",
            "information_needs": {
                "required_information": [],
                "collection_order": [],
                "skip_collection": true,
                "skip_reason": "test"
            }
        }"""

        llm_client = MockLLMClient(responses=[
            (understanding_response, None, 100),
            (collection_response, None, 100),
        ])
        manager = PrePlanningManager(
            config=self.config,
            llm_client=llm_client,
            mcp_clients=self.mcp_clients,
            task=self.task,
        )

        manager.execute()

        # 通知が投稿されていることを確認
        assert len(self.task.comments) >= 3  # 開始、理解完了、収集完了
        assert any("タスク分析を開始" in c for c in self.task.comments)
        assert any("タスク内容の理解が完了" in c for c in self.task.comments)
        assert any("情報収集が完了" in c for c in self.task.comments)


class TestPrePlanningManagerIntegration(unittest.TestCase):
    """PrePlanningManagerの統合テスト."""

    def setUp(self) -> None:
        """テスト環境をセットアップ."""
        self.config = {
            "enabled": True,
            "understanding": {"confidence_threshold": 0.7},
            "collection": {"enabled": False},  # 収集を無効化
            "assumption": {"enabled": False},  # 推測を無効化
            "notification": {
                "notify_on_start": False,
                "notify_on_understanding_complete": False,
                "notify_on_collection_complete": False,
            },
        }
        self.task = MockTask()
        self.mcp_clients = {}

    def test_execute_full_flow(self) -> None:
        """execute()の完全フローをテスト."""
        understanding_response = """{
            "phase": "request_understanding",
            "request_understanding": {
                "task_type": "bug_fix",
                "primary_goal": "バグ修正",
                "expected_deliverables": ["修正コード"],
                "constraints": [],
                "scope": {"in_scope": ["モジュールA"], "out_of_scope": []},
                "understanding_confidence": 0.75,
                "ambiguities": []
            }
        }"""
        collection_response = """{
            "phase": "information_planning",
            "information_needs": {
                "required_information": [],
                "collection_order": [],
                "skip_collection": true,
                "skip_reason": "シンプルなバグ修正"
            }
        }"""

        llm_client = MockLLMClient(responses=[
            (understanding_response, None, 100),
            (collection_response, None, 100),
        ])
        manager = PrePlanningManager(
            config=self.config,
            llm_client=llm_client,
            mcp_clients=self.mcp_clients,
            task=self.task,
        )

        result = manager.execute()

        assert "pre_planning_result" in result
        pre_planning = result["pre_planning_result"]
        
        # 理解結果が含まれている
        assert pre_planning["request_understanding"]["task_type"] == "bug_fix"
        assert pre_planning["request_understanding"]["primary_goal"] == "バグ修正"
        assert pre_planning["request_understanding"]["understanding_confidence"] == 0.75


if __name__ == "__main__":
    unittest.main()
