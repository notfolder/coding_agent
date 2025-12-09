# Command Executor（実行環境管理）仕様書

## 1. 概要

### 1.1 目的

本仕様書は、コーディングエージェントにおけるDocker実行環境の管理とコマンド実行機能の詳細設計を定義します。タスク毎に独立したDockerコンテナを作成し、プロジェクトのクローン、依存関係のインストール、コマンド実行を行う機能を提供します。また、計画フェーズで選択された言語環境に応じた適切なイメージを使用する仕組みを実現します。

### 1.2 背景

コーディングエージェントがGitHub/GitLabのIssueやPull Request/Merge Requestを処理する際、以下のようなコマンド実行が必要になるケースがあります：

- ビルドコマンドの実行（npm build、make等）
- テストコマンドの実行（npm test、pytest等）
- リンターやフォーマッターの実行（eslint、black等）
- ファイル検索・確認（grep、find、cat等）
- その他のプロジェクト固有のスクリプト実行

これらのコマンド実行を安全かつ分離された環境で行うため、Dockerコンテナを使用した実行環境を設計します。

**実装アプローチ:**

当初はCommand Executor MCP Serverという外部MCPサーバーを使用する設計でしたが、現在の実装では`ExecutionEnvironmentManager`クラスがDocker APIを直接使用してコマンドを実行します。これにより、外部プロセスとの通信オーバーヘッドを削減し、実行環境の管理を一元化しています。

### 1.3 要求事項

- ExecutionEnvironmentManagerクラスがDocker APIを直接使用してコマンド実行をサポートする
- 実行環境はDockerで独立してタスク毎に初期化される
- **計画フェーズで適切な言語環境を選択し、その環境でコンテナを起動する**
- **各言語用イメージにはgitとCommand Executorの基盤機能をあらかじめインストールしておき、即座に起動可能な状態にする**
- 実行環境にはあらかじめプロジェクトファイルをダウンロードしておく
- タスク終了時に実行環境を削除する
- Text Editor MCPサーバーと統合してファイル編集機能を提供する
- Function calling形式でLLMから直接ツールを呼び出せるようにする

### 1.4 参照ドキュメント

- [基本仕様](SPEC.md)
- [クラス設計](../CLASS_SPEC.md)
- [継続動作モード仕様](CONTINUOUS_MODE_SPECIFICATION.md)
- [複数言語対応実行環境仕様](MULTI_LANGUAGE_ENVIRONMENT_SPECIFICATION.md)
- [Text Editor MCP仕様](TEXT_EDITOR_MCP_SPECIFICATION.md)
- [プロジェクトエージェントルール仕様](PROJECT_AGENT_RULES_SPECIFICATION.md)

---

## 2. システムアーキテクチャ

### 2.1 全体構成図

```mermaid
flowchart TD
    subgraph CodingAgent[コーディングエージェント]
        TaskHandler[TaskHandler]
        PlanningCoordinator[PlanningCoordinator]
        ExecManager[ExecutionEnvironmentManager]
        TextEditorClient[TextEditorMCPClient]
    end
    
    subgraph DockerHost[Docker Host]
        DockerAPI[Docker API]
        subgraph DockerImages[言語別Dockerイメージ]
            ImgPython[Python イメージ]
            ImgMiniforge[Miniforge イメージ]
            ImgNode[Node.js イメージ]
        end
        subgraph ExecutionContainer[実行環境コンテナ]
            ProjectFiles[プロジェクトファイル]
            WorkDir[作業ディレクトリ]
            TextEditorMCP[Text Editor MCPサーバー]
        end
    end
    
    subgraph GitPlatform[Git Platform]
        GitHub[GitHub]
        GitLab[GitLab]
    end
    
    TaskHandler --> PlanningCoordinator
    PlanningCoordinator -->|環境選択| ExecManager
    TaskHandler --> ExecManager
    ExecManager --> DockerAPI
    ExecManager --> TextEditorClient
    TextEditorClient -.-> TextEditorMCP
    DockerAPI --> DockerImages
    DockerImages --> ExecutionContainer
    ExecManager -->|git clone| GitPlatform
    ExecManager -->|コマンド実行| ExecutionContainer
```

### 2.2 主要コンポーネント

#### ExecutionEnvironmentManager

実行環境の生成、管理、削除を担当する中核コンポーネントです。

**責務:**
- **利用可能な言語環境リストの提供** (`get_available_environments()`)
- **計画フェーズからの環境選択受付** (`prepare()`の`environment_name`パラメータ)
- タスク毎のDockerコンテナの生成（**選択された言語イメージを使用**）
- プロジェクトファイルのクローンと依存関係の自動インストール
- コンテナ内でのコマンド実行 (`execute_command()`)
- Text Editor MCPサーバーの起動と管理
- コンテナの状態監視とライフサイクル管理
- タスク終了時のコンテナ削除とクリーンアップ
- Function calling用のツール定義の提供
- 残存コンテナの定期クリーンアップ

**主要メソッド:**
- `is_enabled()`: Command Executor機能が有効かどうかを確認
- `get_available_environments()`: 利用可能な環境のリストを取得
- `get_default_environment()`: デフォルト環境名を取得
- `set_current_task(task)`: 現在のタスクを設定
- `prepare(task, environment_name)`: タスク用のコンテナを作成し、プロジェクトをクローン
- `execute_command(command, working_directory)`: コマンドを実行
- `cleanup(task_uuid)`: タスク終了時にコンテナを削除
- `cleanup_stale_containers()`: 残存コンテナの定期クリーンアップ
- `get_function_calling_functions()`: Function calling用の関数定義を返す
- `get_function_calling_tools()`: OpenAI形式のツール定義を返す
- `call_text_editor_tool(tool, arguments)`: Text editorツールを呼び出す

#### ContainerInfo

コンテナの情報を保持するデータクラスです。

**属性:**
- `container_id`: DockerコンテナID
- `task_uuid`: 関連するタスクのUUID
- `environment_name`: 使用された環境名（python, node等）
- `workspace_path`: コンテナ内の作業ディレクトリパス（デフォルト: `/workspace/project`）
- `created_at`: コンテナ作成日時
- `status`: コンテナの状態（created, ready等）

#### ExecutionResult

コマンド実行結果を保持するデータクラスです。

**属性:**
- `exit_code`: コマンドの終了コード
- `stdout`: 標準出力
- `stderr`: 標準エラー出力
- `duration_ms`: 実行時間（ミリ秒）

#### TextEditorMCPClient

コンテナ内で動作するText Editor MCPサーバーとの通信を担当するクライアントです。

**責務:**
- コンテナ内でのText Editor MCPサーバーの起動
- ファイル操作コマンドの実行（view、create、str_replace、insert、undo_edit）
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

### 3.3 言語別イメージの設定

実行環境は計画フェーズでLLMが選択した言語に応じた専用イメージを使用します。各イメージには以下の共通機能があらかじめインストールされています：

**共通プリインストール済みツール:**
- git（バージョン管理）
- curl / wget（ファイルダウンロード）
- jq（JSON処理）
- tree（ディレクトリ構造表示）
- その他基本的なコマンドラインツール

**利用可能な言語環境:**

| 環境名 | イメージ名 | 説明 | 主な用途 |
|--------|-----------|------|----------|
| python | coding-agent-executor-python:latest | Python 3.11 + pip + pytest/black/flake8/mypy | 純粋Pythonプロジェクト、Webフレームワーク |
| miniforge | coding-agent-executor-miniforge:latest | conda/mamba + Python + データサイエンスツール | 科学計算、ML/AI、condaenv.yaml使用プロジェクト |
| node | coding-agent-executor-node:latest | Node.js 20 + npm/yarn/pnpm + TypeScript/ESLint | フロントエンド、Node.jsバックエンド |

**環境選択の判断基準:**
- プロジェクトルートの依存関係ファイル（package.json, requirements.txt等）
- Issue/MRの内容から推測される言語・フレームワーク
- デフォルト環境: python（選択に失敗した場合）

詳細は[複数言語対応実行環境仕様](MULTI_LANGUAGE_ENVIRONMENT_SPECIFICATION.md)を参照してください。

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
- Docker in Docker: `/var/run/docker.sock`をマウントし、docker.ioパッケージをインストール

**セキュリティ設定:**
- 特定ドメインへのアクセスのみ許可するホワイトリスト方式をオプションで提供
- DNS解決は許可

---

## 4. プロジェクトファイルのダウンロード仕様

### 4.1 ダウンロードフロー

**注意:** コンテナ作成は計画フェーズ完了後、環境選択フェーズで実行されます。

```mermaid
sequenceDiagram
    participant PC as PlanningCoordinator
    participant EM as ExecutionEnvironmentManager
    participant Docker as Docker API
    participant Git as Git Platform

    Note over PC: 計画フェーズ完了
    PC->>EM: 利用可能環境リスト取得
    EM-->>PC: 環境リスト
    PC->>PC: LLMによる環境選択
    PC->>EM: prepare(task, selected_environment)
    EM->>Docker: コンテナ作成（選択されたイメージで）
    Docker-->>EM: コンテナID
    EM->>Docker: コンテナ起動
    Note over Docker: gitはイメージにプリインストール済み
    EM->>Docker: git clone実行
    Docker->>Git: リポジトリクローン
    Git-->>Docker: ファイル取得
    Docker-->>EM: クローン完了
    EM->>Docker: ブランチチェックアウト（PR/MRの場合）
    Docker-->>EM: チェックアウト完了
    EM-->>PC: 実行環境準備完了
    Note over PC: 実行フェーズ開始
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
- GITLAB_API_URLから自動的にプロトコル（http/https）を抽出
- `get_project()` APIでpath_with_namespace取得
- Clone URL: `{protocol}oauth2:{token}@{host}/{path_with_namespace}.git`
- セルフホストGitLab対応: `git -c http.sslVerify=false clone`でSSL検証を無効化

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

### 5.1 初期化フロー（計画後に実行）

**変更点:** コンテナ作成タイミングが「タスク開始時」から「計画フェーズ完了後」に変更されました。

```mermaid
flowchart TD
    A[タスク開始] --> B[計画フェーズ]
    B --> C[計画作成完了]
    C --> D[環境選択フェーズ]
    D --> E[LLMが環境を選択]
    E --> F[ExecutionEnvironmentManager.prepare]
    F --> G{既存コンテナ確認}
    G -->|存在する| H[既存コンテナ削除]
    G -->|存在しない| I[選択されたイメージでコンテナ作成]
    H --> I
    I --> J[コンテナ起動]
    J --> K[プロジェクトファイルダウンロード]
    K --> L[依存関係インストール]
    L --> M[初期化完了]
    M --> N[実行フェーズ開始]
```

### 5.2 クリーン環境の保証

各タスクは完全にクリーンな環境で開始されることを保証します。

**初期化時の処理:**
1. 同一task_uuidのコンテナが存在する場合は削除
2. **選択された言語環境のイメージを使用して**新規コンテナを作成
3. **gitは既にインストール済みのため、即座に**プロジェクトファイルをクローン
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
- condaenv.yaml / environment.yml: `mamba env create -f <環境ファイル>`（miniforge/mambaforge使用）
- Gemfile: `bundle install`

**Conda環境について:**
- ベースイメージにminiforgeをプリインストール
- condaenv.yaml または environment.yml が存在する場合、自動的にconda環境を作成
- mambaを使用して高速な依存関係解決を実現

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

### 6.1 ExecutionEnvironmentManagerによるコマンド実行

コーディングエージェントは外部MCPサーバーを使用せず、ExecutionEnvironmentManagerクラスが直接Dockerコンテナ内でコマンドを実行します。

**実装アプローチ:**
- ExecutionEnvironmentManagerがFunction calling形式のツール定義を提供
- LLMが`command-executor_execute_command`ツール呼び出しをリクエスト
- TaskHandlerまたはPlanningCoordinatorがExecutionEnvironmentManagerの`execute_command()`メソッドを直接呼び出し
- Docker APIを使用してコンテナ内で`docker exec`を実行
- 外部プロセスとの通信オーバーヘッドを削減し、実行環境管理を一元化

**MCPツール呼び出し形式:**
- ツール名: `command-executor_execute_command`（アンダースコア区切り）
- 実装方式: ExecutionEnvironmentManagerが直接コマンドを実行（外部MCPサーバー不使用）
- コンテナ管理: ExecutionEnvironmentManagerが内部で管理

**execute_command()メソッドの処理:**

1. **現在のタスク確認**: `_current_task`が設定されているか確認
2. **コンテナ情報取得**: タスクUUIDからアクティブコンテナ情報を取得
3. **コンテナ状態確認**: コンテナが"ready"状態であることを確認
4. **作業ディレクトリ設定**: 指定されたworking_directoryまたはデフォルト（`/workspace/project`）を使用
5. **Docker execコマンド構築**: `docker exec -w <作業ディレクトリ> <コンテナID> sh -c "<コマンド>"`
6. **コマンド実行**: タイムアウト設定（デフォルト: 1800秒）でsubprocessを使用して実行
7. **結果収集**: exit_code、stdout、stderr、実行時間を収集
8. **出力サイズ制限**: stdoutとstderrが最大サイズ（デフォルト: 1MB）を超える場合は切り詰め
9. **結果返却**: 辞書形式で結果を返却

**エラーハンドリング:**
- タイムアウト発生時: `exit_code=-1`、`stderr="Command timeout after {timeout} seconds"`を返却
- 実行環境未準備: `RuntimeError`を送出
- その他の例外: `exit_code=-1`、`stderr="Command execution error: {error}"`を返却

### 6.2 コマンド実行フロー

```mermaid
sequenceDiagram
    participant LLM as LLMClient
    participant TH as TaskHandler
    participant EM as ExecutionEnvironmentManager
    participant Container as 実行コンテナ

    LLM->>TH: コマンド実行要求（function call）
    TH->>EM: execute_command(command, working_directory)
    EM->>EM: 現在のタスクとコンテナ情報を確認
    EM->>EM: Docker execコマンドを構築
    EM->>Container: docker exec -w /workspace/project container_id sh -c "command"
    Container-->>EM: 実行結果（stdout, stderr, exit_code）
    EM->>EM: 実行時間を計測、出力サイズを制限
    EM-->>TH: 結果辞書 {exit_code, stdout, stderr, duration_ms}
    TH->>LLM: 結果送信
```

### 6.3 許可コマンドリスト

実行環境で許可されるコマンドを以下に明示します。セキュリティと実用性のバランスを考慮して選定しています。

#### 6.3.1 ビルド・パッケージ管理コマンド

| コマンド | 説明 | 用途例 |
|---------|------|-------|
| npm | Node.jsパッケージマネージャー | `npm install`, `npm run build`, `npm test` |
| yarn | Node.jsパッケージマネージャー | `yarn install`, `yarn build`, `yarn test` |
| pnpm | Node.jsパッケージマネージャー | `pnpm install`, `pnpm build` |
| pip | Pythonパッケージマネージャー | `pip install`, `pip list` |
| pip3 | Python3パッケージマネージャー | `pip3 install -r requirements.txt` |
| conda | Conda環境・パッケージマネージャー | `conda activate`, `conda install`, `conda env create` |
| mamba | 高速Condaパッケージマネージャー | `mamba install`, `mamba env create -f environment.yml` |
| python | Pythonインタープリター | `python setup.py`, `python -m pytest` |
| python3 | Python3インタープリター | `python3 -m venv`, `python3 script.py` |
| cargo | Rustパッケージマネージャー | `cargo build`, `cargo test` |
| make | ビルド自動化ツール | `make`, `make install`, `make test` |
| cmake | ビルドシステムジェネレーター | `cmake .`, `cmake --build .` |
| bundle | Rubyパッケージマネージャー | `bundle install`, `bundle exec` |
| gem | Rubyパッケージマネージャー | `gem install` |
| composer | PHPパッケージマネージャー | `composer install`, `composer update` |
| dotnet | .NETツールチェーン | `dotnet build`, `dotnet test` |

#### 6.3.2 テスト実行コマンド

| コマンド | 説明 | 用途例 |
|---------|------|-------|
| pytest | Pythonテストフレームワーク | `pytest`, `pytest -v`, `pytest tests/` |
| jest | JavaScriptテストフレームワーク | `jest`, `jest --coverage` |
| mocha | JavaScriptテストフレームワーク | `mocha`, `mocha tests/` |
| rspec | Rubyテストフレームワーク | `rspec`, `rspec spec/` |
| phpunit | PHPテストフレームワーク | `phpunit`, `phpunit tests/` |
| cargo test | Rustテストコマンド | `cargo test`, `cargo test --all` |
| dotnet test | .NETテストコマンド | `dotnet test` |

#### 6.3.3 リンター・フォーマッターコマンド

| コマンド | 説明 | 用途例 |
|---------|------|-------|
| eslint | JavaScriptリンター | `eslint .`, `eslint --fix .` |
| prettier | コードフォーマッター | `prettier --check .`, `prettier --write .` |
| black | Pythonフォーマッター | `black .`, `black --check .` |
| flake8 | Pythonリンター | `flake8`, `flake8 src/` |
| pylint | Pythonリンター | `pylint src/` |
| mypy | Python型チェッカー | `mypy src/` |
| rubocop | Rubyリンター | `rubocop`, `rubocop -a` |
| rustfmt | Rustフォーマッター | `rustfmt --check .` |
| clippy | Rustリンター | `cargo clippy` |
| tsc | TypeScriptコンパイラ | `tsc --noEmit`, `tsc` |

#### 6.3.4 ファイル操作・検索コマンド

| コマンド | 説明 | 用途例 |
|---------|------|-------|
| ls | ファイル一覧表示 | `ls -la`, `ls -R` |
| cat | ファイル内容表示 | `cat file.txt` |
| head | ファイル先頭表示 | `head -n 50 file.txt` |
| tail | ファイル末尾表示 | `tail -n 50 file.txt` |
| grep | テキスト検索 | `grep -r "pattern" .`, `grep -rn "function" src/` |
| find | ファイル検索 | `find . -name "*.py"`, `find . -type f` |
| wc | 行数・文字数カウント | `wc -l file.txt` |
| diff | ファイル差分表示 | `diff file1.txt file2.txt` |
| tree | ディレクトリ構造表示 | `tree`, `tree -L 2` |
| file | ファイルタイプ判定 | `file filename` |
| stat | ファイル情報表示 | `stat filename` |

#### 6.3.5 バージョン管理コマンド

| コマンド | 説明 | 用途例 |
|---------|------|-------|
| git status | リポジトリ状態確認 | `git status` |
| git diff | 差分表示 | `git diff`, `git diff HEAD~1` |
| git log | コミット履歴表示 | `git log --oneline -10` |
| git branch | ブランチ一覧・操作 | `git branch`, `git branch -a` |
| git show | コミット内容表示 | `git show HEAD` |
| git blame | 行ごとの変更者表示 | `git blame file.txt` |

#### 6.3.6 その他のユーティリティコマンド

| コマンド | 説明 | 用途例 |
|---------|------|-------|
| echo | テキスト出力 | `echo "text"` |
| pwd | カレントディレクトリ表示 | `pwd` |
| cd | ディレクトリ移動 | `cd src/` |
| mkdir | ディレクトリ作成 | `mkdir -p dir/subdir` |
| rm | ファイル削除（単一ファイル） | `rm file.txt` |
| cp | ファイルコピー | `cp src.txt dst.txt` |
| mv | ファイル移動・リネーム | `mv old.txt new.txt` |
| touch | ファイル作成・更新 | `touch newfile.txt` |
| chmod | 権限変更 | `chmod +x script.sh` |
| env | 環境変数表示 | `env` |
| which | コマンドパス表示 | `which python` |
| curl | HTTP通信（読み取り専用） | `curl -s https://api.example.com` |
| wget | ファイルダウンロード | `wget https://example.com/file` |
| tar | アーカイブ操作 | `tar -xzf archive.tar.gz` |
| unzip | ZIP解凍 | `unzip archive.zip` |
| jq | JSON処理 | `cat data.json` パイプ `jq '.key'` |
| sed | テキスト置換（標準出力） | `sed 's/old/new/g' file.txt` |
| awk | テキスト処理 | `awk '{print $1}' file.txt` |
| sort | ソート | `sort file.txt` |
| uniq | 重複除去 | `uniq file.txt` |
| xargs | 引数展開 | `find . -name "*.txt"` パイプ `xargs grep "pattern"` |

#### 6.3.7 禁止コマンドリスト

以下のコマンドはセキュリティ上の理由から実行を禁止します。

| コマンド | 禁止理由 |
|---------|---------|
| sudo | 特権昇格の防止 |
| su | ユーザー切り替えの防止 |
| rm -rf | 再帰的強制削除による誤削除の防止 |
| chmod 777 | 過剰な権限付与の防止 |
| chown | 所有者変更の防止 |
| mount / umount | ファイルシステム操作の防止 |
| iptables / ip6tables | ネットワーク設定変更の防止 |
| systemctl / service | サービス制御の防止 |
| kill / killall | プロセス強制終了の防止（自身のプロセス以外） |
| reboot / shutdown | システム制御の防止 |
| dd | 低レベルディスク操作の防止 |
| mkfs | ファイルシステム作成の防止 |
| fdisk / parted | パーティション操作の防止 |
| nc / netcat | 任意ネットワーク接続の防止 |
| nmap | ネットワークスキャンの防止 |
| ssh | リモート接続の防止 |
| scp / rsync | リモートファイル転送の防止（外部への） |

#### 6.3.8 コマンド許可リストの設定

設定ファイルでコマンド許可リストをカスタマイズできます。

```yaml
command_executor:
  # 許可コマンドの設定
  allowed_commands:
    # デフォルト許可リストを使用するか
    use_default: true
    
    # 追加で許可するコマンド
    additional:
      - "custom-build-tool"
      - "project-specific-script"
    
    # デフォルトから除外するコマンド
    exclude:
      - "curl"
      - "wget"
    
    # 完全カスタムリスト（use_default: falseの場合に使用）
    custom_list:
      - "npm"
      - "python"
      - "grep"
```

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

### 6.5 システムプロンプト拡張仕様

LLMがCommand Executor MCP Serverの機能を適切に活用できるよう、システムプロンプトに以下の情報を追加します。

#### 6.5.1 追加するプロンプト内容

システムプロンプトに以下の文言を追加します：

```
## Command Execution Feature

You can execute commands in an isolated Docker execution environment with project source code through the `command-executor` MCP server.

**Important:** Use the tool name `command-executor_execute_command` when calling the command execution tool.

**Execution Environment Information:**
- Working directory: `/workspace/project/` (where project files are cloned)
- Dependencies: Automatically installed

### Available Commands

The following commands are available for execution:

{allowed_commands_list}

### Key Features

**Test Execution:**
- Run the project's test suite to verify code changes work correctly
- Examples: `npm test`, `pytest`, `cargo test`

**Code Search:**
- Use `grep` command to recursively search for code patterns across the entire project
- Example: `grep -rn "function_name" src/` to find function usage locations
- Example: `grep -r "import.*module" --include="*.py"` to search Python import statements

**Build/Compile:**
- Execute project build commands to check for compilation errors
- Examples: `npm run build`, `make`, `cargo build`

**Linter/Formatter:**
- Perform code quality checks and format verification
- Examples: `eslint .`, `black --check .`, `flake8`

**File Operations:**
- Use `ls`, `cat`, `head`, `tail`, `find`, `tree` to check file structure and code contents
- Example: `find . -name "*.ts" -type f` to search for TypeScript files
- Example: `tree -L 2` to display directory structure

### Usage Notes

- Project source code is cloned to `/workspace/project/` in the execution environment
- Dependencies are automatically installed
- Check command execution results (stdout/stderr) and determine the next action
- Long-running commands may timeout

### Recommended Usage

1. **Before code changes**: Search the codebase with `grep` to understand the impact scope of changes
2. **After code changes**: Run tests to verify the correctness of changes
3. **Before creating pull request**: Run linters to verify code quality
```

#### 6.5.2 許可コマンドリストの埋め込み

システムプロンプト内の `{allowed_commands_list}` プレースホルダーは、セクション6.3で定義された許可コマンドリストの内容で動的に置き換えられます。

**置き換え内容:**
- ビルド・パッケージ管理コマンド（npm, yarn, pip, conda, mamba, cargo等）
- テスト実行コマンド（pytest, jest等）
- リンター・フォーマッターコマンド（eslint, black, flake8等）
- ファイル操作・検索コマンド（grep, find, ls, cat等）
- バージョン管理コマンド（git status, git diff等）
- その他ユーティリティコマンド

**生成形式例:**
```
Build/Package Management: npm, yarn, pnpm, pip, pip3, conda, mamba, python, python3, cargo, make, cmake, bundle, gem, composer, dotnet
Test Execution: pytest, jest, mocha, rspec, phpunit, cargo test, dotnet test
Linter/Formatter: eslint, prettier, black, flake8, pylint, mypy, rubocop, rustfmt, clippy, tsc
File Operations: ls, cat, head, tail, grep, find, wc, diff, tree, file, stat
Version Control: git status, git diff, git log, git branch, git show, git blame
Utilities: echo, pwd, cd, mkdir, rm, cp, mv, touch, chmod, env, which, curl, wget, tar, unzip, jq, sed, awk, sort, uniq, xargs
```

#### 6.5.3 プロンプト挿入位置

システムプロンプトの以下の位置に挿入します：

- MCPサーバー一覧（Available MCP Tools）セクションの直後
- Behavior Rulesセクションの直前

#### 6.5.4 動的プロンプト生成

Command Executor機能が有効な場合のみ、上記プロンプトをシステムプロンプトに追加します。

**条件:**
- `command_executor.enabled` が `true` の場合に追加
- `false` の場合はプロンプトに含めない

**プロンプトテンプレートファイル:**
- ファイル名: `system_prompt_command_executor.txt`
- 配置場所: プロジェクトルート

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
        -config: dict
        -logger: Logger
        -_executor_config: dict
        -_environments: dict~str, str~
        -_default_environment: str
        -_docker_config: dict
        -_cpu_limit: int
        -_memory_limit: str
        -_shallow_clone: bool
        -_clone_depth: int
        -_auto_install_deps: bool
        -_timeout_seconds: int
        -_max_output_size: int
        -_active_containers: dict~str, ContainerInfo~
        -_current_task: Task
        -_text_editor_enabled: bool
        -_text_editor_clients: dict~str, TextEditorMCPClient~
        +__init__(config)
        +is_enabled() bool
        +get_available_environments() dict~str, str~
        +get_default_environment() str
        +set_current_task(task)
        +prepare(task, environment_name) ContainerInfo
        +execute_command(command, working_directory) dict
        +cleanup(task_uuid)
        +cleanup_stale_containers() int
        +get_container_info(task_uuid) ContainerInfo
        +get_allowed_commands() dict
        +get_allowed_commands_text() str
        +get_function_calling_functions() list
        +get_function_calling_tools() list
        +is_text_editor_enabled() bool
        +call_text_editor_tool(tool, arguments) dict
        +get_text_editor_functions() list
        +get_text_editor_tools() list
        -_validate_and_select_environment(environment_name) str
        -_get_container_name(task_uuid) str
        -_run_docker_command(args, timeout, check) CompletedProcess
        -_get_clone_url(task) tuple
        -_create_container(task, environment_name) tuple
        -_install_git(container_id)
        -_clone_project(container_id, task)
        -_install_dependencies(container_id)
        -_remove_container(task_uuid)
        -_parse_docker_datetime(datetime_str) datetime
        -_start_text_editor_mcp(container_id, task_uuid)
        -_stop_text_editor_mcp(task_uuid)
    }
    
    class ContainerInfo {
        +container_id: str
        +task_uuid: str
        +environment_name: str
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
    
    class TextEditorMCPClient {
        +container_id: str
        +workspace_path: str
        +timeout_seconds: int
        +start()
        +stop()
        +call_tool(tool, arguments) Result
    }
    
    class TaskHandler {
        -execution_manager: ExecutionEnvironmentManager
        +handle(task)
    }
    
    TaskHandler --> ExecutionEnvironmentManager
    ExecutionEnvironmentManager --> ContainerInfo
    ExecutionEnvironmentManager --> ExecutionResult
    ExecutionEnvironmentManager --> TextEditorMCPClient
```

### 11.2 クラスの責務と主要メソッド

#### ExecutionEnvironmentManager

タスク毎の実行環境を管理する中核クラスです。

**初期化処理(`__init__`):**
- config辞書からcommand_executor設定を取得
- 利用可能な環境（environments）とデフォルト環境を設定
- Docker設定（CPU制限、メモリ制限）を取得
- クローン設定（shallow、depth、auto_install_deps）を取得
- 実行設定（タイムアウト、最大出力サイズ）を取得
- クリーンアップ設定を取得
- アクティブコンテナ追跡用の辞書を初期化
- Text Editor MCP設定を取得

**環境管理メソッド:**

`get_available_environments()`:
- 利用可能な環境のリスト（環境名→イメージ名のマッピング）を返す
- configから取得した_environments辞書のコピーを返却

`get_default_environment()`:
- デフォルト環境名を返す
- configで設定された値、またはDEFAULT_ENVIRONMENT定数を使用

`is_enabled()`:
- Command Executor機能が有効かどうかを確認
- config['command_executor']['enabled']の値を返す

`set_current_task(task)`:
- 現在処理中のタスクを設定
- execute_command()で使用するタスク情報を保持

**コンテナライフサイクル管理メソッド:**

`prepare(task, environment_name)`:
1. タスクUUIDからコンテナ名を生成
2. 環境名を検証し、有効な環境を選択（無効な場合はデフォルト使用）
3. 既存コンテナがあれば削除
4. 選択された環境のイメージでコンテナを作成
5. カスタムイメージでない場合はgitをインストール
6. プロジェクトをクローン
7. 依存関係を自動インストール（有効な場合）
8. Text Editor MCPサーバーを起動（有効な場合）
9. ContainerInfo作成してアクティブコンテナに登録
10. ContainerInfoを返却

`cleanup(task_uuid)`:
1. Text Editor MCPサーバーを停止
2. _remove_container()でコンテナを削除
3. アクティブコンテナ辞書から削除
4. エラー発生時はログに記録

`cleanup_stale_containers()`:
1. `docker ps -a`で命名規則に合致するコンテナを一覧取得
2. 各コンテナの作成時刻をパース
3. 閾値時間（デフォルト: 24時間）を超過しているコンテナを削除
4. 削除されたコンテナ数を返却

**コマンド実行メソッド:**

`execute_command(command, working_directory)`:
1. 現在のタスクが設定されているか確認
2. タスクUUIDからコンテナ情報を取得
3. コンテナが"ready"状態か確認
4. 作業ディレクトリを設定（指定値またはデフォルト）
5. docker execコマンドを構築
6. subprocess.run()で実行（タイムアウト付き）
7. 実行時間を計測
8. stdout/stderrのサイズを制限（最大1MB）
9. 結果辞書を返却 {exit_code, stdout, stderr, duration_ms}

**内部ヘルパーメソッド:**

`_validate_and_select_environment(environment_name)`:
- 指定された環境名が有効か検証
- 無効またはNoneの場合はデフォルト環境を返す
- 検証結果をログに記録

`_get_container_name(task_uuid)`:
- `coding-agent-exec-{task_uuid}`形式のコンテナ名を生成

`_run_docker_command(args, timeout, check)`:
- `docker <args>`コマンドを実行
- subprocess.run()を使用
- capture_output=True、text=Trueで実行
- タイムアウトとチェックフラグを設定
- CompletedProcessを返却

`_get_clone_url(task)`:
- タスクの種類（GitHub/GitLab）を判定
- 認証トークンを含むクローンURLを生成
- GitHub: `https://x-access-token:{token}@github.com/{owner}/{repo}.git`
- GitLab: `{protocol}oauth2:{token}@{host}/{path_with_namespace}.git`
- ブランチ名（PRソースブランチ等）を取得
- (clone_url, branch)のタプルを返却

`_create_container(task, environment_name)`:
1. 環境名に基づいてイメージを選択（environments辞書またはbase_image）
2. docker createコマンドを構築（CPU/メモリ制限、セキュリティ設定、ネットワーク設定）
3. コンテナを作成してIDを取得
4. docker startでコンテナを起動
5. (container_id, is_custom_image)のタプルを返却

`_install_git(container_id)`:
- `apt-get update && apt-get install -y git`をコンテナ内で実行
- タイムアウト: 300秒
- インストール失敗時はRuntimeErrorを送出

`_clone_project(container_id, task)`:
1. _get_clone_url()でクローンURLとブランチを取得
2. gitクローンコマンドを構築（SSL検証無効化、shallow clone、ブランチ指定）
3. docker execでコンテナ内でクローン実行
4. タイムアウト: 300秒
5. エラー時は認証情報をサニタイズしてログ出力

`_install_dependencies(container_id)`:
1. 依存関係ファイルを検出（package.json、requirements.txt、environment.yml等）
2. 各ファイルに対応するインストールコマンドを実行
3. npm install、pip install、mamba env update等
4. タイムアウト: 600秒
5. 失敗時は警告ログを記録（処理は継続）

`_remove_container(task_uuid)`:
1. タスクUUIDからコンテナ名を取得
2. `docker rm -f <container_name>`で強制削除
3. 最大3回リトライ
4. 失敗した場合はRuntimeErrorを送出

`_parse_docker_datetime(datetime_str)`:
- Docker日時文字列を複数フォーマットでパース試行
- `%Y-%m-%d %H:%M:%S`、`%Y-%m-%dT%H:%M:%SZ`等に対応
- パース成功時はUTCタイムゾーン付きdatetimeを返却
- 失敗時はNoneを返却

**Text Editor MCP関連メソッド:**

`_start_text_editor_mcp(container_id, task_uuid)`:
1. text_editor_enabled設定を確認
2. TextEditorMCPClientをインスタンス化
3. client.start()で起動
4. _text_editor_clients辞書に登録
5. 失敗時はRuntimeErrorを送出

`_stop_text_editor_mcp(task_uuid)`:
1. _text_editor_clients辞書からクライアントを取得・削除
2. client.stop()で停止
3. 失敗時は警告ログを記録

`call_text_editor_tool(tool, arguments)`:
1. 現在のタスクが設定されているか確認
2. タスクUUIDからtext-editorクライアントを取得
3. Noneの値を持つ引数を除去
4. client.call_tool()でツールを呼び出し
5. 結果を{success, content, error}形式で返却

**Function calling定義メソッド:**

`get_function_calling_functions()`:
- command-executor_execute_commandのツール定義を返す
- パラメータ: command（必須）、working_directory（オプション）
- is_enabled()がFalseの場合は空リストを返却

`get_function_calling_tools()`:
- OpenAI形式のツール定義を返す
- type: "function"でラップした形式

`get_text_editor_functions()`:
- text_editorツールの定義を返す
- コマンド: view、create、str_replace、insert、undo_edit
- パラメータ: command（必須）、path（必須）、その他はコマンド依存

`get_text_editor_tools()`:
- text_editorのOpenAI形式ツール定義を返す

**その他ユーティリティメソッド:**

`get_container_info(task_uuid)`:
- タスクUUIDからContainerInfoを取得
- アクティブコンテナ辞書から取得

`get_allowed_commands()`:
- カテゴリ別の許可コマンドリストを返す
- build_package、test、linter_formatter、file_operations、version_control、utilities

`get_allowed_commands_text()`:
- 許可コマンドをテキスト形式で返す
- システムプロンプト埋め込み用

#### ContainerInfo

コンテナの情報を保持するデータクラスです。

**属性:**
- `container_id`: DockerコンテナID
- `task_uuid`: 関連するタスクのUUID
- `environment_name`: 使用された環境名（python, node等）、デフォルトは"python"
- `workspace_path`: コンテナ内の作業ディレクトリパス、デフォルトは"/workspace/project"
- `created_at`: コンテナ作成日時、デフォルトは現在時刻（UTC）
- `status`: コンテナの状態、デフォルトは"created"

**使用例:**
- prepareメソッドで作成され、アクティブコンテナ辞書に登録
- execute_commandメソッドでコンテナ情報を取得して使用

#### ExecutionResult

コマンド実行結果を保持するデータクラスです。

**属性:**
- `exit_code`: コマンドの終了コード（0: 成功、非0: 失敗、-1: タイムアウト/エラー）
- `stdout`: 標準出力（最大1MBまで）
- `stderr`: 標準エラー出力（最大1MBまで）
- `duration_ms`: 実行時間（ミリ秒）

**使用例:**
- executeメソッドの返却値として使用（現在は辞書形式で返却）

#### TextEditorMCPClient

コンテナ内で動作するText Editor MCPサーバーとの通信を担当するクライアントです。

**責務:**
- コンテナ内でのText Editor MCPサーバーの起動
- ファイル操作コマンドの実行（view、create、str_replace、insert、undo_edit）
- 実行結果の返却

**主要メソッド:**
- `start()`: MCPサーバーを起動
- `stop()`: MCPサーバーを停止
- `call_tool(tool, arguments)`: ツールを呼び出してResultを返却

---

## 12. 処理シーケンス

### 12.1 タスク処理全体フロー

```mermaid
sequenceDiagram
    participant TG as TaskGetter
    participant TH as TaskHandler
    participant EM as ExecutionEnvironmentManager
    participant PC as PlanningCoordinator
    participant LLM as LLMClient
    participant Docker as Docker API
    participant Git as Git Platform
    
    TG->>TH: タスク取得
    TH->>EM: set_current_task(task)
    TH->>PC: PlanningCoordinator作成
    TH->>PC: execution_manager設定
    
    Note over PC: 計画フェーズ
    PC->>EM: get_available_environments()
    EM-->>PC: 環境リスト
    PC->>LLM: 環境選択を依頼
    LLM-->>PC: 選択された環境名
    
    Note over PC: 実行環境準備フェーズ
    PC->>EM: prepare(task, environment_name)
    EM->>EM: _validate_and_select_environment()
    EM->>Docker: コンテナ作成（選択されたイメージ）
    Docker-->>EM: コンテナID
    EM->>Docker: コンテナ起動
    EM->>Docker: プロジェクトクローン（git clone）
    Docker->>Git: リポジトリ取得
    Git-->>Docker: ファイル
    EM->>Docker: 依存関係インストール
    EM->>EM: Text Editor MCP起動（有効な場合）
    EM-->>PC: ContainerInfo
    
    Note over PC: 実行フェーズ
    PC->>LLM: システムプロンプト + ツール定義送信
    
    loop タスク処理ループ
        PC->>LLM: メッセージ送信
        LLM-->>PC: 応答（function calls）
        
        alt コマンド実行要求
            PC->>EM: execute_command(command)
            EM->>Docker: docker exec
            Docker-->>EM: 実行結果
            EM-->>PC: {exit_code, stdout, stderr, duration_ms}
            PC->>LLM: 結果送信
        else ファイル編集要求
            PC->>EM: call_text_editor_tool(tool, arguments)
            EM->>EM: TextEditorMCPClientでツール呼び出し
            EM-->>PC: {success, content, error}
            PC->>LLM: 結果送信
        else GitHub/GitLab操作
            PC->>PC: call_mcp_tool(...)
            PC->>LLM: 結果送信
        else 完了
            PC-->>TH: 成功
            TH->>EM: cleanup(task_uuid)
            EM->>EM: Text Editor MCP停止
            EM->>Docker: コンテナ削除
            EM-->>TH: クリーンアップ完了
        end
    end
```

### 12.2 コンテナ準備の詳細シーケンス

```mermaid
sequenceDiagram
    participant PC as PlanningCoordinator
    participant EM as ExecutionEnvironmentManager
    participant Docker as Docker API
    participant Git as Git Platform
    participant TextEditor as TextEditorMCPClient

    PC->>EM: prepare(task, "python")
    EM->>EM: _validate_and_select_environment("python")
    EM->>EM: _get_container_name(task_uuid)
    EM->>EM: _remove_container(task_uuid) (既存削除)
    
    EM->>EM: _create_container(task, "python")
    EM->>Docker: docker create (coding-agent-executor-python:latest)
    Docker-->>EM: container_id
    EM->>Docker: docker start container_id
    Docker-->>EM: 起動完了
    
    Note over EM: プレビルドイメージのため git既にインストール済み
    
    EM->>EM: _clone_project(container_id, task)
    EM->>EM: _get_clone_url(task)
    EM->>Docker: docker exec (git clone)
    Docker->>Git: git clone
    Git-->>Docker: プロジェクトファイル
    Docker-->>EM: クローン完了
    
    EM->>EM: _install_dependencies(container_id)
    EM->>Docker: docker exec (test -f package.json)
    Docker-->>EM: ファイル存在確認
    EM->>Docker: docker exec (npm install)
    Docker-->>EM: インストール完了
    
    EM->>EM: _start_text_editor_mcp(container_id, task_uuid)
    EM->>TextEditor: TextEditorMCPClient作成
    EM->>TextEditor: start()
    TextEditor-->>EM: 起動完了
    
    EM->>EM: ContainerInfo作成 (status="ready")
    EM->>EM: アクティブコンテナに登録
    EM-->>PC: ContainerInfo
```

### 12.3 コマンド実行の詳細シーケンス

```mermaid
sequenceDiagram
    participant LLM as LLMClient
    participant PC as PlanningCoordinator
    participant EM as ExecutionEnvironmentManager
    participant Docker as Docker API

    LLM->>PC: function call: command-executor_execute_command
    Note over LLM: {"command": "pytest tests/", "working_directory": null}
    
    PC->>EM: execute_command("pytest tests/", None)
    EM->>EM: 現在のタスク確認 (_current_task)
    EM->>EM: コンテナ情報取得 (task_uuid)
    EM->>EM: コンテナ状態確認 (status=="ready")
    EM->>EM: 作業ディレクトリ設定 (/workspace/project)
    EM->>EM: Docker execコマンド構築
    
    EM->>EM: 実行時間計測開始
    EM->>Docker: docker exec -w /workspace/project container_id sh -c "pytest tests/"
    Docker-->>EM: stdout, stderr, exit_code
    EM->>EM: 実行時間計測終了
    
    EM->>EM: 出力サイズ制限適用 (最大1MB)
    EM->>EM: 結果辞書作成
    EM-->>PC: {"exit_code": 0, "stdout": "...", "stderr": "", "duration_ms": 1234}
    
    PC->>LLM: function result送信
```

### 12.4 Text Editor Tool呼び出しシーケンス

```mermaid
sequenceDiagram
    participant LLM as LLMClient
    participant PC as PlanningCoordinator
    participant EM as ExecutionEnvironmentManager
    participant TextEditor as TextEditorMCPClient
    participant Container as 実行コンテナ

    LLM->>PC: function call: text_editor
    Note over LLM: {"command": "view", "path": "src/main.py"}
    
    PC->>EM: call_text_editor_tool("text_editor", arguments)
    EM->>EM: 現在のタスク確認
    EM->>EM: TextEditorMCPClient取得 (task_uuid)
    EM->>EM: None値を持つ引数を除去
    
    EM->>TextEditor: call_tool("text_editor", {"command": "view", "path": "src/main.py"})
    TextEditor->>Container: MCPプロトコルでview実行
    Container-->>TextEditor: ファイル内容
    TextEditor-->>EM: Result(success=True, content="...", error="")
    
    EM->>EM: 結果を辞書形式に変換
    EM-->>PC: {"success": True, "content": "...", "error": ""}
    
    PC->>LLM: function result送信
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
