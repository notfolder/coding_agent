# Coding Agent

GitHub Copilot のようなコーディングエージェントを作成するプロジェクト。GitHub や GitLab の Issue、Pull Request、Merge Request を自動処理し、LLM を使って様々なタスクを実行します。

## 概要

このプロジェクトは、以下の特徴を持つ汎用的な LLM エージェントです：

- **マルチプラットフォーム対応**: GitHub と GitLab の両方をサポート
- **MCP (Model Context Protocol) 統合**: 外部サービスとの連携に MCP サーバーを使用
- **複数 LLM プロバイダ対応**: OpenAI、LM Studio、Ollama をサポート
- **タスクベースワークフロー**: ラベル付きの Issue/PR/MR をタスクとして処理
- **Docker 対応**: コンテナでの実行をサポート
- **キューベース処理**: RabbitMQ を使用したタスクキューイング

## 機能

### コア機能
- ✅ GitHub/GitLab の Issue、PR、MR の自動処理
- ✅ 複数の LLM プロバイダ（OpenAI、LM Studio、Ollama）
- ✅ MCP サーバーを通じた外部ツール連携
- ✅ ラベルベースのタスク管理
- ✅ Docker コンテナでの実行
- ✅ RabbitMQ を使用したキューイング
- ✅ 設定可能なロギングシステム

### 対応プラットフォーム
- **GitHub**: Issue、Pull Request の処理
- **GitLab**: Issue、Merge Request の処理

### 対応 LLM プロバイダ
- **OpenAI**: GPT-4o など
- **LM Studio**: ローカル LLM サーバー
- **Ollama**: ローカル LLM 実行環境

## 必要要件

### システム要件
- **OS**: macOS、Linux（Docker 使用時は Windows も対応）
- **Python**: 3.13+
- **Node.js**: 18+ （MCP サーバー用）
- **Git**: バージョン管理
- **Docker**: コンテナ実行（オプション）

### 依存関係
- Python パッケージ（`condaenv.yaml` を参照）
- Node.js パッケージ（`package.json` を参照）
- MCP サーバー各種

## インストール

### 1. リポジトリのクローン
```bash
git clone --recursive https://github.com/notfolder/coding_agent.git
cd coding_agent

# または、既にクローン済みの場合
git submodule update --init --recursive
```

### 2. Conda 環境の作成
```bash
conda env create -f condaenv.yaml
conda activate coding-agent
```

### 3. Node.js 依存関係のインストール
```bash
npm install
```

### 4. MCP サーバーのセットアップ

#### ローカル開発環境の場合
GitHub MCP サーバーをビルド：
```bash
cd github-mcp-server/cmd/github-mcp-server
go build -o ../../../github-mcp-server main.go
cd ../../..
```

その後、`config.yaml` の GitHub MCP サーバーのコマンドパスを更新：
```yaml
mcp_servers:
  - mcp_server_name: "github"
    command:
      - "./github-mcp-server"  # ローカルでビルドした実行ファイル
      - "stdio"
```

#### Docker 環境の場合
Docker ビルド時に自動的に `/bin/github-mcp-server` にビルドされるため、追加設定不要。

## 設定

### 基本設定ファイル
メインの設定は `config.yaml` で行います：

```yaml
# LLM プロバイダの設定
llm:
  provider: "openai"  # "openai" | "lmstudio" | "ollama"
  function_calling: true
  openai:
    api_key: "your-api-key"
    model: "gpt-4o"
    max_token: 40960

# GitHub 設定
github:
  owner: "your-username"
  bot_label: "coding agent"
  processing_label: "coding agent processing"
  done_label: "coding agent done"

# MCP サーバー設定
mcp_servers:
  - mcp_server_name: "github"
    command: ["./github-mcp-server.cmd", "stdio"]
    env:
      GITHUB_TOOLSETS: "all"
```

### 環境変数
`.env` ファイルまたは環境変数で以下を設定：

```bash
# GitHub アクセストークン（GitHub 使用時）
GITHUB_TOKEN=your_github_token

# GitLab アクセストークン（GitLab 使用時）
GITLAB_TOKEN=your_gitlab_token

# OpenAI API キー（OpenAI 使用時）
OPENAI_API_KEY=your_openai_api_key

# ログレベル
DEBUG=true

# MCP サーバーコマンド（GitHub用）
GITHUB_MCP_COMMAND="./github-mcp-server stdio"
```

### プラットフォーム別設定ファイル
プロジェクトには複数の設定ファイルが用意されています：

- **config.yaml**: デフォルト設定（Docker環境向け）
- **config_github.yaml**: GitHub専用設定
- **config_gitlab.yaml**: GitLab専用設定

#### 設定ファイルの使用例
```bash
# GitHub設定で実行
python main.py --config config_github.yaml

# GitLab設定で実行  
python main.py --config config_gitlab.yaml
```

## 使用方法

### 基本的な実行
```bash
# Conda 環境で実行
conda activate coding-agent
python main.py

# または run.sh を使用
./run.sh
```

### Docker での実行
```bash
# Docker コンテナでビルド・実行
docker-compose up

# または Docker run スクリプトを使用
./run-docker.sh
```

### タスクの作成
1. GitHub/GitLab で Issue または PR/MR を作成
2. `coding agent` ラベルを付与
3. エージェントが自動的に検知して処理開始

### 処理フロー
1. **タスク検知**: ラベル付きの Issue/PR/MR を検索
2. **ラベル更新**: `coding agent` → `coding agent processing`
3. **LLM 処理**: システムプロンプトに基づいて自動処理
4. **MCP ツール実行**: 必要に応じて外部ツールを呼び出し
5. **完了通知**: 処理完了時にラベルを `coding agent done` に更新

## アーキテクチャ

### クラス構造
```mermaid
classDiagram
    class TaskGetter {
        <<abstract>>
        +get_task_list()
        +from_task_key()
    }
    class Task {
        <<abstract>>
        +prepare()
        +get_prompt()
        +comment()
        +finish()
    }
    class MCPToolClient {
        +call_tool()
    }
    
    TaskGetter <|-- TaskGetterFromGitHub
    TaskGetter <|-- TaskGetterFromGitLab
    Task <|-- TaskGitHubIssue
    Task <|-- TaskGitLabIssue
```

### 主要コンポーネント
- **main.py**: エントリーポイント、全体のオーケストレーション
- **handlers/**: タスク処理のコアロジック
- **clients/**: LLM および MCP クライアント
- **config.yaml**: 設定ファイル
- **system_prompt.txt**: LLM 用のシステムプロンプト

## 開発

### 開発環境のセットアップ
1. 上記のインストール手順を実行
2. 開発用設定ファイルを作成
3. ログレベルを DEBUG に設定

### テスト
```bash
# テスト実行（テストが実装されている場合）
python -m pytest

# または個別のコンポーネントテスト
python -c "from clients.mcp_tool_client import MCPToolClient; print('MCP client loaded successfully')"
```

### ログの確認
```bash
# ログファイルの確認
tail -f logs/agent.log

# Debug モードでの実行
DEBUG=true python main.py
```

## ディレクトリ構造

```
.
├── main.py                 # メインエントリーポイント
├── config.yaml            # 設定ファイル
├── system_prompt.txt      # システムプロンプト
├── condaenv.yaml          # Conda 環境定義
├── docker-compose.yml     # Docker 構成
├── clients/               # LLM・MCP クライアント
│   ├── lm_client.py
│   ├── mcp_tool_client.py
│   ├── openai_client.py
│   ├── lmstudio_client.py
│   └── ollama_client.py
├── handlers/              # タスク処理ハンドラー
│   ├── task_getter.py
│   ├── task_handler.py
│   ├── task_getter_github.py
│   └── task_getter_gitlab.py
├── github-mcp-server/     # GitHub MCP サーバー
└── docs/                  # ドキュメント
    ├── spec.md
    ├── class_spec.md
    └── *.md
```

## トラブルシューティング

### よくある問題

**1. MCP サーバーが起動しない**
```bash
# GitHub MCP サーバーの再ビルド
cd github-mcp-server/cmd/github-mcp-server
go build -o ../../../github-mcp-server main.go
cd ../../..

# 権限の確認
chmod +x github-mcp-server

# Go のインストール確認
go version
```

**2. 認証エラー**
```bash
# GitHub トークンの確認
echo $GITHUB_TOKEN

# GitLab トークンの確認
echo $GITLAB_TOKEN

# 必要な権限
# GitHub: repo, issues, pull_requests
# GitLab: api, read_api, read_repository, write_repository
```

**3. LLM 接続エラー**
```bash
# OpenAI API キーの確認
echo $OPENAI_API_KEY

# LM Studio の起動確認（LM Studio 使用時）
curl http://localhost:1234/v1/models

# Ollama の起動確認（Ollama 使用時）
curl http://localhost:11434/api/version
```

**4. Python 依存関係エラー**
```bash
# Conda 環境の再作成
conda env remove -n coding-agent
conda env create -f condaenv.yaml
conda activate coding-agent

# 個別パッケージの確認
pip list | grep mcp
```

**5. Node.js MCP サーバーエラー**
```bash
# Node.js パッケージの再インストール
npm install

# GitLab MCP サーバーの確認
npx @zereight/mcp-gitlab --version

# Google Search MCP サーバーの確認
npx @adenot/mcp-google-search --version
```

**6. Docker 関連エラー**
```bash
# Docker コンテナのログ確認
docker-compose logs

# RabbitMQ の状態確認
docker-compose exec rabbitmq rabbitmqctl status

# コンテナの再起動
docker-compose down && docker-compose up --build
```

**7. ラベル設定エラー**
GitHub/GitLab リポジトリに以下のラベルが存在することを確認：
- `coding agent` (初期ラベル)
- `coding agent processing` (処理中ラベル)  
- `coding agent done` (完了ラベル)

**8. ログの確認**
```bash
# ログファイルの確認
tail -f logs/agent.log

# Debug モードでの実行
DEBUG=true python main.py

# 特定コンポーネントのログ
grep "MCP" logs/agent.log
grep "LLM" logs/agent.log
```

## コントリビューション

1. このリポジトリをフォーク
2. 機能ブランチを作成 (`git checkout -b feature/amazing-feature`)
3. 変更をコミット (`git commit -m 'Add amazing feature'`)
4. ブランチにプッシュ (`git push origin feature/amazing-feature`)
5. Pull Request を作成

## ライセンス

このプロジェクトは [ライセンス](LICENSE) の下で公開されています。

## 関連ドキュメント

- [仕様書](spec.md) - 詳細な仕様
- [クラス設計](class_spec.md) - アーキテクチャ詳細
- [GitHub MCP サーバー](github-mcp-server.md) - GitHub 連携
- [GitLab MCP サーバー](gitlab-mcp-server.md) - GitLab 連携
- [OpenAI 設定](openai.md) - OpenAI 設定詳細
- [LM Studio 設定](lmstudio.md) - LM Studio 設定詳細
- [Ollama 設定](ollama.md) - Ollama 設定詳細

## サポート

問題や質問がある場合は、[GitHub Issues](https://github.com/notfolder/coding_agent/issues) で報告してください。