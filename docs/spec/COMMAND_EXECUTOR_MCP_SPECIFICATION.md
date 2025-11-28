# Command Executor MCP Server連携仕様書

## 1. 概要

### 1.1 目的

本仕様書は、コーディングエージェントからCommand Executor MCP Serverを使用してコマンド実行を行うための詳細設計を定義します。Command Executor MCP Serverは、MCPプロトコル経由でOSコマンドを安全に実行するためのサーバーです。

### 1.2 背景

コーディングエージェントがGitHub/GitLabのIssueやPull Request/Merge Requestを処理する際、以下のようなコマンド実行が必要になるケースがあります：

- ビルドコマンドの実行（npm build、make、go build等）
- テストコマンドの実行（npm test、pytest、go test等）
- リンターやフォーマッターの実行（eslint、black、gofmt等）
- その他のプロジェクト固有のスクリプト実行

これらのコマンド実行を安全かつ分離された環境で行うため、Dockerコンテナを使用した実行環境を設計します。

### 1.3 要求事項

- Command Executor MCP Serverを使用してコマンド実行をサポートする
- 実行環境はDockerで独立してタスク毎に初期化される
- 実行環境にはあらかじめプロジェクトファイルをダウンロードしておく
- タスク終了時に実行環境を削除する

### 1.4 参照ドキュメント

- [Command Executor MCP Server（外部）](https://zenn.dev/sunwood_ai_labs/articles/command-executor-mcp-server-v0-1-0-release)
- [基本仕様](spec.md)
- [継続動作モード仕様](CONTINUOUS_MODE_SPECIFICATION.md)

---

## 2. システムアーキテクチャ

### 2.1 全体構成図

```mermaid
flowchart TD
    subgraph CodingAgent[コーディングエージェント]
        TaskHandler[TaskHandler]
        MCPClient[MCPToolClient]
        ExecutionManager[ExecutionEnvironmentManager]
    end
    
    subgraph CommandExecutor[Command Executor MCP Server]
        CommandMCP[MCP Server]
    end
    
    subgraph DockerHost[Docker Host]
        DockerAPI[Docker API]
        subgraph ExecutionContainer[実行環境コンテナ]
            ProjectFiles[プロジェクトファイル]
            WorkDir[作業ディレクトリ]
        end
    end
    
    subgraph GitPlatform[Git Platform]
        GitHub[GitHub]
        GitLab[GitLab]
    end
    
    TaskHandler --> MCPClient
    MCPClient --> CommandMCP
    TaskHandler --> ExecutionManager
    ExecutionManager --> DockerAPI
    DockerAPI --> ExecutionContainer
    ExecutionManager -->|git clone| GitPlatform
    CommandMCP -->|コマンド実行| ExecutionContainer
```

### 2.2 主要コンポーネント

#### ExecutionEnvironmentManager

実行環境の生成、管理、削除を担当するコンポーネントです。

**責務:**
- タスク毎のDockerコンテナの生成
- プロジェクトファイルのダウンロードとマウント
- コンテナの状態監視
- タスク終了時のコンテナ削除

#### Command Executor MCP Server

MCPプロトコルを通じてOSコマンドを実行するサーバーです。

**責務:**
- コーディングエージェントからのコマンド実行要求の受信
- 指定されたDockerコンテナ内でのコマンド実行
- 実行結果の返却

---

## 3. Docker実行環境の設計

### 3.1 コンテナライフサイクル

```mermaid
stateDiagram-v2
    [*] --> Created: タスク開始時
    Created --> Initializing: コンテナ作成
    Initializing --> Ready: プロジェクトファイルダウンロード完了
    Ready --> Running: コマンド実行中
    Running --> Ready: コマンド完了
    Ready --> Stopped: タスク終了
    Running --> Stopped: タスク終了
    Stopped --> Deleted: クリーンアップ
    Deleted --> [*]
```

### 3.2 コンテナの命名規則

コンテナ名は以下の形式で生成します：

```
coding-agent-exec-{task_uuid}
```

- `task_uuid`: タスクに割り当てられた一意のUUID

この命名規則により、タスクとコンテナの紐付けを明確にし、クリーンアップ時の特定を容易にします。

### 3.3 ベースイメージの設定

実行環境のベースイメージは設定ファイルで指定可能とします。デフォルトでは汎用的な開発環境イメージを使用します。

**デフォルトイメージ:**
- Node.js、Python、Go、Java等の主要言語のランタイムを含む
- Git、curl、wget等の基本ツールを含む
- 非rootユーザーで実行

**カスタムイメージ:**
- プロジェクト毎にカスタムイメージを指定可能
- プロジェクトルートの設定ファイルで上書き可能

### 3.4 リソース制限

セキュリティとリソース管理のため、以下の制限を適用します。

**CPU制限:**
- デフォルト: 2コア相当
- 設定ファイルで変更可能

**メモリ制限:**
- デフォルト: 4GB
- 設定ファイルで変更可能

**ディスク制限:**
- 作業ディレクトリのサイズ上限を設定
- デフォルト: 10GB

**実行時間制限:**
- 単一コマンドの最大実行時間
- デフォルト: 30分

### 3.5 ネットワーク設定

**デフォルト設定:**
- 外部ネットワークへのアクセスを許可（パッケージインストール等のため）
- ホストネットワークへのアクセスは制限

**セキュリティ設定:**
- 特定ドメインへのアクセスのみ許可するホワイトリスト方式をオプションで提供
- DNS解決は許可

---

## 4. プロジェクトファイルのダウンロード仕様

### 4.1 ダウンロードフロー

```mermaid
sequenceDiagram
    participant TH as TaskHandler
    participant EM as ExecutionEnvironmentManager
    participant Docker as Docker API
    participant Git as Git Platform

    TH->>EM: 実行環境準備要求(task)
    EM->>Docker: コンテナ作成
    Docker-->>EM: コンテナID
    EM->>Docker: コンテナ起動
    EM->>Docker: git clone実行
    Docker->>Git: リポジトリクローン
    Git-->>Docker: ファイル取得
    Docker-->>EM: クローン完了
    EM->>Docker: ブランチチェックアウト（PR/MRの場合）
    Docker-->>EM: チェックアウト完了
    EM-->>TH: 実行環境準備完了
```

### 4.2 クローン対象の決定

タスクの種類に応じて適切なブランチをクローンします。

**Issueの場合:**
- デフォルトブランチをクローン

**Pull Request/Merge Requestの場合:**
- PRソースブランチをクローン
- マージ先ブランチとの差分を確認可能な状態にする

### 4.3 認証情報の取り扱い

プライベートリポジトリへのアクセスには認証が必要です。

**GitHub:**
- 環境変数`GITHUB_PERSONAL_ACCESS_TOKEN`を使用
- git cloneのURL形式で認証情報を付与

**GitLab:**
- 環境変数`GITLAB_PERSONAL_ACCESS_TOKEN`を使用
- git cloneのURL形式で認証情報を付与

**セキュリティ考慮:**
- 認証情報はコンテナ内に永続化しない
- クローン完了後に認証情報をクリア
- ログに認証情報を出力しない

### 4.4 浅いクローン（Shallow Clone）

大規模リポジトリでの効率化のため、浅いクローンをデフォルトで使用します。

**デフォルト設定:**
- depth: 1（最新コミットのみ）

**フルクローン:**
- 設定でフルクローンを指定可能
- 履歴が必要な操作（blame、log等）の場合に使用

---

## 5. タスク毎の環境初期化仕様

### 5.1 初期化フロー

```mermaid
flowchart TD
    A[タスク開始] --> B[ExecutionEnvironmentManager.prepare]
    B --> C{既存コンテナ確認}
    C -->|存在する| D[既存コンテナ削除]
    C -->|存在しない| E[新規コンテナ作成]
    D --> E
    E --> F[コンテナ起動]
    F --> G[プロジェクトファイルダウンロード]
    G --> H[依存関係インストール]
    H --> I[初期化完了]
    I --> J[タスク処理開始]
```

### 5.2 クリーン環境の保証

各タスクは完全にクリーンな環境で開始されることを保証します。

**初期化時の処理:**
1. 同一task_uuidのコンテナが存在する場合は削除
2. 新規コンテナを作成
3. プロジェクトファイルを新規にクローン
4. 必要に応じて依存関係をインストール

**前タスクの影響排除:**
- ファイルシステムの状態は引き継がない
- 環境変数は引き継がない
- プロセス状態は引き継がない

### 5.3 依存関係の自動インストール

プロジェクトの種類を自動検出し、依存関係をインストールします。

**検出対象:**
- package.json: `npm install` または `yarn install`
- requirements.txt: `pip install -r requirements.txt`
- go.mod: `go mod download`
- pom.xml: `mvn dependency:resolve`
- Gemfile: `bundle install`

**自動インストールの有効/無効:**
- 設定ファイルで制御可能
- デフォルト: 有効

### 5.4 作業ディレクトリの構成

コンテナ内の作業ディレクトリは以下の構成とします。

```
/workspace/
├── project/          # クローンされたプロジェクトファイル
└── tmp/              # 一時ファイル用
```

- `/workspace/project/`: プロジェクトファイルの配置場所
- `/workspace/tmp/`: 一時ファイルの配置場所

---

## 6. コマンド実行仕様

### 6.1 Command Executor MCP Serverとの連携

コーディングエージェントはMCPプロトコルを通じてCommand Executor MCP Serverにコマンド実行を依頼します。

**MCPツール呼び出し形式:**
- ツール名: `command-executor/execute_command`
- コンテナ指定: ExecutionEnvironmentManagerから取得したコンテナIDを使用

### 6.2 コマンド実行フロー

```mermaid
sequenceDiagram
    participant LLM as LLMClient
    participant TH as TaskHandler
    participant MCP as MCPToolClient
    participant CE as CommandExecutor MCP
    participant Container as 実行コンテナ

    LLM->>TH: コマンド実行要求
    TH->>MCP: call_tool(command-executor/execute_command)
    MCP->>CE: execute_command(container_id, command)
    CE->>Container: docker exec
    Container-->>CE: 実行結果
    CE-->>MCP: 結果返却
    MCP-->>TH: ツール結果
    TH->>LLM: 結果送信
```

### 6.3 サポートするコマンドタイプ

**許可されるコマンド:**
- ビルドコマンド（npm、make、gradle等）
- テストコマンド（pytest、jest、go test等）
- リンター・フォーマッター（eslint、black、prettier等）
- バージョン管理コマンド（git status、git diff等）
- ファイル操作（ls、cat、grep等）

**制限されるコマンド:**
- システム管理コマンド（sudo、su等）
- ネットワーク操作コマンド（iptables等）
- デーモン起動コマンド（systemctl等）

### 6.4 実行結果の取得

コマンド実行結果は以下の情報を含みます。

**返却される情報:**
- exit_code: コマンドの終了コード
- stdout: 標準出力の内容
- stderr: 標準エラー出力の内容
- duration: 実行時間（ミリ秒）

**出力の制限:**
- stdout/stderrの最大サイズを制限
- デフォルト: 各1MB
- 超過した場合は末尾を切り詰め

---

## 7. 実行環境の削除仕様

### 7.1 削除トリガー

実行環境は以下のタイミングで削除されます。

**正常終了時:**
- タスク処理が正常に完了した場合
- LLMがdone: trueを返却した場合

**異常終了時:**
- エラーによりタスクが中断された場合
- 最大処理数超過でタスクが終了した場合

**一時停止時:**
- タスクが一時停止された場合
- 再開時に新規コンテナを作成

**タスク停止時:**
- アサイン解除によりタスクが停止された場合

### 7.2 削除フロー

```mermaid
flowchart TD
    A[タスク終了] --> B[ExecutionEnvironmentManager.cleanup]
    B --> C{コンテナ状態確認}
    C -->|実行中| D[コンテナ停止]
    C -->|停止済み| E[コンテナ削除]
    D --> E
    E --> F{関連ボリューム確認}
    F -->|あり| G[ボリューム削除]
    F -->|なし| H[クリーンアップ完了]
    G --> H
```

### 7.3 クリーンアップ処理

**コンテナ削除:**
1. コンテナが実行中の場合は停止（graceful shutdown）
2. 停止猶予時間（デフォルト: 10秒）経過後に強制停止
3. コンテナを削除

**ボリューム削除:**
- コンテナに関連付けられたボリュームを削除
- 匿名ボリュームも含めて削除

**ネットワーク削除:**
- タスク専用のネットワークが作成されていた場合は削除

### 7.4 残存リソースの定期クリーンアップ

異常終了等で削除されなかったリソースを定期的にクリーンアップします。

**クリーンアップ対象:**
- 命名規則に合致するコンテナ（coding-agent-exec-*）
- 作成から一定時間経過したもの（デフォルト: 24時間）

**実行タイミング:**
- Producer起動時
- 設定した間隔での定期実行

---

## 8. エラーハンドリング

### 8.1 エラー種別と対応

#### コンテナ作成エラー

**原因:**
- Docker APIへの接続失敗
- リソース不足
- イメージの取得失敗

**対応:**
1. エラーログを記録
2. Issue/MRにエラーコメントを投稿
3. タスクをエラー状態で終了

#### プロジェクトクローンエラー

**原因:**
- 認証エラー
- ネットワークエラー
- リポジトリが存在しない

**対応:**
1. エラーログを記録
2. 作成したコンテナを削除
3. Issue/MRにエラーコメントを投稿
4. タスクをエラー状態で終了

#### コマンド実行エラー

**原因:**
- コマンドが存在しない
- 権限不足
- タイムアウト

**対応:**
1. エラー内容をLLMに通知
2. LLMが代替手段を検討
3. 必要に応じてリフレクション実行

#### コンテナ削除エラー

**原因:**
- Docker APIへの接続失敗
- コンテナがビジー状態

**対応:**
1. 警告ログを記録
2. 削除をリトライ（最大3回）
3. 失敗した場合は残存リソースとして記録

### 8.2 タイムアウト処理

**コマンド実行タイムアウト:**
- 設定された最大実行時間を超過した場合
- コマンドを強制終了
- タイムアウトエラーをLLMに通知

**コンテナ操作タイムアウト:**
- Docker API呼び出しのタイムアウト
- デフォルト: 60秒
- タイムアウト時はリトライ後にエラー

---

## 9. セキュリティ考慮事項

### 9.1 コンテナ分離

**名前空間の分離:**
- 各タスクは独立したコンテナで実行
- プロセス、ネットワーク、ファイルシステムが分離

**権限の最小化:**
- コンテナは非特権モードで実行
- rootユーザーでの実行を禁止

### 9.2 認証情報の保護

**一時的な使用:**
- 認証情報はクローン時のみ使用
- コンテナ内に永続化しない

**ログ出力の制御:**
- 認証情報をログに出力しない
- URLはサニタイズして出力

### 9.3 リソース制限

**DoS攻撃の防止:**
- CPU、メモリ、ディスクの使用量を制限
- コマンド実行時間を制限

**フォークボムの防止:**
- プロセス数の上限を設定

### 9.4 ネットワークセキュリティ

**アウトバウンド通信の制御:**
- 必要なドメインのみアクセス許可（オプション）
- 内部ネットワークへのアクセス制限

---

## 10. 設定ファイル仕様

### 10.1 config.yamlへの追加設定

```yaml
# Command Executor MCP Server連携設定
command_executor:
  # 機能の有効/無効（デフォルト: false）
  enabled: false
  
  # MCP Server設定
  mcp_server:
    # サーバー名
    name: "command-executor"
    # コマンド
    command:
      - "npx"
      - "@sunwood-ai-labs/command-executor-mcp-server"
  
  # Docker実行環境設定
  docker:
    # ベースイメージ
    base_image: "coding-agent-executor:latest"
    
    # リソース制限
    resources:
      # CPU制限（コア数）
      cpu_limit: 2
      # メモリ制限
      memory_limit: "4g"
      # ディスク制限
      disk_limit: "10g"
    
    # ネットワーク設定
    network:
      # 外部ネットワークアクセスの許可
      external_access: true
      # ホワイトリストモード（external_accessがtrueの場合のみ有効）
      whitelist_mode: false
      # 許可ドメインリスト
      allowed_domains: []
  
  # プロジェクトクローン設定
  clone:
    # 浅いクローンの使用
    shallow: true
    # 浅いクローンの深さ
    depth: 1
    # 依存関係の自動インストール
    auto_install_deps: true
  
  # コマンド実行設定
  execution:
    # コマンド実行の最大時間（秒）
    timeout_seconds: 1800
    # 出力の最大サイズ（バイト）
    max_output_size: 1048576
  
  # クリーンアップ設定
  cleanup:
    # 残存リソースのクリーンアップ間隔（時間）
    interval_hours: 24
    # 残存とみなす経過時間（時間）
    stale_threshold_hours: 24
```

### 10.2 環境変数

| 環境変数名 | 説明 | デフォルト値 |
|-----------|------|-------------|
| COMMAND_EXECUTOR_ENABLED | 機能の有効/無効 | false |
| DOCKER_HOST | Docker APIエンドポイント | unix:///var/run/docker.sock |
| EXECUTOR_BASE_IMAGE | ベースイメージ | coding-agent-executor:latest |
| EXECUTOR_CPU_LIMIT | CPU制限 | 2 |
| EXECUTOR_MEMORY_LIMIT | メモリ制限 | 4g |
| EXECUTOR_TIMEOUT | コマンドタイムアウト | 1800 |

---

## 11. クラス設計

### 11.1 クラス図

```mermaid
classDiagram
    class ExecutionEnvironmentManager {
        -docker_client
        -config
        -active_containers: Dict
        +prepare(task) ContainerInfo
        +execute(container_id, command) ExecutionResult
        +cleanup(task_uuid)
        +cleanup_stale_containers()
        -_create_container(task) str
        -_clone_project(container_id, task)
        -_install_dependencies(container_id)
        -_remove_container(container_id)
    }
    
    class ContainerInfo {
        +container_id: str
        +task_uuid: str
        +workspace_path: str
        +created_at: datetime
        +status: str
    }
    
    class ExecutionResult {
        +exit_code: int
        +stdout: str
        +stderr: str
        +duration_ms: int
    }
    
    class TaskHandler {
        -execution_manager: ExecutionEnvironmentManager
        +handle(task)
    }
    
    TaskHandler --> ExecutionEnvironmentManager
    ExecutionEnvironmentManager --> ContainerInfo
    ExecutionEnvironmentManager --> ExecutionResult
```

### 11.2 クラスの責務

#### ExecutionEnvironmentManager

タスク毎の実行環境を管理するクラスです。

**メソッド:**
- `prepare(task)`: タスク用のコンテナを作成し、プロジェクトをクローン
- `execute(container_id, command)`: 指定コンテナでコマンドを実行
- `cleanup(task_uuid)`: タスク終了時にコンテナを削除
- `cleanup_stale_containers()`: 残存コンテナの定期クリーンアップ

#### ContainerInfo

コンテナの情報を保持するデータクラスです。

**属性:**
- `container_id`: DockerコンテナID
- `task_uuid`: 関連するタスクのUUID
- `workspace_path`: コンテナ内の作業ディレクトリパス
- `created_at`: コンテナ作成日時
- `status`: コンテナの状態

#### ExecutionResult

コマンド実行結果を保持するデータクラスです。

**属性:**
- `exit_code`: コマンドの終了コード
- `stdout`: 標準出力
- `stderr`: 標準エラー出力
- `duration_ms`: 実行時間（ミリ秒）

---

## 12. 処理シーケンス

### 12.1 タスク処理全体フロー

```mermaid
sequenceDiagram
    participant TG as TaskGetter
    participant TH as TaskHandler
    participant EM as ExecutionEnvironmentManager
    participant LLM as LLMClient
    participant MCP as MCPToolClient
    participant CE as CommandExecutor
    
    TG->>TH: タスク取得
    TH->>EM: prepare(task)
    EM-->>TH: ContainerInfo
    TH->>LLM: システムプロンプト送信
    
    loop タスク処理ループ
        TH->>LLM: メッセージ送信
        LLM-->>TH: 応答
        
        alt コマンド実行要求
            TH->>MCP: call_tool(command-executor/execute)
            MCP->>CE: execute_command
            CE-->>MCP: ExecutionResult
            MCP-->>TH: ツール結果
        else GitHub/GitLab操作
            TH->>MCP: call_tool(github/...)
            MCP-->>TH: ツール結果
        else 完了
            TH->>EM: cleanup(task_uuid)
            EM-->>TH: クリーンアップ完了
        end
    end
```

---

## 13. 運用ガイドライン

### 13.1 前提条件

**Docker環境:**
- Docker Engine 20.10以上
- Docker API経由でのアクセスが可能

**ベースイメージ:**
- 事前にベースイメージをビルドして配置

### 13.2 監視項目

**リソース監視:**
- コンテナのCPU/メモリ使用量
- ディスク使用量
- 残存コンテナ数

**エラー監視:**
- コンテナ作成失敗
- クローン失敗
- コマンドタイムアウト

### 13.3 トラブルシューティング

**コンテナが残存する場合:**
- 手動での削除コマンドを実行
- クリーンアップ間隔の見直し

**クローンが失敗する場合:**
- 認証情報の確認
- ネットワーク接続の確認
- リポジトリURLの確認

**コマンドがタイムアウトする場合:**
- タイムアウト値の見直し
- コマンドの最適化
- リソース制限の見直し

---

## 14. 今後の拡張

### 14.1 検討中の機能

**キャッシュ機能:**
- 依存関係のキャッシュ
- ビルド成果物のキャッシュ

**並列実行:**
- 複数コマンドの並列実行
- 複数コンテナの同時管理

**カスタム環境:**
- プロジェクト毎のカスタムDockerfile
- 環境変数のカスタマイズ

### 14.2 制限事項

**現バージョンでの制限:**
- GUIアプリケーションの実行は非対応
- GPUの使用は非対応
- Windows/macOS固有のコマンドは非対応

---

## 15. 関連ドキュメント

- [基本仕様](spec.md)
- [クラス設計](class_spec.md)
- [継続動作モード仕様](CONTINUOUS_MODE_SPECIFICATION.md)
- [プロジェクトエージェントルール仕様](PROJECT_AGENT_RULES_SPECIFICATION.md)

---

**文書バージョン:** 1.0  
**最終更新日:** 2024-11-28  
**ステータス:** 設計中
