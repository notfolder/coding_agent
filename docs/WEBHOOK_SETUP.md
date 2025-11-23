# Webhook実装セットアップガイド

このドキュメントは、Webhook方式でのタスク監視をセットアップする手順を説明します。

## 概要

Webhook方式では、GitHubやGitLabからリアルタイムでイベントを受信し、タスクを処理します。
従来のポーリング方式と比較して、以下のメリットがあります：

- **リアルタイム性**: イベント発生時に即座に処理（5分 → 数秒）
- **APIレート削減**: ポーリング不要でAPI呼び出し回数を削減
- **効率性**: 必要な時だけ処理が実行される

## アーキテクチャ

```
GitHub/GitLab → Webhook Server (port 8000) → RabbitMQ → Task Consumer
```

- **Webhook Server**: FastAPIベースのサーバーでWebhookイベントを受信
- **RabbitMQ**: タスクキューとして使用
- **Task Consumer**: キューからタスクを取得して処理

## セットアップ手順

### 1. 環境変数の設定

`.env`ファイルを作成し、以下の環境変数を設定します：

```bash
# 基本設定
TASK_SOURCE=github  # または gitlab
GITHUB_PERSONAL_ACCESS_TOKEN=your_github_token
GITLAB_PERSONAL_ACCESS_TOKEN=your_gitlab_token
OPENAI_API_KEY=your_openai_api_key

# Webhook設定（新規）
GITHUB_WEBHOOK_SECRET=your_github_webhook_secret
GITLAB_WEBHOOK_TOKEN=your_gitlab_webhook_token
GITLAB_SYSTEM_HOOK_TOKEN=your_gitlab_system_hook_token  # オプション
```

参考：`sample_docker.env`ファイルを参照してください。

### 2. Docker Composeでサービスを起動

```bash
docker-compose up -d webhook-server task-consumer rabbitmq
```

これにより、以下のサービスが起動します：
- `webhook-server`: ポート8000でWebhookイベントを受信
- `task-consumer`: タスクキューから処理
- `rabbitmq`: タスクキューとして動作

### 3. GitHubでWebhook設定

#### 3.1 リポジトリ設定

1. GitHubリポジトリの **Settings** → **Webhooks** → **Add webhook**
2. 以下を設定：
   - **Payload URL**: `https://your-server.com/webhook/github`
   - **Content type**: `application/json`
   - **Secret**: 環境変数`GITHUB_WEBHOOK_SECRET`と同じ値
   - **Which events would you like to trigger this webhook?**:
     - ☑ **Issues**
     - ☑ **Pull requests**
   - **Active**: ☑

#### 3.2 必要な権限
- Webhookを設定するには、リポジトリの **Admin** 権限が必要

### 4. GitLabでWebhook設定

#### 4.1 プロジェクトWebhook（通常の場合）

1. GitLabプロジェクトの **Settings** → **Webhooks** → **Add new webhook**
2. 以下を設定：
   - **URL**: `https://your-server.com/webhook/gitlab`
   - **Secret token**: 環境変数`GITLAB_WEBHOOK_TOKEN`と同じ値
   - **Trigger**:
     - ☑ **Issues events**
     - ☑ **Merge request events**
   - **Enable SSL verification**: ☑ (推奨)

#### 4.2 システムフック（複数プロジェクトを監視する場合・オプション）

GitLabインスタンス全体で監視する場合：

1. GitLab管理エリア **Admin Area** → **System Hooks** → **Add new hook**
2. 以下を設定：
   - **URL**: `https://your-server.com/webhook/gitlab/system`
   - **Secret token**: 環境変数`GITLAB_SYSTEM_HOOK_TOKEN`と同じ値
   - **Trigger**:
     - ☑ **Issues events**
     - ☑ **Merge request events**
   - **Enable SSL verification**: ☑ (推奨)

注意：システムフックは管理者権限が必要です。

### 5. 動作確認

#### 5.1 ヘルスチェック

```bash
curl http://localhost:8000/health
# 期待される応答: {"status":"healthy"}
```

#### 5.2 タスク処理の確認

1. GitHubまたはGitLabでIssueを作成
2. `coding agent`ラベルを追加
3. ログを確認：
   ```bash
   docker-compose logs -f webhook-server
   docker-compose logs -f task-consumer
   ```

期待されるログ出力（webhook-server）:
```
INFO [webhook.server] Received GitHub webhook: event=issues, action=labeled
INFO [webhook.server] Label matched: coding agent
INFO [webhook.server] Task queued successfully
```

## トラブルシューティング

### Webhookが届かない場合

1. **ファイアウォール設定を確認**
   - ポート8000が外部からアクセス可能か確認
   
2. **署名/トークン検証エラー**
   - 環境変数とWebhook設定のSecret/Tokenが一致しているか確認
   - ログに`401 Unauthorized`が表示される場合は検証失敗

3. **イベントが無視される場合**
   - ラベル名が`coding agent`と一致しているか確認
   - ログに`Ignoring`メッセージがある場合はフィルタリングされている

### RabbitMQ接続エラー

```bash
# RabbitMQが起動しているか確認
docker-compose ps rabbitmq

# RabbitMQ管理画面にアクセス
# http://localhost:15672 (guest/guest)
```

### ローカル開発でのテスト

ローカル環境でWebhookをテストするには、ngrokやlocaltunnelを使用：

```bash
# ngrokを使用
ngrok http 8000

# 表示されたURLをGitHub/GitLabのWebhook URLに設定
```

## 本番環境への展開

### HTTPS必須化

本番環境では必ずHTTPSを使用してください：

1. **リバースプロキシの設定（nginxの例）**:

```nginx
server {
    listen 443 ssl;
    server_name your-server.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location /webhook/ {
        proxy_pass http://localhost:8000/webhook/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

2. **Let's Encryptで証明書取得**:
```bash
sudo certbot --nginx -d your-server.com
```

### スケーリング

複数のインスタンスでWebhookサーバーを起動する場合：

```yaml
# docker-compose.yml
webhook-server:
  deploy:
    replicas: 3
```

ロードバランサー（nginx等）で負荷分散を設定してください。

## 後方互換性

ポーリング方式も引き続き使用可能です：

```bash
# ポーリングモードで実行
docker-compose run --rm coding-agent --mode producer
```

## 参考資料

- [Webhook仕様書](./webhook_specification.md)
- [GitHub Webhooksドキュメント](https://docs.github.com/en/developers/webhooks-and-events/webhooks)
- [GitLab Webhooksドキュメント](https://docs.gitlab.com/ee/user/project/integrations/webhooks.html)
