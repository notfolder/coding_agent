# 開発ガイドライン (Development Guidelines)

## 🚨 重要な注意事項

### **Dev Container 環境での開発**

このプロジェクトは **VS Code Dev Container** を使用した開発環境を提供しています。
適切な開発を行うために、以下の手順を必ず守ってください。

## 📋 初期セットアップ手順

### 1. **必須：適切な場所でのクローン**

```bash
# ❌ 間違った例：ルートディレクトリでクローン
cd /
git clone https://github.com/notfolder/coding_agent.git

# ✅ 正しい例：ホームディレクトリ配下でクローン
cd /home/your_username
git clone https://github.com/notfolder/coding_agent.git
cd coding_agent
```

**⚠️ 重要**: 
- `/` (ルートディレクトリ) 直下でのクローンは避けてください
- ホームディレクトリ (`/home/username/`) 配下を推奨します
- Windows: `C:\Users\username\` 配下を推奨
- macOS: `/Users/username/` 配下を推奨

### 2. **VS Code Dev Container で開く**

```bash
# VS Code でプロジェクトを開く
code .
```

1. VS Code が起動したら、右下に表示される通知で **"Reopen in Container"** をクリック
2. または、コマンドパレット (`Ctrl+Shift+P`) から **"Dev Containers: Reopen in Container"** を選択

### 3. **Dev Container の自動セットアップ確認**

コンテナが起動すると、以下が自動的に実行されます：

- Python Conda 環境 (`coding-agent`) の作成
- 必要な拡張機能のインストール
- GitHub MCP サーバーのビルド
- 開発環境の準備

## 🔧 開発環境の構成

### **コンテナ環境の詳細**

- **ベースイメージ**: `condaforge/miniforge3`
- **Python環境**: Conda環境 `coding-agent`
- **作業ディレクトリ**: `/app`
- **ユーザー**: `root`

### **自動インストールされる拡張機能**

- Python関連：`ms-python.python`, `ms-python.pylint`, `ms-python.black-formatter`
- 開発ツール：`ms-vscode.makefile-tools`, `redhat.vscode-yaml`
- フォーマッター：`ms-python.isort`

### **ポートフォワーディング**

- `5672`: RabbitMQ AMQP
- `15672`: RabbitMQ Management UI (自動でブラウザが開きます)
- `8080`: GitLab (必要に応じて)

## 📁 プロジェクト構造の理解

### **重要なディレクトリ**

```
coding_agent/
├── .devcontainer/          # Dev Container設定
│   ├── devcontainer.json   # VS Code Dev Container設定
│   └── devcontainer-compose.json
├── clients/                # LLM・MCPクライアント
├── handlers/               # タスク処理ロジック
├── config/                 # 設定ファイル
├── tests/                  # テストケース
│   ├── unit/              # ユニットテスト
│   ├── integration/       # 統合テスト
│   └── real_integration/  # 実際のGitHub/GitLab連携テスト
└── docs/                  # ドキュメント
```

### **主要な設定ファイル**

- `config.yaml`: メイン設定
- `config_github.yaml`: GitHub専用設定
- `config_gitlab.yaml`: GitLab専用設定
- `condaenv.yaml`: Python環境定義
- `docker-compose.yml`: Docker構成

## 🚀 開発ワークフロー

### **1. 日常的な開発**

```bash
# Dev Container内で実行
conda activate coding-agent  # 通常は自動で有効

# アプリケーション実行
python main.py

# または実行スクリプト使用
./run.sh
```

### **2. テスト実行**

```bash
# ユニットテスト
python -m pytest tests/unit/

# 統合テスト
python -m pytest tests/integration/

# 実際のGitHub/GitLab連携テスト（要認証設定）
python -m pytest tests/real_integration/
```

### **3. コードフォーマット**

```bash
# Black でフォーマット
black .

# isort で import整理
isort .

# Pylint でチェック
pylint main.py handlers/ clients/
```

## 🔐 認証設定

### **環境変数の設定**

`.env` ファイルを作成して必要な認証情報を設定：

```bash
# GitHub設定
GITHUB_PERSONAL_ACCESS_TOKEN=your_github_token

# GitLab設定（GitLab使用時）
GITLAB_PERSONAL_ACCESS_TOKEN=your_gitlab_token

# LLM設定
OPENAI_API_KEY=your_openai_key
# または
LLM_PROVIDER=lmstudio  # lmstudio, ollama等
```

### **Dev Container環境変数**

`devcontainer.json`で以下の環境変数が自動設定されます：

```json
"containerEnv": {
    "TASK_SOURCE": "github",
    "DEBUG": "true",
    "GITHUB_PERSONAL_ACCESS_TOKEN": "${localEnv:GITHUB_PERSONAL_ACCESS_TOKEN}",
    "GITLAB_PERSONAL_ACCESS_TOKEN": "${localEnv:GITLAB_PERSONAL_ACCESS_TOKEN}"
}
```

## 🐛 トラブルシューティング

### **よくある問題と解決策**

#### 1. **Dev Container が起動しない**

```bash
# Docker Desktop の確認
docker --version
docker info

# VS Code Dev Container拡張機能の確認
# Extensions > Dev Containers がインストールされているか確認
```

#### 2. **Python環境が正しく設定されない**

```bash
# Dev Container内で確認
conda info --envs
conda activate coding-agent
python --version
```

#### 3. **MCP サーバーのビルドエラー**

```bash
# GitHub MCP サーバーの手動ビルド
cd github-mcp-server/cmd/github-mcp-server
go build -o ../../../github-mcp-server main.go
chmod +x ../../../github-mcp-server
```

#### 4. **ポート衝突**

```bash
# 使用中のポートを確認
netstat -tulpn | grep :5672
netstat -tulpn | grep :15672

# 必要に応じてdevcontainer.jsonのforwardPortsを変更
```

## 📚 参考資料

- [VS Code Dev Containers](https://code.visualstudio.com/docs/remote/containers)
- [Docker Desktop](https://www.docker.com/products/docker-desktop)
- [プロジェクト詳細仕様](docs/spec.md)
- [クラス設計](docs/class_spec.md)
- [GitHub MCP サーバー](docs/github-mcp-server.md)
- [GitLab MCP サーバー](docs/gitlab-mcp-server.md)

## 🤝 貢献ガイドライン

### **Pull Request 作成時**

1. 適切なブランチから作業開始
2. コードフォーマット実行
3. テスト追加・実行
4. ドキュメント更新（必要に応じて）
5. 明確なコミットメッセージ

### **コミットメッセージ規約**

```
タイプ: 簡潔な説明

詳細な説明（必要に応じて）

例:
feat: GitHub Issues自動処理機能を追加
fix: MCPクライアント接続エラーを修正
docs: 開発ガイドラインを更新
test: 実際のGitHub連携テストを追加
```

## ⚠️ 注意事項

### **やってはいけないこと**

- ❌ ルートディレクトリ（`/`）でのクローン
- ❌ Dev Container外での開発（環境の不整合を防ぐため）
- ❌ 認証情報をコードにハードコーディング
- ❌ `.env`ファイルのコミット

### **推奨事項**

- ✅ ホームディレクトリ配下でのクローン
- ✅ Dev Container環境での開発
- ✅ 環境変数による設定管理
- ✅ テストケースの作成・実行
- ✅ コードフォーマットの実行

---

**最終更新**: 2025年9月7日
**作成者**: Development Team
