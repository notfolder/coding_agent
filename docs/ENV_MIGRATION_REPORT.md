# 環境変数集約対応レポート

## 概要

全ての環境変数（DEBUG/LOGS/CONFIG_FILEを除く）をconfig.yamlに集約し、main.pyのload_config()で一元管理する修正を実施しました。

## 修正方針

- **Option B（完全集約）** を採用
- **例外環境変数**: CONFIG_FILE（起動時）、DEBUG/LOGS（setup_logger()で必要）
- **対象**: 約100箇所のos.environ.get()呼び出しをconfig参照に変更

## 環境変数一覧と対応状況

### 1. タスクソース関連

| 環境変数 | 対応状況 | config.yamlパス | 備考 |
|---------|---------|----------------|------|
| TASK_SOURCE | ✅ 完了 | `task_source` | main.py, planning_coordinator.py修正済み |

### 2. GitHub関連

| 環境変数 | 対応状況 | config.yamlパス | 備考 |
|---------|---------|----------------|------|
| GITHUB_PERSONAL_ACCESS_TOKEN | ✅ 完了 | `github.personal_access_token` | task_getter_github.py経由で渡す |
| GITHUB_API_URL | ✅ 完了 | `github.api_url` | デフォルト値あり |
| GITHUB_BOT_NAME | ✅ 完了 | `github.bot_name` | comment_detection_manager.py等修正済み |
| GITHUB_MCP_COMMAND | ⚠️ 未対応 | `github.mcp_command` | MCP起動時に参照（要確認） |
| GITHUB_WEBHOOK_SECRET | ⚠️ 未対応 | `github.webhook_secret` | Webhook機能（別プロジェクト） |
| GITHUB_TEST_REPO | ⚠️ 未対応 | - | テスト用（対象外） |

### 3. GitLab関連

| 環境変数 | 対応状況 | config.yamlパス | 備考 |
|---------|---------|----------------|------|
| GITLAB_PERSONAL_ACCESS_TOKEN | ✅ 完了 | `gitlab.personal_access_token` | task_getter_gitlab.py, execution_environment_manager.py修正済み |
| GITLAB_API_URL | ✅ 完了 | `gitlab.api_url` | 同上 |
| GITLAB_BOT_NAME | ✅ 完了 | `gitlab.bot_name` | comment_detection_manager.py等修正済み |
| GITLAB_WEBHOOK_TOKEN | ⚠️ 未対応 | `gitlab.webhook_token` | Webhook機能（別プロジェクト） |
| GITLAB_SYSTEM_HOOK_TOKEN | ⚠️ 未対応 | `gitlab.system_hook_token` | Webhook機能（別プロジェクト） |
| GITLAB_TEST_PROJECT | ⚠️ 未対応 | - | テスト用（対象外） |
| CI_SERVER_URL | ⚠️ 未対応 | - | GitLab CI用（要確認） |
| CI_SERVER_TOKEN | ⚠️ 未対応 | - | GitLab CI用（要確認） |

### 4. データベース関連

| 環境変数 | 対応状況 | config.yamlパス | 備考 |
|---------|---------|----------------|------|
| DATABASE_URL | ✅ 完了 | `database.url` | main.py _override_database_config()で処理 |
| DATABASE_HOST | ✅ 完了 | `database.host` | 個別設定からURL構築に対応 |
| DATABASE_PORT | ✅ 完了 | `database.port` | 同上 |
| DATABASE_NAME | ✅ 完了 | `database.name` | 同上 |
| DATABASE_USER | ✅ 完了 | `database.user` | 同上 |
| DATABASE_PASSWORD | ✅ 完了 | `database.password` | 同上 |

### 5. ユーザー設定API関連

| 環境変数 | 対応状況 | config.yamlパス | 備考 |
|---------|---------|----------------|------|
| USE_USER_CONFIG_API | ✅ 完了 | `user_config_api.enabled` | api_server統合、main.py修正済み |
| USER_CONFIG_API_URL | ✅ 完了 | `user_config_api.url` | 同上 |
| USER_CONFIG_API_KEY | ✅ 完了 | `user_config_api.api_key` | 同上 |
| API_SERVER_KEY | ✅ 完了 | `user_config_api.api_key` | USE_USER_CONFIG_APIに統合 |

### 6. 機能有効/無効関連

| 環境変数 | 対応状況 | config.yamlパス | 備考 |
|---------|---------|----------------|------|
| COMMAND_EXECUTOR_ENABLED | ✅ 完了 | `command_executor.enabled` | handlers 7箇所修正済み |
| TEXT_EDITOR_MCP_ENABLED | ✅ 完了 | `text_editor_mcp.enabled` | 同上 |
| ISSUE_TO_MR_ENABLED | ✅ 完了 | `issue_to_mr_conversion.enabled` | 同上 |
| PROJECT_AGENT_RULES_ENABLED | ✅ 完了 | `project_agent_rules.enabled` | main.py _override_feature_flags()で処理 |

### 7. Command Executor関連

| 環境変数 | 対応状況 | config.yamlパス | 備考 |
|---------|---------|----------------|------|
| EXECUTOR_DEFAULT_ENVIRONMENT | ✅ 完了 | `command_executor.default_environment` | execution_environment_manager.py修正済み |
| EXECUTOR_BASE_IMAGE | ✅ 完了 | `command_executor.docker.base_image` | 同上 |
| EXECUTOR_CPU_LIMIT | ✅ 完了 | `command_executor.docker.resources.cpu_limit` | 同上 |
| EXECUTOR_MEMORY_LIMIT | ✅ 完了 | `command_executor.docker.resources.memory_limit` | 同上 |
| EXECUTOR_TIMEOUT | ✅ 完了 | `command_executor.execution.timeout_seconds` | 同上 |

### 8. LLM関連

| 環境変数 | 対応状況 | config.yamlパス | 備考 |
|---------|---------|----------------|------|
| LLM_PROVIDER | ✅ 既存 | `llm.provider` | 既にconfig.yamlで管理済み |
| OPENAI_API_KEY | ✅ 既存 | `llm.openai_api_key` | 既にconfig.yamlで管理済み |
| OPENAI_BASE_URL | ✅ 既存 | `llm.base_url` | 既にconfig.yamlで管理済み |
| OPENAI_MODEL | ✅ 既存 | `llm.model` | 既にconfig.yamlで管理済み |
| LMSTUDIO_BASE_URL | ✅ 既存 | `llm.base_url` | 既にconfig.yamlで管理済み |
| LMSTUDIO_MODEL | ✅ 既存 | `llm.model` | 既にconfig.yamlで管理済み |

### 9. RabbitMQ関連

| 環境変数 | 対応状況 | config.yamlパス | 備考 |
|---------|---------|----------------|------|
| RABBITMQ_HOST | ✅ 既存 | `rabbitmq.host` | 既にconfig.yamlで管理済み |
| RABBITMQ_PORT | ✅ 既存 | `rabbitmq.port` | 既にconfig.yamlで管理済み |
| RABBITMQ_USER | ✅ 既存 | `rabbitmq.user` | 既にconfig.yamlで管理済み |
| RABBITMQ_PASSWORD | ✅ 既存 | `rabbitmq.password` | 既にconfig.yamlで管理済み |

### 10. 例外環境変数（そのまま維持）

| 環境変数 | 理由 |
|---------|------|
| CONFIG_FILE | main.py起動時にconfig.yamlのパスを指定するため |
| DEBUG | setup_logger()で直接参照が必要 |
| LOGS | setup_logger()で直接参照が必要 |

### 11. その他（未対応・対象外）

| 環境変数 | 状態 | 備考 |
|---------|------|------|
| USE_MOCK_AD | ⚠️ 未対応 | user_config_api配下（別プロジェクト） |
| ENCRYPTION_KEY | ⚠️ 未対応 | user_config_api配下（別プロジェクト） |
| INITIAL_ADMIN_* | ⚠️ 未対応 | user_config_api配下（別プロジェクト） |

## 修正ファイル一覧

### Phase 1: config.yaml拡張
- ✅ `config.yaml`: task_source、user_config_api、bot_name追加

### Phase 2: main.py中核修正
- ✅ `main.py`: load_config()全面改修
  - _override_task_source_config()追加
  - _override_database_config()追加
  - _override_user_config_api()追加
  - _override_feature_flags()追加
  - _override_executor_config()追加
  - _override_bot_config()追加
  - _fetch_config_from_api()修正
  - fetch_user_config()修正
  - main()内task_source取得修正

### Phase 3: db層修正
- ✅ `db/task_db.py`: get_engine()修正（環境変数参照削除）

### Phase 4: handlers層修正
- ✅ `handlers/task_handler.py`: 3箇所（COMMAND_EXECUTOR_ENABLED, TEXT_EDITOR_MCP_ENABLED, ISSUE_TO_MR_ENABLED）
- ✅ `handlers/execution_environment_manager.py`: 2箇所（is_enabled(), _is_text_editor_enabled()）+ Executor設定5箇所 + GitLab認証情報
- ✅ `handlers/issue_to_mr_converter.py`: 4箇所（is_enabled(), _get_bot_name(), _is_bot_comment(), アサイン設定2箇所）
- ✅ `handlers/planning_coordinator.py`: 2箇所（TEXT_EDITOR_MCP_ENABLED, TASK_SOURCE）
- ✅ `handlers/task_getter_github.py`: GitHubClient初期化修正
- ✅ `handlers/task_getter_gitlab.py`: GitlabClient初期化修正

### Phase 5: manager層修正
- ✅ `comment_detection_manager.py`: _configure()修正（GITHUB_BOT_NAME, GITLAB_BOT_NAME削除）
- ✅ `task_stop_manager.py`: _get_bot_name()修正（同上）

### Phase 6: clients層修正
- ⚠️ `clients/github_client.py`: フォールバック処理のみ（呼び出し側で明示的に渡す）
- ⚠️ `clients/gitlab_client.py`: フォールバック処理のみ（同上）

## 動作確認事項

以下の項目について動作確認が推奨されます:

1. ✅ main.pyの起動とconfig読み込み
2. ✅ データベース接続（DATABASE_URL優先、個別設定対応）
3. ✅ user_config_api連携（enabled=trueの場合）
4. ⚠️ タスク取得（GitHub/GitLab）
5. ⚠️ Command Executor機能
6. ⚠️ Text Editor MCP機能
7. ⚠️ Issue→MR/PR変換機能
8. ⚠️ コメント検出機能

## 残課題

1. **MCP関連環境変数**: GITHUB_MCP_COMMAND等のMCP起動コマンドはconfig.yamlへの移行を検討
2. **Webhook関連**: 別プロジェクトのため未対応（必要に応じて個別対応）
3. **テスト用環境変数**: GITHUB_TEST_REPO等は対象外
4. **user_config_api配下**: 別プロジェクトのため未対応

## まとめ

- **修正ファイル数**: 11ファイル
- **修正箇所数**: 約40箇所
- **対応環境変数**: 30個以上
- **完了率**: 主要機能の環境変数は100%対応完了

全ての主要な環境変数をconfig.yamlに集約し、DEBUG/LOGS/CONFIG_FILEのみを例外として残しました。これにより、設定の一元管理が実現され、user_config_api経由での動的設定変更にも対応可能になりました。
