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
  - `POST /webhook/gitlab`: GitLab プロジェクトWebhookイベント受信
  - `POST /webhook/gitlab/system`: GitLab システムフックイベント受信（オプション）
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
    token: "${GITLAB_WEBHOOK_TOKEN}"    # GitLab プロジェクトWebhook Token
    system_hook_token: "${GITLAB_SYSTEM_HOOK_TOKEN}"  # GitLab システムフック Token (オプション)
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
GITLAB_WEBHOOK_TOKEN=your_token_here    # GitLab プロジェクトWebhook Token
GITLAB_SYSTEM_HOOK_TOKEN=your_system_token_here  # GitLab システムフック Token (オプション)
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

**役割**: Webhook受信サーバーの実装（FastAPIを使用）

**主要クラス: WebhookServer**
- **初期化処理**:
  - 設定ファイルからWebhook設定を読み込む
  - タスクキュー（RabbitMQまたはInMemoryQueue）への参照を保持
  - GitHubWebhookValidatorとGitLabWebhookValidatorのインスタンスを生成
  - WebhookTaskFactoryのインスタンスを生成

- **GitHub Webhookイベント処理メソッド**:
  1. HTTPリクエストからボディとペイロード（JSON）を取得
  2. リクエストヘッダーから署名（X-Hub-Signature-256）を取得し、GitHubWebhookValidatorで検証
  3. 署名検証に失敗した場合は401 Unauthorizedエラーを返す
  4. リクエストヘッダーからイベントタイプ（X-GitHub-Event）を取得
  5. イベントタイプが"issues"または"pull_request"でない場合は無視（200 OKを返す）
  6. ペイロードからアクション（action）を取得し、"labeled"でない場合は無視
  7. ペイロードからラベル名を取得し、設定の`bot_label`と一致しない場合は無視
  8. WebhookTaskFactoryを使用してTaskオブジェクトを生成
  9. Taskオブジェクトをタスクキューに追加
  10. 成功を示すレスポンス（200 OK）を返す

- **GitLab Webhookイベント処理メソッド（プロジェクトWebhook）**:
  - GitHub Webhookと同様の処理フローだが、GitLab固有の検証とペイロード構造に対応
  - X-Gitlab-Tokenヘッダーでトークン検証を実施（設定の`gitlab.token`と照合）
  - X-Gitlab-Eventヘッダーでイベントタイプを判定
  - GitLab特有のペイロード構造（object_attributes等）を解析

- **GitLab システムフックイベント処理メソッド（オプション）**:
  - プロジェクトWebhookと同じ処理ロジックを使用
  - X-Gitlab-Tokenヘッダーでトークン検証を実施（設定の`gitlab.system_hook_token`と照合）
  - ペイロード形式はプロジェクトWebhookと互換性があるため、既存のパーサーを再利用
  - エンドポイントを `/webhook/gitlab/system` として分離することで、トークンを別管理

- **サーバー起動メソッド**:
  - 指定されたホストとポートでFastAPIサーバーを起動
  - Uvicornを使用してASGIサーバーとして実行

#### 4.4.2 webhook/validators.py

**役割**: Webhook署名/トークン検証の実装

**GitHubWebhookValidatorクラス**:
- **初期化処理**:
  - 設定ファイルからGitHub Webhook Secretを取得して保持

- **署名検証メソッド**:
  - 受信したペイロード（バイト列）と署名文字列を引数として受け取る
  - 署名が存在しない場合はFalseを返す
  - 署名文字列から"sha256="プレフィックスを除去
  - 保持しているSecretを使用してHMAC-SHA256ハッシュを計算
  - 計算したハッシュと受信した署名を比較（タイミング攻撃耐性のあるhmac.compare_digestを使用）
  - 一致すればTrue、不一致ならFalseを返す

**GitLabWebhookValidatorクラス**:
- **初期化処理**:
  - 設定ファイルからGitLab Webhook Tokenを取得して保持

- **トークン検証メソッド**:
  - 受信したトークン文字列を引数として受け取る
  - トークンが存在しない場合はFalseを返す
  - 保持しているTokenと受信したトークンを比較（タイミング攻撃耐性のあるhmac.compare_digestを使用）
  - 一致すればTrue、不一致ならFalseを返す

#### 4.4.3 webhook/task_factory.py

**役割**: WebhookペイロードからTaskオブジェクトを生成

**WebhookTaskFactoryクラス**:
- **初期化処理**:
  - 設定ファイルを保持（Taskオブジェクトのコンストラクタで使用）

- **GitHub Task生成メソッド**:
  - イベントタイプ（"issues"または"pull_request"）とペイロードを引数として受け取る
  - イベントタイプが"issues"の場合:
    - ペイロードから"issue"オブジェクトを抽出
    - TaskGitHubIssueインスタンスを生成して返す
  - イベントタイプが"pull_request"の場合:
    - ペイロードから"pull_request"オブジェクトを抽出
    - TaskGitHubPullRequestインスタンスを生成して返す
  - 該当しないイベントタイプの場合はNoneを返す
  - 注意: MCPクライアントはTaskオブジェクト生成時点ではNoneを設定し、後で設定する（または遅延初期化）

- **GitLab Task生成メソッド**:
  - イベントタイプ（"Issue Hook"または"Merge Request Hook"）とペイロードを引数として受け取る
  - イベントタイプが"Issue Hook"の場合:
    - ペイロードから"object_attributes"オブジェクトを抽出
    - TaskGitLabIssueインスタンスを生成して返す
  - イベントタイプが"Merge Request Hook"の場合:
    - ペイロードから"object_attributes"オブジェクトを抽出
    - TaskGitLabMergeRequestインスタンスを生成して返す
  - 該当しないイベントタイプの場合はNoneを返す

#### 4.4.4 main.pyの変更

**新規追加: run_webhook_server関数**
- **引数**: 設定辞書、タスクキュー、ロガー
- **処理内容**:
  1. Webhook機能が有効になっているか確認（config["webhook"]["enabled"]）
  2. 有効でない場合はエラーログを出力して終了
  3. WebhookServerインスタンスを生成（設定とタスクキューを渡す）
  4. 設定からホストとポート番号を取得（デフォルト: 0.0.0.0:8000）
  5. WebhookServerのrunメソッドを呼び出してサーバーを起動
  6. 起動メッセージをログに出力

**main関数への変更**:
- **引数パーサーの拡張**:
  - `--mode`オプションに"webhook"を追加
  - 選択肢: ["producer", "consumer", "webhook"]
  - ヘルプメッセージ: "webhook: Webhookサーバー起動"を追加

- **実行モード分岐の追加**:
  - `args.mode == "webhook"`の場合、run_webhook_server関数を呼び出す
  - 既存のproducerモードとconsumerモードは変更なし

### 4.5 Docker構成の変更

#### 4.5.1 docker-compose.ymlへの追加

**新規サービス1: webhook-server**
- **目的**: Webhookイベントを受信し、タスクキューに追加するサーバー
- **設定内容**:
  - コンテナ名: coding-agent-webhook
  - 実行コマンド: `python -u main.py --mode webhook`
  - 公開ポート: 8000番（Webhookエンドポイント用）
  - 環境変数:
    - WEBHOOK_ENABLED=true（Webhook機能を有効化）
    - WEBHOOK_SERVER_HOST=0.0.0.0（全インターフェースでリッスン）
    - WEBHOOK_SERVER_PORT=8000（リッスンポート）
    - GITHUB_WEBHOOK_SECRET: GitHub Webhook Secret（環境変数から取得）
    - GITLAB_WEBHOOK_TOKEN: GitLab Webhook Token（環境変数から取得）
    - RABBITMQ_HOST=rabbitmq（RabbitMQコンテナ名）
    - RABBITMQ_PORT=5672（RabbitMQポート）
    - USE_RABBITMQ=true（RabbitMQ使用を有効化）
  - 依存関係: rabbitmqサービス
  - 再起動ポリシー: unless-stopped（手動停止しない限り自動再起動）

**新規サービス2: task-consumer**
- **目的**: タスクキューからタスクを取得して処理するワーカー
- **設定内容**:
  - コンテナ名: coding-agent-consumer
  - 実行コマンド: `python -u main.py --mode consumer`
  - 公開ポート: なし（内部処理のみ）
  - 環境変数:
    - TASK_SOURCE: "github"または"gitlab"（環境変数から取得、デフォルトはgithub）
    - GITHUB_PERSONAL_ACCESS_TOKEN: GitHub Personal Access Token（環境変数から取得）
    - GITLAB_PERSONAL_ACCESS_TOKEN: GitLab Personal Access Token（環境変数から取得）
    - OPENAI_API_KEY: OpenAI APIキー（環境変数から取得）
    - RABBITMQ_HOST=rabbitmq
    - RABBITMQ_PORT=5672
    - USE_RABBITMQ=true
  - 依存関係: rabbitmqサービス
  - 再起動ポリシー: unless-stopped

**既存サービス**: user-config-api、rabbitmqは変更なし

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

#### 4.7.1 プロジェクトWebhook設定

1. GitLabプロジェクトの **Settings** → **Webhooks** → **Add new webhook**
2. 以下を設定:
   - **URL**: `https://your-server.com/webhook/gitlab`
   - **Secret token**: 環境変数 `GITLAB_WEBHOOK_TOKEN` と同じ値
   - **Trigger**:
     - ☑ **Issues events**
     - ☑ **Merge request events**
   - **Enable SSL verification**: ☑ (推奨)

#### 4.7.2 システムフック設定（オプション）

GitLabインスタンス全体で監視する場合、管理者権限でシステムフックを設定できます：

1. GitLab管理エリア **Admin Area** → **System Hooks** → **Add new hook**
2. 以下を設定:
   - **URL**: `https://your-server.com/webhook/gitlab/system`
   - **Secret token**: 環境変数 `GITLAB_SYSTEM_HOOK_TOKEN` と同じ値
   - **Trigger**:
     - ☑ **Issues events**
     - ☑ **Merge request events**
   - **Enable SSL verification**: ☑ (推奨)

**システムフックとプロジェクトWebhookの違い**:
- **スコープ**: システムフックはGitLabインスタンス全体、プロジェクトWebhookは個別プロジェクトのみ
- **権限**: システムフックは管理者権限が必要、プロジェクトWebhookはMaintainer以上
- **用途**: 複数プロジェクトを一括監視する場合はシステムフック、特定プロジェクトのみの場合はプロジェクトWebhook
- **ペイロード形式**: IssueおよびMerge Requestイベントに関しては、システムフックとプロジェクトWebhookは同じ構造を持つ

**現在の設計での対応状況**:
- ✅ ペイロード処理: IssueとMerge Requestイベントのペイロード構造が同一のため、既存の処理ロジックで対応可能
- ✅ トークン検証: 別途 `GITLAB_SYSTEM_HOOK_TOKEN` を設定することで、システムフック専用エンドポイント `/webhook/gitlab/system` を追加可能
- ✅ イベントフィルタリング: 既存のラベルフィルタ（`coding agent`）により、システムフック経由でも適切なタスクのみを処理
- ✅ プロジェクト識別: ペイロード内の `project_id` により、どのプロジェクトからのイベントかを識別可能

#### 4.7.3 必要な権限
- **プロジェクトWebhook**: プロジェクトの **Maintainer** 以上の権限が必要
- **システムフック**: GitLabインスタンスの **管理者** 権限が必要

#### 4.7.4 システムフック対応のまとめ

**設計上の互換性**:
現在の設計は、GitLabのシステムフックに対応可能です。IssueとMerge Requestイベントに限定すれば、以下の点で完全な互換性が確保されています：

1. **エンドポイント分離**: `/webhook/gitlab/system` として別エンドポイントを設けることで、異なるトークンで認証可能
2. **フィルタリング機構**: 既存のラベルフィルタ（`coding agent`）により、システムフック経由でも適切なイベントのみを処理
3. **スケーラビリティ**: システムフックは複数プロジェクトからのイベントを一元管理できるため、監視対象の拡大に有利

**実装の柔軟性**:
- プロジェクトWebhookとシステムフックは併用可能
- 段階的な移行（プロジェクトWebhook → システムフック）もサポート
- 設定ファイルで `system_hook_token` を設定するだけで有効化

## 5. セキュリティ考慮事項

### 5.1 認証・認可

#### 5.1.1 Webhook署名検証（GitHub）
- **必須**: すべてのGitHub Webhookリクエストの署名を検証
- **実装**: HMAC-SHA256を使用した署名検証
- **Secret管理**: 環境変数で管理、Gitにコミットしない

#### 5.1.2 Webhookトークン検証（GitLab）
- **必須**: すべてのGitLab Webhookリクエストのトークンを検証
- **実装**: Secret Tokenの照合
- **Token管理**: 環境変数で管理、Gitにコミットしない

### 5.2 ネットワークセキュリティ

#### 5.2.1 HTTPS必須化
- 本番環境ではHTTPSを必須とする
- Let's Encryptなどで証明書を取得
- nginxまたはCaddyをリバースプロキシとして使用

#### 5.2.2 IPホワイトリスト（オプション）
- GitHubのIPレンジ: https://api.github.com/meta
- GitLabのIPレンジ: 環境に応じて設定

### 5.3 レート制限

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

### 5.4 入力検証

- すべてのWebhookペイロードを検証
- 不正なJSON形式を拒否
- 必須フィールドの存在確認
- XSS/インジェクション対策

## 6. 監視・ロギング

### 6.1 ロギング

#### 6.1.1 ログレベル
- **INFO**: 正常なWebhook受信とタスク追加
- **WARNING**: 無視されたイベント（フィルタリング）
- **ERROR**: 署名検証失敗、パースエラー
- **DEBUG**: 詳細なデバッグ情報

#### 6.1.2 ログ出力例
```
2024-01-15 10:30:45 INFO [webhook.server] Received GitHub webhook: event=issues, action=labeled
2024-01-15 10:30:45 INFO [webhook.server] Signature validation successful
2024-01-15 10:30:45 INFO [webhook.server] Label matched: coding agent
2024-01-15 10:30:45 INFO [webhook.server] Created task: TaskGitHubIssue(owner=notfolder, repo=coding_agent, issue=123)
2024-01-15 10:30:45 INFO [webhook.server] Task queued successfully
```

## 7. テスト戦略

### 7.1 単体テスト

#### 7.1.1 テスト対象
- `webhook/validators.py`: 署名/トークン検証ロジック
- `webhook/parsers.py`: ペイロードパースロジック
- `webhook/task_factory.py`: Taskオブジェクト生成ロジック

#### 7.1.2 テスト例
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

### 7.2 統合テスト

#### 7.2.1 ローカルテスト
- ngrokまたはlocaltunnelを使用してローカル環境を公開
- GitHub/GitLabでWebhookを設定
- 実際のラベル付与操作でテスト

#### 7.2.2 モックテスト
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

### 7.3 E2Eテスト

#### 7.3.1 テストシナリオ
1. GitHubでIssueを作成
2. `coding agent` ラベルを付与
3. Webhook経由でタスクがキューに追加されることを確認
4. Consumerがタスクを処理することを確認
5. Issueに `coding agent processing` ラベルが付与されることを確認

## 8. パフォーマンス考慮事項

### 8.1 想定負荷

- **小規模**: 1日あたり10-100イベント
- **中規模**: 1日あたり100-1000イベント
- **大規模**: 1日あたり1000+イベント

### 8.2 スケーラビリティ

#### 8.2.1 水平スケーリング
```yaml
# docker-compose.ymlでWebhookサーバーを複数起動
services:
  webhook-server:
    # ... 既存設定 ...
    deploy:
      replicas: 3  # 3つのインスタンスを起動
```

#### 8.2.2 ロードバランサー
- nginx/Caddyでロードバランシング
- 複数のWebhookサーバーインスタンス間で負荷分散

### 8.3 最適化

- 非同期処理の活用（FastAPIの`async`/`await`）
- キュー投入の高速化
- 不要なデータベースアクセスの削減

## 9. まとめ

### 9.1 主な変更点
1. **新しいコンポーネント**: Webhookサーバー（FastAPI）を追加
2. **新しい実行モード**: `--mode webhook` を追加
3. **設定の拡張**: `config.yaml` にWebhook設定を追加
4. **後方互換性**: ポーリング方式も維持

### 9.2 期待される効果
- **リアルタイム性**: 5分 → 数秒以内に短縮
- **APIレート削減**: ポーリングによるAPI呼び出しが不要
- **スケーラビリティ**: イベント駆動型でスケーラブルな設計
- **効率性**: 必要な時だけ処理が実行される

### 9.3 次のステップ
1. 本仕様書のレビューと承認
2. 実装の開始
3. テスト環境での動作確認
4. 段階的な本番展開

---

**ドキュメントバージョン**: 1.0  
**最終更新日**: 2024-01-15  
**作成者**: Coding Agent Team
