"""EnvironmentVerifierのユニットテスト."""
import unittest
from unittest.mock import MagicMock

from handlers.environment_verifier import EnvironmentVerifier


class TestEnvironmentVerifier(unittest.TestCase):
    """EnvironmentVerifierのテストクラス."""

    def setUp(self) -> None:
        """各テストの前に実行されるセットアップ."""
        self.execution_manager = MagicMock()
        self.verifier = EnvironmentVerifier(self.execution_manager)

    def test_verify_setup_success(self) -> None:
        """検証成功のテスト."""
        verification_commands = [
            {
                "command": "python -c 'print(\"OK\")'",
                "expected_output": "OK",
            },
        ]
        
        # モックの設定
        self.execution_manager.execute_command.return_value = {
            "exit_code": 0,
            "stdout": "OK\n",
            "stderr": "",
            "duration_ms": 100,
        }
        
        result = self.verifier.verify_setup(verification_commands)
        
        self.assertTrue(result["success"])
        self.assertEqual(len(result["results"]), 1)
        self.assertTrue(result["results"][0]["success"])

    def test_verify_setup_output_mismatch(self) -> None:
        """出力が一致しない場合のテスト."""
        verification_commands = [
            {
                "command": "python -c 'print(\"OK\")'",
                "expected_output": "OK",
            },
        ]
        
        # モックの設定（出力が異なる）
        self.execution_manager.execute_command.return_value = {
            "exit_code": 0,
            "stdout": "NG\n",
            "stderr": "",
            "duration_ms": 100,
        }
        
        result = self.verifier.verify_setup(verification_commands)
        
        self.assertFalse(result["success"])
        self.assertFalse(result["results"][0]["success"])
        self.assertEqual(result["results"][0]["error"], "Output mismatch")

    def test_verify_setup_command_failure(self) -> None:
        """コマンド実行失敗のテスト."""
        verification_commands = [
            {
                "command": "python -c 'import nonexistent'",
                "expected_output": "OK",
            },
        ]
        
        # モックの設定（exit_codeが非ゼロ）
        self.execution_manager.execute_command.return_value = {
            "exit_code": 1,
            "stdout": "",
            "stderr": "ModuleNotFoundError: No module named 'nonexistent'",
            "duration_ms": 100,
        }
        
        result = self.verifier.verify_setup(verification_commands)
        
        self.assertFalse(result["success"])
        self.assertFalse(result["results"][0]["success"])
        self.assertIn("Command failed", result["results"][0]["error"])

    def test_verify_setup_multiple_commands(self) -> None:
        """複数のコマンド検証テスト."""
        verification_commands = [
            {
                "command": "python -c 'print(\"OK\")'",
                "expected_output": "OK",
            },
            {
                "command": "python -c 'import sys; print(sys.version_info.major)'",
                "expected_output": "3",
            },
        ]
        
        # モックの設定
        self.execution_manager.execute_command.side_effect = [
            {"exit_code": 0, "stdout": "OK\n", "stderr": "", "duration_ms": 100},
            {"exit_code": 0, "stdout": "3\n", "stderr": "", "duration_ms": 100},
        ]
        
        result = self.verifier.verify_setup(verification_commands)
        
        self.assertTrue(result["success"])
        self.assertEqual(len(result["results"]), 2)
        self.assertTrue(result["results"][0]["success"])
        self.assertTrue(result["results"][1]["success"])

    def test_verify_setup_empty_commands(self) -> None:
        """検証コマンドが空の場合のテスト."""
        verification_commands = []
        
        result = self.verifier.verify_setup(verification_commands)
        
        self.assertTrue(result["success"])
        self.assertEqual(len(result["results"]), 0)

    def test_verify_setup_exception(self) -> None:
        """実行中に例外が発生した場合のテスト."""
        verification_commands = [
            {
                "command": "test command",
                "expected_output": "OK",
            },
        ]
        
        # モックの設定（例外を発生させる）
        self.execution_manager.execute_command.side_effect = Exception("Test error")
        
        result = self.verifier.verify_setup(verification_commands)
        
        self.assertFalse(result["success"])
        self.assertFalse(result["results"][0]["success"])
        self.assertIn("Test error", result["results"][0]["error"])


if __name__ == "__main__":
    unittest.main()
