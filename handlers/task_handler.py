"""タスクハンドラー.

このモジュールは、LLMクライアントとMCPツールクライアントを使用して
タスクを処理するハンドラークラスを提供します。
"""
from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

from mcp import McpError

if TYPE_CHECKING:
    from handlers.task import Task


class TaskHandler:
    """タスク処理ハンドラー.

    LLMクライアントとMCPツールクライアントを統合し、
    タスクに対する自動化された処理を実行します。
    """

    def __init__(
        self,
        llm_client: Any,  # LLMClientの具象クラス
        mcp_clients: dict[str, Any],  # MCPToolClientの辞書
        config: dict[str, Any],
    ) -> None:
        """タスクハンドラーを初期化する.

        Args:
            llm_client: LLMクライアントのインスタンス
            mcp_clients: MCPツールクライアントの辞書
            config: アプリケーション設定辞書

        """
        self.llm_client = llm_client
        self.mcp_clients = mcp_clients
        self.config = config
        self.logger = logging.getLogger(__name__)

    def sanitize_arguments(self, arguments: Any) -> dict[str, Any]:
        """引数をサニタイズして辞書形式に変換する.

        引数がdict型でない場合はJSON文字列としてパースし、
        dict型に変換します。不正な形式の場合は例外を発生させます。

        Args:
            arguments: サニタイズ対象の引数

        Returns:
            辞書形式に変換された引数

        Raises:
            ValueError: JSON文字列の解析に失敗した場合
            TypeError: サポートされていない型の場合

        """
        # 既に辞書型の場合はそのまま返す
        if isinstance(arguments, dict):
            return arguments

        # 文字列の場合はJSONとしてパース
        if isinstance(arguments, str):
            try:
                parsed = json.loads(arguments)
                if isinstance(parsed, dict):
                    return parsed
                error_msg = "Parsed JSON is not a dictionary."
                raise ValueError(error_msg)
            except json.JSONDecodeError as e:
                msg = f"Invalid JSON string for arguments: {e}"
                raise ValueError(msg) from e
        else:
            # サポートされていない型の場合はエラー
            msg = f"Unsupported type for arguments: {type(arguments)}"
            raise TypeError(msg)

    def handle(self, task: Task) -> None:
        """タスクを処理する.

        LLMに対してタスクのプロンプトを送信し、レスポンスに基づいて
        必要なツールを実行しながらタスクを完了まで処理します。

        Args:
            task: 処理対象のタスクオブジェクト

        """
        # タスクからプロンプトを取得
        prompt = task.get_prompt()
        self.logger.info(f"LLMに送信するプロンプト: {prompt}")

        # システムプロンプトとユーザーメッセージを送信
        self.llm_client.send_system_prompt(self._make_system_prompt())
        self.llm_client.send_user_message(prompt)

        # 処理ループの初期化
        prev_output: str | None = None
        count = 0
        max_count = self.config.get("max_llm_process_num", 1000)

        # 連続ツールエラー管理用の変数
        last_tool: str | None = None
        tool_error_count = 0
        should_break = False

        # LLMとの対話ループ
        while count < max_count:
            # LLMからレスポンスを取得
            resp, functions = self.llm_client.get_response()
            self.logger.info(f"LLM応答: {resp}")

            # <think>...</think>の内容をコメントとして投稿し、レスポンスから除去
            think_matches = re.findall(r"<think>(.*?)</think>", resp, flags=re.DOTALL)
            for think_content in think_matches:
                # 思考内容をタスクにコメントとして追加
                task.comment(think_content.strip())


            # JSON応答の解析
            try:
                data = self._extract_json(resp_clean)
            except Exception as e:
                self.logger.exception(f"LLM応答JSONパース失敗: {e}")
                count += 1
                # 5回連続でJSONパースに失敗した場合は処理を中断
                if count >= 5:
                    task.comment("LLM応答エラーでスキップ")
                    break
                continue

            # function_callフィールドの処理
            if "function_call" in data:
                functions = data["function_call"]
                # 単一の関数呼び出しの場合はリストに変換
                if not isinstance(functions, list):
                    functions = [functions]

            # 関数呼び出しの実行
            if len(functions) != 0:
                # 呼び出し対象の関数名をコメントとして記録
                comments = [
                    function["name"]
                    for function in functions
                    if isinstance(function, dict) and "name" in function
                ]
                task.comment(f"関数呼び出し: {', '.join(list(comments))}")

                # 各関数を順次実行
                for function in functions:
                    # 関数名の取得
                    name = function["name"] if isinstance(function, dict) else function.name

                    # MCPサーバー名とツール名を分離
                    mcp_server, tool_name = name.split("_", 1)

                    # 引数の取得とサニタイズ
                    args = (
                        function["arguments"] if isinstance(function, dict) else function.arguments
                    )
                    args = self.sanitize_arguments(args)
                    self.logger.info(f"関数呼び出し: {name} with args: {args}")

                    # ツールの実行とエラーハンドリング
                    try:
                        try:
                            # MCPツールの呼び出し
                            output = self.mcp_clients[mcp_server].call_tool(tool_name, args)

                            # ツール呼び出し成功時はエラーカウントリセット
                            if last_tool == tool_name:
                                tool_error_count = 0
                        except* McpError as e:
                            # MCPエラーの処理
                            self.logger.exception(
                                f"ツール呼び出し失敗: {e.exceptions[0].exceptions[0]}",
                            )
                            task.comment(f"ツール呼び出しエラー: {e.exceptions[0].exceptions[0]}")
                            output = f"error: {e.exceptions[0].exceptions[0]!s}"

                            # 連続ツールエラーの判定と処理
                            if last_tool == name:
                                tool_error_count += 1
                            else:
                                tool_error_count = 1
                                last_tool = name

                            # 3回連続エラーの場合は処理を中止
                            if tool_error_count >= 3:
                                task.comment(
                                    f"同じツール({name})で3回連続エラーが発生したため処理を中止します。",
                                )
                                should_break = True
                    except BaseException as e:
                        # その他の例外の処理
                        while isinstance(e, ExceptionGroup):
                            e = e.exceptions[0]
                        self.logger.exception(f"ツール呼び出しエラー: {e}")
                        task.comment(f"ツール呼び出しエラー: {e}")
                        output = f"error: {e!s}"

                        # 連続ツールエラーの判定と処理
                        if last_tool == name:
                            tool_error_count += 1
                        else:
                            tool_error_count = 1
                            last_tool = name

                        # 3回連続エラーの場合は処理を中止
                        if tool_error_count >= 3:
                            task.comment(
                                f"同じツール({name})で3回連続エラーが発生したため処理を中止します。",
                            )
                            should_break = True

                    # ツール実行結果をLLMに送信
                    self.llm_client.send_function_result(name, output)

            # planフィールドの処理
            if "plan" in data:
                # コメントとプランをタスクに追加し、LLMに送信
                task.comment(str(data["comment"]))
                task.comment(str(data["plan"]))
                self.llm_client.send_user_message(str(data["plan"]))

            # commandフィールドの処理(レガシー形式)
            if "command" in data:
                task.comment(data.get("comment", ""))
                tool = data["command"]["tool"]
                args = data["command"]["args"]
                args = self.sanitize_arguments(args)
                mcp_server, tool_name = tool.split("_", 1)
                try:
                    output = self.mcp_clients[mcp_server].call_tool(tool_name, args)
                    # ツール呼び出し成功時はエラーカウントリセット
                    if last_tool == tool:
                        tool_error_count = 0
                except* McpError as e:
                    self.logger.exception(f"ツール呼び出し失敗: {e.exceptions[0].exceptions[0]}")
                    task.comment(f"ツール呼び出しエラー: {e.exceptions[0].exceptions[0]}")
                    output = f"error: {e.exceptions[0].exceptions[0]!s}"
                    # 連続ツールエラー判定
                    if last_tool == tool:
                        tool_error_count += 1
                    else:
                        tool_error_count = 1
                        last_tool = tool
                    if tool_error_count >= 3:
                        # 連続ツールエラーの判定と処理
                        if last_tool == tool:
                            tool_error_count += 1
                        else:
                            tool_error_count = 1
                            last_tool = tool

                        # 3回連続エラーの場合は処理を中止
                        if tool_error_count >= 3:
                            task.comment(
                                f"同じツール({tool})で3回連続エラーが発生したため処理を中止します。",
                            )
                            should_break = True

                # ツール実行結果をLLMに送信
                self.llm_client.send_user_message(f"output: {output}")

            # done フィールドの処理(タスク完了)
            if data.get("done"):
                # 完了コメントを追加し、タスクの完了処理を実行
                comment_text = data.get("comment", "") or "処理が完了しました。"
                task.comment(comment_text, mention=True)
                task.finish()
                break

            # エラー発生時の処理中断
            if should_break:
                break

            # ループカウンターの増加
            count += 1

    def _make_system_prompt(self) -> str:
        """システムプロンプトを生成する.

        設定に基づいてfunction callingの有無を判定し、
        適切なシステムプロンプトファイルを読み込んで、
        MCPプロンプトを埋め込んで返します。

        Returns:
            生成されたシステムプロンプト文字列

        """
        if self.config.get("llm", {}).get("function_calling", True):
            # function callingが有効な場合
            with open("system_prompt_function_call.txt") as f:
                prompt = f.read()
        else:
            # function callingが無効な場合
            with open("system_prompt.txt") as f:
                prompt = f.read()

        # MCPクライアントからシステムプロンプトを取得して結合
        mcp_prompt = ""
        for client in self.mcp_clients.values():
            mcp_prompt += client.system_prompt + "\n"

        # プロンプトテンプレートのプレースホルダーを置換
        return prompt.replace("{mcp_prompt}", mcp_prompt)

    def _extract_json(self, text: str) -> dict[str, Any]:
        """テキストから最初のJSONブロックを抽出する.

        LLMの応答テキストからJSON形式の部分を抽出し、
        パースして辞書として返します。

        Args:
            text: JSON を含む可能性があるテキスト

        Returns:
            抽出・パースされたJSONデータの辞書

        Raises:
            ValueError: JSONが見つからない場合
            json.JSONDecodeError: JSONの解析に失敗した場合

        """
        # テキストから最初の"{" と最後の "}" を見つける
        start = text.find("{")
        end = text.rfind("}")

        if start == -1 or end == -1:
            msg = "No JSON found"
            raise ValueError(msg)

        # JSON部分を抽出してパース
        return json.loads(text[start : end + 1])
