"""EnvironmentAnalyzerのユニットテスト."""
import unittest
from unittest.mock import MagicMock

from handlers.environment_analyzer import EnvironmentAnalyzer


class TestEnvironmentAnalyzer(unittest.TestCase):
    """EnvironmentAnalyzerのテストクラス."""

    def setUp(self) -> None:
        """各テストの前に実行されるセットアップ."""
        self.mcp_clients = {
            "github": MagicMock(),
            "gitlab": MagicMock(),
        }
        self.analyzer = EnvironmentAnalyzer(self.mcp_clients)

    def test_detect_environment_files_python(self) -> None:
        """Python環境ファイルの検出テスト."""
        file_list = [
            "requirements.txt",
            "setup.py",
            "README.md",
            "src/main.py",
        ]
        
        detected = self.analyzer.detect_environment_files(file_list)
        
        self.assertIn("python", detected)
        self.assertIn("requirements.txt", detected["python"])
        self.assertIn("setup.py", detected["python"])

    def test_detect_environment_files_node(self) -> None:
        """Node.js環境ファイルの検出テスト."""
        file_list = [
            "package.json",
            "package-lock.json",
            "src/index.js",
        ]
        
        detected = self.analyzer.detect_environment_files(file_list)
        
        self.assertIn("node", detected)
        self.assertIn("package.json", detected["node"])
        self.assertIn("package-lock.json", detected["node"])

    def test_detect_environment_files_conda(self) -> None:
        """Conda環境ファイルの検出テスト."""
        file_list = [
            "condaenv.yaml",
            "environment.yml",
            "README.md",
        ]
        
        detected = self.analyzer.detect_environment_files(file_list)
        
        self.assertIn("conda", detected)
        self.assertIn("condaenv.yaml", detected["conda"])

    def test_detect_environment_files_multiple(self) -> None:
        """複数の環境ファイル検出テスト."""
        file_list = [
            "requirements.txt",
            "package.json",
        ]
        
        detected = self.analyzer.detect_environment_files(file_list)
        
        self.assertIn("python", detected)
        self.assertIn("node", detected)

    def test_detect_environment_files_subdirectory(self) -> None:
        """サブディレクトリ内の環境ファイル検出テスト."""
        file_list = [
            "src/requirements.txt",
            "backend/package.json",
        ]
        
        detected = self.analyzer.detect_environment_files(file_list)
        
        self.assertIn("python", detected)
        self.assertIn("node", detected)

    def test_detect_environment_files_empty(self) -> None:
        """ファイルが検出されない場合のテスト."""
        file_list = [
            "README.md",
            "LICENSE",
            "src/main.py",
        ]
        
        detected = self.analyzer.detect_environment_files(file_list)
        
        # 環境ファイルが検出されない場合は空の辞書
        self.assertEqual(len(detected), 0)

    def test_analyze_environment_files(self) -> None:
        """環境ファイル解析テスト."""
        detected_files = {
            "python": ["requirements.txt"],
        }
        
        # MCPクライアントのモック設定
        self.mcp_clients["github"].call_tool.return_value = {
            "content": "requests==2.28.0\nflask==2.3.0",
        }
        
        result = self.analyzer.analyze_environment_files(detected_files)
        
        self.assertIn("detected_files", result)
        self.assertIn("file_contents", result)
        self.assertEqual(result["detected_files"]["requirements.txt"], "python")


if __name__ == "__main__":
    unittest.main()
