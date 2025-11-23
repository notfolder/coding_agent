# Webhook監視方式への移行仕様書

## 1. 概要

### 1.1 背景
現在、Coding Agentは以下の方式でタスクを検出しています：

- **ポーリング方式**: 定期的にGitHub/GitLabのAPIを呼び出し、特定のラベル（`coding agent`）が付いたIssueやPull Request/Merge Requestを検索
- **実行間隔**: 300秒（5分）ごとにcronまたは手動実行
- **動作フロー**: `main.py` → `TaskGetter.get_task_list()` → API検索 → タスク処理

この方式には以下の課題があります：

1. **リアルタイム性の欠如**: 最大5分の遅延が発生
2. **APIレート制限**: 頻繁なポーリングによるAPI呼び出し回数の消費
3. **リソースの無駄**: 新しいタスクがない場合でもAPI呼び出しが発生
4. **スケーラビリティの問題**: 監視対象リポジトリが増えるとAPI呼び出しが増加

### 1.2 目的
本仕様書は、ポーリング方式からWebhook方式への移行を定義します。

**Webhook方式の利点**:
- リアルタイム性の向上（イベント発生時に即座に処理）
- APIレート制限の軽減（ポーリング不要）
- 効率的なリソース利用（必要な時だけ処理）
- スケーラビリティの向上

### 1.3 対象範囲
- GitHub Webhooks（Issues、Pull Requests）
- GitLab Webhooks（Issues、Merge Requests）

## 2. 現状分析

### 2.1 現在のアーキテクチャ

```
┌─────────────┐
│   cron /    │
│   手動実行  │
└──────┬──────┘
       │
       v
┌──────────────────┐
│    main.py       │
│  produce_tasks() │
└──────┬───────────┘
       │
       v
┌─────────────────────────┐
│  TaskGetter             │
│  - get_task_list()      │
│    (API検索/ポーリング)  │
└──────┬──────────────────┘
       │
       v
┌─────────────────────┐
│  RabbitMQ Queue /   │
│  InMemory Queue     │
└──────┬──────────────┘
       │
       v
┌─────────────────────┐
│   consume_tasks()   │
│   TaskHandler       │
└─────────────────────┘
```

### 2.2 ポーリング方式の実装詳細

**main.py の produce_tasks()**:
```python
def produce_tasks(config, mcp_clients, task_source, task_queue, logger):
    task_getter = TaskGetter.factory(config, mcp_clients, task_source)
    tasks = task_getter.get_task_list()  # API検索によるポーリング
    for task in tasks:
        task.prepare()
        task_queue.put(task.get_task_key().to_dict())
```

**TaskGetterFromGitHub.get_task_list()**:
```python
def get_task_list(self):
    # 'coding agent' ラベルでIssueを検索
    query = f'label:"{self.config["github"]["bot_label"]}"'
    issues = self.github_client.search_issues(query)
    # Pull Requestも同様に検索
    prs = self.github_client.search_pull_requests(query)
    return tasks
```

## 3. Webhook方式の設計

### 3.1 アーキテクチャ概要

```
┌─────────────────┐
│  GitHub /       │
│  GitLab         │
│  (Webhook送信)  │
└────────┬────────┘
         │ HTTP POST (Webhook Event)
         v
┌──────────────────────────┐
│  Webhook Receiver        │
│  (FastAPI/Flask Server)  │
│  - POST /webhook/github  │
│  - POST /webhook/gitlab  │
└────────┬─────────────────┘
         │
         v
┌──────────────────────┐
│  Event Validator &   │
│  Filter              │
│  - 署名検証          │
│  - イベントフィルタ  │
└────────┬─────────────┘
         │
         v
┌──────────────────────┐
│  Task Factory        │
│  - WebhookからTask   │
│    オブジェクト生成  │
└────────┬─────────────┘
         │
         v
┌─────────────────────┐
│  RabbitMQ Queue /   │
│  InMemory Queue     │
└──────┬──────────────┘
       │
       v
┌─────────────────────┐
│   consume_tasks()   │
│   TaskHandler       │
│   (既存のまま)      │
└─────────────────────┘
```

### 3.2 主要コンポーネント

#### 3.2.1 Webhook Receiver (新規)
- **役割**: GitHubやGitLabからのWebhookイベントを受信するHTTPサーバー
- **実装**: FastAPIまたはFlaskを使用
- **エンドポイント**:
  - `POST /webhook/github`: GitHub Webhookイベント受信
  - `POST /webhook/gitlab`: GitLab Webhookイベント受信
  - `GET /health`: ヘルスチェック
- **ポート**: 8000 (環境変数で設定可能)

#### 3.2.2 Event Validator & Filter (新規)
- **役割**: Webhookイベントの検証とフィルタリング
- **機能**:
  - **署名検証**: GitHubのHMAC-SHA256またはGitLabのトークン検証
  - **イベントタイプフィルタ**: Issues、Pull Requests、Merge Requestsのイベントのみ処理
  - **アクションフィルタ**: `labeled`アクション（特定ラベル追加時）のみ処理
  - **ラベルフィルタ**: `coding agent`ラベルが追加された場合のみタスク化

#### 3.2.3 Task Factory (新規/拡張)
- **役割**: WebhookペイロードからTaskオブジェクトを生成
- **機能**:
  - GitHubイベント → `TaskGitHubIssue` or `TaskGitHubPullRequest`
  - GitLabイベント → `TaskGitLabIssue` or `TaskGitLabMergeRequest`
  - 既存の`Task`クラス階層と統合

#### 3.2.4 既存コンポーネントの継続利用
- **RabbitMQ/InMemory Queue**: 引き続き使用（Webhook経由でタスク追加）
- **TaskHandler**: 既存のまま使用
- **Task Classes**: 既存のまま使用
- **MCP Clients**: 既存のまま使用

### 3.3 実行モードの変更

#### 3.3.1 新しい実行モード

```
┌─────────────────────┐
│  --mode webhook     │  ← 新規
│  Webhook Server起動 │
└─────────────────────┘

┌─────────────────────┐
│  --mode consumer    │  ← 既存
│  タスク処理のみ     │
└─────────────────────┘

┌─────────────────────┐
│  --mode producer    │  ← 既存（非推奨になる可能性）
│  ポーリング実行     │
└─────────────────────┘

┌─────────────────────┐
│  引数なし           │  ← 既存（非推奨になる可能性）
│  producer+consumer  │
└─────────────────────┘
```

#### 3.3.2 推奨構成（本番環境）

**Webhook方式（推奨）**:
```
┌────────────────────────┐
│  Container 1           │
│  main.py --mode webhook│
│  (Webhook Server)      │
└────────────────────────┘
         │
         v (RabbitMQ経由)
┌────────────────────────┐
│  Container 2           │
│  main.py --mode consumer│
│  (Task Handler)        │
└────────────────────────┘
```

**ポーリング方式（後方互換性のため維持）**:
```
┌────────────────────────┐
│  cron                  │
│  main.py --mode producer│
│  (5分ごと)             │
└────────────────────────┘
         │
         v (RabbitMQ経由)
┌────────────────────────┐
│  main.py --mode consumer│
│  (Task Handler)        │
└────────────────────────┘
```

## 4. 詳細設計

### 4.1 Webhookイベント受信フロー

#### 4.1.1 GitHubイベント処理

```
┌─────────────────────────────────────┐
│ 1. GitHubからWebhook POST           │
│    URL: https://<server>/webhook/github
│    Headers:                          │
│      X-GitHub-Event: issues/pull_request
│      X-Hub-Signature-256: sha256=... │
│    Body: JSON payload               │
└──────────────┬──────────────────────┘
               │
               v
┌──────────────────────────────────────┐
│ 2. 署名検証                          │
│    - X-Hub-Signature-256を検証       │
│    - Secretと照合                    │
│    - 検証失敗 → 401 Unauthorized     │
└──────────────┬───────────────────────┘
               │
               v
┌──────────────────────────────────────┐
│ 3. イベントタイプ確認                │
│    X-GitHub-Event:                   │
│      - "issues" → Issue処理          │
│      - "pull_request" → PR処理       │
│      - その他 → 200 OK (無視)        │
└──────────────┬───────────────────────┘
               │
               v
┌──────────────────────────────────────┐
│ 4. アクション確認                    │
│    payload.action:                   │
│      - "labeled" → 次へ              │
│      - その他 → 200 OK (無視)        │
└──────────────┬───────────────────────┘
               │
               v
┌──────────────────────────────────────┐
│ 5. ラベル確認                        │
│    payload.label.name:               │
│      - "coding agent" → タスク化     │
│      - その他 → 200 OK (無視)        │
└──────────────┬───────────────────────┘
               │
               v
┌──────────────────────────────────────┐
│ 6. Taskオブジェクト生成              │
│    - TaskGitHubIssue or              │
│    - TaskGitHubPullRequest           │
└──────────────┬───────────────────────┘
               │
               v
┌──────────────────────────────────────┐
│ 7. キューに追加                      │
│    task_queue.put(task_dict)         │
│    → 200 OK                          │
└──────────────────────────────────────┘
```

#### 4.1.2 GitLabイベント処理

```
┌─────────────────────────────────────┐
│ 1. GitLabからWebhook POST           │
│    URL: https://<server>/webhook/gitlab
│    Headers:                          │
│      X-Gitlab-Event: Issue Hook / Merge Request Hook
│      X-Gitlab-Token: <secret_token> │
│    Body: JSON payload               │
└──────────────┬──────────────────────┘
               │
               v
┌──────────────────────────────────────┐
│ 2. トークン検証                      │
│    - X-Gitlab-Tokenを検証            │
│    - 設定値と照合                    │
│    - 検証失敗 → 401 Unauthorized     │
└──────────────┬───────────────────────┘
               │
               v
┌──────────────────────────────────────┐
│ 3. イベントタイプ確認                │
│    X-Gitlab-Event:                   │
│      - "Issue Hook" → Issue処理      │
│      - "Merge Request Hook" → MR処理 │
│      - その他 → 200 OK (無視)        │
└──────────────┬───────────────────────┘
               │
               v
┌──────────────────────────────────────┐
│ 4. アクション確認                    │
│    payload.object_attributes.action: │
│      - "update" → 次へ               │
│      - その他 → 200 OK (無視)        │
└──────────────┬───────────────────────┘
               │
               v
┌──────────────────────────────────────┐
│ 5. ラベル確認                        │
│    payload.labels[]:                 │
│      - "coding agent"含む → タスク化 │
│      - その他 → 200 OK (無視)        │
└──────────────┬───────────────────────┘
               │
               v
┌──────────────────────────────────────┐
│ 6. Taskオブジェクト生成              │
│    - TaskGitLabIssue or              │
│    - TaskGitLabMergeRequest          │
└──────────────┬───────────────────────┘
               │
               v
┌──────────────────────────────────────┐
│ 7. キューに追加                      │
│    task_queue.put(task_dict)         │
│    → 200 OK                          │
└──────────────────────────────────────┘
```

### 4.2 設定ファイルの変更

#### 4.2.1 config.yamlへの追加項目

```yaml
# 既存設定（変更なし）
github:
  owner: "notfolder"
  bot_label: "coding agent"
  processing_label: "coding agent processing"
  done_label: "coding agent done"
  query: 'state:open archived:false sort:updated-desc'

gitlab:
  owner: "notfolder"
  bot_label: "coding agent"
  processing_label: "coding agent processing"
  done_label: "coding agent done"
  project_id: "coding-agent-project"
  query: ''

# 新規追加: Webhook設定
webhook:
  enabled: true                    # Webhook機能の有効/無効
  server:
    host: "0.0.0.0"                # リッスンアドレス
    port: 8000                     # リッスンポート
  github:
    secret: "${GITHUB_WEBHOOK_SECRET}"  # GitHub Webhook Secret
    events:                        # 処理対象イベント
      - "issues"
      - "pull_request"
    actions:                       # 処理対象アクション
      - "labeled"
  gitlab:
    token: "${GITLAB_WEBHOOK_TOKEN}"    # GitLab Webhook Token
    events:                        # 処理対象イベント
      - "Issue Hook"
      - "Merge Request Hook"

# 既存設定（後方互換性のため維持）
scheduling:
  interval: 300  # 秒（ポーリング方式で使用）
```

#### 4.2.2 環境変数の追加

```bash
# 既存環境変数（変更なし）
TASK_SOURCE=github
GITHUB_PERSONAL_ACCESS_TOKEN=...
GITLAB_PERSONAL_ACCESS_TOKEN=...
OPENAI_API_KEY=...

# 新規追加: Webhook関連環境変数
WEBHOOK_ENABLED=true                    # Webhook機能の有効/無効
WEBHOOK_SERVER_HOST=0.0.0.0             # Webhookサーバーのホスト
WEBHOOK_SERVER_PORT=8000                # Webhookサーバーのポート
GITHUB_WEBHOOK_SECRET=your_secret_here  # GitHub Webhook Secret
GITLAB_WEBHOOK_TOKEN=your_token_here    # GitLab Webhook Token
```

### 4.3 新規ファイル構成

```
.
├── main.py                        # 既存（拡張）
├── config.yaml                    # 既存（拡張）
├── handlers/
│   ├── task_getter.py             # 既存
│   ├── task_getter_github.py      # 既存
│   ├── task_getter_gitlab.py      # 既存
│   ├── task_handler.py            # 既存
│   └── webhook_handler.py         # 新規 ★
├── webhook/                       # 新規ディレクトリ ★
│   ├── __init__.py                # 新規
│   ├── server.py                  # 新規 - FastAPIサーバー
│   ├── validators.py              # 新規 - 署名/トークン検証
│   ├── parsers.py                 # 新規 - Webhookペイロードパース
│   └── task_factory.py            # 新規 - Webhook→Taskファクトリ
├── tests/
│   └── webhook/                   # 新規ディレクトリ ★
│       ├── test_server.py         # 新規
│       ├── test_validators.py     # 新規
│       └── test_parsers.py        # 新規
└── docs/
    └── webhook_specification.md   # 本ドキュメント
```

### 4.4 主要モジュールの詳細設計

#### 4.4.1 webhook/server.py

```python
"""Webhook受信サーバー（FastAPI実装）"""
from fastapi import FastAPI, Request, HTTPException
from typing import Dict, Any
import logging

app = FastAPI()
logger = logging.getLogger(__name__)

class WebhookServer:
    def __init__(self, config: Dict[str, Any], task_queue):
        self.config = config
        self.task_queue = task_queue
        self.github_validator = GitHubWebhookValidator(config)
        self.gitlab_validator = GitLabWebhookValidator(config)
        self.task_factory = WebhookTaskFactory(config)
    
    async def handle_github_webhook(self, request: Request):
        """GitHub Webhookイベント処理"""
        # 1. リクエストボディ取得
        body = await request.body()
        payload = await request.json()
        
        # 2. 署名検証
        signature = request.headers.get("X-Hub-Signature-256")
        if not self.github_validator.validate_signature(body, signature):
            raise HTTPException(status_code=401, detail="Invalid signature")
        
        # 3. イベントタイプ確認
        event_type = request.headers.get("X-GitHub-Event")
        if event_type not in ["issues", "pull_request"]:
            return {"status": "ignored", "reason": "unsupported event type"}
        
        # 4. アクション確認
        action = payload.get("action")
        if action != "labeled":
            return {"status": "ignored", "reason": "not a labeled action"}
        
        # 5. ラベル確認
        label_name = payload.get("label", {}).get("name")
        if label_name != self.config["github"]["bot_label"]:
            return {"status": "ignored", "reason": "not the target label"}
        
        # 6. Taskオブジェクト生成とキュー追加
        task = self.task_factory.create_github_task(event_type, payload)
        if task:
            self.task_queue.put(task.get_task_key().to_dict())
            logger.info(f"Queued GitHub {event_type} task: {task.get_task_key()}")
            return {"status": "success", "task_queued": True}
        
        return {"status": "ignored", "reason": "failed to create task"}
    
    async def handle_gitlab_webhook(self, request: Request):
        """GitLab Webhookイベント処理"""
        # GitHubと同様の処理フロー
        # 詳細は省略（GitLab特有の検証ロジック実装）
        pass
    
    def run(self, host: str = "0.0.0.0", port: int = 8000):
        """Webhookサーバー起動"""
        import uvicorn
        uvicorn.run(app, host=host, port=port)
```

#### 4.4.2 webhook/validators.py

```python
"""Webhook署名/トークン検証"""
import hmac
import hashlib
from typing import Optional

class GitHubWebhookValidator:
    def __init__(self, config: dict):
        self.secret = config["webhook"]["github"]["secret"]
    
    def validate_signature(self, payload: bytes, signature: Optional[str]) -> bool:
        """GitHub HMAC-SHA256署名検証"""
        if not signature:
            return False
        
        # "sha256=" プレフィックスを除去
        expected_signature = signature.replace("sha256=", "")
        
        # HMAC-SHA256計算
        mac = hmac.new(
            self.secret.encode("utf-8"),
            msg=payload,
            digestmod=hashlib.sha256
        )
        computed_signature = mac.hexdigest()
        
        # タイミング攻撃耐性のある比較
        return hmac.compare_digest(computed_signature, expected_signature)

class GitLabWebhookValidator:
    def __init__(self, config: dict):
        self.token = config["webhook"]["gitlab"]["token"]
    
    def validate_token(self, request_token: Optional[str]) -> bool:
        """GitLabトークン検証"""
        if not request_token:
            return False
        return hmac.compare_digest(self.token, request_token)
```

#### 4.4.3 webhook/task_factory.py

```python
"""Webhook PayloadからTaskオブジェクトを生成"""
from handlers.task_getter_github import TaskGitHubIssue, TaskGitHubPullRequest
from handlers.task_getter_gitlab import TaskGitLabIssue, TaskGitLabMergeRequest

class WebhookTaskFactory:
    def __init__(self, config: dict):
        self.config = config
    
    def create_github_task(self, event_type: str, payload: dict):
        """GitHub WebhookペイロードからTaskを生成"""
        if event_type == "issues":
            issue = payload["issue"]
            # MCPクライアントは後で設定されるため、ここではNoneまたは遅延設定
            return TaskGitHubIssue(issue, None, None, self.config)
        
        elif event_type == "pull_request":
            pr = payload["pull_request"]
            return TaskGitHubPullRequest(pr, None, None, self.config)
        
        return None
    
    def create_gitlab_task(self, event_type: str, payload: dict):
        """GitLab WebhookペイロードからTaskを生成"""
        if event_type == "Issue Hook":
            issue = payload["object_attributes"]
            return TaskGitLabIssue(issue, None, None, self.config)
        
        elif event_type == "Merge Request Hook":
            mr = payload["object_attributes"]
            return TaskGitLabMergeRequest(mr, None, None, self.config)
        
        return None
```

#### 4.4.4 main.pyの変更

```python
# main.pyに追加
def run_webhook_server(config: dict, task_queue, logger):
    """Webhookサーバーモードで起動"""
    from webhook.server import WebhookServer
    
    logger.info("Starting Webhook Server...")
    
    # Webhook設定の確認
    if not config.get("webhook", {}).get("enabled", False):
        logger.error("Webhook is not enabled in config")
        return
    
    # Webhookサーバー初期化と起動
    webhook_config = config.get("webhook", {})
    server = WebhookServer(config, task_queue)
    
    host = webhook_config.get("server", {}).get("host", "0.0.0.0")
    port = webhook_config.get("server", {}).get("port", 8000)
    
    logger.info(f"Webhook server listening on {host}:{port}")
    server.run(host=host, port=port)

def main():
    # 既存コード...
    
    # 新規: --mode webhook の追加
    parser.add_argument(
        "--mode",
        choices=["producer", "consumer", "webhook"],  # "webhook"を追加
        help="producer: タスク取得のみ, consumer: キューから実行のみ, webhook: Webhookサーバー起動",
    )
    
    # 既存コード...
    
    # 実行モード分岐に追加
    if args.mode == "webhook":
        # Webhookサーバーモード
        run_webhook_server(config, task_queue, logger)
    elif args.mode == "producer":
        # 既存: プロデューサーモード
        # ...
    # ... 以下既存コード
```

### 4.5 Docker構成の変更

#### 4.5.1 docker-compose.ymlへの追加

```yaml
version: '3.6'
services:
  # 既存サービス（変更なし）
  user-config-api:
    # ...既存設定...
  
  rabbitmq:
    # ...既存設定...
  
  # 新規追加: Webhookサーバー
  webhook-server:
    build: .
    container_name: coding-agent-webhook
    command: python -u main.py --mode webhook
    ports:
      - "8000:8000"  # Webhookエンドポイント
    environment:
      - WEBHOOK_ENABLED=true
      - WEBHOOK_SERVER_HOST=0.0.0.0
      - WEBHOOK_SERVER_PORT=8000
      - GITHUB_WEBHOOK_SECRET=${GITHUB_WEBHOOK_SECRET}
      - GITLAB_WEBHOOK_TOKEN=${GITLAB_WEBHOOK_TOKEN}
      - RABBITMQ_HOST=rabbitmq
      - RABBITMQ_PORT=5672
      - USE_RABBITMQ=true
    depends_on:
      - rabbitmq
    restart: unless-stopped
  
  # 新規追加: タスク処理ワーカー
  task-consumer:
    build: .
    container_name: coding-agent-consumer
    command: python -u main.py --mode consumer
    environment:
      - TASK_SOURCE=${TASK_SOURCE:-github}
      - GITHUB_PERSONAL_ACCESS_TOKEN=${GITHUB_PERSONAL_ACCESS_TOKEN}
      - GITLAB_PERSONAL_ACCESS_TOKEN=${GITLAB_PERSONAL_ACCESS_TOKEN}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - RABBITMQ_HOST=rabbitmq
      - RABBITMQ_PORT=5672
      - USE_RABBITMQ=true
    depends_on:
      - rabbitmq
    restart: unless-stopped
```

### 4.6 GitHubでのWebhook設定手順

#### 4.6.1 Webhook設定

1. GitHubリポジトリの **Settings** → **Webhooks** → **Add webhook**
2. 以下を設定:
   - **Payload URL**: `https://your-server.com/webhook/github`
   - **Content type**: `application/json`
   - **Secret**: 環境変数 `GITHUB_WEBHOOK_SECRET` と同じ値
   - **Which events would you like to trigger this webhook?**:
     - ☑ **Issues**
     - ☑ **Pull requests**
   - **Active**: ☑

#### 4.6.2 必要な権限
- Webhookを設定するには、リポジトリの **Admin** 権限が必要

### 4.7 GitLabでのWebhook設定手順

#### 4.7.1 Webhook設定

1. GitLabプロジェクトの **Settings** → **Webhooks** → **Add new webhook**
2. 以下を設定:
   - **URL**: `https://your-server.com/webhook/gitlab`
   - **Secret token**: 環境変数 `GITLAB_WEBHOOK_TOKEN` と同じ値
   - **Trigger**:
     - ☑ **Issues events**
     - ☑ **Merge request events**
   - **Enable SSL verification**: ☑ (推奨)

#### 4.7.2 必要な権限
- Webhookを設定するには、プロジェクトの **Maintainer** 以上の権限が必要

## 5. 実装計画

### 5.1 フェーズ1: 基盤構築（Week 1-2）

#### 5.1.1 タスク
- [ ] `webhook/` ディレクトリとモジュール作成
  - [ ] `webhook/server.py` - FastAPI基本実装
  - [ ] `webhook/validators.py` - 署名検証実装
  - [ ] `webhook/parsers.py` - ペイロードパース実装
  - [ ] `webhook/task_factory.py` - Taskファクトリ実装
- [ ] `config.yaml` へのWebhook設定追加
- [ ] 環境変数の追加
- [ ] `main.py` への `--mode webhook` 追加

#### 5.1.2 成果物
- Webhook受信サーバーの基本実装
- 設定ファイルの更新
- ローカルでのWebhook受信テスト成功

### 5.2 フェーズ2: GitHub統合（Week 3）

#### 5.2.1 タスク
- [ ] GitHub Webhook署名検証の実装
- [ ] GitHub Issues イベント処理
- [ ] GitHub Pull Request イベント処理
- [ ] GitHubでのWebhook設定とテスト
- [ ] 単体テストの作成（`tests/webhook/`）

#### 5.2.2 成果物
- GitHub Webhook完全対応
- 単体テスト完備
- GitHub上でのE2Eテスト成功

### 5.3 フェーズ3: GitLab統合（Week 4）

#### 5.3.1 タスク
- [ ] GitLab Webhookトークン検証の実装
- [ ] GitLab Issues イベント処理
- [ ] GitLab Merge Request イベント処理
- [ ] GitLabでのWebhook設定とテスト
- [ ] 単体テストの作成

#### 5.3.2 成果物
- GitLab Webhook完全対応
- 単体テスト完備
- GitLab上でのE2Eテスト成功

### 5.4 フェーズ4: Docker化と本番対応（Week 5）

#### 5.4.1 タスク
- [ ] `docker-compose.yml` の更新
- [ ] Dockerfile の更新（必要に応じて）
- [ ] HTTPS対応（nginx/Caddyリバースプロキシ）
- [ ] ヘルスチェックエンドポイントの実装
- [ ] ロギングとモニタリングの強化
- [ ] エラーハンドリングの強化

#### 5.4.2 成果物
- 本番環境用Docker構成
- HTTPS対応
- 監視・ロギング機能

### 5.5 フェーズ5: ドキュメント化と移行（Week 6）

#### 5.5.1 タスク
- [ ] README.md の更新（Webhook設定手順追加）
- [ ] 移行ガイドの作成
- [ ] トラブルシューティングガイドの作成
- [ ] 既存ユーザー向け移行手順の文書化
- [ ] 後方互換性の確認

#### 5.5.2 成果物
- 完全なドキュメント
- 移行ガイド
- リリースノート

## 6. 移行戦略

### 6.1 段階的移行アプローチ

#### ステップ1: ハイブリッド運用（推奨）
```
期間: 2-4週間
目的: Webhook方式の安定性確認

┌─────────────────┐     ┌─────────────────┐
│  Webhook Server │     │  Cron (Polling) │
│  (新規)         │     │  (既存)         │
└────────┬────────┘     └────────┬────────┘
         │                       │
         └───────┬───────────────┘
                 v
         ┌───────────────┐
         │  RabbitMQ     │
         └───────┬───────┘
                 v
         ┌───────────────┐
         │  Consumer     │
         └───────────────┘

メリット:
- Webhookが動作しない場合でもポーリングでカバー
- 段階的にWebhook方式への信頼性を確認
- ロールバックが容易
```

#### ステップ2: Webhook完全移行
```
期間: ハイブリッド運用で問題がなければ移行
目的: ポーリング停止、Webhookのみで運用

┌─────────────────┐
│  Webhook Server │
│  (本番運用)     │
└────────┬────────┘
         v
  ┌─────────────┐
  │  RabbitMQ   │
  └──────┬──────┘
         v
  ┌─────────────┐
  │  Consumer   │
  └─────────────┘

実施内容:
- cronジョブの停止
- config.yamlのscheduling設定を無効化（オプション）
- ポーリング関連コードの非推奨化（削除はしない）
```

### 6.2 ロールバック計画

万が一Webhook方式に問題が発生した場合の対処:

1. **即座の対応**:
   - Webhookサーバーコンテナを停止
   - cronジョブを再開（ポーリング方式に戻す）

2. **切り戻し手順**:
   ```bash
   # Webhookサーバー停止
   docker-compose stop webhook-server
   
   # ポーリング再開
   docker-compose up -d producer  # またはcron再開
   ```

3. **データ整合性**:
   - RabbitMQキューは両方式で共通のため、データロスなし
   - 処理中タスクは影響を受けない

### 6.3 移行チェックリスト

#### 移行前の準備
- [ ] Webhook設定のテスト環境での動作確認
- [ ] GitHub/GitLabでのWebhook設定完了
- [ ] Secret/Tokenの安全な管理方法の確立
- [ ] 監視・ログ設定の準備
- [ ] ロールバック手順の文書化

#### 移行実施
- [ ] Webhookサーバーの起動
- [ ] ヘルスチェック確認
- [ ] テストイベントの送信と処理確認
- [ ] ログの確認
- [ ] 1-2週間のハイブリッド運用

#### 移行完了
- [ ] Webhookの安定動作確認（2-4週間）
- [ ] ポーリングcronの停止
- [ ] ドキュメントの更新
- [ ] チーム内への通知

## 7. セキュリティ考慮事項

### 7.1 認証・認可

#### 7.1.1 Webhook署名検証（GitHub）
- **必須**: すべてのGitHub Webhookリクエストの署名を検証
- **実装**: HMAC-SHA256を使用した署名検証
- **Secret管理**: 環境変数で管理、Gitにコミットしない

#### 7.1.2 Webhookトークン検証（GitLab）
- **必須**: すべてのGitLab Webhookリクエストのトークンを検証
- **実装**: Secret Tokenの照合
- **Token管理**: 環境変数で管理、Gitにコミットしない

### 7.2 ネットワークセキュリティ

#### 7.2.1 HTTPS必須化
- 本番環境ではHTTPSを必須とする
- Let's Encryptなどで証明書を取得
- nginxまたはCaddyをリバースプロキシとして使用

#### 7.2.2 IPホワイトリスト（オプション）
- GitHubのIPレンジ: https://api.github.com/meta
- GitLabのIPレンジ: 環境に応じて設定

### 7.3 レート制限

```python
# webhook/server.pyに追加
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/webhook/github")
@limiter.limit("100/minute")  # 1分間に100リクエストまで
async def github_webhook(request: Request):
    # ... 処理 ...
```

### 7.4 入力検証

- すべてのWebhookペイロードを検証
- 不正なJSON形式を拒否
- 必須フィールドの存在確認
- XSS/インジェクション対策

## 8. 監視・ロギング

### 8.1 ロギング

#### 8.1.1 ログレベル
- **INFO**: 正常なWebhook受信とタスク追加
- **WARNING**: 無視されたイベント（フィルタリング）
- **ERROR**: 署名検証失敗、パースエラー
- **DEBUG**: 詳細なデバッグ情報

#### 8.1.2 ログ出力例
```
2024-01-15 10:30:45 INFO [webhook.server] Received GitHub webhook: event=issues, action=labeled
2024-01-15 10:30:45 INFO [webhook.server] Signature validation successful
2024-01-15 10:30:45 INFO [webhook.server] Label matched: coding agent
2024-01-15 10:30:45 INFO [webhook.server] Created task: TaskGitHubIssue(owner=notfolder, repo=coding_agent, issue=123)
2024-01-15 10:30:45 INFO [webhook.server] Task queued successfully
```

### 8.2 メトリクス

#### 8.2.1 収集すべきメトリクス
- Webhook受信数（成功/失敗）
- イベントタイプ別の受信数
- 署名検証失敗数
- タスク生成数
- キュー投入成功/失敗数
- レスポンス時間

#### 8.2.2 監視ダッシュボード（推奨）
- Prometheus + Grafanaの導入を検討
- 基本的なヘルスチェックエンドポイントの実装

```python
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "queue_connected": task_queue.is_connected(),
    }

@app.get("/metrics")
async def metrics():
    return {
        "webhooks_received": metrics_counter["received"],
        "webhooks_processed": metrics_counter["processed"],
        "webhooks_failed": metrics_counter["failed"],
        "tasks_queued": metrics_counter["queued"],
    }
```

## 9. テスト戦略

### 9.1 単体テスト

#### 9.1.1 テスト対象
- `webhook/validators.py`: 署名/トークン検証ロジック
- `webhook/parsers.py`: ペイロードパースロジック
- `webhook/task_factory.py`: Taskオブジェクト生成ロジック

#### 9.1.2 テスト例
```python
# tests/webhook/test_validators.py
import pytest
from webhook.validators import GitHubWebhookValidator

def test_github_signature_validation_success():
    config = {"webhook": {"github": {"secret": "test_secret"}}}
    validator = GitHubWebhookValidator(config)
    
    payload = b'{"action":"labeled"}'
    # 正しい署名を生成
    signature = "sha256=" + generate_signature(payload, "test_secret")
    
    assert validator.validate_signature(payload, signature) is True

def test_github_signature_validation_failure():
    config = {"webhook": {"github": {"secret": "test_secret"}}}
    validator = GitHubWebhookValidator(config)
    
    payload = b'{"action":"labeled"}'
    invalid_signature = "sha256=invalid"
    
    assert validator.validate_signature(payload, invalid_signature) is False
```

### 9.2 統合テスト

#### 9.2.1 ローカルテスト
- ngrokまたはlocaltunnelを使用してローカル環境を公開
- GitHub/GitLabでWebhookを設定
- 実際のラベル付与操作でテスト

#### 9.2.2 モックテスト
```python
# tests/webhook/test_server.py
from fastapi.testclient import TestClient
from webhook.server import app

client = TestClient(app)

def test_github_webhook_labeled_event():
    payload = {
        "action": "labeled",
        "label": {"name": "coding agent"},
        "issue": {...},
    }
    headers = {
        "X-GitHub-Event": "issues",
        "X-Hub-Signature-256": generate_test_signature(payload),
    }
    
    response = client.post("/webhook/github", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "success"
```

### 9.3 E2Eテスト

#### 9.3.1 テストシナリオ
1. GitHubでIssueを作成
2. `coding agent` ラベルを付与
3. Webhook経由でタスクがキューに追加されることを確認
4. Consumerがタスクを処理することを確認
5. Issueに `coding agent processing` ラベルが付与されることを確認

## 10. パフォーマンス考慮事項

### 10.1 想定負荷

- **小規模**: 1日あたり10-100イベント
- **中規模**: 1日あたり100-1000イベント
- **大規模**: 1日あたり1000+イベント

### 10.2 スケーラビリティ

#### 10.2.1 水平スケーリング
```yaml
# docker-compose.ymlでWebhookサーバーを複数起動
services:
  webhook-server:
    # ... 既存設定 ...
    deploy:
      replicas: 3  # 3つのインスタンスを起動
```

#### 10.2.2 ロードバランサー
- nginx/Caddyでロードバランシング
- 複数のWebhookサーバーインスタンス間で負荷分散

### 10.3 最適化

- 非同期処理の活用（FastAPIの`async`/`await`）
- キュー投入の高速化
- 不要なデータベースアクセスの削減

## 11. よくある質問（FAQ）

### Q1: ポーリング方式は完全に廃止されますか？
**A**: いいえ。後方互換性のため、ポーリング方式も維持されます。Webhook方式が推奨されますが、必要に応じてポーリング方式も使用可能です。

### Q2: Webhookサーバーがダウンした場合はどうなりますか？
**A**: ハイブリッド運用期間中はポーリングでカバーされます。完全移行後は、WebhookサーバーのダウンタイムはGitHub/GitLabのリトライ機能に依存します（通常、複数回リトライされます）。

### Q3: ローカル開発環境でWebhookをテストする方法は？
**A**: ngrokやlocaltunnelを使用してローカル環境を公開し、GitHub/GitLabのWebhook URLに設定します。

### Q4: 既存のタスク処理に影響はありますか？
**A**: いいえ。Webhook方式は新しいタスク検出方法を提供するだけで、タスク処理ロジック（`TaskHandler`、`Task`クラス）は変更されません。

### Q5: RabbitMQは必須ですか？
**A**: いいえ。InMemoryQueueも使用可能ですが、本番環境ではRabbitMQの使用を推奨します（耐障害性とスケーラビリティのため）。

## 12. まとめ

### 12.1 主な変更点
1. **新しいコンポーネント**: Webhookサーバー（FastAPI）を追加
2. **新しい実行モード**: `--mode webhook` を追加
3. **設定の拡張**: `config.yaml` にWebhook設定を追加
4. **後方互換性**: ポーリング方式も維持

### 12.2 期待される効果
- **リアルタイム性**: 5分 → 数秒以内に短縮
- **APIレート削減**: ポーリングによるAPI呼び出しが不要
- **スケーラビリティ**: イベント駆動型でスケーラブルな設計
- **効率性**: 必要な時だけ処理が実行される

### 12.3 次のステップ
1. 本仕様書のレビューと承認
2. フェーズ1の実装開始
3. テスト環境での動作確認
4. 段階的な本番展開

---

**ドキュメントバージョン**: 1.0  
**最終更新日**: 2024-01-15  
**作成者**: Coding Agent Team
