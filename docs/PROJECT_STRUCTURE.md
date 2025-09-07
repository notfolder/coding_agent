# プロジェクト構造

## ルートディレクトリ
```
coding-agent/
├── README.md                    # プロジェクト概要
├── LICENSE                      # ライセンス
├── Dockerfile                   # コンテナビルド設定
├── docker-compose.yml           # マルチコンテナ設定
├── package.json                 # Node.js依存関係
├── pyproject.toml              # Python プロジェクト設定
├── Makefile                    # ビルドタスク
├── main.py                     # メインエントリーポイント
├── .env                        # 環境変数（Docker Compose用）
├── .gitignore                  # Git除外設定
├── .gitmodules                 # Gitサブモジュール設定
│
├── clients/                    # API クライアント実装
│   ├── __init__.py
│   ├── github_client.py        # GitHub API クライアント
│   ├── gitlab_client.py        # GitLab API クライアント
│   ├── llm_base.py             # LLM基底クラス
│   ├── lm_client.py            # LLMクライアント統合
│   ├── lmstudio_client.py      # LM Studio クライアント
│   ├── mcp_tool_client.py      # MCP ツールクライアント
│   ├── ollama_client.py        # Ollama クライアント
│   └── openai_client.py        # OpenAI クライアント
│
├── config/                     # 設定ファイル
│   ├── config.yaml             # メイン設定
│   ├── config_github.yaml      # GitHub専用設定
│   ├── config_gitlab.yaml      # GitLab専用設定
│   ├── condaenv.yaml           # Conda環境設定
│   ├── logging.conf            # ログ設定
│   ├── system_prompt.txt       # システムプロンプト
│   ├── system_prompt_function_call.txt
│   ├── sample_command.env      # 環境変数サンプル
│   └── sample_docker.env       # Docker環境変数サンプル
│
├── docs/                       # ドキュメント
│   ├── README.md               # 詳細README
│   ├── SETUP_GUIDE.md          # セットアップガイド
│   ├── class_spec.md           # クラス仕様
│   ├── spec.md                 # 仕様書
│   ├── LINT_PROGRESS_REPORT.md # Lint進捗レポート
│   ├── github-mcp-server.md    # GitHub MCP サーバー説明
│   ├── gitlab-mcp-server.md    # GitLab MCP サーバー説明
│   ├── mcp_client.md           # MCPクライアント説明
│   ├── lmstudio.md             # LM Studio説明
│   ├── ollama.md               # Ollama説明
│   ├── openai.md               # OpenAI説明
│   └── *.pdf, *.png            # 図表・レポート類
│
├── handlers/                   # ビジネスロジック
│   ├── __init__.py
│   ├── task.py                 # タスク基底クラス
│   ├── task_factory.py         # タスクファクトリー
│   ├── task_getter.py          # タスク取得統合
│   ├── task_getter_github.py   # GitHubタスク取得
│   ├── task_getter_gitlab.py   # GitLabタスク取得
│   ├── task_handler.py         # タスク処理
│   └── task_key.py             # タスクキー管理
│
├── utils/                      # ユーティリティ
│   ├── filelock_util.py        # ファイルロック
│   └── queueing.py             # キューイング機能
│
├── scripts/                    # 実行スクリプト
│   ├── init_data.sh            # データ初期化
│   ├── run.sh                  # メイン実行スクリプト
│   ├── run-docker.sh           # Docker実行スクリプト
│   ├── run-mock.sh             # モック実行スクリプト
│   └── test_rabbitmq.py        # RabbitMQテスト
│
├── tests/                      # テストコード
│   ├── __init__.py
│   ├── demo.py
│   ├── run_tests.py
│   ├── test_config.yaml
│   ├── integration/            # 統合テスト
│   ├── mocks/                  # モッククラス
│   ├── real_integration/       # 実統合テスト
│   └── unit/                   # 単体テスト
│
├── data/                       # データディレクトリ
│   ├── data_input/             # 入力データ
│   ├── data_raw/               # 生データ
│   ├── data_cleaned/           # クリーニング済み
│   ├── data_chunked/           # チャンク化済み
│   ├── data_json/              # JSON形式
│   ├── data_hash/              # ハッシュ値
│   └── data_chromadb_meta/     # ChromaDB メタデータ
│
├── logs/                       # ログファイル
│
├── github-mcp-server/          # GitHub MCP サーバー
│
└── test_rag_project/           # テスト用RAGプロジェクト
    ├── data/
    ├── logs/
    └── reports/
```

## コーディングルール適用結果

### ✅ 実装された整理項目

1. **フォルダ構造の標準化**
   - `docs/`: 全ドキュメント類を集約
   - `config/`: 設定ファイルを一元化
   - `utils/`: 汎用ユーティリティを分離
   - `scripts/`: 実行スクリプトを整理

2. **不要ファイルの削除**
   - バックアップファイル（`*.bak`, `*.corrupt.*`）
   - 重複ファイルの統合

3. **インポートパスの更新**
   - `main.py`で移動されたモジュールのパス修正
   - Dockerfileでの設定ファイルパス修正

4. **プロジェクトルート簡素化**
   - 必要最小限のファイルのみをルートに保持
   - README.mdは慣例に従いルートに配置

### 📁 各フォルダの役割

- **clients/**: 外部API・サービスとの通信を担当
- **handlers/**: ビジネスロジック・タスク処理を担当  
- **utils/**: 汎用的な機能・ユーティリティ
- **config/**: アプリケーションの設定・構成管理
- **docs/**: プロジェクトドキュメント・仕様書
- **scripts/**: 実行・デプロイメントスクリプト
- **tests/**: テストコード・テストデータ
- **data/**: アプリケーションデータ・キャッシュ
