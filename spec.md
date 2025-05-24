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

## 動作

以下githubのissueに対する操作はmcpサーバー[githubのmcpサーバー](https://github.com/github/github-mcp-server)を使う

1.　起動したら```coding agent```というラベルのissueを一覧(list_issues)する
2. issue一覧のissue一つ一つについて、下記の処理を実施
3. llmを呼び出す。システムプロンプトしてgithubのmcpサーバーを使う様に指示し,ユーザープロンプトとしてissueの内容を読んで指示に従い、指示に従い終わったら```^^^complete^^^```といった終了マークを表示するといったプロンプトを指定して呼び出す
4. 以下の処理を```^^^complete^^^```が現れるまで繰り返す
5. llmの応答をissueのコメントとして記録する(add_issue_comment)
6. mcpサーバーを利用したい旨の回答があったらmcpサーバーを呼び出し応答に対応する処理を行う
7. llmを呼び出す。mcpサーバーの応答をllmに渡して応答を得て4.に戻る
7. llmの応答に終了マーク```^^^complete^^^```があったらissueの```coding agent```を削除(update_issue)する
8. 次のissueを同様に処理する
9. 一覧したissueを全て処理したら処理を終了する

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
│   └── issue_handler.py
└── utils/
    └── logger.py

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
```
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
* `update_issue` → \`{ "owner": string, "repo": string, "issue\_numb
```

## エラーハンドリングと通知

再試行ポリシー（例：HTTP 5xx → 3回リトライ）
失敗時はログに出力する
