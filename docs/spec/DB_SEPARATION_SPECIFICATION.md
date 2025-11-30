# データベース分離設計書

## 1. 概要

### 1.1 目的
タスク情報の永続化層をSQLiteからPostgreSQLに移行し、SQLAlchemyを使用してデータベースアクセスを汎用化する。これにより、以下のメリットを実現する：

- **スケーラビリティの向上**: PostgreSQLの採用により、大規模なタスク処理やマルチインスタンス環境に対応可能
- **データベース抽象化**: SQLAlchemyを使用することで、将来的に他のデータベース（MySQL、MariaDB等）への切り替えが容易
- **トランザクション管理の強化**: SQLAlchemyのセッション管理により、データ整合性の保証を強化
- **運用性の向上**: PostgreSQLの豊富な管理機能とモニタリング機能を活用可能

### 1.2 現状分析

#### 現在のデータベース構成
- **タスク情報DB**: SQLite（`contexts/tasks.db`）
- **メッセージ履歴**: JSONLファイル（`messages.jsonl`、`current.jsonl`）
- **要約履歴**: JSONLファイル（`summaries.jsonl`）
- **ツール実行履歴**: JSONLファイル（`tools.jsonl`）

#### 現在のテーブル構造（tasks テーブル）
```
uuid TEXT PRIMARY KEY,          -- タスクの一意識別子
task_source TEXT NOT NULL,      -- タスクソース（github/gitlab）
owner TEXT NOT NULL,            -- リポジトリオーナー
repo TEXT NOT NULL,             -- リポジトリ名
task_type TEXT NOT NULL,        -- タスクタイプ（issue/pull_request/merge_request）
task_id TEXT NOT NULL,          -- タスクID（Issue番号等）
status TEXT NOT NULL,           -- ステータス（running/completed/failed/stopped）
created_at TEXT NOT NULL,       -- 作成日時
started_at TEXT,                -- 開始日時
completed_at TEXT,              -- 完了日時
process_id INTEGER,             -- プロセスID
hostname TEXT,                  -- ホスト名
llm_provider TEXT,              -- LLMプロバイダー
model TEXT,                     -- 使用モデル
context_length INTEGER,         -- コンテキスト長
llm_call_count INTEGER,         -- LLM呼び出し回数
tool_call_count INTEGER,        -- ツール呼び出し回数
total_tokens INTEGER,           -- 総トークン数
compression_count INTEGER,      -- 圧縮回数
error_message TEXT,             -- エラーメッセージ
user TEXT                       -- ユーザー名
```

---

## 2. 詳細設計

### 2.1 アーキテクチャ設計

#### 2.1.1 レイヤー構成
データベースアクセス層を以下の3層構造で設計する：

1. **モデル層（Models）**: SQLAlchemyのORMモデルを定義
2. **リポジトリ層（Repository）**: データアクセスロジックをカプセル化
3. **サービス層（既存）**: 既存のビジネスロジック（TaskContextManager等）

#### 2.1.2 ディレクトリ構成
以下の新規ディレクトリとファイルを追加する：

```
db/
├── __init__.py           # DBモジュールの公開インターフェース
├── config.py             # DB接続設定
├── connection.py         # DB接続管理（エンジン・セッション）
├── models/
│   ├── __init__.py       # モデルの公開
│   ├── base.py           # SQLAlchemy Baseクラス
│   └── task.py           # Taskモデル
└── repositories/
    ├── __init__.py       # リポジトリの公開
    └── task_repository.py # タスクリポジトリ
```

### 2.2 データベース接続設計

#### 2.2.1 接続設定（db/config.py）
設定ファイルおよび環境変数から接続情報を取得する機能を実装する。

**処理内容**:
- 環境変数から接続情報を優先的に取得する
- 環境変数が未設定の場合は設定ファイル（config.yaml）から取得する
- SQLite互換モードをサポートし、後方互換性を維持する
- 接続URLの構築とバリデーションを行う

**設定項目**:
| 環境変数名 | config.yaml キー | 説明 | デフォルト値 |
|-----------|-----------------|------|------------|
| DATABASE_TYPE | database.type | データベースタイプ | sqlite |
| DATABASE_HOST | database.host | PostgreSQLホスト | localhost |
| DATABASE_PORT | database.port | PostgreSQLポート | 5432 |
| DATABASE_NAME | database.name | データベース名 | coding_agent |
| DATABASE_USER | database.user | ユーザー名 | - |
| DATABASE_PASSWORD | database.password | パスワード | - |
| DATABASE_URL | database.url | 完全な接続URL（他設定を上書き） | - |

#### 2.2.2 接続管理（db/connection.py）
SQLAlchemyのエンジンとセッションを管理するシングルトンクラスを実装する。

**処理内容**:
- SQLAlchemyエンジンの初期化と管理を行う
- スコープ付きセッションファクトリーを提供する
- コンテキストマネージャーによるセッションの自動コミットとロールバックを実装する
- コネクションプールの設定と管理を行う
- シングルトンパターンによるインスタンス管理を実装する

**コネクションプール設定**:
| パラメータ | 値 | 説明 |
|-----------|-----|------|
| pool_size | 5 | プール内の常駐接続数 |
| max_overflow | 10 | 最大追加接続数 |
| pool_timeout | 30 | 接続取得タイムアウト（秒） |
| pool_recycle | 3600 | 接続の再利用時間（秒） |

### 2.3 モデル設計

#### 2.3.1 Baseクラス（db/models/base.py）
SQLAlchemyの宣言的ベースクラスを定義する。

**処理内容**:
- SQLAlchemy 2.0スタイルの宣言的ベースクラスを定義する
- 共通カラム（作成日時、更新日時）のミックスインを提供する
- テーブル命名規則を設定する

#### 2.3.2 Taskモデル（db/models/task.py）
タスク情報を表すORMモデルを定義する。

**処理内容**:
- 現在のSQLiteテーブル構造を継承したモデルを定義する
- PostgreSQL固有の型（UUID型等）を適切に使用する
- インデックスの最適化を行う
- 型ヒントによる静的型チェックをサポートする

**カラム定義**:
| カラム名 | 型 | PostgreSQL型 | 制約 | 説明 |
|---------|-----|-------------|------|------|
| uuid | String(36) | UUID | PRIMARY KEY | タスク一意識別子 |
| task_source | String(50) | VARCHAR(50) | NOT NULL | タスクソース |
| owner | String(255) | VARCHAR(255) | NOT NULL | リポジトリオーナー |
| repo | String(255) | VARCHAR(255) | NOT NULL | リポジトリ名 |
| task_type | String(50) | VARCHAR(50) | NOT NULL | タスクタイプ |
| task_id | String(50) | VARCHAR(50) | NOT NULL | タスクID |
| status | String(20) | VARCHAR(20) | NOT NULL | ステータス |
| created_at | DateTime | TIMESTAMP WITH TIME ZONE | NOT NULL | 作成日時 |
| started_at | DateTime | TIMESTAMP WITH TIME ZONE | - | 開始日時 |
| completed_at | DateTime | TIMESTAMP WITH TIME ZONE | - | 完了日時 |
| process_id | Integer | INTEGER | - | プロセスID |
| hostname | String(255) | VARCHAR(255) | - | ホスト名 |
| llm_provider | String(50) | VARCHAR(50) | - | LLMプロバイダー |
| model | String(100) | VARCHAR(100) | - | 使用モデル |
| context_length | Integer | INTEGER | - | コンテキスト長 |
| llm_call_count | Integer | INTEGER | DEFAULT 0 | LLM呼び出し回数 |
| tool_call_count | Integer | INTEGER | DEFAULT 0 | ツール呼び出し回数 |
| total_tokens | Integer | INTEGER | DEFAULT 0 | 総トークン数 |
| compression_count | Integer | INTEGER | DEFAULT 0 | 圧縮回数 |
| error_message | Text | TEXT | - | エラーメッセージ |
| user | String(255) | VARCHAR(255) | - | ユーザー名 |

**インデックス定義**:
| インデックス名 | カラム | 用途 |
|--------------|--------|------|
| ix_tasks_status | status | ステータス別検索の高速化 |
| ix_tasks_created_at | created_at | 作成日時順ソートの高速化 |
| ix_tasks_user | user | ユーザー別検索の高速化 |
| ix_tasks_task_source_owner_repo | task_source, owner, repo | リポジトリ別検索の高速化 |

### 2.4 リポジトリ設計

#### 2.4.1 TaskRepository（db/repositories/task_repository.py）
タスクのCRUD操作をカプセル化するリポジトリクラスを実装する。

**メソッド定義**:

| メソッド名 | 引数 | 戻り値 | 説明 |
|-----------|------|--------|------|
| create | task_data: dict | Task | 新規タスクを作成する |
| get_by_uuid | uuid: str | Task または None | UUIDでタスクを取得する |
| update | uuid: str, updates: dict | Task または None | タスクを更新する |
| update_status | uuid: str, status: str, error_message: str (optional) | bool | ステータスを更新する |
| update_statistics | uuid: str, llm_calls: int, tool_calls: int, tokens: int, compressions: int | bool | 統計情報を加算更新する |
| complete | uuid: str | bool | タスクを完了状態に更新する |
| fail | uuid: str, error_message: str | bool | タスクを失敗状態に更新する |
| list_by_status | status: str, limit: int, offset: int | list[Task] | ステータス別にタスク一覧を取得する |
| list_by_user | user: str, limit: int, offset: int | list[Task] | ユーザー別にタスク一覧を取得する |
| delete | uuid: str | bool | タスクを削除する |

**処理内容**:
- セッション管理をコンテキストマネージャーで自動化する
- 例外発生時の自動ロールバックを実装する
- 存在しないタスクへの操作時のエラーハンドリングを実装する
- ログ出力によるデバッグ支援を提供する

### 2.5 既存コード修正設計

#### 2.5.1 TaskContextManager の修正（context_storage/task_context_manager.py）
現在のSQLite直接操作を、TaskRepositoryを介したアクセスに変更する。

**修正対象メソッド**:
| メソッド | 修正内容 |
|---------|---------|
| `__init__` | DB初期化処理をDatabaseConnectionクラスに委譲する |
| `_init_database` | 削除。初期化はDatabaseConnectionで一元管理する |
| `_register_or_update_task` | TaskRepository.create または TaskRepository.update を使用する |
| `update_status` | TaskRepository.update_status を使用する |
| `update_statistics` | TaskRepository.update_statistics を使用する |
| `complete` | TaskRepository.complete を使用する |
| `stop` | TaskRepository.update_status を使用する |
| `fail` | TaskRepository.fail を使用する |

#### 2.5.2 初期化処理の変更
アプリケーション起動時に以下の初期化処理を行う：

1. 設定ファイル・環境変数からDB設定を読み込む
2. DatabaseConnectionの初期化（エンジン・セッションファクトリー作成）
3. テーブルの自動作成（開発環境のみ。本番環境ではマイグレーションツールを使用）

### 2.6 設定ファイル設計

#### 2.6.1 config.yaml への追加
以下の設定セクションを追加する：

```yaml
# データベース設定
database:
  # データベースタイプ: "sqlite" または "postgresql"
  # 環境変数 DATABASE_TYPE で上書き可能
  type: "sqlite"
  
  # SQLite設定（type: sqlite の場合に使用）
  sqlite:
    # データベースファイルパス（context_storage.base_dir からの相対パス）
    path: "tasks.db"
  
  # PostgreSQL設定（type: postgresql の場合に使用）
  postgresql:
    # ホスト名（環境変数 DATABASE_HOST で上書き可能）
    host: "localhost"
    # ポート番号（環境変数 DATABASE_PORT で上書き可能）
    port: 5432
    # データベース名（環境変数 DATABASE_NAME で上書き可能）
    name: "coding_agent"
    # ユーザー名（環境変数 DATABASE_USER で上書き可能）
    user: ""
    # パスワード（環境変数 DATABASE_PASSWORD で上書き可能）
    password: ""
  
  # コネクションプール設定
  pool:
    # プール内の常駐接続数
    size: 5
    # 最大追加接続数
    max_overflow: 10
    # 接続取得タイムアウト（秒）
    timeout: 30
    # 接続の再利用時間（秒）
    recycle: 3600
```

---

## 3. Docker環境設計

### 3.1 docker-compose.yml への追加
PostgreSQLコンテナを追加する。

**サービス定義**:
- サービス名: `postgres`
- イメージ: `postgres:16`
- ボリューム: データ永続化用ボリューム
- 環境変数: DB名、ユーザー名、パスワード
- ヘルスチェック: pg_isready コマンド

### 3.2 依存関係設定
既存のサービス（producer、consumer等）にPostgreSQLへの依存を追加する。

**処理内容**:
- `depends_on` に postgres サービスを追加する
- ヘルスチェック完了を待機する設定を追加する

---

## 4. 後方互換性設計

### 4.1 SQLite互換モード
PostgreSQLが利用できない環境でも動作するよう、SQLite互換モードを維持する。

**動作仕様**:
- `database.type` が `sqlite` の場合は従来通りSQLiteを使用する
- SQLAlchemyを経由してSQLiteにアクセスする（直接sqlite3を使用しない）
- ファイルパスは `context_storage.base_dir` と `database.sqlite.path` から構築する

### 4.2 段階的移行
以下の手順で段階的に移行を進めることを推奨する：

1. **フェーズ1**: SQLAlchemy導入（SQLite継続使用）
2. **フェーズ2**: PostgreSQL環境構築・テスト
3. **フェーズ3**: データ移行・本番切り替え

---

## 5. 依存関係

### 5.1 追加パッケージ
以下のパッケージを追加する：

| パッケージ名 | バージョン | 用途 |
|-------------|----------|------|
| sqlalchemy | >=2.0.0 | ORM・DB抽象化 |
| psycopg2-binary | >=2.9.0 | PostgreSQLドライバ |

### 5.2 pyproject.toml / condaenv.yaml への追加
上記パッケージを依存関係に追加する。

---

## 6. テスト設計

### 6.1 ユニットテスト
以下のテストを追加する：

| テストファイル | 対象 | 内容 |
|--------------|------|------|
| test_db_config.py | db/config.py | 設定読み込みのテスト |
| test_db_connection.py | db/connection.py | 接続管理のテスト |
| test_task_model.py | db/models/task.py | Taskモデルのテスト |
| test_task_repository.py | db/repositories/task_repository.py | TaskRepositoryのテスト |

### 6.2 統合テスト
以下の統合テストを追加する：

| テストファイル | 対象 | 内容 |
|--------------|------|------|
| test_task_context_with_db.py | TaskContextManager | PostgreSQL使用時の動作テスト |

### 6.3 テスト用データベース
テスト実行時は以下の方法でデータベースを分離する：
- インメモリSQLiteを使用する（高速なユニットテスト用）
- テスト用PostgreSQLコンテナを使用する（統合テスト用）

---

## 7. 運用考慮事項

### 7.1 バックアップ
PostgreSQLの標準ツール（pg_dump）を使用したバックアップ手順を提供する。

### 7.2 モニタリング
以下のメトリクスを監視対象とする：
- 接続数
- クエリ実行時間
- デッドロック発生数
- テーブルサイズ

### 7.3 セキュリティ
以下のセキュリティ対策を実施する：
- パスワードは環境変数で管理する（設定ファイルには記載しない）
- SSL接続を推奨する
- 最小権限のDBユーザーを使用する

---

## 8. 影響範囲

### 8.1 修正対象ファイル
| ファイル | 修正内容 |
|---------|---------|
| context_storage/task_context_manager.py | DB操作をリポジトリ経由に変更 |
| main.py | DB初期化処理を追加 |
| config.yaml | database セクションを追加 |
| docker-compose.yml | postgres サービスを追加 |
| pyproject.toml | 依存パッケージを追加 |
| condaenv.yaml | 依存パッケージを追加 |

### 8.2 新規作成ファイル
| ファイル | 内容 |
|---------|------|
| db/__init__.py | DBモジュールの公開インターフェース |
| db/config.py | DB接続設定 |
| db/connection.py | DB接続管理 |
| db/models/__init__.py | モデルの公開 |
| db/models/base.py | SQLAlchemy Baseクラス |
| db/models/task.py | Taskモデル |
| db/repositories/__init__.py | リポジトリの公開 |
| db/repositories/task_repository.py | タスクリポジトリ |

---

## 9. リスクと対策

| リスク | 影響度 | 対策 |
|-------|-------|------|
| パフォーマンス低下 | 中 | インデックスの最適化。コネクションプール設定の調整 |
| 接続エラー | 中 | リトライロジックの実装。ヘルスチェックの設定 |
| 後方互換性の問題 | 低 | SQLite互換モードの維持。十分なテスト |

---

## 10. 用語集

| 用語 | 説明 |
|------|------|
| ORM | Object-Relational Mapping。オブジェクトとリレーショナルデータベースの間のマッピング |
| リポジトリパターン | データアクセスロジックをビジネスロジックから分離するデザインパターン |
| コネクションプール | データベース接続を再利用するための接続プール |
