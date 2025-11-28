# コーディングエージェント 仕様書

本ドキュメントは、コーディングエージェント（coding_agent）プロジェクトの全体仕様を統合したものです。各機能の詳細については、それぞれの仕様書を参照してください。

---

## 1. プロジェクト概要

### 1.1 目的

本プロジェクトは、GitHub Copilot Coding Agentのようなコーディングエージェントを構築することを目的としています。GitHubやGitLabのIssue、Pull Request、Merge Requestに対して、LLM（大規模言語モデル）を活用して自動的にコード変更や対応を行います。

### 1.2 主要機能

- **タスク取得**: GitHub/GitLabから特定ラベルが付与されたIssue/PR/MRをタスクとして取得
- **LLM対話**: OpenAI、Ollama、LM Studio等のLLMプロバイダーと連携
- **MCP連携**: Model Context Protocol（MCP）サーバーを通じてGitHub/GitLabの操作を実行
- **コンテキスト管理**: 会話履歴の管理と自動圧縮
- **一時停止・再開**: タスク処理の一時停止と状態保存からの再開
- **タスク停止**: アサイン解除によるタスクの停止
- **継続動作モード**: Docker Composeによる継続的なタスク処理
- **ユーザー設定管理**: ユーザーごとのLLM設定の管理

### 1.3 詳細仕様

→ 詳細は [spec.md](spec/spec.md) を参照

---

## 2. システムアーキテクチャ

### 2.1 全体構成

本システムは以下のコンポーネントで構成されています：

- **main.py**: メインエントリーポイント、Producer/Consumerモードの制御
- **TaskGetter**: GitHub/GitLabからタスクを取得する抽象クラスと具象クラス
- **Task**: タスクを表現する抽象クラスと具象クラス（Issue/PR/MR対応）
- **TaskHandler**: タスク処理のオーケストレーション
- **LLMClient**: 各LLMプロバイダーへのインターフェース
- **MCPToolClient**: MCPサーバーとの通信クライアント
- **TaskQueue**: タスクキュー管理（インメモリまたはRabbitMQ）

### 2.2 処理フロー

1. Producerモードでタスク一覧を取得し、キューに投入
2. Consumerモードでキューからタスクを取得
3. タスクに対してLLMとMCPサーバーを用いて処理を実行
4. 処理完了後、タスクの状態を更新

### 2.3 詳細仕様

→ 詳細は [class_spec.md](spec/class_spec.md) を参照

---

## 3. コンテキスト管理

### 3.1 概要

LLMとの会話履歴（コンテキスト）を効率的に管理するための仕組みです。メモリ消費を抑えながら、長時間の処理に対応します。

### 3.2 主要機能

- **ファイルベース管理**: 会話履歴をJSONL形式でファイルに保存
- **コンテキスト圧縮**: トークン数が閾値を超えた場合に要約を生成
- **状態管理**: SQLiteデータベースでタスク状態を一元管理
- **UUID管理**: 各タスクに一意のUUIDを割り当て

### 3.3 ディレクトリ構造

contextsディレクトリ配下に以下の構造でファイルを管理します：

- **tasks.db**: タスク状態管理データベース
- **running/**: 実行中タスクのコンテキスト
- **completed/**: 完了済みタスクのコンテキスト
- **paused/**: 一時停止中タスクのコンテキスト

### 3.4 詳細仕様

→ 詳細は [context_file_spec.md](spec/context_file_spec.md) および [CONTEXT_STORAGE_IMPLEMENTATION.md](spec/CONTEXT_STORAGE_IMPLEMENTATION.md) を参照

---

## 4. 計画実行モード（Planning）

### 4.1 概要

タスク処理を計画フェーズと実行フェーズに分割し、より構造化されたタスク処理を実現します。

### 4.2 主要機能

- **計画フェーズ**: タスクの分析と実行計画の作成
- **実行フェーズ**: 計画に基づいたアクションの順次実行
- **振り返りフェーズ**: 実行結果の評価と計画の修正
- **チェックリスト管理**: 進捗状況の可視化

### 4.3 処理フロー

1. タスク内容を分析し、実行計画を作成
2. 計画に基づいてアクションを順次実行
3. 各アクション完了後に振り返りを実施
4. 必要に応じて計画を修正
5. 全アクション完了で処理終了

### 4.4 詳細仕様

→ 詳細は [PLANNING_SPECIFICATION.md](spec/PLANNING_SPECIFICATION.md) を参照

---

## 5. 一時停止・再開機能

### 5.1 概要

実行中のタスク処理を一時停止し、後から同じ状態から再開できる機能です。

### 5.2 主要機能

- **シグナルファイル検知**: pause_signalファイルの存在で一時停止を検知
- **状態保存**: 一時停止時にコンテキストと状態を保存
- **自動再開**: 次回Producer実行時に一時停止タスクを自動的にキューに再投入
- **ラベル管理**: 一時停止状態をラベルで可視化

### 5.3 処理フロー

1. pause_signalファイルを検知
2. 現在のコンテキストをpausedディレクトリに保存
3. ラベルを「coding agent paused」に変更
4. 再開時、pausedディレクトリからコンテキストを復元
5. 処理を継続

### 5.4 詳細仕様

→ 詳細は [PAUSE_RESUME_SPECIFICATION.md](spec/PAUSE_RESUME_SPECIFICATION.md) を参照

---

## 6. タスク停止機能

### 6.1 概要

Issue/PR/MRからコーディングエージェントのアサインを解除することで、タスクを停止する機能です。

### 6.2 主要機能

- **アサイン状況監視**: 定期的にアサイン状況をチェック
- **停止処理**: アサイン解除検出時にタスクを停止
- **状態保存**: 停止時にコンテキストをcompletedディレクトリに移動
- **ラベル管理**: 停止状態をラベルで可視化

### 6.3 一時停止との違い

| 項目 | 一時停止 | 停止 |
|------|---------|------|
| トリガー | pause_signalファイル | アサイン解除 |
| 再開可能性 | 可能 | 不可（新規タスクとして開始） |
| 状態保存先 | paused/ | completed/ |
| ラベル | coding agent paused | coding agent stopped |

### 6.4 詳細仕様

→ 詳細は [TASK_STOP_SPECIFICATION.md](spec/TASK_STOP_SPECIFICATION.md) を参照

---

## 7. 新規コメント検知機能

### 7.1 概要

タスク処理中に追加されたユーザーコメントを検知し、LLMコンテキストに反映する機能です。

### 7.2 主要機能

- **コメント監視**: 一時停止チェックと同じタイミングでコメントをチェック
- **差分検知**: 前回チェック時以降の新規コメントを特定
- **ボット除外**: 自身（ボット）のコメントは除外
- **コンテキスト追加**: 新規コメントをLLMに通知

### 7.3 処理フロー

1. 現在のコメント一覧を取得
2. 前回取得時のコメントIDと比較
3. ボットのコメントを除外
4. 新規コメントをLLMコンテキストに追加

### 7.4 詳細仕様

→ 詳細は [COMMENT_DETECTION_SPECIFICATION.md](spec/COMMENT_DETECTION_SPECIFICATION.md) を参照

---

## 8. 継続動作モード

### 8.1 概要

Docker Composeを使用して、ProducerとConsumerをそれぞれ独立したコンテナとして継続的に動作させるモードです。

### 8.2 主要機能

- **Producer継続動作**: 設定した間隔でタスク取得をループ実行
- **Consumer継続動作**: タスクがあれば即座に処理、なければ待機
- **Gracefulシャットダウン**: シグナルファイルによる安全な停止
- **スケールアウト**: 複数Consumerの並列実行

### 8.3 コマンドラインオプション

main.pyに--continuousオプションを追加して継続動作モードを有効化します。

### 8.4 詳細仕様

→ 詳細は [CONTINUOUS_MODE_SPECIFICATION.md](spec/CONTINUOUS_MODE_SPECIFICATION.md) を参照

---

## 9. プロジェクトエージェントルール

### 9.1 概要

プロジェクトごとの個別設定やルールを定義し、エージェントの動作をカスタマイズする機能です。

### 9.2 主要機能

- **ルールファイル**: プロジェクトルートの設定ファイルでルールを定義
- **システムプロンプト拡張**: プロジェクト固有のプロンプトを追加
- **ツール制限**: 使用可能なMCPツールを制限
- **ファイルパターン**: 操作対象ファイルの制限

### 9.3 詳細仕様

→ 詳細は [PROJECT_AGENT_RULES_SPECIFICATION.md](spec/PROJECT_AGENT_RULES_SPECIFICATION.md) を参照

---

## 10. プロジェクトファイル一覧の初期コンテキスト化

### 10.1 概要

IssueやMerge Request/Pull Requestの処理を行う際、対象プロジェクトのファイル一覧を初期コンテキストに含める機能です。

### 10.2 主要機能

- **自動取得**: タスク処理開始時にローカルgitリポジトリからファイル一覧を自動取得
- **階層制限**: 取得するディレクトリ階層を制限可能（デフォルト: 無制限）
- **フォーマット**: フラットリスト形式で出力
- **格納位置**: システムプロンプト末尾に追加

### 10.3 期待効果

- エージェントがプロジェクト構造を把握した状態で処理開始
- ファイル一覧取得のためのツール呼び出しを削減
- より適切な判断による処理品質の向上

### 10.4 詳細仕様

→ 詳細は [PROJECT_FILE_LIST_CONTEXT_SPECIFICATION.md](spec/PROJECT_FILE_LIST_CONTEXT_SPECIFICATION.md) を参照

---

## 11. ユーザー設定管理

### 11.1 概要

ユーザーごとにLLMのAPIキーやモデル設定を管理する機能です。

### 11.2 主要機能

- **REST API**: コーディングエージェントからの設定取得
- **Streamlit管理画面**: ブラウザからの設定管理
- **Active Directory認証**: 企業環境での認証連携
- **データベース管理**: SQLAlchemyによる設定の永続化

### 11.3 システム構成

- **FastAPIサーバー（ポート8080）**: 設定取得API
- **Streamlitサーバー（ポート8501）**: 管理画面

### 11.4 詳細仕様

→ 詳細は [USER_CONFIG_WEB_SPECIFICATION.md](spec/USER_CONFIG_WEB_SPECIFICATION.md) および [user_management_api_spec.md](spec/user_management_api_spec.md) を参照

---

## 12. Command Executor MCP Server連携

### 12.1 概要

コーディングエージェントからCommand Executor MCP Serverを使用してコマンド実行を行う機能です。ビルド、テスト、リンター等のコマンドを安全なDocker環境で実行します。

### 12.2 主要機能

- **Docker実行環境**: タスク毎に独立したDockerコンテナを作成
- **プロジェクトクローン**: Git経由でプロジェクトファイルを自動ダウンロード
- **コマンド実行**: MCPプロトコル経由でコマンドを実行
- **自動クリーンアップ**: タスク終了時にコンテナを自動削除

### 12.3 処理フロー

1. タスク開始時にDockerコンテナを作成
2. プロジェクトリポジトリをクローン
3. 必要に応じて依存関係をインストール
4. MCPプロトコル経由でコマンドを実行
5. タスク終了時にコンテナを削除

### 12.4 詳細仕様

→ 詳細は [COMMAND_EXECUTOR_MCP_SPECIFICATION.md](spec/COMMAND_EXECUTOR_MCP_SPECIFICATION.md) を参照

---

## 13. 外部API仕様

本プロジェクトで使用する外部APIの仕様については、以下を参照してください。

- **OpenAI API**: [external-api/openai.md](external-api/openai.md)
- **Ollama API**: [external-api/ollama.md](external-api/ollama.md)
- **LM Studio API**: [external-api/lmstudio.md](external-api/lmstudio.md)
- **MCP Client**: [external-api/mcp_client.md](external-api/mcp_client.md)
- **GitHub MCP Server**: [external-api/github-mcp-server.md](external-api/github-mcp-server.md)
- **GitLab MCP Server**: [external-api/gitlab-mcp-server.md](external-api/gitlab-mcp-server.md)

---

## 14. 仕様書一覧

| ファイル名 | 内容 |
|-----------|------|
| [spec.md](spec/spec.md) | プロジェクト基本仕様 |
| [class_spec.md](spec/class_spec.md) | クラス設計・関係図 |
| [context_file_spec.md](spec/context_file_spec.md) | コンテキストファイル化仕様 |
| [CONTEXT_STORAGE_IMPLEMENTATION.md](spec/CONTEXT_STORAGE_IMPLEMENTATION.md) | コンテキストストレージ実装仕様 |
| [PLANNING_SPECIFICATION.md](spec/PLANNING_SPECIFICATION.md) | 計画実行モード仕様 |
| [PAUSE_RESUME_SPECIFICATION.md](spec/PAUSE_RESUME_SPECIFICATION.md) | 一時停止・再開機能仕様 |
| [TASK_STOP_SPECIFICATION.md](spec/TASK_STOP_SPECIFICATION.md) | タスク停止機能仕様 |
| [COMMENT_DETECTION_SPECIFICATION.md](spec/COMMENT_DETECTION_SPECIFICATION.md) | 新規コメント検知機能仕様 |
| [CONTINUOUS_MODE_SPECIFICATION.md](spec/CONTINUOUS_MODE_SPECIFICATION.md) | 継続動作モード仕様 |
| [PROJECT_AGENT_RULES_SPECIFICATION.md](spec/PROJECT_AGENT_RULES_SPECIFICATION.md) | プロジェクトエージェントルール仕様 |
| [PROJECT_FILE_LIST_CONTEXT_SPECIFICATION.md](spec/PROJECT_FILE_LIST_CONTEXT_SPECIFICATION.md) | プロジェクトファイル一覧コンテキスト仕様 |
| [USER_CONFIG_WEB_SPECIFICATION.md](spec/USER_CONFIG_WEB_SPECIFICATION.md) | ユーザー設定Web仕様 |
| [user_management_api_spec.md](spec/user_management_api_spec.md) | ユーザー管理API仕様 |
| [COMMAND_EXECUTOR_MCP_SPECIFICATION.md](spec/COMMAND_EXECUTOR_MCP_SPECIFICATION.md) | Command Executor MCP Server連携仕様 |

---

**文書バージョン:** 1.0  
**最終更新日:** 2024-11-28  
**ステータス:** 統合ドキュメント
