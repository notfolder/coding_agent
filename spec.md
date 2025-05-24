# local coding agentの作成

## 概要
github copilot coding agentの様なコーディングエージェントを作る.

## 環境
 - OS: mac os
 - 言語: python
 - 起動方法: crontab

## 条件
 - ローカルに起動しているlm studioのllmを利用する(lmstudio-pythonを利用)
 - dockerローカルに起動しているgit hubのmcpサーバーを利用する(mcp-useを利用)
 - loggerはpython標準のものを使用。loggerの設定ファイルも生成して。ログはファイルにだけ出力する様な設定で、デイリーでローテーションして圧縮して

## 動作

以下githubのissueに対する操作はmcpサーバー[githubのmcpサーバー](https://github.com/github/github-mcp-server)を使う

1.　起動したら```coding agent```というラベルのissueを一覧(list_issues)する
2. issue一覧のissue一つ一つについて、下記の処理を実施
3. llmを呼び出す。システムプロンプトしてgithubのmcpサーバーを使う様に指示し,ユーザープロンプトとしてissueの内容を読んで指示に従い、指示に従い終わったらjson応答の中に```done: true```といった終了マークを表示するといったプロンプトを指定して呼び出す.llmの応答にはjsonが含まれるものとする。
4. 以下の処理をjson応答の中に```done: true```が現れるまで繰り返す
5. llmの応答をissueのコメントとして記録する(add_issue_comment)
6. mcpサーバーを利用したい旨の回答があったらmcpサーバーを呼び出し応答に対応する処理を行う
7. llmを呼び出す。mcpサーバーの応答をllmに渡して応答を得て4.に戻る
7. llmのjson応答の中に終了マーク```done: true```があったらissueの```coding agent```を削除(update_issue)する
8. 次のissueを同様に処理する
9. 一覧したissueを全て処理したら処理を終了する

## JSON応答のスキーマ

llmの応答に含まれるjson応答は下記の形式になる。

### command応答

```json
{
  "command": {
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
  "result": {
    // structured result object, e.g., pull request URL, branch name, files modified
  }
}
```

### llm応答のパース仕様

1. **JSONパース**:

   * LLMからのレスポンスからjson部分を探して処理する
   * JSON部分が見つからない時はログを記録し、制御プログラムが再試行またはスキップを判断。
   * 5回llmの呼び出しを再試行してもエラーになる場合はissueにエラーになった旨をコメントして```coding agent```ラベルを削除する

2. **コマンド検出**:

   * レスポンスに `command` キーが存在すればツール呼び出し要求とみなす。
   * `command.tool` と `command.args` を抽出し、MCPサーバーへPOST。
3. **ツール出力受け渡し**:

   * MCPサーバーの `output` フィールドを取得し、次の LLM 呼び出し時に `previous_output` としてプロンプトに含める。
4. **完了判定**:

   * レスポンスに `done: true` が含まれる場合、処理を終了。
   * `result` フィールドを最終成果物としてログおよび通知に利用。
5. **ループ**:

   * `done` が `true` になるまで手順2〜4を繰り返す。


## コードの生成

上記環境、条件、動作を実現するコードを生成する。
 - システムプロンプト、ユーザープロンプトについては設定ファイルを読み込む様にする
 - mcpサーバーについては設定ファイルを読んで動作する(githubのmcpサーバーの呼び出し方など)

mcpサーバーの設定ファイル例は下記.
```
mcp:
  server_url: "http://localhost:8000"
  api_key_env: "GITHUB_MCP_TOKEN"
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

.
├── mcp_config.yaml
├── system_prompt.txt
├── main.py
├── clients/
│   ├── mcp_client.py
│   └── lm_client.py
├── handlers/
    └── issue_handler.py

## 関数/クラスのインターフェース

```
class Issue(TypedDict):
    number: int
    title: str
    body: str

class MCPClient:
    def get_issues(self, label: str) -> List[Issue]: ...
    def update_issue(self, number: int, remove_label: str) -> None: ...
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
       "tool": "<tool_name>",
       "args": { /* tool-specific parameters */ }
     }
   }
````

2. **Final completion signal**

   ```json
   {
     "done": true,
     "result": {
       /* Final structured result, e.g., PR information */
     }
   }
   ```

---

## Available MCP Tools and Args

* `get_issue`   → `{ "owner": string, "repo": string, "issue_number": int }`
* `get_file_contents` → `{ "owner": string, "repo": string, "path": string, "ref": string }`
* `create_or_update_file` → `{ "owner": string, "repo": string, "path": string, "content": string, "branch": string, "message": string }`
* `create_pull_request` → `{ "owner": string, "repo": string, "title": string, "body": string, "head": string, "base": string }`
* `update_issue` → `{ "owner": string, "repo": string, "issue_number": int, "remove_labels"?: [string], "add_labels"?: [string] }`

---

## Behavior Rules

1. **First** action: request `get_issue` to fetch the Issue data.
2. The controlling program parses your JSON `command` and invokes the MCP server over HTTP.
3. Upon receiving the tool `output`, generate the next JSON `command`.
4. When the task is complete, return the JSON with `{ "done": true, ... }`.
5. On errors, the program logs automatically—continue normal flow without emitting error messages.
6. Infer project language by file extensions and generate or modify files accordingly.

Always adhere strictly to JSON-only output under this system prompt.

```

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
