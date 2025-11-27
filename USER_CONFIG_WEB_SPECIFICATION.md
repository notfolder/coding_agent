# ユーザーコンフィグWeb仕様書

## 1. 概要

### 1.1 目的

本仕様書は、LLMへのAPIキーやシステムプロンプトをユーザーごとに上書きできる「ユーザーコンフィグWeb」の詳細設計を定義します。既存のuser_config_apiを拡張し、以下の機能を実現します。

### 1.2 主要機能

1. **データベースによるユーザー設定の永続化**
   - SQLAlchemyを使用してデータベースアクセスを抽象化
   - SQLiteを初期実装として採用
   - 将来的なデータベース変更（PostgreSQL、MySQL等）に対応可能

2. **管理者画面**
   - ユーザーの追加・削除・編集機能
   - ユーザー一覧表示

3. **Active Directory認証**
   - Active Directoryサーバーと連携した認証
   - GitHub/GitLabユーザー名との紐付け（ADメールアドレスの@以前をユーザー名として使用）

### 1.3 技術スタック

**フロントエンド（管理画面）:**
- **Streamlit**: Python製のWebアプリケーションフレームワーク
  - シンプルなPythonコードでUIを構築可能
  - 迅速なプロトタイピングと開発が可能
  - セッション状態管理機能を内蔵

**バックエンド（API）:**
- **FastAPI**: 既存のuser_config_apiを拡張
  - コーディングエージェントからの設定取得用API
  - Streamlit管理画面からも呼び出し可能

**データベース:**
- **SQLAlchemy**: PythonのORMライブラリ
  - データベース抽象化により将来のDB変更に対応
  - SQLite（初期実装）からPostgreSQL/MySQL等への移行が容易

### 1.4 システムアーキテクチャ概要

```
[管理者/ユーザー（ブラウザ）]
            |
    [Streamlit管理画面]
            |
[コーディングエージェント]  <-->  [FastAPI（REST API）]
                                         |
                              [Active Directory]    [データベース（SQLite）]
```

**2つのサーバー構成:**
1. **Streamlit管理画面サーバー（ポート8501）**: ブラウザからの管理操作用
2. **FastAPIサーバー（ポート8080）**: コーディングエージェント・API呼び出し用

## 2. データベース設計

### 2.1 設計方針

SQLAlchemyを使用してデータベースアクセスを抽象化し、将来的にSQLite以外のデータベース（PostgreSQL、MySQLなど）への移行を容易にします。

### 2.2 SQLAlchemyモデル定義

SQLAlchemyのORMを使用してモデルを定義します。

**Baseクラス:**
```
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass
```

**Userモデル:**
```
class User(Base):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    ldap_uid: Mapped[str] = mapped_column(String(255), unique=True, nullable=True)
    ldap_email: Mapped[str] = mapped_column(String(255), unique=True, nullable=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    
    config: Mapped["UserConfig"] = relationship(back_populates="user", uselist=False)
```

**UserConfigモデル:**
```
class UserConfig(Base):
    __tablename__ = "user_configs"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    llm_api_key: Mapped[str] = mapped_column(Text, nullable=True)  # 暗号化保存
    llm_model: Mapped[str] = mapped_column(String(255), nullable=True)
    additional_system_prompt: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    
    user: Mapped["User"] = relationship(back_populates="config")
```

### 2.3 テーブル設計

#### 2.3.1 usersテーブル

ユーザーの基本情報を管理するテーブル。

| カラム名 | データ型 | 制約 | 説明 |
|---------|---------|------|------|
| id | INTEGER | PRIMARY KEY, AUTOINCREMENT | ユーザーID |
| username | VARCHAR(255) | NOT NULL, UNIQUE | GitHub/GitLabユーザー名 |
| ldap_uid | VARCHAR(255) | UNIQUE | Active DirectoryのUID |
| ldap_email | VARCHAR(255) | UNIQUE | Active Directoryのメールアドレス |
| display_name | VARCHAR(255) | | 表示名 |
| is_admin | BOOLEAN | NOT NULL, DEFAULT FALSE | 管理者フラグ |
| is_active | BOOLEAN | NOT NULL, DEFAULT TRUE | 有効フラグ |
| created_at | TIMESTAMP | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 作成日時 |
| updated_at | TIMESTAMP | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 更新日時 |

**インデックス:**
- `idx_users_username` ON username
- `idx_users_ldap_uid` ON ldap_uid
- `idx_users_ldap_email` ON ldap_email

#### 2.3.2 user_configsテーブル

ユーザーごとのLLM設定を管理するテーブル。

| カラム名 | データ型 | 制約 | 説明 |
|---------|---------|------|------|
| id | INTEGER | PRIMARY KEY, AUTOINCREMENT | 設定ID |
| user_id | INTEGER | FOREIGN KEY(users.id), UNIQUE | ユーザーID |
| llm_api_key | TEXT | | LLM APIキー（暗号化保存） |
| llm_model | VARCHAR(255) | | LLMモデル名 |
| additional_system_prompt | TEXT | | 追加のシステムプロンプト |
| created_at | TIMESTAMP | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 作成日時 |
| updated_at | TIMESTAMP | NOT NULL, DEFAULT CURRENT_TIMESTAMP | 更新日時 |

**インデックス:**
- `idx_user_configs_user_id` ON user_id

### 2.4 データ暗号化

#### 2.4.1 暗号化対象フィールド

APIキーなどの機密情報は暗号化して保存します。

**暗号化対象:**
- `user_configs.llm_api_key`

#### 2.4.2 暗号化方式

- **アルゴリズム**: AES-256-GCM
- **鍵管理**: 環境変数（`ENCRYPTION_KEY`）から読み込み

### 2.5 SQLAlchemyセッション管理

#### 2.5.1 データベース接続設定

```
# config.yamlの設定例
database:
  url: "sqlite:///./data/users.db"  # SQLite
  # url: "postgresql://user:password@localhost/dbname"  # PostgreSQL
  # url: "mysql+pymysql://user:password@localhost/dbname"  # MySQL
  echo: false  # SQLログ出力
```

#### 2.5.2 セッションファクトリ

```
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine(database_url, echo=echo)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
```

## 3. Active Directory認証設計

### 3.1 設計方針

Active Directory認証を使用してユーザーを認証し、認証されたユーザーのメールアドレスからGitHub/GitLabユーザー名を導出します。

### 3.2 認証フロー

```
1. ユーザーがログイン画面でAD認証情報を入力
   |
2. Active Directoryサーバーに認証リクエストを送信
   |
3. AD認証が成功した場合:
   a. ユーザーのメールアドレスとUIDを取得
   b. メールアドレスの@以前をGitHub/GitLabユーザー名として抽出
   c. データベースでユーザーを検索または新規作成
   d. セッションを開始
   |
4. ログイン完了
```

### 3.3 Active Directory設定

#### 3.3.1 config.yamlへの追加設定

```yaml
# Active Directory認証設定
active_directory:
  # ADサーバー設定
  server:
    host: "ad.example.com"
    port: 636
    use_ssl: true
  
  # バインド設定（サービスアカウント）
  bind:
    dn: "CN=service_account,OU=Service Accounts,DC=example,DC=com"
    password_env: "AD_BIND_PASSWORD"
  
  # ユーザー検索設定
  user_search:
    base_dn: "OU=Users,DC=example,DC=com"
    filter: "(sAMAccountName={username})"
    
    # 取得する属性
    attributes:
      uid: "sAMAccountName"
      email: "userPrincipalName"
      display_name: "displayName"
  
  # タイムアウト設定
  timeout:
    connect: 5
    operation: 10
```

### 3.4 ユーザー名の導出ルール

#### 3.4.1 基本ルール

ADメールアドレスからGitHub/GitLabユーザー名を導出します。

```
ADメールアドレス: "taro.yamada@example.com"
              |
GitHub/GitLabユーザー名: "taro.yamada"
```

#### 3.4.2 導出処理

1. AD認証後、ユーザーのメールアドレス（userPrincipalName属性）を取得
2. メールアドレスから`@`以前の部分を抽出
3. 抽出した文字列をGitHub/GitLabユーザー名として使用
4. データベースのusersテーブルでusernameとして保存

### 3.5 ADClientクラス設計

#### 3.5.1 責務

- Active Directoryサーバーへの接続管理
- ユーザー認証の実行
- ユーザー属性の取得

#### 3.5.2 主要メソッド

```
ADClient
|-- __init__(config: dict)
|   - AD設定を初期化
|
|-- authenticate(username: str, password: str) -> ADUser | None
|   - ユーザーの認証を実行
|   - 成功時: ADUserオブジェクトを返却
|   - 失敗時: Noneを返却
|
|-- get_user_info(username: str) -> ADUser | None
|   - ユーザー情報を取得（認証なし、サービスアカウントで検索）
|
+-- test_connection() -> bool
    - AD接続テスト
```

#### 3.5.3 ADUserデータクラス

```
ADUser
|-- dn: str                    # 識別名
|-- uid: str                   # sAMAccountName
|-- email: str                 # メールアドレス
|-- display_name: str          # 表示名
+-- derived_username: str      # 導出されたGitHub/GitLabユーザー名
```

### 3.6 セッション管理

Streamlitの`st.session_state`を使用してセッション情報を管理します。

**セッション状態の構造:**

```
st.session_state = {
    "authenticated": bool,        # 認証済みフラグ
    "user": {                     # ログインユーザー情報
        "username": str,
        "ldap_uid": str,
        "ldap_email": str,
        "display_name": str,
        "is_admin": bool
    },
    "current_page": str,          # 現在のページ
    "messages": list,             # フラッシュメッセージ
}
```

## 4. 管理者画面設計

### 4.1 機能一覧

#### 4.1.1 ユーザー管理

| 機能 | 説明 | 権限 |
|------|------|------|
| ユーザー一覧表示 | 登録済みユーザーの一覧を表示 | 管理者 |
| ユーザー追加 | 新規ユーザーを手動で追加 | 管理者 |
| ユーザー編集 | ユーザー情報の編集（管理者フラグ、有効フラグ等） | 管理者 |
| ユーザー削除 | ユーザーの削除（論理削除） | 管理者 |

#### 4.1.2 個人設定

| 機能 | 説明 | 権限 |
|------|------|------|
| モデル設定 | 使用するLLMモデル名を入力・変更 | 本人 |

### 4.2 画面遷移

```
[ログイン画面]
      | AD認証
[ダッシュボード]
      |
  |-- [ユーザー管理]（管理者のみ）
  |      |-- [ユーザー一覧]
  |      |      |-- [ユーザー追加]
  |      |      |-- [ユーザー編集]
  |      |      +-- [ユーザー削除確認]
  |
  +-- [個人設定]（一般ユーザー）
         +-- [モデル設定]
```

### 4.3 Streamlit管理画面設計

#### 4.3.1 ディレクトリ構成

```
user_config_api/
|-- streamlit_app/           # Streamlit管理画面
|   |-- app.py               # メインエントリポイント
|   |-- pages/               # マルチページ構成
|   |   |-- 01_dashboard.py
|   |   |-- 02_user_management.py
|   |   +-- 03_personal_settings.py
|   |-- components/          # 再利用可能なUIコンポーネント
|   |   |-- __init__.py
|   |   |-- auth.py          # 認証コンポーネント
|   |   |-- user_form.py     # ユーザーフォーム
|   |   +-- data_table.py    # データテーブル
|   |-- utils/               # ユーティリティ
|   |   |-- __init__.py
|   |   +-- session.py       # セッション管理
|   +-- .streamlit/          # Streamlit設定
|       +-- config.toml
|-- server.py                # FastAPIサーバー
+-- ...
```

#### 4.3.2 画面設計詳細

##### ログイン画面（app.py）

```
+----------------------------------------------------------+
|                                                          |
|              ユーザーコンフィグ管理                       |
|                                                          |
|     +------------------------------------------+         |
|     | ユーザー名                               |         |
|     | [                                      ] |         |
|     +------------------------------------------+         |
|                                                          |
|     +------------------------------------------+         |
|     | パスワード                               |         |
|     | [                                      ] |         |
|     +------------------------------------------+         |
|                                                          |
|              [ ログイン ]                                |
|                                                          |
+----------------------------------------------------------+
```

**処理フロー:**
1. ユーザー名とパスワードを入力
2. AD認証を実行（ADClientを呼び出し）
3. 認証成功時: セッション状態にユーザー情報を保存し、ダッシュボードへ遷移
4. 認証失敗時: エラーメッセージを表示

##### ダッシュボード（01_dashboard.py）

```
+----------------------------------------------------------+
| ダッシュボード                         [ログアウト]       |
+----------------------------------------------------------+
|                                                          |
|  ようこそ、山田太郎 さん                                 |
|                                                          |
|  +---------------+  +---------------+                    |
|  | ユーザー      |  | 設定済        |                    |
|  |    数: 42     |  |    数: 38     |                    |
|  +---------------+  +---------------+                    |
|                                                          |
+----------------------------------------------------------+
```

##### ユーザー管理（02_user_management.py）

```
+----------------------------------------------------------+
| ユーザー管理                           [ログアウト]       |
+----------------------------------------------------------+
|                                                          |
|  [+ ユーザー追加]                                        |
|                                                          |
|  検索: [________________] [アクティブのみ]               |
|                                                          |
|  +------------------------------------------------------+|
|  | ユーザー名    | 表示名    | 管理者 | 状態  | 操作    ||
|  +---------------+-----------+--------+-------+---------+|
|  | taro.yamada   | 山田太郎  | Yes    | 有効  | 編集 削除||
|  | hanako.suzuki | 鈴木花子  |        | 有効  | 編集 削除||
|  | jiro.tanaka   | 田中次郎  |        | 無効  | 編集 削除||
|  +------------------------------------------------------+|
|                                                          |
|  < 1 / 5 >                                               |
|                                                          |
+----------------------------------------------------------+
```

**ユーザー追加/編集ダイアログ:**

```
+----------------------------------------------------------+
| ユーザー追加                                    [X]       |
+----------------------------------------------------------+
|                                                          |
|  ユーザー名（GitHub/GitLab）                             |
|  [_______________________]                               |
|                                                          |
|  AD UID                                                  |
|  [_______________________]                               |
|                                                          |
|  ADメールアドレス                                        |
|  [_______________________]                               |
|                                                          |
|  表示名                                                  |
|  [_______________________]                               |
|                                                          |
|  [ ] 管理者権限を付与                                    |
|  [x] アクティブ                                          |
|                                                          |
|              [キャンセル] [保存]                         |
|                                                          |
+----------------------------------------------------------+
```

##### 個人設定（03_personal_settings.py）

```
+----------------------------------------------------------+
| 個人設定                               [ログアウト]       |
+----------------------------------------------------------+
|                                                          |
|  ユーザー: taro.yamada                                   |
|  メール: taro.yamada@example.com                         |
|  権限: 一般ユーザー                                      |
|                                                          |
|  --- モデル設定 ---                                      |
|                                                          |
|  LLMモデル名                                             |
|  [gpt-4o                                    ]            |
|  ※ 使用するLLMモデル名を入力してください                 |
|                                                          |
|              [デフォルトに戻す] [保存]                    |
|                                                          |
+----------------------------------------------------------+
```

#### 4.3.3 Streamlitセッション管理

**認証チェック処理:**

各ページの先頭で認証状態をチェックし、未認証の場合はログイン画面にリダイレクトします。

```
処理フロー:
1. st.session_state.authenticatedをチェック
2. Falseの場合: ログイン画面を表示
3. Trueの場合: ページコンテンツを表示
```

#### 4.3.4 Streamlit設定（.streamlit/config.toml）

```toml
[server]
port = 8501
headless = true
enableCORS = false
enableXsrfProtection = true

[browser]
gatherUsageStats = false

[theme]
primaryColor = "#1f77b4"
backgroundColor = "#ffffff"
secondaryBackgroundColor = "#f0f2f6"
textColor = "#262730"
font = "sans serif"

[client]
showErrorDetails = false
toolbarMode = "minimal"
```

#### 4.3.5 コンポーネント設計

##### 認証コンポーネント（components/auth.py）

**責務:**
- ログインフォームの表示
- AD認証の実行
- セッション状態の更新
- ログアウト処理

**主要関数:**

```
show_login_form()
    - ログインフォームを表示
    - 入力値のバリデーション

authenticate_user(username: str, password: str) -> bool
    - ADClientを使用してユーザーを認証
    - 成功時: セッション状態を更新しTrueを返す
    - 失敗時: エラーメッセージを表示しFalseを返す

check_authentication() -> bool
    - 現在の認証状態をチェック

logout()
    - セッション状態をクリア
    - ログイン画面にリダイレクト

require_admin() -> bool
    - 管理者権限をチェック
    - 権限がない場合はエラーメッセージを表示
```

##### ユーザーフォームコンポーネント（components/user_form.py）

**責務:**
- ユーザー追加/編集フォームの表示
- 入力値のバリデーション

**主要関数:**

```
show_user_form(user: User | None = None) -> User | None
    - ユーザー追加/編集フォームを表示
    - user引数がNoneの場合は新規作成モード
    - user引数がある場合は編集モード
    - フォーム送信時にUserオブジェクトを返す

validate_username(username: str) -> tuple[bool, str]
    - ユーザー名のバリデーション
    - (有効かどうか, エラーメッセージ)を返す

show_delete_confirmation(user: User) -> bool
    - 削除確認ダイアログを表示
    - 確認された場合Trueを返す
```

##### データテーブルコンポーネント（components/data_table.py）

**責務:**
- ページネーション付きデータテーブルの表示
- ソート・フィルタ機能
- 行アクション（編集・削除ボタン）

**主要関数:**

```
show_data_table(
    data: list[dict],
    columns: list[str],
    page: int = 1,
    per_page: int = 20,
    sortable: bool = True,
    actions: list[str] = ["edit", "delete"]
) -> tuple[int, str, Any]
    - データテーブルを表示
    - (選択された行インデックス, アクション種別, 行データ)を返す

show_pagination(total: int, page: int, per_page: int) -> int
    - ページネーションコントロールを表示
    - 選択されたページ番号を返す

show_search_filter(placeholder: str = "検索...") -> str
    - 検索フィルタを表示
    - 入力された検索文字列を返す
```

### 4.4 API仕様（コーディングエージェント用）

既存の`/config/{platform}/{username}`エンドポイントは維持し、データベースから設定を取得するように拡張します。

```
GET /config/{platform}/{username}
Authorization: Bearer {api_key}

処理フロー:
1. APIキーの検証
2. データベースからユーザー設定を取得
3. ユーザー設定がない場合はデフォルト設定（config.yaml）を返却
4. ユーザー設定がある場合はデフォルト設定とマージして返却

Response:
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
    "system_prompt": "...",
    "max_llm_process_num": 1000
  }
}
```

## 5. アーキテクチャ設計

### 5.1 全体構成

```
user_config_api/
|-- server.py                # FastAPIサーバー（APIエントリポイント）
|-- streamlit_app.py         # Streamlitアプリ（管理画面エントリポイント）
|-- config.yaml              # 設定ファイル
|-- requirements.txt         # Python依存関係
|-- Dockerfile               # Dockerイメージ（API + Streamlit）
|-- Dockerfile.streamlit     # Streamlit専用Dockerイメージ
|-- docker-compose.yml       # Docker Compose設定
|-- data/                    # データディレクトリ
|   +-- users.db             # SQLiteデータベース
|-- app/                     # 共通アプリケーションコード
|   |-- __init__.py
|   |-- config.py            # 設定読み込み
|   |-- database.py          # SQLAlchemyセッション管理
|   |-- models/              # SQLAlchemyモデル
|   |   |-- __init__.py
|   |   |-- user.py
|   |   +-- user_config.py
|   |-- services/            # ビジネスロジック
|   |   |-- __init__.py
|   |   |-- auth_service.py
|   |   +-- user_service.py
|   |-- auth/                # 認証関連
|   |   |-- __init__.py
|   |   +-- ad_client.py
|   +-- utils/               # ユーティリティ
|       |-- __init__.py
|       +-- encryption.py    # 暗号化ユーティリティ
|-- api/                     # FastAPI関連
|   |-- __init__.py
|   |-- dependencies.py      # 依存関係注入
|   +-- routers/             # APIルーター
|       |-- __init__.py
|       +-- config.py        # 既存API互換
|-- streamlit_custom/        # Streamlit管理画面
|   |-- __init__.py
|   |-- pages/               # マルチページ構成
|   |   |-- 01_dashboard.py
|   |   |-- 02_user_management.py
|   |   +-- 03_personal_settings.py
|   |-- components/          # 再利用可能なUIコンポーネント
|   |   |-- __init__.py
|   |   |-- auth.py          # 認証コンポーネント
|   |   |-- user_form.py     # ユーザーフォーム
|   |   +-- data_table.py    # データテーブル
|   |-- utils/               # Streamlit用ユーティリティ
|   |   |-- __init__.py
|   |   +-- session.py       # セッション管理
|   +-- .streamlit/          # Streamlit設定
|       +-- config.toml
+-- tests/                   # テスト
    |-- __init__.py
    +-- unit/
        |-- test_auth_service.py
        +-- test_user_service.py
```

### 5.2 レイヤー構成

```
+----------------------------------------------------------+
|                   プレゼンテーション層                    |
|  +--------------------+    +--------------------+        |
|  | Streamlit管理画面  |    |   FastAPI REST     |        |
|  |   (ポート8501)     |    |    (ポート8080)    |        |
|  +---------+----------+    +---------+----------+        |
+------------|--------------------------|-------------------+
             |                          |
             v                          v
+----------------------------------------------------------+
|                   サービス層（共有）                      |
|  +--------------+ +---------------+                      |
|  | AuthService  | | UserService   |                      |
|  +--------------+ +---------------+                      |
+----------------------------+-----------------------------+
                             |
                             v
+----------------------------------------------------------+
|                   データアクセス層                        |
|  +--------------------------------------------------+   |
|  |              SQLAlchemy ORM                       |   |
|  +--------------------------------------------------+   |
+----------------------------+-----------------------------+
                             |
                             v
+----------------------------------------------------------+
|                   データベース層                          |
|  +--------------------------------------------------+   |
|  |            SQLite / PostgreSQL / MySQL            |   |
|  +--------------------------------------------------+   |
+----------------------------------------------------------+
```

### 5.3 Streamlitとサービス層の連携

Streamlit管理画面は、サービス層を直接呼び出してデータベース操作を行います。
FastAPIを経由せず、Pythonコードを直接呼び出すことで効率的に処理できます。

```
Streamlit管理画面
        |
        |-- 認証 ------> AuthService ------> ADClient
        |                    |
        |                    +------> SQLAlchemy Session
        |
        +-- ユーザー管理 --> UserService --> SQLAlchemy Session
```

### 5.4 SQLAlchemy設定

#### 5.4.1 config.yamlの拡張

```yaml
# データベース設定（SQLAlchemy）
database:
  # 接続URL
  # SQLite: sqlite:///./data/users.db
  # PostgreSQL: postgresql://user:password@localhost/dbname
  # MySQL: mysql+pymysql://user:password@localhost/dbname
  url: "sqlite:///./data/users.db"
  
  # SQLログ出力
  echo: false
  
  # コネクションプール設定（PostgreSQL/MySQL用）
  pool_size: 5
  max_overflow: 10

# Active Directory認証設定
active_directory:
  server:
    host: "ad.example.com"
    port: 636
    use_ssl: true
  bind:
    dn: "CN=service_account,OU=Service Accounts,DC=example,DC=com"
    password_env: "AD_BIND_PASSWORD"
  user_search:
    base_dn: "OU=Users,DC=example,DC=com"
    filter: "(sAMAccountName={username})"
    attributes:
      uid: "sAMAccountName"
      email: "userPrincipalName"
      display_name: "displayName"
  timeout:
    connect: 5
    operation: 10

# 暗号化設定
encryption:
  key_env: "ENCRYPTION_KEY"

# APIサーバー設定（既存）
api_server:
  api_key: "your-secret-api-key-here"

# LLM設定（デフォルト）
llm:
  provider: "openai"
  function_calling: true
  openai:
    base_url: "https://api.openai.com/v1"
    api_key: "OPENAI_API_KEY"
    model: "gpt-4o"
    max_token: 40960
```

## 6. セキュリティ仕様

### 6.1 認証・認可

#### 6.1.1 認証方式

| 認証方式 | 用途 | 説明 |
|---------|------|------|
| AD認証 | 管理画面ログイン | Active Directoryサーバーによるユーザー認証 |
| APIキー | コーディングエージェント | 既存の固定APIキー認証を維持 |

#### 6.1.2 認可（権限管理）

| ロール | 権限 |
|--------|------|
| 管理者（is_admin=true） | 全ユーザーの管理 |
| 一般ユーザー | 自分のモデル設定の変更のみ |

### 6.2 データ保護

#### 6.2.1 通信の暗号化

- 本番環境ではHTTPS（TLS 1.2以上）を必須とする
- Docker内部ネットワークでの通信はHTTPを許容

#### 6.2.2 機密データの暗号化

- APIキー等の機密データはAES-256-GCMで暗号化して保存
- 暗号化キーは環境変数から読み込み

### 6.3 セキュリティヘッダー

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Content-Security-Policy: default-src 'self'
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

## 7. デプロイメント

### 7.1 Docker構成

#### 7.1.1 Dockerfile.api（API専用）

```dockerfile
FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /app/data

EXPOSE 8080

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
```

#### 7.1.2 Dockerfile.streamlit（Streamlit専用）

```dockerfile
FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

CMD ["streamlit", "run", "streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

#### 7.1.3 docker-compose.yml

```yaml
version: '3.8'

services:
  # FastAPI（REST API）サーバー
  user-config-api:
    build:
      context: ./user_config_api
      dockerfile: Dockerfile.api
    container_name: user-config-api
    environment:
      - AD_BIND_PASSWORD=${AD_BIND_PASSWORD}
      - ENCRYPTION_KEY=${ENCRYPTION_KEY}
      - API_SERVER_KEY=${API_SERVER_KEY}
      - DATABASE_URL=sqlite:///./data/users.db
    volumes:
      - user-config-data:/app/data
    ports:
      - "8080:8080"
    networks:
      - coding-agent-network

  # Streamlit管理画面サーバー
  user-config-web:
    build:
      context: ./user_config_api
      dockerfile: Dockerfile.streamlit
    container_name: user-config-web
    environment:
      - AD_BIND_PASSWORD=${AD_BIND_PASSWORD}
      - ENCRYPTION_KEY=${ENCRYPTION_KEY}
      - DATABASE_URL=sqlite:///./data/users.db
    volumes:
      - user-config-data:/app/data
    ports:
      - "8501:8501"
    networks:
      - coding-agent-network
    depends_on:
      - user-config-api

  # テスト用OpenLDAPサーバー
  openldap:
    image: osixia/openldap:1.5.0
    container_name: openldap
    environment:
      - LDAP_ORGANISATION=Example Inc
      - LDAP_DOMAIN=example.com
      - LDAP_ADMIN_PASSWORD=admin_password
      - LDAP_CONFIG_PASSWORD=config_password
      - LDAP_READONLY_USER=true
      - LDAP_READONLY_USER_USERNAME=readonly
      - LDAP_READONLY_USER_PASSWORD=readonly_password
    volumes:
      - openldap-data:/var/lib/ldap
      - openldap-config:/etc/ldap/slapd.d
    ports:
      - "389:389"
      - "636:636"
    networks:
      - coding-agent-network

  # テスト用LDAP管理画面（LAM）
  ldap-account-manager:
    image: ldapaccountmanager/lam:stable
    container_name: ldap-account-manager
    environment:
      - LAM_SKIP_PRECONFIGURE=false
      - LDAP_DOMAIN=example.com
      - LDAP_BASE_DN=dc=example,dc=com
      - LDAP_USERS_DN=ou=users,dc=example,dc=com
      - LDAP_GROUPS_DN=ou=groups,dc=example,dc=com
      - LDAP_SERVER=ldap://openldap:389
      - LAM_LANG=ja_JP
      - LAM_PASSWORD=lam_password
    ports:
      - "8090:80"
    networks:
      - coding-agent-network
    depends_on:
      - openldap

volumes:
  user-config-data:
  openldap-data:
  openldap-config:

networks:
  coding-agent-network:
    driver: bridge
```

#### 7.1.4 requirements.txt

```
# FastAPI関連
fastapi==0.104.1
uvicorn==0.24.0
pydantic==2.5.0

# Streamlit関連
streamlit==1.29.0

# データベース（SQLAlchemy）
sqlalchemy==2.0.23
aiosqlite==0.19.0

# 認証関連
python-ldap==3.4.4
bcrypt==4.1.1

# 暗号化
cryptography==41.0.7

# 設定
PyYAML==6.0.1
python-dotenv==1.0.0

# ユーティリティ
pandas==2.1.3
```

### 7.2 環境変数

| 環境変数 | 説明 | 必須 |
|---------|------|------|
| AD_BIND_PASSWORD | Active Directoryサービスアカウントのパスワード | Yes |
| ENCRYPTION_KEY | データ暗号化キー（32バイト） | Yes |
| API_SERVER_KEY | コーディングエージェント用APIキー | Yes |
| DATABASE_URL | データベースURL（デフォルト: sqlite:///./data/users.db） | No |
| STREAMLIT_SERVER_PORT | Streamlitポート（デフォルト: 8501） | No |

### 7.3 初期セットアップ

#### 7.3.1 初期管理者の作成

```bash
# コンテナ内で実行
docker-compose exec user-config-web python -m app.commands.create_admin \
  --username admin \
  --ldap-uid admin \
  --ldap-email admin@example.com

# または環境変数で初期管理者を指定
INITIAL_ADMIN_USERNAME=admin
INITIAL_ADMIN_LDAP_UID=admin
INITIAL_ADMIN_LDAP_EMAIL=admin@example.com
```

#### 7.3.2 データベース初期化

SQLAlchemyのマイグレーション機能を使用してデータベースを初期化します。

```bash
# テーブル作成
docker-compose exec user-config-api python -c "from app.database import engine, Base; Base.metadata.create_all(engine)"
```

### 7.4 起動方法

#### 7.4.1 Docker Composeで起動

```bash
# サービスの起動
docker-compose up -d

# ログの確認
docker-compose logs -f

# サービスの停止
docker-compose down
```

#### 7.4.2 ローカル開発環境での起動

```bash
# 仮想環境の作成と有効化
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 依存関係のインストール
pip install -r requirements.txt

# FastAPIサーバーの起動（ターミナル1）
uvicorn server:app --host 0.0.0.0 --port 8080 --reload

# Streamlitサーバーの起動（ターミナル2）
streamlit run streamlit_app.py --server.port 8501

# アクセス
# - API: http://localhost:8080
# - 管理画面: http://localhost:8501
```

### 7.5 テスト用LDAP環境

#### 7.5.1 OpenLDAPの設定

docker-compose.ymlに含まれるOpenLDAPサーバーをテスト用ADサーバーとして使用します。

**初期設定:**
- ドメイン: example.com
- Base DN: dc=example,dc=com
- 管理者DN: cn=admin,dc=example,dc=com
- 管理者パスワード: admin_password

#### 7.5.2 LDAP Account Manager (LAM)

WebベースのLDAP管理ツールでテストユーザーを作成できます。

**アクセス:**
- URL: http://localhost:8090
- 初期パスワード: lam_password

**使用方法:**
1. ブラウザでhttp://localhost:8090にアクセス
2. LAM設定画面でLDAPサーバー接続を確認
3. ユーザー管理画面でテストユーザーを作成

### 7.6 アクセスURL

| サービス | URL | 説明 |
|---------|-----|------|
| Streamlit管理画面 | http://localhost:8501 | ブラウザで管理操作 |
| FastAPI REST API | http://localhost:8080 | コーディングエージェント用API |
| API ドキュメント | http://localhost:8080/docs | Swagger UI |
| LDAP Account Manager | http://localhost:8090 | テスト用LDAP管理 |

## 8. まとめ

### 8.1 主要な設計ポイント

1. **Streamlitによる管理画面**
   - Pythonのみでフル機能の管理UIを構築
   - 迅速な開発とメンテナンス性の向上
   - バックエンドコードとの直接連携

2. **SQLAlchemyによるデータベース抽象化**
   - ORMによる型安全なデータアクセス
   - SQLiteからPostgreSQL/MySQL等への移行が容易
   - マイグレーション機能でスキーマ変更を管理

3. **Active Directory認証**
   - 既存のADインフラを活用
   - メールアドレスからGitHub/GitLabユーザー名を自動導出

4. **2サーバー構成**
   - Streamlit管理画面（ポート8501）: 人間向けUI
   - FastAPI REST API（ポート8080）: コーディングエージェント向け

5. **テスト環境**
   - OpenLDAP + LAMでADサーバーをシミュレート
   - 開発・テストが容易

### 8.2 今後の拡張性

- 複数ADサーバーのサポート
- OAuth2/OIDC認証の追加
- ロールベースアクセス制御（RBAC）の拡張
- ダークモード対応

---

**文書バージョン:** 2.0  
**最終更新日:** 2024-11-27  
**ステータス:** 詳細設計完了（レビュー反映版）
