"""環境解析モジュール.

プロジェクト内の環境構築関連ファイルを検出・解析するクラスを提供します。
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from clients.mcp_tool_client import MCPToolClient


class EnvironmentAnalyzer:
    """プロジェクトの環境情報を分析するクラス.
    
    責務:
    - プロジェクト内の環境構築関連ファイルを検出
    - ファイル内容を解析して環境情報を抽出
    """

    # 環境構築関連ファイルのパターン定義
    ENVIRONMENT_FILES = {
        "python": [
            "requirements.txt",
            "pyproject.toml",
            "setup.py",
            "Pipfile",
            "poetry.lock",
        ],
        "conda": [
            "environment.yml",
            "condaenv.yaml",
        ],
        "node": [
            "package.json",
            "package-lock.json",
            "yarn.lock",
            "pnpm-lock.yaml",
        ],
        "common": [
            "Dockerfile",
            "docker-compose.yml",
            "Makefile",
        ],
    }

    def __init__(self, mcp_clients: dict[str, MCPToolClient]) -> None:
        """EnvironmentAnalyzerを初期化する.
        
        Args:
            mcp_clients: MCPツールクライアントの辞書
        """
        self.mcp_clients = mcp_clients
        self.logger = logging.getLogger(__name__)

    def detect_environment_files(self, file_list: list[str]) -> dict[str, list[str]]:
        """環境構築関連ファイルを検出する.
        
        Args:
            file_list: プロジェクトのファイルリスト
            
        Returns:
            検出されたファイルを環境タイプ別に分類した辞書
        """
        detected_files: dict[str, list[str]] = {}
        
        # ファイルリストを小文字に変換して検索しやすくする
        file_set = set(file_list)
        
        # 各環境タイプのファイルを検出
        for env_type, patterns in self.ENVIRONMENT_FILES.items():
            detected = []
            for pattern in patterns:
                # 完全一致で検索
                if pattern in file_set:
                    detected.append(pattern)
                # サブディレクトリも検索（例: src/requirements.txt）
                else:
                    for file in file_list:
                        if file.endswith(f"/{pattern}") or file.endswith(f"\\{pattern}"):
                            detected.append(file)
            
            if detected:
                detected_files[env_type] = detected
        
        self.logger.info("検出された環境ファイル: %s", detected_files)
        return detected_files

    def analyze_environment_files(
        self,
        detected_files: dict[str, list[str]],
    ) -> dict[str, Any]:
        """検出されたファイルの内容を読み込み、環境情報を抽出する.
        
        Args:
            detected_files: 検出されたファイルの辞書（環境タイプ別）
            
        Returns:
            環境情報の辞書
        """
        environment_info: dict[str, Any] = {
            "detected_files": {},
            "file_contents": {},
        }
        
        # ファイル内容を読み込み
        for env_type, file_paths in detected_files.items():
            for file_path in file_paths:
                try:
                    content = self._read_file(file_path)
                    if content:
                        environment_info["detected_files"][file_path] = env_type
                        # 内容が長すぎる場合は切り詰める
                        if len(content) > 5000:
                            content = content[:5000] + "\n... (truncated)"
                        environment_info["file_contents"][file_path] = content
                        self.logger.debug("ファイル読み込み成功: %s", file_path)
                except Exception as e:
                    self.logger.warning("ファイル読み込み失敗: %s - %s", file_path, e)
        
        return environment_info

    def _read_file(self, file_path: str) -> str | None:
        """ファイルの内容を読み込む.
        
        Args:
            file_path: 読み込むファイルのパス
            
        Returns:
            ファイルの内容（読み込み失敗時はNone）
        """
        # MCPクライアントを使用してファイルを読み込み
        # GitHub/GitLab MCPクライアントを探す
        for client_name, mcp_client in self.mcp_clients.items():
            if client_name in ("github", "gitlab"):
                try:
                    # get_file_contents toolを使用
                    result = mcp_client.call_tool(
                        "get_file_contents",
                        {"path": file_path},
                    )
                    if result and isinstance(result, dict):
                        content = result.get("content", "")
                        if isinstance(content, str):
                            return content
                except Exception as e:
                    self.logger.debug(
                        "MCPクライアント %s でファイル読み込み失敗: %s - %s",
                        client_name,
                        file_path,
                        e,
                    )
        
        return None
