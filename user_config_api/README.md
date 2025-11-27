# User Config API

ユーザー設定API - データベース連携版

## 概要

このAPIサーバーは、SQLAlchemyを使用してデータベースからユーザー固有のLLM設定を提供します。
また、Streamlit管理画面を通じてユーザー管理と設定変更が可能です。

## 機能

- **データベースによるユーザー設定の永続化**: SQLiteを初期実装として採用（PostgreSQL/MySQL等に移行可能）
- **管理者画面（Streamlit）**: ユーザーの追加・編集・削除機能
- **Active Directory認証**: ADサーバーと連携した認証
- **REST API**: コーディングエージェント用の設定取得API
- **暗号化**: APIキー等の機密情報をAES-256-GCMで暗号化保存

## ディレクトリ構成

```
user_config_api/
├── server.py              # FastAPIサーバー（APIエントリポイント）
├── streamlit_app.py       # Streamlitアプリ（管理画面エントリポイント）
├── config.yaml            # 設定ファイル
├── requirements.txt       # Python依存関係
├── Dockerfile             # API用Dockerイメージ
├── Dockerfile.streamlit   # Streamlit用Dockerイメージ
├── data/                  # データディレクトリ
│   └── users.db           # SQLiteデータベース
├── app/                   # 共通アプリケーションコード
│   ├── __init__.py
│   ├── config.py          # 設定読み込み
│   ├── database.py        # SQLAlchemyセッション管理
│   ├── models/            # SQLAlchemyモデル
│   │   ├── base.py
│   │   ├── user.py
│   │   └── user_config.py
│   ├── services/          # ビジネスロジック
│   │   ├── auth_service.py
│   │   └── user_service.py
│   ├── auth/              # 認証関連
│   │   └── ad_client.py
│   ├── utils/             # ユーティリティ
│   │   └── encryption.py
│   └── commands/          # コマンドラインツール
│       └── create_admin.py
├── api/                   # FastAPI関連
│   ├── dependencies.py
│   └── routers/
│       └── config.py
├── streamlit/             # Streamlit管理画面
│   ├── pages/
│   │   ├── 01_dashboard.py
│   │   ├── 02_user_management.py
│   │   └── 03_personal_settings.py
│   ├── components/
│   │   ├── auth.py
│   │   ├── user_form.py
│   │   └── data_table.py
│   └── utils/
│       └── session.py
└── tests/                 # テスト
    └── unit/
        ├── test_encryption.py
        ├── test_user_service.py
        └── test_auth_service.py
```

## セットアップ

### ローカル環境で実行

1. 依存関係のインストール:
   ```bash
   cd user_config_api
   pip install -r requirements.txt
   ```

2. FastAPIサーバーの起動:
   ```bash
   uvicorn server:app --host 0.0.0.0 --port 8080 --reload
   ```

3. Streamlit管理画面の起動（別ターミナル）:
   ```bash
   streamlit run streamlit_app.py --server.port 8501
   ```

4. 初期管理者の作成:
   ```bash
   python -m app.commands.create_admin --username admin --ldap-uid admin --ldap-email admin@example.com
   ```

### Docker Composeで実行

メインディレクトリから:

```bash
# API + Streamlit管理画面を起動
docker-compose up --build user-config-api user-config-web

# テスト用LDAP環境も起動する場合
docker-compose --profile ldap up --build
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
- `username`: ユーザー名

ユーザー固有の設定がある場合はそれを、ない場合はデフォルト設定を返します。

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

| 変数名 | 説明 | 必須 |
|-------|------|------|
| `AD_BIND_PASSWORD` | Active Directoryサービスアカウントのパスワード | 本番環境 |
| `ENCRYPTION_KEY` | データ暗号化キー（32バイト） | 本番環境 |
| `API_SERVER_KEY` | コーディングエージェント用APIキー | Yes |
| `DATABASE_URL` | データベースURL | No (デフォルト: sqlite:///./data/users.db) |
| `USE_MOCK_AD` | モックAD認証を使用（true/false） | No (デフォルト: false) |

## アクセスURL

| サービス | URL | 説明 |
|---------|-----|------|
| Streamlit管理画面 | http://localhost:8501 | ブラウザで管理操作 |
| FastAPI REST API | http://localhost:8080 | コーディングエージェント用API |
| API ドキュメント | http://localhost:8080/docs | Swagger UI |
| LDAP Account Manager | http://localhost:8090 | テスト用LDAP管理（--profile ldap使用時） |

## テスト実行

```bash
cd user_config_api
python -m pytest tests/unit/ -v
```

## セキュリティ

- APIキー等の機密データはAES-256-GCMで暗号化して保存
- 暗号化キーは環境変数から読み込み
- 本番環境ではHTTPS（TLS 1.2以上）を必須
- Active Directory認証でユーザー管理

## 参考資料

- [USER_CONFIG_WEB_SPECIFICATION.md](../USER_CONFIG_WEB_SPECIFICATION.md) - 詳細仕様書
- [TESTING.md](TESTING.md) - 手動テストガイド
