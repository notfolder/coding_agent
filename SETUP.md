# コーディングエージェント セットアップガイド

本ドキュメントは、コーディングエージェント（coding_agent）のセットアップ手順をまとめたものです。

---

## 1. 前提条件

### 1.1 必要なソフトウェア

- **Docker**: MCPサーバー、RabbitMQ、PostgreSQLの実行
- **Docker Compose**: 複数コンテナの管理

### 1.2 必要なアカウントとトークン

以下のいずれかは必須です：

- **GitHub Personal Access Token**: GitHub操作用（GitHubをタスクソースとする場合）
  - 必要なスコープ: `repo`（リポジトリへのフルアクセス）
  - 取得方法: https://github.com/settings/tokens

- **GitLab Personal Access Token**: GitLab操作用（GitLabをタスクソースとする場合）
  - 必要なスコープ: `api`（API全般へのアクセス）
  - 取得方法: https://gitlab.com/-/profile/personal_access_tokens

LLMプロバイダーのいずれかも必須です：

- **OpenAI API Key**: OpenAI LLMを使用する場合（推奨）
  - 取得方法: https://platform.openai.com/api-keys

- **LM Studio**: ローカルLLMを使用する場合
- **Ollama**: ローカルLLMを使用する場合

---

## 2. セットアップ手順

### 2.1 リポジトリのクローン

```bash
git clone https://github.com/notfolder/coding_agent.git
cd coding_agent
```

### 2.2 環境変数の設定

`.env.sample`をコピーして`.env`ファイルを作成します：

```bash
cp .env.sample .env
```

`.env`ファイルを編集し、以下の**必須項目**を設定します：

#### GitHub使用時の必須設定

```bash
TASK_SOURCE=github
GITHUB_PERSONAL_ACCESS_TOKEN=ghp_your_github_token_here
```

#### GitLab使用時の必須設定

```bash
TASK_SOURCE=gitlab
GITLAB_PERSONAL_ACCESS_TOKEN=glpat_your_gitlab_token_here
GITLAB_API_URL=https://gitlab.com/api/v4
```

#### LLM設定（OpenAI推奨）

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your_openai_api_key_here
```

**または** LM Studio使用時：

```bash
LLM_PROVIDER=lmstudio
LMSTUDIO_BASE_URL=host.docker.internal:1234
LMSTUDIO_MODEL=your-model-name
```

**または** Ollama使用時：

```bash
LLM_PROVIDER=ollama
OLLAMA_ENDPOINT=http://host.docker.internal:11434
OLLAMA_MODEL=your-model-name
```

**注意**: Docker環境からホストマシンのLLMサーバーにアクセスする場合は `host.docker.internal` を使用します。

### 2.3 config.yamlの確認

`config.yaml`はデフォルト設定で動作しますが、必要に応じて以下を調整できます：

- **github/gitlab**: リポジトリオーナー、ラベル名
- **llm**: LLMモデル、パラメータ
- **planning**: プランニング機能の設定
- **command_executor**: 実行環境の設定

**重要**: APIキーやトークンは`config.yaml`に直接記載せず、必ず環境変数（`.env`）で設定してください。

### 2.4 GitHubリポジトリでのラベル作成

GitHubリポジトリの設定でラベルを作成します：

1. リポジトリの **Settings** → **Labels** に移動
2. 以下のラベルを作成：

| ラベル名 | 色 | 説明 |
|---------|-----|------|
| `coding agent` | `#0E8A16` | タスク対象 |
| `coding agent processing` | `#FBCA04` | 処理中 |
| `coding agent done` | `#1D76DB` | 完了 |
| `coding agent paused` | `#D93F0B` | 一時停止 |
| `coding agent stopped` | `#E99695` | 停止 |

### 2.5 GitLabプロジェクトでのラベル作成

GitLabプロジェクトの設定でラベルを作成します：

1. プロジェクトの **Settings** → **Labels** に移動
2. 上記と同じラベルを作成

---

## 3. 起動方法（Docker Compose）

### 3.1 起動

```bash
docker-compose up -d
```

このコマンドで以下のサービスが起動します：

- **postgres**: PostgreSQLデータベース
- **rabbitmq**: RabbitMQメッセージキュー
- **producer**: タスク取得サービス（定期実行）
- **consumer**: タスク処理サービス（継続実行）

### 3.2 ログ確認

```bash
# 全サービスのログを確認
docker-compose logs -f

# 特定サービスのログを確認
docker-compose logs -f producer
docker-compose logs -f consumer
```

### 3.3 停止

**一時停止シグナルを使用した停止（推奨）:**

```bash
# 一時停止シグナルを作成
touch contexts/pause_signal

# サービスを停止
docker-compose down
```

**即座に停止:**

```bash
docker-compose down
```

### 3.4 再開

```bash
# 一時停止シグナルを削除
rm -f contexts/pause_signal

# サービスを起動
docker-compose up -d
```

---

## 4. 使用方法

### 4.1 タスクの作成

1. GitHubでIssueまたはPull Requestを作成
2. `coding agent`ラベルを付与
3. 詳細な要件を記述

**例**:
```markdown
## やりたいこと
READMEにプロジェクトの概要を追加してください。

## 詳細
- プロジェクト名: coding_agent
- 目的: LLMを使用したコーディングエージェント
- 主要機能: GitHub/GitLabとの連携、プランニングモード、実行環境管理
```

### 4.2 タスクの処理

Producerが定期的にタスクをキューに追加し、Consumerが処理を実行します：

1. タスクに`coding agent processing`ラベルが付与される
2. プランニングフェーズで計画が作成される
3. 実行フェーズでコード変更が行われる
4. 検証フェーズで結果が確認される
5. 完了すると`coding agent done`ラベルが付与される

### 4.3 進捗確認

Issue/PR/MRのコメント欄で進捗を確認できます：

- **進捗コメント**: タスクの実行状況をリアルタイム更新
- **チェックリスト**: 計画の進行状況を視覚化
- **エラー通知**: 問題が発生した場合の詳細

---

## 5. 一時停止・再開

### 5.1 タスクの一時停止

実行中のタスクを一時停止するには：

```bash
touch contexts/pause_signal
```

Consumerは次のチェックポイントで一時停止シグナルを検出し、現在の状態を保存して終了します。

### 5.2 タスクの再開

一時停止されたタスクは、次回Producerモードを実行した際に自動的にキューに再投入されます：

```bash
rm contexts/pause_signal
docker-compose up -d
```

詳細は [docs/setup/PAUSE_RESUME_USAGE.md](docs/setup/PAUSE_RESUME_USAGE.md) を参照してください。

---

## 6. ユーザー設定API（オプション）

ユーザーごとのLLM設定を管理する場合、User Config APIを使用できます。

### 6.1 有効化

`.env`ファイルに以下を追加：

```bash
USE_USER_CONFIG_API=true
USER_CONFIG_API_URL=http://user-config-api:8080
USER_CONFIG_API_KEY=your-secret-api-key
```

### 6.2 管理画面

ブラウザで http://localhost:8501 にアクセスし、ユーザー設定を管理できます。

詳細は [USER_CONFIG_SETUP.md](USER_CONFIG_SETUP.md) を参照してください。

---

## 7. トラブルシューティング

### 7.1 一時停止が実行されない場合

- `contexts/pause_signal`ファイルが正しい場所にあることを確認
- `config.yaml`の`pause_resume.enabled`が`true`であることを確認
- Consumerプロセスのログを確認

### 7.2 タスクが取得されない場合

- GitHub/GitLab Personal Access Tokenが正しく設定されているか確認
- ラベル名が`config.yaml`の設定と一致しているか確認
- Producerのログでエラーがないか確認

### 7.3 LLMに接続できない場合

- LLMプロバイダーの設定（`OPENAI_API_KEY`等）が正しいか確認
- ローカルLLMの場合、サーバーが起動しているか確認
- ネットワーク接続を確認

### 7.4 MCPサーバーに接続できない場合

- Dockerが正常に動作しているか確認
- 環境変数（`GITHUB_PERSONAL_ACCESS_TOKEN`等）が設定されているか確認
- MCPサーバーのログを確認

### 7.5 データベースに接続できない場合

- PostgreSQLコンテナが起動しているか確認：`docker-compose ps`
- データベース設定が正しいか確認
- ネットワーク接続を確認

---

## 8. セキュリティ上の注意

### 8.1 トークン管理

- 環境変数でトークンを管理し、設定ファイルに直接記載しない
- `.env`ファイルをGitにコミットしない（`.gitignore`に含まれています）
- トークンには最小限の権限のみを付与

### 8.2 コンテキストデータ

- `contexts/`ディレクトリには機密情報が含まれる可能性があるため、適切なアクセス権限を設定
- 一時停止状態のバックアップを定期的に取ることを推奨

### 8.3 ユーザー設定API

- `USER_CONFIG_API_KEY`は強力なランダム文字列を使用
- 本番環境ではHTTPS（TLS 1.2以上）を必須とする
- `ENCRYPTION_KEY`は32バイトのランダムバイト列を使用

---

## 9. 関連ドキュメント

### 9.1 仕様書

- **統合仕様書**: [docs/SPEC.md](docs/SPEC.md)
- **クラス設計**: [docs/CLASS_SPEC.md](docs/CLASS_SPEC.md)

### 9.2 個別仕様書

- **プランニング**: [docs/spec/PLANNING_SPECIFICATION.md](docs/spec/PLANNING_SPECIFICATION.md)
- **一時停止・再開**: [docs/spec/PAUSE_RESUME_SPECIFICATION.md](docs/spec/PAUSE_RESUME_SPECIFICATION.md)
- **コマンド実行環境**: [docs/spec/COMMAND_EXECUTOR_MCP_SPECIFICATION.md](docs/spec/COMMAND_EXECUTOR_MCP_SPECIFICATION.md)
- **テキストエディタMCP**: [docs/spec/TEXT_EDITOR_MCP_SPECIFICATION.md](docs/spec/TEXT_EDITOR_MCP_SPECIFICATION.md)
- **ユーザー設定Web**: [docs/spec/USER_CONFIG_WEB_SPECIFICATION.md](docs/spec/USER_CONFIG_WEB_SPECIFICATION.md)

### 9.3 その他

- **ユーザー設定APIセットアップ**: [USER_CONFIG_SETUP.md](USER_CONFIG_SETUP.md)
- **一時停止・再開の使い方**: [docs/setup/PAUSE_RESUME_USAGE.md](docs/setup/PAUSE_RESUME_USAGE.md)

---

## 10. よくある質問

### Q1. Docker Composeを使わずに実行できますか？

A1. 可能ですが、RabbitMQとPostgreSQLを別途セットアップする必要があります。Python環境を準備し、`python main.py`で実行できます。

### Q2. 複数のリポジトリを同時に監視できますか？

A2. 現在は1つのリポジトリのみをサポートしています。複数リポジトリを監視する場合は、それぞれ別のインスタンスを起動してください。

### Q3. GitHubとGitLabを同時に使用できますか？

A3. いいえ、`TASK_SOURCE`で一方のみを指定できます。両方を使用する場合は、それぞれ別のインスタンスを起動してください。

### Q4. タスクの実行時間に制限はありますか？

A4. デフォルトでは制限がありませんが、`command_executor.execution.timeout_seconds`で設定できます。

### Q5. プランニング機能を無効にできますか？

A5. `config.yaml`の`planning.enabled`を`false`に設定することで無効にできます。

---

**文書バージョン:** 3.0  
**最終更新日:** 2024-12-07  
**ステータス:** 最新版
