# コーディングエージェント セットアップガイド

本ドキュメントは、コーディングエージェント（coding_agent）のセットアップ手順をまとめたものです。詳細な設定や使用方法については、各詳細ドキュメントを参照してください。

---

## 1. 前提条件

### 1.1 必要なソフトウェア

- **Python 3.13以上**: 本プロジェクトの実行環境
- **Docker**: MCPサーバーおよびRabbitMQの実行
- **Docker Compose**: 複数コンテナの管理

### 1.2 必要なアカウントとトークン

- **GitHub Personal Access Token**: GitHub操作用（GitHubをタスクソースとする場合）
- **GitLab Personal Access Token**: GitLab操作用（GitLabをタスクソースとする場合）
- **OpenAI API Key**: OpenAI LLMを使用する場合

---

## 2. インストール手順

### 2.1 リポジトリのクローン

リポジトリをローカル環境にクローンします。

### 2.2 Python環境のセットアップ

condaenvまたはrequirements.txtを使用して、必要なPythonパッケージをインストールします。

condaを使用する場合は、condaenv.yamlを使用して環境を作成します。

pipを使用する場合は、requirements.txtを使用してパッケージをインストールします。

### 2.3 設定ファイルの準備

config.yamlを作成し、以下の項目を設定します：

- **LLMプロバイダー設定**: 使用するLLM（openai/ollama/lmstudio）と接続情報
- **MCPサーバー設定**: 使用するMCPサーバーのコマンドと設定
- **GitHub/GitLab設定**: リポジトリオーナー、ラベル名など
- **RabbitMQ設定**: メッセージキューの接続情報（分散環境の場合）

---

## 3. 環境変数の設定

### 3.1 必須環境変数

- **GITHUB_PERSONAL_ACCESS_TOKEN**: GitHub API操作用トークン
- **GITLAB_PERSONAL_ACCESS_TOKEN**: GitLab API操作用トークン（GitLab使用時）
- **OPENAI_API_KEY**: OpenAI API Key（OpenAI使用時）

### 3.2 オプション環境変数

- **TASK_SOURCE**: タスクソース（github/gitlab）
- **LLM_PROVIDER**: LLMプロバイダー（openai/ollama/lmstudio）
- **LOGS**: ログファイルのパス
- **DEBUG**: デバッグモードの有効化

---

## 4. 実行方法

### 4.1 単発実行

main.pyを直接実行することで、タスクの取得と処理を行います。

**Producerモード**: タスクを取得してキューに投入

**Consumerモード**: キューからタスクを取得して処理

**両方同時実行**: モード指定なしで実行

### 4.2 継続動作モード

--continuousオプションを指定することで、継続的にタスクを処理します。

**Producer継続動作**: 設定した間隔でタスク取得をループ実行

**Consumer継続動作**: タスクがあれば即座に処理、なければ待機

### 4.3 Docker Compose実行

docker-compose.ymlを使用して、ProducerとConsumerを別々のコンテナとして実行します。

---

## 5. 一時停止・再開機能

### 5.1 タスクの一時停止

実行中のタスクを一時停止するには、pause_signalファイルを作成します。

Consumerは次のチェックポイントで一時停止シグナルを検出し、現在の状態を保存して終了します。

### 5.2 タスクの再開

一時停止されたタスクは、次回Producerモードを実行した際に自動的にキューに再投入されます。

その後、Consumerモードで処理を再開します。

### 5.3 詳細設定

一時停止・再開機能の詳細な設定については、config.yamlのpause_resumeセクションで設定します。

→ 詳細は [docs/setup/PAUSE_RESUME_USAGE.md](docs/setup/PAUSE_RESUME_USAGE.md) を参照

---

## 6. ラベル管理

### 6.1 使用するラベル

本システムでは、以下のラベルを使用してタスクの状態を管理します：

- **coding agent**: タスクとして処理対象とするためのラベル
- **coding agent processing**: 処理中のタスクに付与されるラベル
- **coding agent done**: 処理完了したタスクに付与されるラベル
- **coding agent paused**: 一時停止中のタスクに付与されるラベル
- **coding agent stopped**: 停止したタスクに付与されるラベル

### 6.2 ラベルの作成

GitHub/GitLabのリポジトリ設定で、上記ラベルを事前に作成してください。

---

## 7. トラブルシューティング

### 7.1 一時停止が実行されない場合

- pause_signalファイルが正しい場所（contexts/pause_signal）にあることを確認
- config.yamlのpause_resume.enabledがtrueであることを確認
- Consumerプロセスのログを確認

### 7.2 再開時にエラーが発生する場合

- contexts/paused/{uuid}/task_state.jsonが正しく保存されているか確認
- GitHub/GitLabでタスクが削除されていないか確認
- ログファイルでエラーの詳細を確認

### 7.3 MCPサーバーに接続できない場合

- Dockerが正常に動作しているか確認
- config.yamlのmcp_servers設定が正しいか確認
- 環境変数（GITHUB_PERSONAL_ACCESS_TOKEN等）が設定されているか確認

### 7.4 LLMに接続できない場合

- LLMプロバイダーの設定（base_url、api_key等）が正しいか確認
- ネットワーク接続を確認
- LLMサーバー（Ollama、LM Studio）が起動しているか確認

---

## 8. セキュリティ上の注意

### 8.1 トークン管理

- 環境変数でトークンを管理し、設定ファイルに直接記載しない
- トークンには最小限の権限のみを付与

### 8.2 コンテキストデータ

- contexts/ディレクトリには機密情報が含まれる可能性があるため、適切なアクセス権限を設定
- 一時停止状態のバックアップを定期的に取ることを推奨

---

## 9. 関連ドキュメント

- **基本仕様**: [docs/spec_all.md](docs/spec_all.md)
- **一時停止・再開の使い方**: [docs/setup/PAUSE_RESUME_USAGE.md](docs/setup/PAUSE_RESUME_USAGE.md)
- **継続動作モード**: [docs/spec/CONTINUOUS_MODE_SPECIFICATION.md](docs/spec/CONTINUOUS_MODE_SPECIFICATION.md)

---

**文書バージョン:** 1.0  
**最終更新日:** 2024-11-28  
**ステータス:** セットアップガイド
