import json
import logging
import re

from mcp import McpError


class TaskHandler:
    def __init__(self, llm_client, mcp_clients, config):
        self.llm_client = llm_client
        self.mcp_clients = mcp_clients
        self.config = config
        self.logger = logging.getLogger(__name__)

    def sanitize_arguments(self, arguments):
        """引数が dict でなければ JSON 文字列としてパースし、dict に変換する。
        """
        if isinstance(arguments, dict):
            return arguments
        if isinstance(arguments, str):
            try:
                parsed = json.loads(arguments)
                if isinstance(parsed, dict):
                    return parsed
                raise ValueError("Parsed JSON is not a dictionary.")
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON string for arguments: {e}")
        else:
            raise TypeError(f"Unsupported type for arguments: {type(arguments)}")

    def handle(self, task):
        prompt = task.get_prompt()
        self.logger.info(f"LLMに送信するプロンプト: {prompt}")
        self.llm_client.send_system_prompt(self._make_system_prompt())
        self.llm_client.send_user_message(prompt)
        prev_output = None
        count = 0
        max_count = self.config.get("max_llm_process_num", 1000)
        # 連続ツールエラー管理用
        last_tool = None
        tool_error_count = 0
        should_break = False
        while count < max_count:
            resp, functions = self.llm_client.get_response()
            self.logger.info(f"LLM応答: {resp}")
            # <think>...</think> の内容をコメントとして投稿し、除去
            think_matches = re.findall(r"<think>(.*?)</think>", resp, flags=re.DOTALL)
            for think_content in think_matches:
                task.comment(think_content.strip())
            resp_clean = re.sub(r"<think>.*?</think>", "", resp, flags=re.DOTALL)
            try:
                data = self._extract_json(resp_clean)
            except Exception as e:
                self.logger.error(f"LLM応答JSONパース失敗: {e}")
                count += 1
                if count >= 5:
                    task.comment("LLM応答エラーでスキップ")
                    break
                continue
            if "function_call" in data:
                functions = data["function_call"]
                if not isinstance(functions, list):
                    functions = [functions]  # 単一の関数呼び出しをリストに変換
            if len(functions) != 0:
                # 関数呼び出しがある場合は、関数の結果をLLMに送信
                comments = [
                    function["name"]
                    for function in functions
                    if isinstance(function, dict) and "name" in function
                ]
                task.comment(f"関数呼び出し: {', '.join([f for f in comments])}")
                for function in functions:
                    name = function["name"] if isinstance(function, dict) else function.name
                    mcp_server, tool_name = name.split("_", 1)
                    args = (
                        function["arguments"] if isinstance(function, dict) else function.arguments
                    )
                    args = self.sanitize_arguments(args)  # 引数を適切にサニタイズ
                    self.logger.info(f"関数呼び出し: {name} with args: {args}")
                    try:
                        try:
                            output = self.mcp_clients[mcp_server].call_tool(tool_name, args)
                            # ツール呼び出し成功時はエラーカウントリセット
                            if last_tool == tool_name:
                                tool_error_count = 0
                        except* McpError as e:
                            self.logger.error(
                                f"ツール呼び出し失敗: {e.exceptions[0].exceptions[0]}",
                            )
                            task.comment(f"ツール呼び出しエラー: {e.exceptions[0].exceptions[0]}")
                            output = f"error: {e.exceptions[0].exceptions[0]!s}"
                            # 連続ツールエラー判定
                            if last_tool == name:
                                tool_error_count += 1
                            else:
                                tool_error_count = 1
                                last_tool = name
                            if tool_error_count >= 3:
                                task.comment(
                                    f"同じツール({name})で3回連続エラーが発生したため処理を中止します。",
                                )
                                should_break = True
                    except BaseException as e:
                        while isinstance(e, ExceptionGroup):
                            e = e.exceptions[0]
                        self.logger.error(f"ツール呼び出しエラー: {e}")
                        task.comment(f"ツール呼び出しエラー: {e}")
                        output = f"error: {e!s}"
                        # 連続ツールエラー判定
                        if last_tool == name:
                            tool_error_count += 1
                        else:
                            tool_error_count = 1
                            last_tool = name
                        if tool_error_count >= 3:
                            task.comment(
                                f"同じツール({name})で3回連続エラーが発生したため処理を中止します。",
                            )
                            should_break = True
                    self.llm_client.send_function_result(name, output)
            if "plan" in data:
                task.comment(str(data["comment"]))
                task.comment(str(data["plan"]))
                self.llm_client.send_user_message(str(data["plan"]))
            if "command" in data:
                task.comment(data.get("comment", ""))
                tool = data["command"]["tool"]
                args = data["command"]["args"]
                args = self.sanitize_arguments(args)  # 引数を適切にサニタイズ
                mcp_server, tool_name = tool.split("_", 1)
                try:
                    output = self.mcp_clients[mcp_server].call_tool(tool_name, args)
                    # ツール呼び出し成功時はエラーカウントリセット
                    if last_tool == tool:
                        tool_error_count = 0
                except* McpError as e:
                    self.logger.error(f"ツール呼び出し失敗: {e.exceptions[0].exceptions[0]}")
                    task.comment(f"ツール呼び出しエラー: {e.exceptions[0].exceptions[0]}")
                    output = f"error: {e.exceptions[0].exceptions[0]!s}"
                    # 連続ツールエラー判定
                    if last_tool == tool:
                        tool_error_count += 1
                    else:
                        tool_error_count = 1
                        last_tool = tool
                    if tool_error_count >= 3:
                        task.comment(
                            f"同じツール({tool})で3回連続エラーが発生したため処理を中止します。",
                        )
                        should_break = True
                self.llm_client.send_user_message(f"output: {output}")
            if data.get("done"):
                comment_text = data.get("comment", "") or "処理が完了しました。"
                task.comment(comment_text, mention=True)
                task.finish()
                break
            if should_break:
                break
            count += 1

    def _make_system_prompt(self):
        if self.config.get("llm", {}).get("function_calling", True):
            # function callingを有効にする場合は、system_prompt_function_call.txtを読み込む
            with open("system_prompt_function_call.txt") as f:
                prompt = f.read()
            mcp_prompt = ""
            for name, client in self.mcp_clients.items():
                mcp_prompt += client.system_prompt + "\n"
            return prompt.replace("{mcp_prompt}", mcp_prompt)
        # system_prompt.txtを読み込み、mcp_promptをmcp_clientsから取得したsystem_promptで埋め込む
        with open("system_prompt.txt") as f:
            prompt = f.read()
        mcp_prompt = ""
        for name, client in self.mcp_clients.items():
            mcp_prompt += client.system_prompt + "\n"
        return prompt.replace("{mcp_prompt}", mcp_prompt)

    def _extract_json(self, text):
        # テキストから最初のJSONブロックを抽出
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("No JSON found")
        return json.loads(text[start : end + 1])
