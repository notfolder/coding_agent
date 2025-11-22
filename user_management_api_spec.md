# ユーザー管理とLLM設定API仕様書

## 1. 概要

### 1.1 目的
現在、LLMの呼び出しキー（APIキー）や設定は設定ファイル（config.yaml）に直接記述されており、シングルユーザー環境を前提としている。本仕様は、マルチユーザー環境に対応するため、GitHub/GitLabのユーザー名を基に、各ユーザーのLLM設定をREST API経由で取得する仕組みを定義する。

### 1.2 適用範囲
- LLM設定（APIキー、モデル名、エンドポイント、システムプロンプト等）の取得
- GitHub/GitLabユーザー名によるユーザー識別
- 既存のコーディングエージェントシステムとの統合

### 1.3 用語定義
- **LLM設定**: LLMプロバイダ（OpenAI、LM Studio、Ollama等）への接続情報や動作設定
- **ユーザー識別子**: GitHub/GitLabのユーザー名
- **システムプロンプト**: LLMに送信される基本指示文

## 2. システムアーキテクチャ

### 2.1 現在のアーキテクチャ
```
[コーディングエージェント]
         ↓
   [config.yaml]
         ↓
    [LLM設定取得]
         ↓
   [LLMクライアント]
```

### 2.2 新しいアーキテクチャ
```
[コーディングエージェント]
         ↓
 [ユーザー識別（GitHub/GitLab）]
         ↓
   [REST API リクエスト]
         ↓
 [ユーザー管理APIサーバー]
         ↓
   [ユーザーDB/設定DB]
         ↓
   [LLM設定レスポンス]
         ↓
   [LLMクライアント]
```

## 3. REST API仕様

### 3.1 ベースURL
```
https://api.coding-agent.example.com/v1
```

### 3.2 認証方式
#### 3.2.1 APIキー認証
リクエストヘッダーにAPIキーを含める方式。

**ヘッダー:**
```
Authorization: Bearer <API_TOKEN>
```

**API_TOKEN**: 
- コーディングエージェントシステムに事前に設定されたトークン
- ユーザー管理APIサーバーが検証する

#### 3.2.2 相互TLS認証（オプション）
より高いセキュリティが必要な場合、クライアント証明書による相互TLS認証を使用。

### 3.3 エンドポイント

#### 3.3.1 LLM設定取得API

**エンドポイント:**
```
GET /users/{platform}/{username}/llm-config
```

**パスパラメータ:**
| パラメータ | 型 | 必須 | 説明 |
|----------|-----|------|------|
| platform | string | ✓ | プラットフォーム名（`github` または `gitlab`） |
| username | string | ✓ | ユーザー名 |

**クエリパラメータ:**
| パラメータ | 型 | 必須 | 説明 |
|----------|-----|------|------|
| include_system_prompt | boolean | | システムプロンプトを含めるか（デフォルト: true） |

**リクエスト例:**
```http
GET /users/github/notfolder/llm-config HTTP/1.1
Host: api.coding-agent.example.com
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**レスポンス（成功時）:**
```json
{
  "status": "success",
  "data": {
    "user_id": "github:notfolder",
    "platform": "github",
    "username": "notfolder",
    "llm_config": {
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
    "system_prompt": "あなたは優秀なコーディングアシスタントです...",
    "max_llm_process_num": 1000,
    "created_at": "2025-01-01T00:00:00Z",
    "updated_at": "2025-11-22T00:00:00Z"
  }
}
```

**レスポンスフィールド:**
| フィールド | 型 | 説明 |
|----------|-----|------|
| status | string | レスポンスステータス（`success` / `error`） |
| data.user_id | string | ユーザー一意識別子 |
| data.platform | string | プラットフォーム（`github` / `gitlab`） |
| data.username | string | ユーザー名 |
| data.llm_config | object | LLM設定オブジェクト |
| data.llm_config.provider | string | LLMプロバイダ（`openai` / `lmstudio` / `ollama`） |
| data.llm_config.function_calling | boolean | 関数呼び出し機能の有効/無効 |
| data.llm_config.openai | object/null | OpenAI設定（使用時のみ） |
| data.llm_config.lmstudio | object/null | LM Studio設定（使用時のみ） |
| data.llm_config.ollama | object/null | Ollama設定（使用時のみ） |
| data.system_prompt | string | システムプロンプト |
| data.max_llm_process_num | integer | LLM処理の最大反復回数 |
| data.created_at | string | 設定作成日時（ISO 8601形式） |
| data.updated_at | string | 設定更新日時（ISO 8601形式） |

**LLMプロバイダ別設定:**

*OpenAI設定:*
```json
{
  "api_key": "sk-proj-...",
  "base_url": "https://api.openai.com/v1",
  "model": "gpt-4o",
  "max_token": 40960
}
```

*LM Studio設定:*
```json
{
  "base_url": "localhost:1234",
  "context_length": 32768,
  "model": "qwen3-30b-a3b-mlx"
}
```

*Ollama設定:*
```json
{
  "endpoint": "http://localhost:11434",
  "model": "qwen3-30b-a3b-mlx",
  "max_token": 32768
}
```

**エラーレスポンス:**

*ユーザーが見つからない場合（404）:*
```json
{
  "status": "error",
  "error": {
    "code": "USER_NOT_FOUND",
    "message": "User 'github:notfolder' not found",
    "details": {
      "platform": "github",
      "username": "notfolder"
    }
  }
}
```

*認証エラー（401）:*
```json
{
  "status": "error",
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Invalid or missing API token"
  }
}
```

*設定未登録エラー（404）:*
```json
{
  "status": "error",
  "error": {
    "code": "CONFIG_NOT_FOUND",
    "message": "LLM configuration not found for user 'github:notfolder'",
    "details": {
      "platform": "github",
      "username": "notfolder"
    }
  }
}
```

*サーバーエラー（500）:*
```json
{
  "status": "error",
  "error": {
    "code": "INTERNAL_SERVER_ERROR",
    "message": "An unexpected error occurred"
  }
}
```

#### 3.3.2 ユーザー設定の存在確認API

**エンドポイント:**
```
HEAD /users/{platform}/{username}/llm-config
```

**説明:**
ユーザーのLLM設定が存在するかを効率的に確認する。

**レスポンス:**
- 200 OK: 設定が存在する
- 404 Not Found: 設定が存在しない
- 401 Unauthorized: 認証エラー

#### 3.3.3 複数ユーザーの設定取得API（オプション）

**エンドポイント:**
```
POST /users/llm-configs/batch
```

**リクエストボディ:**
```json
{
  "users": [
    {"platform": "github", "username": "user1"},
    {"platform": "gitlab", "username": "user2"}
  ],
  "include_system_prompt": true
}
```

**レスポンス:**
```json
{
  "status": "success",
  "data": {
    "configs": [
      {
        "user_id": "github:user1",
        "llm_config": { /* ... */ }
      },
      {
        "user_id": "gitlab:user2",
        "llm_config": { /* ... */ }
      }
    ],
    "not_found": []
  }
}
```

### 3.4 HTTPステータスコード

| ステータスコード | 説明 |
|----------------|------|
| 200 OK | リクエスト成功 |
| 400 Bad Request | リクエストパラメータが不正 |
| 401 Unauthorized | 認証失敗 |
| 403 Forbidden | アクセス権限なし |
| 404 Not Found | ユーザーまたは設定が見つからない |
| 429 Too Many Requests | レート制限超過 |
| 500 Internal Server Error | サーバー内部エラー |
| 503 Service Unavailable | サービス一時停止中 |

### 3.5 レート制限
APIの過剰な使用を防ぐため、レート制限を設定する。

**制限:**
- 1分あたり60リクエスト
- 1時間あたり1000リクエスト

**レスポンスヘッダー:**
```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 55
X-RateLimit-Reset: 1700000000
```

**制限超過時:**
```json
{
  "status": "error",
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Rate limit exceeded. Please try again later.",
    "retry_after": 30
  }
}
```

## 4. データモデル

### 4.1 ユーザー設定データモデル

```typescript
interface UserLLMConfig {
  user_id: string;           // "platform:username" 形式
  platform: "github" | "gitlab";
  username: string;
  llm_config: LLMConfig;
  system_prompt: string;
  max_llm_process_num: number;
  created_at: string;        // ISO 8601
  updated_at: string;        // ISO 8601
}

interface LLMConfig {
  provider: "openai" | "lmstudio" | "ollama";
  function_calling: boolean;
  openai?: OpenAIConfig;
  lmstudio?: LMStudioConfig;
  ollama?: OllamaConfig;
}

interface OpenAIConfig {
  api_key: string;
  base_url: string;
  model: string;
  max_token: number;
}

interface LMStudioConfig {
  base_url: string;
  context_length: number;
  model: string;
}

interface OllamaConfig {
  endpoint: string;
  model: string;
  max_token: number;
}
```

### 4.2 データベーススキーマ例

**usersテーブル:**
```sql
CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  user_id VARCHAR(255) UNIQUE NOT NULL,  -- "platform:username"
  platform VARCHAR(50) NOT NULL,
  username VARCHAR(255) NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(platform, username)
);
```

**llm_configurationsテーブル:**
```sql
CREATE TABLE llm_configurations (
  id SERIAL PRIMARY KEY,
  user_id VARCHAR(255) REFERENCES users(user_id) ON DELETE CASCADE,
  provider VARCHAR(50) NOT NULL,
  function_calling BOOLEAN DEFAULT TRUE,
  config_json JSONB NOT NULL,  -- プロバイダ固有の設定
  system_prompt TEXT,
  max_llm_process_num INTEGER DEFAULT 1000,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(user_id)
);
```

## 5. セキュリティ仕様

### 5.1 APIキーの保護
- APIキーはハッシュ化してデータベースに保存
- 転送時はTLS/SSL暗号化を必須とする
- レスポンスでAPIキーを返す際は、マスキングオプションを提供（例: `sk-proj-****...****`）

### 5.2 アクセス制御
- APIトークンは環境変数または安全なシークレット管理システム（AWS Secrets Manager、HashiCorp Vault等）に保存
- 定期的なトークンローテーション

### 5.3 監査ログ
- すべてのAPI呼び出しをログに記録
- ユーザー、タイムスタンプ、アクション、IPアドレスを記録

### 5.4 データ暗号化
- データベース内のAPIキーは暗号化して保存
- 通信はHTTPS（TLS 1.2以上）を使用

## 6. 既存コードとの統合

### 6.1 main.pyの変更

**現在の実装:**
```python
def load_config(config_file: str = "config.yaml") -> dict[str, Any]:
    with Path(config_file).open() as f:
        config = yaml.safe_load(f)
    
    _override_llm_config(config)
    # ...
    return config
```

**新しい実装:**
```python
def load_config(config_file: str = "config.yaml") -> dict[str, Any]:
    with Path(config_file).open() as f:
        config = yaml.safe_load(f)
    
    # ユーザー管理API経由でLLM設定を取得
    if os.environ.get("USE_USER_MANAGEMENT_API", "false").lower() == "true":
        task_source = os.environ.get("TASK_SOURCE", "github")
        username = _get_username_from_task_source(task_source, config)
        llm_config = _fetch_llm_config_from_api(task_source, username)
        config["llm"] = llm_config["llm_config"]
        # システムプロンプトも上書き可能
        if "system_prompt" in llm_config:
            config["system_prompt"] = llm_config["system_prompt"]
        if "max_llm_process_num" in llm_config:
            config["max_llm_process_num"] = llm_config["max_llm_process_num"]
    else:
        # 従来通り環境変数で上書き
        _override_llm_config(config)
    
    _override_mcp_config(config)
    _override_rabbitmq_config(config)
    _override_bot_config(config)
    
    return config

def _get_username_from_task_source(task_source: str, config: dict[str, Any]) -> str:
    """タスクソースからユーザー名を取得する."""
    if task_source == "github":
        return config.get("github", {}).get("owner", "")
    elif task_source == "gitlab":
        return config.get("gitlab", {}).get("owner", "")
    else:
        raise ValueError(f"Unknown task source: {task_source}")

def _fetch_llm_config_from_api(platform: str, username: str) -> dict[str, Any]:
    """ユーザー管理APIからLLM設定を取得する."""
    import requests
    
    api_base_url = os.environ.get("USER_MANAGEMENT_API_URL", "https://api.coding-agent.example.com/v1")
    api_token = os.environ.get("USER_MANAGEMENT_API_TOKEN")
    
    if not api_token:
        raise ValueError("USER_MANAGEMENT_API_TOKEN is not set")
    
    url = f"{api_base_url}/users/{platform}/{username}/llm-config"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }
    
    response = requests.get(url, headers=headers, timeout=10)
    
    if response.status_code == 200:
        return response.json()["data"]
    elif response.status_code == 404:
        raise ValueError(f"LLM config not found for user {platform}:{username}")
    elif response.status_code == 401:
        raise ValueError("API authentication failed")
    else:
        raise ValueError(f"API request failed with status {response.status_code}: {response.text}")
```

### 6.2 新しい環境変数

```bash
# ユーザー管理API使用フラグ
USE_USER_MANAGEMENT_API=true

# ユーザー管理APIのベースURL
USER_MANAGEMENT_API_URL=https://api.coding-agent.example.com/v1

# ユーザー管理APIの認証トークン
USER_MANAGEMENT_API_TOKEN=your_api_token_here

# タスクソース（既存）
TASK_SOURCE=github
```

### 6.3 フォールバック戦略

API呼び出しが失敗した場合のフォールバック処理を実装する。

```python
def _fetch_llm_config_from_api(platform: str, username: str) -> dict[str, Any]:
    try:
        # API呼び出し処理
        # ...
    except Exception as e:
        logger.warning(f"Failed to fetch LLM config from API: {e}")
        
        # フォールバック: 環境変数から設定を読み込む
        fallback_config = _build_fallback_llm_config()
        return {"llm_config": fallback_config}

def _build_fallback_llm_config() -> dict[str, Any]:
    """環境変数からフォールバック用のLLM設定を構築する."""
    provider = os.environ.get("LLM_PROVIDER", "openai")
    config = {
        "provider": provider,
        "function_calling": os.environ.get("FUNCTION_CALLING", "true").lower() == "true"
    }
    
    if provider == "openai":
        config["openai"] = {
            "api_key": os.environ.get("OPENAI_API_KEY", ""),
            "base_url": os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            "model": os.environ.get("OPENAI_MODEL", "gpt-4o"),
            "max_token": int(os.environ.get("OPENAI_MAX_TOKEN", "40960"))
        }
    # ... 他のプロバイダも同様
    
    return config
```

### 6.4 キャッシング戦略

API呼び出しを減らすため、取得した設定をキャッシュする。

```python
import time
from typing import Optional

class LLMConfigCache:
    def __init__(self, ttl: int = 3600):
        self.cache: dict[str, tuple[dict, float]] = {}
        self.ttl = ttl  # Time to live in seconds
    
    def get(self, key: str) -> Optional[dict]:
        if key in self.cache:
            config, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl:
                return config
            else:
                del self.cache[key]
        return None
    
    def set(self, key: str, config: dict) -> None:
        self.cache[key] = (config, time.time())
    
    def clear(self) -> None:
        self.cache.clear()

# グローバルキャッシュインスタンス
_llm_config_cache = LLMConfigCache(ttl=3600)  # 1時間キャッシュ

def _fetch_llm_config_from_api(platform: str, username: str) -> dict[str, Any]:
    cache_key = f"{platform}:{username}"
    
    # キャッシュチェック
    cached_config = _llm_config_cache.get(cache_key)
    if cached_config:
        logger.info(f"Using cached LLM config for {cache_key}")
        return cached_config
    
    # API呼び出し
    # ...
    
    # キャッシュに保存
    _llm_config_cache.set(cache_key, config_data)
    
    return config_data
```

## 7. エラーハンドリング

### 7.1 エラーコード一覧

| エラーコード | HTTPステータス | 説明 |
|------------|---------------|------|
| USER_NOT_FOUND | 404 | ユーザーが見つからない |
| CONFIG_NOT_FOUND | 404 | LLM設定が見つからない |
| INVALID_PLATFORM | 400 | 無効なプラットフォーム名 |
| INVALID_USERNAME | 400 | 無効なユーザー名 |
| UNAUTHORIZED | 401 | 認証失敗 |
| FORBIDDEN | 403 | アクセス権限なし |
| RATE_LIMIT_EXCEEDED | 429 | レート制限超過 |
| INTERNAL_SERVER_ERROR | 500 | サーバー内部エラー |
| SERVICE_UNAVAILABLE | 503 | サービス停止中 |

### 7.2 クライアント側エラーハンドリング

```python
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class UserManagementAPIError(Exception):
    """ユーザー管理API関連のエラー."""
    pass

def _fetch_llm_config_from_api(
    platform: str, 
    username: str,
    retry_count: int = 3
) -> dict[str, Any]:
    """ユーザー管理APIからLLM設定を取得する（リトライ機能付き）."""
    import requests
    from requests.adapters import HTTPAdapter
    from requests.packages.urllib3.util.retry import Retry
    
    api_base_url = os.environ.get("USER_MANAGEMENT_API_URL")
    api_token = os.environ.get("USER_MANAGEMENT_API_TOKEN")
    
    if not api_base_url or not api_token:
        raise UserManagementAPIError("API configuration is incomplete")
    
    # リトライ設定
    retry_strategy = Retry(
        total=retry_count,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    
    url = f"{api_base_url}/users/{platform}/{username}/llm-config"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }
    
    try:
        response = session.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        if data.get("status") == "success":
            logger.info(f"Successfully fetched LLM config for {platform}:{username}")
            return data["data"]
        else:
            error_info = data.get("error", {})
            raise UserManagementAPIError(
                f"API returned error: {error_info.get('message', 'Unknown error')}"
            )
    
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            logger.error(f"LLM config not found for {platform}:{username}")
            raise UserManagementAPIError(f"Config not found for {platform}:{username}") from e
        elif e.response.status_code == 401:
            logger.error("API authentication failed")
            raise UserManagementAPIError("Authentication failed") from e
        else:
            logger.error(f"HTTP error: {e}")
            raise UserManagementAPIError(f"HTTP error: {e}") from e
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error while calling API: {e}")
        raise UserManagementAPIError(f"Network error: {e}") from e
```

## 8. テスト仕様

### 8.1 単体テスト

```python
import unittest
from unittest.mock import patch, Mock
import main

class TestUserManagementAPIIntegration(unittest.TestCase):
    
    @patch('main.requests.get')
    def test_fetch_llm_config_success(self, mock_get):
        """正常系：LLM設定の取得成功"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "user_id": "github:testuser",
                "llm_config": {
                    "provider": "openai",
                    "openai": {
                        "api_key": "sk-test",
                        "model": "gpt-4o"
                    }
                }
            }
        }
        mock_get.return_value = mock_response
        
        result = main._fetch_llm_config_from_api("github", "testuser")
        
        self.assertEqual(result["llm_config"]["provider"], "openai")
        self.assertEqual(result["llm_config"]["openai"]["api_key"], "sk-test")
    
    @patch('main.requests.get')
    def test_fetch_llm_config_user_not_found(self, mock_get):
        """異常系：ユーザーが見つからない"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        with self.assertRaises(ValueError):
            main._fetch_llm_config_from_api("github", "nonexistent")
    
    @patch('main.requests.get')
    def test_fetch_llm_config_unauthorized(self, mock_get):
        """異常系：認証エラー"""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response
        
        with self.assertRaises(ValueError):
            main._fetch_llm_config_from_api("github", "testuser")
```

### 8.2 統合テスト

```python
import unittest
import os

class TestUserManagementAPIIntegration(unittest.TestCase):
    
    def setUp(self):
        os.environ["USE_USER_MANAGEMENT_API"] = "true"
        os.environ["USER_MANAGEMENT_API_URL"] = "https://api.test.example.com/v1"
        os.environ["USER_MANAGEMENT_API_TOKEN"] = "test_token"
        os.environ["TASK_SOURCE"] = "github"
    
    def tearDown(self):
        # クリーンアップ
        del os.environ["USE_USER_MANAGEMENT_API"]
        del os.environ["USER_MANAGEMENT_API_URL"]
        del os.environ["USER_MANAGEMENT_API_TOKEN"]
    
    @patch('main._fetch_llm_config_from_api')
    def test_load_config_with_api(self, mock_fetch):
        """API経由での設定読み込み"""
        mock_fetch.return_value = {
            "llm_config": {
                "provider": "openai",
                "openai": {"api_key": "sk-test", "model": "gpt-4o"}
            },
            "system_prompt": "Test prompt",
            "max_llm_process_num": 500
        }
        
        config = main.load_config("config.yaml")
        
        self.assertEqual(config["llm"]["provider"], "openai")
        self.assertEqual(config["system_prompt"], "Test prompt")
        self.assertEqual(config["max_llm_process_num"], 500)
```

### 8.3 負荷テスト

APIサーバーのレート制限とスケーラビリティを検証。

```python
import concurrent.futures
import time

def load_test_api():
    """負荷テスト: 1分間に100リクエスト"""
    results = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [
            executor.submit(_fetch_llm_config_from_api, "github", f"user{i}")
            for i in range(100)
        ]
        
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                results.append(("success", result))
            except Exception as e:
                results.append(("error", str(e)))
    
    success_count = sum(1 for r in results if r[0] == "success")
    error_count = sum(1 for r in results if r[0] == "error")
    
    print(f"Success: {success_count}, Error: {error_count}")
```

## 9. デプロイメント

### 9.1 APIサーバーの実装技術スタック（推奨）

- **言語**: Python 3.11+
- **フレームワーク**: FastAPI（高性能、自動APIドキュメント生成）
- **データベース**: PostgreSQL（JSONBサポート）
- **キャッシュ**: Redis（高速キャッシング）
- **認証**: JWT（JSON Web Tokens）
- **デプロイ**: Docker + Kubernetes / AWS ECS / Google Cloud Run

### 9.2 APIサーバー実装例（FastAPI）

```python
from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel
from typing import Optional, Literal
import os
import jwt

app = FastAPI(title="User Management API", version="1.0.0")

# データモデル
class LLMConfigResponse(BaseModel):
    status: str
    data: dict

class ErrorResponse(BaseModel):
    status: str
    error: dict

# 認証
def verify_token(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    
    token = authorization.replace("Bearer ", "")
    expected_token = os.environ.get("API_TOKEN")
    
    if token != expected_token:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    return token

# エンドポイント
@app.get("/users/{platform}/{username}/llm-config", response_model=LLMConfigResponse)
async def get_llm_config(
    platform: Literal["github", "gitlab"],
    username: str,
    include_system_prompt: bool = True,
    token: str = Depends(verify_token)
):
    """ユーザーのLLM設定を取得"""
    
    # データベースから設定を取得（実装例）
    config = await fetch_config_from_db(platform, username)
    
    if not config:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "CONFIG_NOT_FOUND",
                "message": f"LLM configuration not found for user '{platform}:{username}'"
            }
        )
    
    response_data = {
        "user_id": f"{platform}:{username}",
        "platform": platform,
        "username": username,
        "llm_config": config["llm_config"],
        "max_llm_process_num": config.get("max_llm_process_num", 1000),
        "created_at": config["created_at"],
        "updated_at": config["updated_at"]
    }
    
    if include_system_prompt:
        response_data["system_prompt"] = config.get("system_prompt", "")
    
    return {"status": "success", "data": response_data}

@app.head("/users/{platform}/{username}/llm-config")
async def check_llm_config_exists(
    platform: Literal["github", "gitlab"],
    username: str,
    token: str = Depends(verify_token)
):
    """設定の存在確認"""
    config = await fetch_config_from_db(platform, username)
    
    if not config:
        raise HTTPException(status_code=404)
    
    return {}

# ヘルスチェック
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

async def fetch_config_from_db(platform: str, username: str):
    """データベースから設定を取得（実装は省略）"""
    # ここでデータベースアクセス処理を実装
    pass
```

### 9.3 Docker Compose例

```yaml
version: '3.8'

services:
  api:
    build: ./user-management-api
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:password@db:5432/user_management
      - REDIS_URL=redis://redis:6379/0
      - API_TOKEN=${API_TOKEN}
    depends_on:
      - db
      - redis
  
  db:
    image: postgres:15
    environment:
      - POSTGRES_DB=user_management
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=password
    volumes:
      - postgres_data:/var/lib/postgresql/data
  
  redis:
    image: redis:7
    volumes:
      - redis_data:/data

volumes:
  postgres_data:
  redis_data:
```

## 10. 移行計画

### 10.1 段階的移行

**フェーズ1: 準備（1-2週間）**
- APIサーバーの実装と単体テスト
- データベーススキーマの設計と作成
- 既存ユーザーデータの移行スクリプト作成

**フェーズ2: パイロット運用（2-3週間）**
- テスト環境でのAPI稼働
- 一部のユーザーでのパイロット運用
- パフォーマンスとセキュリティの検証

**フェーズ3: 本番移行（1週間）**
- 本番環境へのデプロイ
- 段階的なユーザー移行
- モニタリングとログ監視

**フェーズ4: 完全移行（1週間）**
- 全ユーザーのAPI経由での設定取得に切り替え
- 旧設定ファイルベースの仕組みを非推奨化

### 10.2 後方互換性

移行期間中、設定ファイルとAPI両方をサポートする。

```python
def load_config(config_file: str = "config.yaml") -> dict[str, Any]:
    with Path(config_file).open() as f:
        config = yaml.safe_load(f)
    
    # 環境変数でAPI使用を判定
    use_api = os.environ.get("USE_USER_MANAGEMENT_API", "false").lower() == "true"
    
    if use_api:
        try:
            # API経由で設定取得
            task_source = os.environ.get("TASK_SOURCE", "github")
            username = _get_username_from_task_source(task_source, config)
            llm_config = _fetch_llm_config_from_api(task_source, username)
            config["llm"] = llm_config["llm_config"]
        except Exception as e:
            logger.warning(f"Failed to fetch config from API, falling back to file: {e}")
            # フォールバック: 従来の設定ファイル読み込み
            _override_llm_config(config)
    else:
        # 従来通りの設定ファイル読み込み
        _override_llm_config(config)
    
    return config
```

## 11. 監視とロギング

### 11.1 APIサーバー監視

**メトリクス:**
- リクエスト数（成功/失敗）
- レスポンスタイム（平均、P95、P99）
- エラー率
- レート制限ヒット数

**ツール:**
- Prometheus（メトリクス収集）
- Grafana（可視化）
- AlertManager（アラート）

### 11.2 ログ形式

**アクセスログ:**
```json
{
  "timestamp": "2025-11-22T01:15:28Z",
  "method": "GET",
  "path": "/users/github/notfolder/llm-config",
  "status": 200,
  "response_time_ms": 45,
  "user_agent": "CodingAgent/1.0",
  "ip_address": "192.168.1.1"
}
```

**エラーログ:**
```json
{
  "timestamp": "2025-11-22T01:15:28Z",
  "level": "ERROR",
  "message": "User not found",
  "error_code": "USER_NOT_FOUND",
  "platform": "github",
  "username": "notfolder",
  "stack_trace": "..."
}
```

## 12. ドキュメント

### 12.1 API ドキュメント

FastAPIの自動ドキュメント生成機能を利用:
- OpenAPI/Swagger UI: `https://api.coding-agent.example.com/docs`
- ReDoc: `https://api.coding-agent.example.com/redoc`

### 12.2 ユーザーガイド

エンドユーザー向けに以下のドキュメントを提供:
- API利用開始ガイド
- 認証トークンの取得方法
- LLM設定の登録・更新方法
- トラブルシューティングガイド

## 13. まとめ

本仕様書では、既存のシングルユーザーベースのコーディングエージェントシステムを、マルチユーザー環境に対応させるためのREST API設計を提案した。

**主要なポイント:**
1. **RESTful API設計**: GitHub/GitLabユーザー名を基にLLM設定を取得
2. **セキュリティ**: APIトークン認証、TLS暗号化、APIキーの安全な管理
3. **既存システムとの統合**: 環境変数による切り替え、フォールバック機能
4. **スケーラビリティ**: キャッシング、レート制限、負荷分散対応
5. **段階的移行**: 後方互換性を保ちながらの段階的な移行計画

この仕様に基づいてAPIサーバーを実装することで、複数ユーザーが独自のLLM設定を管理できるようになり、システムの拡張性とセキュリティが向上する。
