# GitHub MCP サーバー仕様

本ドキュメントは、GitHub MCP サーバーの概要と使用方法を日本語でまとめたものです。

---

## 1. 概要

### 1.1 GitHub MCP サーバーとは

GitHub MCP サーバーは、Model Context Protocol（MCP）に準拠したサーバーで、GitHub APIとのシームレスな統合を提供します。開発者やツールに対して、高度な自動化およびインタラクション機能を提供します。

### 1.2 ユースケース

- GitHubワークフローとプロセスの自動化
- GitHubリポジトリからのデータ抽出と分析
- GitHubエコシステムと連携するAIツールやアプリケーションの構築

---

## 2. 前提条件

### 2.1 必要なソフトウェア

- **Docker**: コンテナでサーバーを実行する場合
- **Go**: ソースからビルドする場合

### 2.2 必要な認証情報

GitHub Personal Access Tokenが必要です。GitHub設定画面から作成できます。MCPサーバーは多くのGitHub APIを使用するため、AIツールに付与する権限を適切に設定してください。

---

## 3. インストール方法

### 3.1 Docker使用の場合

Dockerがインストールされ実行中であることを確認します。イメージは公開されているため、認証なしでプルできます。エラーが発生した場合は、期限切れトークンの可能性があるため、docker logout ghcr.ioを実行してください。

### 3.2 ソースからビルドの場合

Dockerがない場合は、go buildを使用してcmd/github-mcp-serverディレクトリでバイナリをビルドできます。ビルドした実行ファイルを使用してサーバーを起動します。

---

## 4. ツール設定

### 4.1 ツールセットの概念

GitHub MCPサーバーは、--toolsetsフラグを使用して特定の機能グループの有効/無効を制御できます。必要なツールセットのみを有効にすることで、LLMのツール選択を支援し、コンテキストサイズを削減できます。

### 4.2 利用可能なツールセット

- **repos**: リポジトリ関連ツール（ファイル操作、ブランチ、コミット）
- **issues**: Issue関連ツール（作成、読み取り、更新、コメント）
- **users**: GitHubユーザーに関連するツール
- **pull_requests**: Pull Request操作（作成、マージ、レビュー）
- **code_security**: コードスキャンアラートとセキュリティ機能
- **experiments**: 実験的機能（安定版ではない）

### 4.3 ツールセットの指定方法

コマンドライン引数または環境変数で指定できます。環境変数GITHUB_TOOLSETSは、コマンドライン引数より優先されます。

### 4.4 「all」ツールセット

特別なツールセット「all」を指定すると、他の設定に関係なくすべての利用可能なツールセットが有効になります。

---

## 5. 動的ツール検出

### 5.1 概要

すべてのツールを有効にして開始する代わりに、動的ツールセット検出を有効にできます。これにより、MCPホストがユーザープロンプトに応じてツールセットをリストおよび有効化できます。利用可能なツールの数が多すぎてモデルが混乱する状況を回避するのに役立ちます。

### 5.2 使用方法

バイナリ使用時は--dynamic-toolsetsフラグを渡します。Docker使用時は環境変数GITHUB_DYNAMIC_TOOLSETS=1を設定します。

---

## 6. GitHub Enterprise Server

### 6.1 設定方法

--gh-hostフラグまたは環境変数GITHUB_HOSTを使用してGitHub Enterprise Serverのホスト名を設定できます。GitHub Enterprise ServerはHTTPをサポートしていないため、ホスト名にはhttpsのURIスキームをプレフィックスとして付けてください。

---

## 7. 国際化/説明のオーバーライド

### 7.1 設定ファイル

バイナリと同じディレクトリにgithub-mcp-server-config.jsonファイルを作成することで、ツールの説明をオーバーライドできます。

### 7.2 環境変数でのオーバーライド

環境変数を使用して説明をオーバーライドすることもできます。環境変数名はJSONファイルのキーと同じで、GITHUB_MCP_プレフィックスを付け、すべて大文字にします。

---

## 8. 利用可能なツール

### 8.1 ユーザー関連

- **get_me**: 認証済みユーザーの詳細を取得（パラメータ不要）

### 8.2 Issue関連

- **get_issue**: リポジトリ内のIssueの内容を取得
- **get_issue_comments**: GitHub IssueのコメントをS取得
- **create_issue**: GitHubリポジトリに新しいIssueを作成
- **add_issue_comment**: Issueにコメントを追加
- **list_issues**: リポジトリのIssueを一覧表示およびフィルタリング
- **update_issue**: 既存のIssueを更新
- **search_issues**: IssueとPull Requestを検索

### 8.3 Pull Request関連

- **get_pull_request**: 特定のPull Requestの詳細を取得
- **list_pull_requests**: リポジトリのPull Requestを一覧表示およびフィルタリング
- **merge_pull_request**: Pull Requestをマージ
- **get_pull_request_files**: Pull Requestで変更されたファイルのリストを取得
- **get_pull_request_status**: Pull Requestのすべてのステータスチェックの結合ステータスを取得
- **update_pull_request_branch**: ベースブランチの最新の変更でPull Requestブランチを更新
- **get_pull_request_comments**: Pull Requestのレビューコメントを取得
- **get_pull_request_reviews**: Pull Requestのレビューを取得
- **create_pull_request_review**: Pull Requestにレビューを作成
- **create_pull_request**: 新しいPull Requestを作成
- **add_pull_request_review_comment**: Pull Requestにレビューコメントを追加または既存のコメントに返信
- **update_pull_request**: 既存のPull Requestを更新

### 8.4 リポジトリ関連

- **create_or_update_file**: リポジトリ内の単一ファイルを作成または更新
- **list_branches**: GitHubリポジトリのブランチを一覧表示
- **push_files**: 単一のコミットで複数のファイルをプッシュ
- **search_repositories**: GitHubリポジトリを検索
- **create_repository**: 新しいGitHubリポジトリを作成
- **get_file_contents**: ファイルまたはディレクトリの内容を取得
- **fork_repository**: リポジトリをフォーク
- **create_branch**: 新しいブランチを作成
- **list_commits**: リポジトリのブランチのコミット一覧を取得
- **get_commit**: リポジトリからコミットの詳細を取得
- **search_code**: GitHubリポジトリ全体でコードを検索

### 8.5 ユーザー検索

- **search_users**: GitHubユーザーを検索

### 8.6 コードスキャン

- **get_code_scanning_alert**: コードスキャンアラートを取得
- **list_code_scanning_alerts**: リポジトリのコードスキャンアラートを一覧表示

### 8.7 シークレットスキャン

- **get_secret_scanning_alert**: シークレットスキャンアラートを取得
- **list_secret_scanning_alerts**: リポジトリのシークレットスキャンアラートを一覧表示

### 8.8 通知

- **list_notifications**: GitHubユーザーの通知を一覧表示
- **get_notification_details**: 特定のGitHub通知の詳細情報を取得
- **dismiss_notification**: 通知を既読またはDoneとしてマーク
- **mark_all_notifications_read**: すべての通知を既読としてマーク
- **manage_notification_subscription**: 通知スレッドのサブスクリプションを管理
- **manage_repository_notification_subscription**: リポジトリ通知サブスクリプションを管理

---

## 9. リソース

### 9.1 リポジトリコンテンツ

URIテンプレートを使用して、リポジトリの特定のパス、ブランチ、コミット、タグ、Pull Requestのコンテンツを取得できます。

---

## 10. 本プロジェクトでの使用

### 10.1 設定方法

config.yamlのmcp_serversセクションでGitHub MCPサーバーを設定します。Dockerまたはローカルビルドのどちらかを使用できます。

### 10.2 必要な環境変数

GITHUB_PERSONAL_ACCESS_TOKENを環境変数として設定する必要があります。このトークンには、操作に必要な権限を付与してください。

### 10.3 ツール呼び出し形式

LLMからのツール呼び出しは「github/ツール名」の形式で指定します。例えば、「github/get_issue」や「github/create_pull_request」などです。

---

**参照元**: GitHub MCP Server公式ドキュメント（https://github.com/github/github-mcp-server）
