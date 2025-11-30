# データベース分離設計書

## 1. 概要

### 1.1 目的
タスク情報の永続化層をSQLiteからPostgreSQLに移行し、SQLAlchemyを使用してデータベースアクセスを汎用化する。

### 1.2 対象範囲
- **タスク情報DB（tasksテーブル）のみ**を対象とする
- メッセージ履歴、要約履歴、ツール実行履歴（JSONLファイル）は対象外

### 1.3 TaskKey構造の分析
現在のTaskKeyは以下の4種類があり、それぞれ異なるフィールドを持つ：

| TaskKey種別 | task_source | task_type | owner | repo | project_id | number |
|------------|-------------|-----------|-------|------|------------|--------|
| GitHubIssueTaskKey | github | issue | ○ | ○ | - | ○ |
| GitHubPullRequestTaskKey | github | pull_request | ○ | ○ | - | ○ |
| GitLabIssueTaskKey | gitlab | issue | - | - | ○ | ○(issue_iid) |
| GitLabMergeRequestTaskKey | gitlab | merge_request | - | - | ○ | ○(mr_iid) |

これらを統一的に扱うため、以下のフィールド構成でtask_keyを分解する：
- `task_source`: タスクソース（github/gitlab）
- `task_type`: タスクタイプ（issue/pull_request/merge_request）
- `owner`: GitHubリポジトリオーナー（GitLabの場合はNULL）
- `repo`: GitHubリポジトリ名（GitLabの場合はNULL）
- `project_id`: GitLabプロジェクトID（GitHubの場合はNULL）
- `number`: タスク番号（GitHub: number、GitLab: issue_iid/mr_iid）

---

## 2. 詳細設計

### 2.1 ファイル構成
1ファイルにDBTaskモデルとDBアクセスロジックをまとめる：

```
db/
└── task_db.py    # DBTaskモデル定義 + TaskDBManagerクラス
```

### 2.2 task_db.py の設計

#### 2.2.1 DBTask モデル
SQLAlchemy ORMを使用してtasksテーブルを定義する。

**処理内容**:
- SQLAlchemy 2.0スタイルの宣言的ベースクラスを使用する
- PostgreSQL用の型定義を行う
- task_key分解フィールドのインデックスを定義する
- `get_task_key()` メソッドでTaskKeyオブジェクトを復元する

**カラム定義**:
| カラム名 | 型 | PostgreSQL型 | 制約 | 説明 |
|---------|-----|-------------|------|------|
| uuid | String(36) | VARCHAR(36) | PRIMARY KEY | タスク一意識別子 |
| task_source | String(50) | VARCHAR(50) | NOT NULL | タスクソース（github/gitlab） |
| task_type | String(50) | VARCHAR(50) | NOT NULL | タスクタイプ（issue/pull_request/merge_request） |
| owner | String(255) | VARCHAR(255) | NULL可 | GitHubリポジトリオーナー |
| repo | String(255) | VARCHAR(255) | NULL可 | GitHubリポジトリ名 |
| project_id | String(255) | VARCHAR(255) | NULL可 | GitLabプロジェクトID |
| number | Integer | INTEGER | NOT NULL | タスク番号 |
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
| ix_tasks_task_key | task_source, task_type, owner, repo, project_id, number | TaskKey検索の高速化 |

**DBTaskモデルのメソッド**:
| メソッド名 | 引数 | 戻り値 | 説明 |
|-----------|------|--------|------|
| get_task_key | - | TaskKey | task_key分解フィールドからTaskKeyオブジェクトを復元する |

#### 2.2.2 TaskDBManager クラス
タスクのDB操作を行うロジッククラスを実装する。

**初期化処理**:
- 環境変数またはconfig.yamlからPostgreSQL接続情報を取得する
- SQLAlchemyエンジンを作成する
- セッションファクトリーを初期化する

**接続設定**:
| 環境変数名 | 説明 | デフォルト値 |
|-----------|------|------------|
| DATABASE_HOST | PostgreSQLホスト | localhost |
| DATABASE_PORT | PostgreSQLポート | 5432 |
| DATABASE_NAME | データベース名 | coding_agent |
| DATABASE_USER | ユーザー名 | - |
| DATABASE_PASSWORD | パスワード | - |
| DATABASE_URL | 完全な接続URL（他設定を上書き） | - |

**メソッド定義**:

| メソッド名 | 引数 | 戻り値 | 説明 |
|-----------|------|--------|------|
| create_task | task_data: dict | DBTask | 新規タスクを作成する |
| get_task | uuid: str | DBTask または None | UUIDでタスクを取得する |
| get_task_by_key | task_key: TaskKey | DBTask または None | TaskKeyでタスクを取得する |
| save_task | db_task: DBTask | DBTask | DBTaskオブジェクトを保存（更新）する |

**処理内容**:
- セッション管理をコンテキストマネージャーで自動化する
- 例外発生時の自動ロールバックを実装する
- ログ出力によるデバッグ支援を提供する

### 2.3 既存コード修正設計

#### 2.3.1 TaskContextManager の修正（context_storage/task_context_manager.py）
現在のSQLite直接操作を、TaskDBManagerクラスを使用したアクセスに変更する。

**修正対象メソッド**:
| メソッド | 修正内容 |
|---------|---------|
| `__init__` | TaskDBManagerクラスのインスタンスを作成する |
| `_init_database` | 削除。初期化はTaskDBManagerクラスで行う |
| `_register_or_update_task` | TaskDBManager.create_task または TaskDBManager.save_task を使用する |
| `update_status` | DBTaskオブジェクトを取得し、ステータスを変更後、save_taskを使用する |
| `update_statistics` | DBTaskオブジェクトを取得し、統計情報を更新後、save_taskを使用する |
| `complete` | DBTaskオブジェクトを取得し、完了状態に変更後、save_taskを使用する |
| `stop` | DBTaskオブジェクトを取得し、停止状態に変更後、save_taskを使用する |
| `fail` | DBTaskオブジェクトを取得し、失敗状態に変更後、save_taskを使用する |

### 2.4 設定ファイル設計

#### 2.4.1 config.yaml への追加
以下の設定セクションを追加する：

```yaml
# データベース設定
database:
  # PostgreSQL設定
  host: "localhost"
  port: 5432
  name: "coding_agent"
  user: ""
  password: ""
  
  # コネクションプール設定
  pool_size: 5
  max_overflow: 10
```

### 2.5 DB作成ツール
データベースとテーブルを作成するコマンドラインツールを提供する。

**ファイル**: `scripts/create_db.py`

**処理内容**:
- PostgreSQLに接続する
- tasksテーブルが存在しない場合は作成する
- インデックスを作成する

**使用方法**:
```bash
python scripts/create_db.py
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

## 4. 依存関係

### 4.1 追加パッケージ
以下のパッケージを追加する：

| パッケージ名 | バージョン | 用途 |
|-------------|----------|------|
| sqlalchemy | >=2.0.0 | ORM・DB抽象化 |
| psycopg2-binary | >=2.9.0 | PostgreSQLドライバ |

### 4.2 pyproject.toml / condaenv.yaml への追加
上記パッケージを依存関係に追加する。

---

## 5. テスト設計

### 5.1 ユニットテスト
以下のテストを追加する：

| テストファイル | 対象 | 内容 |
|--------------|------|------|
| test_task_db.py | db/task_db.py | TaskDBManagerクラスのテスト |

### 5.2 テスト用データベース
テスト実行時はテスト用PostgreSQLコンテナを使用する。

---

## 6. 影響範囲

### 6.1 修正対象ファイル
| ファイル | 修正内容 |
|---------|---------|
| context_storage/task_context_manager.py | DB操作をTaskDBManagerクラス経由に変更 |
| config.yaml | database セクションを追加 |
| docker-compose.yml | postgres サービスを追加 |
| pyproject.toml | 依存パッケージを追加 |
| condaenv.yaml | 依存パッケージを追加 |

### 6.2 新規作成ファイル
| ファイル | 内容 |
|---------|------|
| db/task_db.py | DBTaskモデル + TaskDBManagerクラス |
| scripts/create_db.py | DB作成ツール |

---

## 7. 用語集

| 用語 | 説明 |
|------|------|
| ORM | Object-Relational Mapping。オブジェクトとリレーショナルデータベースの間のマッピング |
| コネクションプール | データベース接続を再利用するための接続プール |
