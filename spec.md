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
 - ローカルに起動しているlm studioのllmを利用する([lmstudio-python](https://lmstudio.ai/docs/python):lmstudio.mdを利用)
 - ローカルに起動しているのmcpサーバーを利用する([modelcontextprotocol](https://modelcontextprotocol.io/quickstart/client):mcp_client.mdを利用)
 - loggerはpython標準のものを使用。loggerの設定ファイルも生成して。ログはファイルにだけ出力する様な設定で、デイリーでローテーションして圧縮して
 - このエージェントは、任意のMCPサーバー（Model Context Protocol準拠）を対象とします。

mcpのクライアントは下記2種類の使い方があります。

1. タスクを取得する抽象TaskGetterクラスおよびその具象クラスであるTaskGetterFromGitHubクラスとする。TaskGetterクラスはTaskオブジェクトを返し、その具象クラスとしてTaskGitHubIssueクラスを用意する
2. llmからの`command`要求に応えるための`MCPToolClient`クラス→設定ファイルからオブジェクトを生成し、llmの応答に従って利用する。

## 動作

1.　起動したらタスクの一覧を取得する(TaskGetter.get_task_list)
2. タスク一覧のTask一つ一つについて、下記の処理を実施
3. タスクの処理を通知するためTask.prepare()を呼び出す
4. llmを呼び出す。システムプロンプトしてユーザープロンプトとしてTask.get_prompt()の内容に従い、指示に従い終わったらjson応答の中に```done: true```といった終了マークを表示するといったプロンプトを指定して呼び出す.llmの応答にはjsonが含まれるものとする。
5. 以下の処理をjson応答の中に```done: true```が現れるまで繰り返す
6. llmの応答の中の`comment`フィールドをTask.comment()を呼び出して記録する
7. mcpサーバーを利用したい旨の回答(`command`)があったらmcpサーバーを呼び出し応答を得る
8. llmを呼び出す。mcpサーバーの応答をllmに渡して応答を得て4.に戻る
9. llmのjson応答の中に終了マーク```done: true```があったらTask.finish()してタスクに終了を記録する。
10. 次のissueを同様に処理する
11. 一覧したissueを全て処理したら処理を終了する

### TaskGetterFromGitHubクラスのメソッドマッピング

以下githubのissueに対する操作はmcpサーバー[githubのmcpサーバー](https://github.com/github/github-mcp-server):git-hub-mcp-server.mdを使います。

- **TaskGetterFromGitHub.get_task_list**: `coding agent`というラベルがついたissueを一覧(list_issues)し、TaskGitHubIssueクラスのオブジェクトリストを作成する
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
    "comment": "なぜこのコマンドを実行するのかの説明"
    "tool": "<tool_name>",
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


## コードの生成

上記環境、条件、動作を実現するコードを生成する。
 - システムプロンプト、ユーザープロンプトについては設定ファイルを読み込む様にする
 - mcpサーバーについては設定ファイルを読んで動作する
 - mcpサーバーの`system_prompt`フィールドの内容を統合して`system_prompt.txt`の`{mcp_prompt}`に埋め込む

mcpサーバーの設定ファイル例は下記.
```
mcp_servers:
  [
    {
      server_url: "http://localhost:8000",
      api_key_env: "GITHUB_MCP_TOKEN",
      system_prompt: |
        ### github mcp tools
        * `get_issue`   → `{ "owner": string, "repo": string, "issue_number": int }`
        * `get_file_contents` → `{ "owner": string, "repo": string, "path": string, "ref": string }`
        * `create_or_update_file` → `{ "owner": string, "repo": string, "path": string, "content": string, "branch": string, "message": string }`
        * `create_pull_request` → `{ "owner": string, "repo": string, "title": string, "body": string, "head": string, "base": string }`
        * `update_issue` → `{ "owner": string, "repo": string, "issue_number": int, "remove_labels"?: [string], "add_labels"?: [string] }`
    }
  ]
lmstudio:
  base_url: "http://localhost:8080/v1"
  api_key_env: "LMSTUDIO_API_KEY"
github:
  owner: "my-org"
  repo: "my-repo"
  bot_label: "coding agent"
scheduling:
  interval: 300  # 秒
```

## コードのディレクトリ構成

```
.
├── mcp_config.yaml
├── system_prompt.txt
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
     "command": {
       "comment": "<The comment field should briefly explain why the tool is being called, to make the action clear and traceable.>",
       "tool": "<tool_name>",
       "args": { /* tool-specific parameters */ }
     }
   }
   ```

2. **Final completion signal**

   ```json
   {
     "done": true,
     "comment": "e.g., All requested changes were implemented and tested successfully."
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
