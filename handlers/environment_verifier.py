"""環境検証モジュール.

環境構築が正常に完了したことを検証するクラスを提供します。
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from handlers.execution_environment_manager import (
        ExecutionEnvironmentManager,
        ExecutionResult,
    )


class EnvironmentVerifier:
    """環境構築の検証を行うクラス.
    
    責務:
    - 環境構築コマンドが正常に実行されたことを検証
    - expected_outputとの完全一致確認
    """

    def __init__(self, execution_manager: ExecutionEnvironmentManager) -> None:
        """EnvironmentVerifierを初期化する.
        
        Args:
            execution_manager: コマンド実行用のマネージャー
        """
        self.execution_manager = execution_manager
        self.logger = logging.getLogger(__name__)

    def verify_setup(
        self,
        verification_commands: list[dict[str, str]],
        container_id: str,
    ) -> dict[str, Any]:
        """環境構築を検証する.
        
        Args:
            verification_commands: 検証コマンドのリスト
                各要素は {"command": str, "expected_output": str} の形式
            container_id: 検証対象のコンテナID
            
        Returns:
            検証結果の辞書
        """
        if not verification_commands:
            self.logger.info("検証コマンドが指定されていません")
            return {
                "success": True,
                "message": "No verification commands specified",
                "results": [],
            }
        
        results = []
        all_passed = True
        
        for i, verification in enumerate(verification_commands):
            command = verification.get("command", "")
            expected_output = verification.get("expected_output", "")
            
            if not command:
                self.logger.warning("検証コマンド%d: コマンドが空です", i + 1)
                results.append({
                    "command": command,
                    "success": False,
                    "error": "Empty command",
                })
                all_passed = False
                continue
            
            self.logger.info("検証コマンド%d実行: %s", i + 1, command)
            
            try:
                # コマンドを実行
                exec_result = self.execution_manager.execute_command(
                    container_id=container_id,
                    command=command,
                )
                
                # 実行結果をチェック
                success = self._verify_result(exec_result, expected_output)
                
                result_info = {
                    "command": command,
                    "expected_output": expected_output,
                    "actual_output": exec_result.stdout.rstrip(),
                    "exit_code": exec_result.exit_code,
                    "success": success,
                }
                
                if not success:
                    all_passed = False
                    # 失敗理由を追加
                    if exec_result.exit_code != 0:
                        result_info["error"] = f"Command failed with exit code {exec_result.exit_code}"
                        result_info["stderr"] = exec_result.stderr
                    else:
                        result_info["error"] = "Output mismatch"
                
                results.append(result_info)
                
                if success:
                    self.logger.info("検証コマンド%d: 成功", i + 1)
                else:
                    self.logger.warning(
                        "検証コマンド%d: 失敗 - expected: %r, actual: %r",
                        i + 1,
                        expected_output,
                        exec_result.stdout.rstrip(),
                    )
                    
            except Exception as e:
                self.logger.error("検証コマンド%d実行エラー: %s", i + 1, e, exc_info=True)
                results.append({
                    "command": command,
                    "success": False,
                    "error": str(e),
                })
                all_passed = False
        
        return {
            "success": all_passed,
            "message": "All verifications passed" if all_passed else "Some verifications failed",
            "results": results,
        }

    def _verify_result(
        self,
        exec_result: ExecutionResult,
        expected_output: str,
    ) -> bool:
        """実行結果を検証する.
        
        Args:
            exec_result: コマンド実行結果
            expected_output: 期待される出力
            
        Returns:
            検証成功の場合True
        """
        # exit codeが0でない場合は失敗
        if exec_result.exit_code != 0:
            return False
        
        # stdoutとexpected_outputの末尾の空白・改行を削除して比較
        # 先頭の空白は意味がある可能性があるため残す
        actual_output = exec_result.stdout.rstrip()
        expected = expected_output.rstrip()
        
        # 完全一致確認
        return actual_output == expected
