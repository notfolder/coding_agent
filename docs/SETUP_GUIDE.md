# Coding Agent コンテナ環境 - 起動手順

## 前提条件
- Docker と Docker Compose がインストール済み
- GitHub Personal Access Token を取得済み

## 起動手順

### 1. 環境変数設定
`.env` ファイルにトークンを設定：
```bash
GITHUB_PERSONAL_ACCESS_TOKEN=your_github_token_here
GITLAB_PERSONAL_ACCESS_TOKEN=your_gitlab_token_here
```

### 2. コンテナ起動
```bash
# 全サービス起動
docker compose --env-file .env up

# または個別起動
docker compose up -d rabbitmq
docker compose --env-file .env up coding-agent
```

### 3. 動作確認
- RabbitMQ管理画面: http://localhost:15672 (guest/guest)
- GitLab: http://localhost:8080
- ログ確認: `./logs/` ディレクトリ

## 主要コンポーネント
- **coding-agent**: Python アプリケーション (MCP クライアント)
- **rabbitmq**: メッセージキューサーバー
- **web**: GitLab CE サーバー
- **MCP サーバー**: GitHub, GitLab, WebFetch

## トラブルシューティング
- GitHub API 401エラー → トークンを確認
- RabbitMQ 接続エラー → サービス起動順序を確認
- MCP サーバーエラー → npm パッケージのインストール状況を確認
