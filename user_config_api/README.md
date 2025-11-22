# User Config API

ユーザー設定API（モックアップ版）

## 概要

このAPIサーバーは、`config.yaml`からLLM設定を読み込み、REST API経由で設定を提供するモックアップサーバーです。将来的なマルチユーザー対応に向けた設計となっています。

## 機能

- **設定の一元管理**: `config.yaml`から設定を読み込み、APIで提供
- **Bearer トークン認証**: APIキーによる認証機能
- **Docker対応**: Docker Composeで簡単にデプロイ可能
- **環境変数サポート**: APIキーを環境変数で上書き可能

## ディレクトリ構成

```
user_config_api/
├── server.py          # FastAPIサーバー本体
├── config.yaml        # LLM設定ファイル（メインのconfig.yamlのコピー）
├── requirements.txt   # Python依存関係
├── Dockerfile         # コンテナイメージ
├── TESTING.md         # 手動テストガイド
└── README.md          # このファイル
```

## セットアップ

### ローカル環境で実行

1. 依存関係のインストール:
   ```bash
   cd user_config_api
   pip install -r requirements.txt
   ```

2. サーバーの起動:
   ```bash
   uvicorn server:app --host 0.0.0.0 --port 8080
   ```

### Docker Composeで実行

メインディレクトリから:

```bash
docker-compose up --build user-config-api
```

## API仕様

### エンドポイント

#### 1. ヘルスチェック（認証不要）

```
GET /health
```

レスポンス例:
```json
{
  "status": "ok"
}
```

#### 2. 設定取得（認証必須）

```
GET /config/{platform}/{username}
```

- `platform`: `github` または `gitlab`
- `username`: ユーザー名（現在はモックなので無視される）

リクエスト例:
```bash
curl -H "Authorization: Bearer your-secret-api-key-here" \
  http://localhost:8080/config/github/notfolder
```

レスポンス例:
```json
{
  "status": "success",
  "data": {
    "llm": {
      "provider": "openai",
      "function_calling": true,
      "openai": {
        "api_key": "sk-...",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o",
        "max_token": 40960
      }
    },
    "system_prompt": "あなたは優秀なコーディングアシスタントです...",
    "max_llm_process_num": 1000
  }
}
```

### 認証

- **認証方式**: Bearer トークン
- **ヘッダー**: `Authorization: Bearer {api_key}`
- **APIキー設定**:
  1. 環境変数 `API_SERVER_KEY`（優先）
  2. `config.yaml`の`api_server.api_key`
  3. デフォルト値

## 環境変数

| 変数名 | 説明 | デフォルト値 |
|-------|------|------------|
| `API_SERVER_KEY` | APIサーバーの認証キー | config.yamlの値 |

## 使用方法（main.pyとの連携）

main.pyでAPI経由の設定読み込みを有効にするには、以下の環境変数を設定します:

```bash
# API経由の設定読み込みを有効化
export USE_USER_CONFIG_API=true

# APIサーバーのURL
export USER_CONFIG_API_URL=http://user-config-api:8080

# APIサーバーの認証キー
export USER_CONFIG_API_KEY=your-secret-api-key-here
```

詳細は`sample_api.env`を参照してください。

## セキュリティ

- Docker内部ネットワークでの使用を想定
- 本番環境では、より強固な認証機構（JWT等）の導入を推奨
- APIキーは環境変数で管理し、ソースコードにコミットしない

## トラブルシューティング

### サーバーが起動しない

- `config.yaml`が存在するか確認
- ポート8080が既に使用されていないか確認
- 依存関係が正しくインストールされているか確認

### 認証エラー

- APIキーが正しく設定されているか確認
- Authorizationヘッダーの形式が正しいか確認（`Bearer {token}`）

## 参考資料

- [TESTING.md](TESTING.md) - 手動テストガイド
- [user_management_api_spec.md](../user_management_api_spec.md) - API仕様書
