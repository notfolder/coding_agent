# ユーザー管理API仕様書（モックアップ版）

## 1. 概要

### 1.1 目的
現在、LLMの呼び出しキー（APIキー）や設定は設定ファイル（config.yaml）に直接記述されている。本仕様は、将来的なマルチユーザー対応に向けて、GitHub/GitLabのユーザー名を基にLLM設定をREST API経由で取得するモックアップサーバーを定義する。

**モックアップの特徴:**
- サーバー側は従来の設定ファイル（config.yaml）を読み込む
- 最小限のコードで実装可能
- Docker内のローカルネットワークで動作（最低限のセキュリティ）
- 詳細ログや監視機能は不要

### 1.2 システムアーキテクチャ

```
[コーディングエージェント]
         ↓
  [REST API リクエスト]
         ↓
  [モックアップAPIサーバー] ← [config.yaml を読み込む]
         ↓
  [LLM設定レスポンス]
         ↓
  [LLMクライアント]
```

## 2. REST API仕様

### 2.1 ベースURL
```
http://user-config-api:8080
```
※ Docker内部のローカルネットワーク用（HTTPのみ）

### 2.2 認証
最低限のセキュリティとして、設定ファイルから読み込んだ固定APIキーによる認証を実施する。

**認証方式:**
- リクエストヘッダーに`X-API-Key`を含める
- APIキーは`config.yaml`の`api_server.api_key`から読み込む
- APIキーが一致しない場合は401エラーを返す

**ヘッダー例:**
```http
X-API-Key: your-secret-api-key
```

### 2.3 エンドポイント

#### 2.3.1 LLM設定取得API

**エンドポイント:**
```
GET /config/{platform}/{username}
```

**パスパラメータ:**
| パラメータ | 説明 |
|----------|------|
| platform | `github` または `gitlab` |
| username | ユーザー名（現在は無視され、config.yamlの内容を返す） |

**リクエスト例:**
```http
GET /config/github/notfolder HTTP/1.1
Host: user-config-api:8080
X-API-Key: your-secret-api-key
```

**レスポンス（成功時）:**
```json
{
  "status": "success",
  "data": {
    "llm": {
      "provider": "openai",
      "function_calling": true,
      "openai": {
        "api_key": "sk-proj-...",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o",
        "max_token": 40960
      },
      "lmstudio": null,
      "ollama": null
    },
    "max_llm_process_num": 1000
  }
}
```

**レスポンス（エラー時）:**
```json
{
  "status": "error",
  "message": "設定ファイルの読み込みに失敗しました"
}
```

**レスポンス（認証エラー時）:**
```json
{
  "status": "error",
  "message": "認証に失敗しました"
}
```
HTTPステータスコード: 401 Unauthorized

#### 2.3.2 ヘルスチェックAPI

**エンドポイント:**
```
GET /health
```

**レスポンス:**
```json
{
  "status": "ok"
}
```

## 3. モックアップサーバー実装

### 3.1 実装方式
- **言語**: Python 3.13+
- **フレームワーク**: Flask（軽量・シンプル）
- **設定読み込み**: YAMLファイル（既存のconfig.yaml）

### 3.2 ディレクトリ構成
```
user_config_api/
├── server.py          # APIサーバー本体
├── config.yaml        # LLM設定ファイル（既存のものをコピー）
├── Dockerfile         # コンテナイメージ
└── requirements.txt   # Python依存関係
```

### 3.3 config.yaml の設定例

APIサーバー用の設定を追加した`config.yaml`の例:

```yaml
# APIサーバー設定（追加）
api_server:
  api_key: "your-secret-api-key-here"  # 固定APIキー

# 既存のLLM設定
llm:
  provider: "openai"
  function_calling: true
  openai:
    api_key: "sk-proj-..."
    base_url: "https://api.openai.com/v1"
    model: "gpt-4o"
    max_token: 40960
  lmstudio: null
  ollama: null

max_llm_process_num: 1000

# その他の既存設定...
```

**注意:** `api_server.api_key`は環境変数で上書き可能にすることを推奨:
```python
API_KEY = os.environ.get("API_SERVER_KEY") or CONFIG.get("api_server", {}).get("api_key", "default-api-key")
```

### 3.4 server.py の実装例

```python
"""ユーザー設定APIモックアップサーバー."""
from flask import Flask, jsonify, request
import yaml
from pathlib import Path

app = Flask(__name__)

# グローバル変数として設定を保持
CONFIG = None
API_KEY = None

def load_config():
    """config.yamlを読み込む."""
    global CONFIG, API_KEY
    config_path = Path("config.yaml")
    if not config_path.exists():
        return None
    
    with config_path.open() as f:
        CONFIG = yaml.safe_load(f)
        # APIキーを設定から取得（設定されていない場合はデフォルト値）
        API_KEY = CONFIG.get("api_server", {}).get("api_key", "default-api-key")
        return CONFIG

def check_api_key():
    """APIキーを検証する."""
    api_key = request.headers.get('X-API-Key')
    if not api_key or api_key != API_KEY:
        return False
    return True

@app.route('/config/<platform>/<username>', methods=['GET'])
def get_user_config(platform, username):
    """ユーザーのLLM設定を取得（モックアップ: config.yamlを返す）."""
    # APIキーの検証
    if not check_api_key():
        return jsonify({
            "status": "error",
            "message": "認証に失敗しました"
        }), 401
    
    config = load_config()
    
    if config is None:
        return jsonify({
            "status": "error",
            "message": "設定ファイルの読み込みに失敗しました"
        }), 500
    
    # モックアップ版: platformとusernameは現在無視し、config.yamlの内容をそのまま返す
    # 将来の実装: configs/{platform}_{username}.yamlから個別設定を読み込む
    response_data = {
        "llm": config.get("llm", {}),
        "max_llm_process_num": config.get("max_llm_process_num", 1000)
    }
    
    return jsonify({
        "status": "success",
        "data": response_data
    })

@app.route('/health', methods=['GET'])
def health_check():
    """ヘルスチェック（認証不要）."""
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    # 起動時に設定を読み込む
    load_config()
    app.run(host='0.0.0.0', port=8080, debug=False)
```

### 3.5 requirements.txt

```
Flask==3.0.0
PyYAML==6.0.1
```

### 3.6 Dockerfile

```dockerfile
FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .
COPY config.yaml .

EXPOSE 8080

CMD ["python", "server.py"]
```

### 3.7 docker-compose.yml への追加

既存の`docker-compose.yml`に以下を追加:

```yaml
  user-config-api:
    build: ./user_config_api
    container_name: user-config-api
    # Docker内部ネットワークのみで使用（外部公開不要）
    # テスト用に外部アクセスが必要な場合のみ、以下のコメントを外す
    # ports:
    #   - "8080:8080"
    networks:
      - coding-agent-network

networks:
  coding-agent-network:
    driver: bridge
```

## 4. クライアント側の統合

### 4.1 main.pyの変更

```python
def load_config(config_file: str = "config.yaml") -> dict[str, Any]:
    """設定ファイルを読み込み、環境変数で上書きする."""
    with Path(config_file).open() as f:
        config = yaml.safe_load(f)
    
    # API経由でLLM設定を取得するかチェック
    use_api = os.environ.get("USE_USER_CONFIG_API", "false").lower() == "true"
    
    if use_api:
        try:
            config = _fetch_config_from_api(config)
        except Exception as e:
            logger.warning(f"API経由の設定取得に失敗、設定ファイルを使用: {e}")
            # フォールバック: 従来通り設定ファイルを使用
    
    # 環境変数による上書き処理
    _override_llm_config(config)
    _override_mcp_config(config)
    _override_rabbitmq_config(config)
    _override_bot_config(config)
    
    return config

def _fetch_config_from_api(config: dict[str, Any]) -> dict[str, Any]:
    """API経由で設定を取得する."""
    import requests
    
    # タスクソースとユーザー名を取得
    task_source = os.environ.get("TASK_SOURCE", "github")
    
    # config.yamlからユーザー名を取得
    if task_source == "github":
        username = config.get("github", {}).get("owner", "")
    elif task_source == "gitlab":
        username = config.get("gitlab", {}).get("owner", "")
    else:
        raise ValueError(f"Unknown task source: {task_source}")
    
    # APIエンドポイントとAPIキー
    api_url = os.environ.get("USER_CONFIG_API_URL", "http://user-config-api:8080")
    api_key = os.environ.get("USER_CONFIG_API_KEY", "")
    
    if not api_key:
        raise ValueError("USER_CONFIG_API_KEY is not set")
    
    url = f"{api_url}/config/{task_source}/{username}"
    
    # APIキーをヘッダーに含めて呼び出し
    headers = {"X-API-Key": api_key}
    response = requests.get(url, headers=headers, timeout=5)
    response.raise_for_status()
    
    data = response.json()
    if data.get("status") == "success":
        # LLM設定を上書き
        config["llm"] = data["data"]["llm"]
        config["max_llm_process_num"] = data["data"]["max_llm_process_num"]
        logger.info(f"API経由でLLM設定を取得: {task_source}:{username}")
    else:
        raise ValueError(f"API returned error: {data.get('message')}")
    
    return config
```

### 4.2 新しい環境変数

```bash
# ユーザー設定API使用フラグ
USE_USER_CONFIG_API=true

# ユーザー設定APIのURL（デフォルト: http://user-config-api:8080）
USER_CONFIG_API_URL=http://user-config-api:8080

# ユーザー設定APIのAPIキー（必須）
USER_CONFIG_API_KEY=your-secret-api-key
```

### 4.3 .envファイルの例

```bash
# 既存の設定
TASK_SOURCE=github
GITHUB_PERSONAL_ACCESS_TOKEN=your_token

# ユーザー設定API設定（オプション）
USE_USER_CONFIG_API=true
USER_CONFIG_API_URL=http://user-config-api:8080
USER_CONFIG_API_KEY=your-secret-api-key
```

## 5. セットアップ手順

### 5.1 モックアップサーバーの作成

```bash
# ディレクトリ作成
mkdir user_config_api
cd user_config_api

# ファイル作成
cat > server.py << 'EOF'
# （上記3.3のserver.pyの内容）
EOF

cat > requirements.txt << 'EOF'
Flask==3.0.0
PyYAML==6.0.1
EOF

cat > Dockerfile << 'EOF'
# （上記3.5のDockerfileの内容）
EOF

# 既存のconfig.yamlをコピー
cp ../config.yaml .

# config.yamlにAPIサーバー設定を追加
cat >> config.yaml << 'EOF'

# APIサーバー設定
api_server:
  api_key: "your-secret-api-key-here"
EOF
```

### 5.2 起動

```bash
# Docker Composeで起動
docker-compose up --build

# または個別に起動
cd user_config_api
docker build -t user-config-api .
docker run -p 8080:8080 user-config-api
```

### 5.3 動作確認

```bash
# ヘルスチェック（認証不要）
curl http://localhost:8080/health

# 設定取得（APIキー必須）
curl -H "X-API-Key: your-secret-api-key" http://localhost:8080/config/github/notfolder

# 期待される出力:
# {"status":"success","data":{"llm":{...},"max_llm_process_num":1000}}

# 認証エラーの確認
curl http://localhost:8080/config/github/notfolder

# 期待される出力:
# {"status":"error","message":"認証に失敗しました"}
```

## 6. テスト

### 6.1 単体テスト

```python
import unittest
import json
from server import app, load_config

class TestUserConfigAPI(unittest.TestCase):
    
    def setUp(self):
        self.client = app.test_client()
        # テスト用に設定を読み込む
        load_config()
    
    def test_health_check(self):
        """ヘルスチェックのテスト（認証不要）."""
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'ok')
    
    def test_get_config_with_valid_api_key(self):
        """正しいAPIキーでの設定取得のテスト."""
        headers = {'X-API-Key': 'your-secret-api-key'}
        response = self.client.get('/config/github/testuser', headers=headers)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        self.assertIn('llm', data['data'])
    
    def test_get_config_without_api_key(self):
        """APIキーなしでの設定取得のテスト（エラー）."""
        response = self.client.get('/config/github/testuser')
        self.assertEqual(response.status_code, 401)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'error')
        self.assertEqual(data['message'], '認証に失敗しました')
    
    def test_get_config_with_invalid_api_key(self):
        """無効なAPIキーでの設定取得のテスト（エラー）."""
        headers = {'X-API-Key': 'invalid-key'}
        response = self.client.get('/config/github/testuser', headers=headers)
        self.assertEqual(response.status_code, 401)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'error')
```

## 7. 将来の拡張

現在はモックアップのため、すべてのユーザーに同じconfig.yamlの内容を返しているが、将来的には以下の拡張が可能:

1. **ユーザーごとの設定ファイル**
   ```python
   config_path = Path(f"configs/{platform}_{username}.yaml")
   ```

2. **データベース連携**
   - SQLiteやPostgreSQLに設定を保存
   - ユーザーごとの設定を管理

3. **認証機能の強化**
   - 動的なAPIトークン管理
   - JWTトークン
   - ユーザーごとの認証

4. **設定の更新API**
   - PUT/POSTエンドポイントで設定を更新

## 8. まとめ

本仕様では、以下の特徴を持つモックアップAPIサーバーを定義した:

- **シンプル**: Flask + YAML、約70行のコード
- **最小限のセキュリティ**: Docker内部ネットワーク、固定APIキー認証
- **既存設定の再利用**: config.yamlをそのまま使用
- **段階的な移行**: 環境変数で切り替え可能
- **将来の拡張性**: ユーザーごとの設定やDB連携に容易に対応可能

このモックアップにより、マルチユーザー対応のアーキテクチャを検証しながら、最小限の実装で機能を実現できる。
