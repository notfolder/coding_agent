# local coding agentの作成

## 概要
github copilot coding agentの様なコーディングエージェントを作る.
将来的にはシステムプロンプトを変更することで、メールを振り分けたり、様々なタスクのソースからタスクを取得してllmを使って自動処理する汎用的なllmエージェントを考えている。
コーディングエージェント以外の例としてはメール振分し、重要メールを通知するなど。
今回はgit hubにラベル付されたissueをタスクとして処理するコーディングエージェントを作成する。

## 環境
 - OS: mac os
 - 言語: python
 - 起動方法: crontab

## 条件
 - llmの呼び出しは設定ファイルの`llm.provider` で使用するプロバイダを指定する（`lmstudio`/`ollama`/`openai`）。
 - 各プロバイダ固有の設定項目を `llm.<provider>` セクションに定義する。
 - ローカルでdockerでstdioで起動するmcpサーバーを利用する([modelcontextprotocol](https://modelcontextprotocol.io/quickstart/client):mcp_client.mdを利用)
 - loggerはpython標準のものを使用。loggerの設定ファイルも生成して。ログはファイルにだけ出力する様な設定で、デイリーでローテーションして圧縮して
 - このエージェントは、任意のMCPサーバー（Model Context Protocol準拠）を対象とします。

mcpのクライアントは下記2種類の使い方があります。

1. タスクを取得する抽象TaskGetterクラスおよびその具象クラスであるTaskGetterFromGitHubクラスとする。TaskGetterクラスはTaskオブジェクトを返し、その具象クラスとしてTaskGitHubIssueクラスを用意する
2. llmからの`command`要求に応えるための`MCPToolClient`クラス→設定ファイルからオブジェクトを生成し、llmの応答に従って利用する。

**MCP サーバー起動（stdio モード）**
  - `MCPToolClient`クラスを作り、`mcp`ライブラリのクライアントのラッパーにしてください。(非同期を同期にするため)
  - 設定ファイル `config.yaml` の `mcp_servers[].command` に定義されたコマンドを`from mcp.client.stdio import stdio_client`で起動して使う.

## 動作

1. MCPサーバーを起動する(複数のmcp_clientを起動し、辞書で管理、8番で利用する際に振り分けられる様にする)
2.　起動したらタスクの一覧を取得する(TaskGetter.get_task_list)
3. タスク一覧のTask一つ一つについて、下記の処理を実施
4. タスクの処理を通知するためTask.prepare()を呼び出す
5. llmを呼び出す。システムプロンプトしてユーザープロンプトとしてTask.get_prompt()の内容に従い、指示に従い終わったらjson応答の中に```done: true```といった終了マークを表示するといったプロンプトを指定して呼び出す.llmの応答にはjsonが含まれるものとする。
6. 以下の処理をjson応答の中に```done: true```が現れるまで繰り返す
7. llmの応答の中の`comment`フィールドをTask.comment()を呼び出して記録する
8. mcpサーバーを利用したい旨の回答(`command`)があったらmcpサーバーを呼び出し応答を得る.`command`の`tool`は`<mcp_server_name>/<tool_name>`形式になっているため、`<mcp_server_name>`のmcpサーバーの`<tool_name>`toolを呼び出して`args`を渡す.mcpサーバーは設定ファイルの`mcp_server_name` と`<mcp_server_name>`を単純マッチングする.
9. llmを呼び出す。mcpサーバーの応答をllmに渡して応答を得る
10. llmのjson応答の中に終了マーク```done: true```があるか、1タスクあたりのLLM API への呼び出し回数が最大処理数(設定ファイルの`max_llm_process_num`)を超えた場合、Task.finish()してタスクに終了を記録してループを終了する。それ以外は4.に戻る
11. 次のTaskを同様に処理する
12. 一覧したTaskを全て処理したら処理を終了する

### TaskGetterFromGitHubクラスのメソッドマッピング

以下githubのissueに対する操作はmcpサーバー[githubのmcpサーバー](https://github.com/github/github-mcp-server):git-hub-mcp-server.mdを使います。

- **TaskGetterFromGitHub.get_task_list**: `coding agent`というラベルがついたissueを一覧(search_issues)し、TaskGitHubIssueクラスのオブジェクトリストを作成する
- **TaskGitHubIssue.prepare**: そのタスクに紐づいているissueの`coding agent`ラベルを削除し、`coding agent processing`ラベルを付与する(update_issue)
- **TaskGitHubIssue.get_prompt**: そのタスクに紐づいているissueの内容とコメントを取得(get_issue,get_issue_comments)してプロンプトとして提示する
- **TaskGitHubIssue.comment**: そのタスクに紐づいているissueにコメントを記録する(add_issue_comment)
- **TaskGitHubIssue.finish()**: issueの`coding agent processing`ラベルを削除(update_issue)


## JSON応答のスキーマ

llmの応答に含まれるjson応答は下記の形式になる。

### command応答

```json
{
  "command": {
    "comment": "なぜこのコマンドを実行するのかの説明",
    "tool": "<mcp_server_name>/<tool_name>",
    "args": {
      // tool-specific parameters, matching the definitions above
    }
  }
}
```

### 完了応答

```json
{
  "done": true,
  "comment": "終了コメント"
}
```

### llm応答のパース仕様

1. **JSONパース**:

   * LLMからのレスポンスからjson部分を探して処理する
   * JSON部分が見つからない時はログを記録し、制御プログラムが再試行またはスキップを判断。
   * 5回llmの呼び出しを再試行してもエラーになる場合はissueにエラーになった旨をコメントして```coding agent```ラベルを削除する

2. **コマンド検出**:

   * レスポンスに `command` キーが存在すればツール呼び出し要求とみなす。
   * `comment`フィールドの内容でTask.commentメソッドを呼び出す。
   * `command.tool` と `command.args` を抽出し、MCPサーバーへPOST。
3. **ツール出力受け渡し**:

   * MCPサーバーの `output` フィールドを取得し、次の LLM 呼び出し時に `previous_output` としてプロンプトに含める。
4. **完了判定**:

   * レスポンスに `done: true` が含まれる場合、処理を終了。
   * `comment` フィールドの内容をissueのコメントに追加。
5. **ループ**:

   * `done` が `true` になるまで手順2〜4を繰り返す。

### LLM アダプター

- `LLMClient` 抽象クラスを定義し、以下を必ず実装する：
  1. `send_system_prompt(prompt: str) -> None`
  2. `send_user_message(message: str) -> None`
  3. `get_response() -> str`

**呼び出しシーケンス**
1. `send_system_prompt` を呼出し
2. 毎ターン：`send_user_message` → `get_response`
3. `get_response` は内部で履歴にアシスタント応答を追加

- `config.yaml` の `llm.provider` に応じて、以下のラッパークラスを初期化：
  - `lmstudio` → `LMStudioClient`
  - `openai`   → `OpenAIClient`
  - `ollama`   → `OllamaClient`

- エージェントの LLM 呼び出し部は、`LLMClient` の上記３メソッドのみを呼び出すことでプロバイダ差異を完全に吸収する。

- lmstudioの場合は、llm.Chatを利用してコンテキストを保存する
- ollamaの場合は、```from ollama import chat```を使い、自前で messages リストを管理することで状態を継続.4文字を1トークンとして`max_token`を超えない様に切り詰める。

```
from ollama import chat

messages = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "空はなぜ青いの？"}
]

response = chat(model='llama3', messages=messages)

# 応答をmessagesに追加
messages.append({"role": "assistant", "content": response['message']['content']})
```

- openaiの場合は、`OpenAI Python SDK (openai パッケージ)`の`ChatCompletion.create(messages=[...])` を使い、自前で messages リストを管理することで状態を継続.4文字を1トークンとして`max_token`を超えない様に切り詰める。
```
import openai

messages = [{"role":"system","content":"You are…"}]
messages.append({"role":"user","content":"Hello"})
resp = openai.ChatCompletion.create(model="gpt-4o", messages=messages)
reply = resp.choices[0].message
messages.append({"role":"assistant","content":reply.content})
```

### LLM 初期化例（擬似コード）
```python
prov = cfg["llm"]["provider"]
if prov == "lmstudio":
    client = LMStudioClient(...)
elif prov == "ollama":
    client = OllamaClient(...)
elif prov == "openai":
    client = OpenAIClient(...)
else:
    raise ValueError(...)
client.send_system_prompt(system_prompt)


### llmへの要求方法

各LLM呼び出し時には、以下の情報を連結してプロンプトに含めること：

 * 直前に実行されたMCPコマンドとそのargs
 * MCPサーバーからのoutput(整形済み)

## コードの生成

上記環境、条件、動作を実現するコードを生成する。
 - システムプロンプト、ユーザープロンプトについては設定ファイルを読み込む様にする
 - mcpサーバーについては設定ファイルを読んで動作する
 - mcpサーバーの`system_prompt`フィールドの内容を統合して`system_prompt.txt`の`{mcp_prompt}`に埋め込む

設定ファイル例は下記.
```
mcp_servers:
  - mcp_server_name: "github"
    command:
      - "docker"
      - "run"
      - "-i"
      - "--rm"
      - "-e"
      - "GITHUB_PERSONAL_ACCESS_TOKEN"
      - "-e"
      - "GITHUB_DYNAMIC_TOOLSETS=1"
      - "ghcr.io/github/github-mcp-server"
    system_prompt: |
      ### github mcp tools
      * `github/get_issue`           → `{ "owner": string, "repo": string, "issue_number": int }`
      * `github/get_file_contents`   → `{ "owner": string, "repo": string, "path": string, "ref": string }`
      * `github/create_or_update_file` → `{ "owner": string, "repo": string, "path": string, "content": string, "branch": string, "message": string }`
      * `github/create_pull_request` → `{ "owner": string, "repo": string, "title": string, "body": string, "head": string, "base": string }`
      * `github/update_issue`        → `{ "owner": string, "repo": string, "issue_number": int, "remove_labels"?: [string], "add_labels"?: [string] }`

llm:
  provider: "lmstudio"    # "ollama" | "openai"
  lmstudio:
    base_url: "http://127.0.0.1:1234"
    context_length: 32768
    model: "qwen3-30b-a3b-mlx"
  ollama:
    endpoint: "http://localhost:11434"
    model: "qwen3-30b-a3b-mlx"
    max_token: 32768
  openai:
    api_key_env: "OPENAI_API_KEY"
    model: "gpt-4o"
    max_token: 32768
max_llm_process_num: 1000
github:
  owner:     "my-org"
  bot_label: "coding agent"
  query: 'label:"question"'

scheduling:
  interval: 300  # 秒
```

GITHUB_PERSONAL_ACCESS_TOKENはcronの起動時に環境変数として設定します

## コードのディレクトリ構成

```
.
├── config.yaml
├── system_prompt.txt
├── condaenv.yaml # anaconda形式の環境構築ファイル(lmstudio以外はcondaで入れる)
├── main.py
├── clients/
│   ├── mcp_tool_client.py
│   └── lm_client.py
└── handlers/
    ├── task_handler.py
    ├── task_getter.py
    └── task_getter_github.py
```

## プロンプトファイルの中身

### system_prompt.txt
````markdown
You are an AI coding assistant that cooperates with a controlling program to automate GitHub workflows via a GitHub MCP server over HTTP.  

**Output Format**: Your output **must** be valid JSON only. Do **not** include any human-readable explanations or extra text. Return only one of the following structures:

1. **Tool invocation request**
  ```json
  {
    "comment": "<The comment field should briefly explain why the tool is being called, to make the action clear and traceable.>",
    "command": {
       "tool": "<tool_name>",
       "args": { /* tool-specific parameters */ }
    }
  }
  ```

2. **Final completion signal**

   ```json
   {
     "comment": "e.g., All requested changes were implemented and tested successfully.",
     "done": true
   }
   ```

---

## Available MCP Tools and Args

{mcp_prompt}

---

## Behavior Rules

1. The controlling program parses your JSON `command` and invokes the MCP server over HTTP.
2. Upon receiving the tool `output`, generate the next JSON `command`.
3. When the task is complete, return the JSON with `{ "done": true, ... }`.
4. Infer project language by file extensions and generate or modify files accordingly.

Always adhere strictly to JSON-only output under this system prompt.

````

### first_user_prompt.txt
```
Issue #{issue_number}:
Title: "{title}"
Body:
{body}

Repository settings:
- Owner: {owner}
- Repo: {repo}
- Base branch: `main`
- Label: `coding agent`
```

## エラーハンドリングと通知

再試行ポリシー（例：HTTP 5xx → 3回リトライ）
失敗時はログに出力する
