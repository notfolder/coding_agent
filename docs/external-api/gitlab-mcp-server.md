# GitLab MCP サーバー仕様

本ドキュメントは、GitLab MCP サーバーの概要と使用方法を日本語でまとめたものです。

---

## 1. 概要

### 1.1 GitLab MCP サーバーとは

GitLab MCP サーバーは、Model Context Protocol（MCP）に準拠したサーバーで、GitLab APIとの連携を提供します。GitLabのリポジトリ、Issue、Merge Request、パイプラインなどの操作を自動化できます。

### 1.2 ユースケース

- GitLabワークフローとプロセスの自動化
- GitLabリポジトリからのデータ抽出と分析
- GitLabエコシステムと連携するAIツールやアプリケーションの構築

---

## 2. 前提条件

### 2.1 必要なソフトウェア

- **Node.js**: npxでサーバーを実行
- **GitLab Personal Access Token**: GitLab API操作用

### 2.2 必要な権限

GitLab Personal Access Tokenには、操作に必要な権限を付与してください。
- api: 全API操作
- read_api: 読み取り操作のみ
- read_repository: リポジトリ読み取り
- write_repository: リポジトリ書き込み

---

## 3. 利用可能なツール

### 3.1 ファイル操作

- **gitlab/create_or_update_file**: ファイルの作成または更新
  - プロジェクトID、ファイルパス、ブランチ、内容、コミットメッセージを指定

- **gitlab/get_file_contents**: ファイル内容の取得
  - プロジェクトID、ファイルパス、参照（ブランチ/タグ）を指定

- **gitlab/push_files**: 複数ファイルの一括プッシュ
  - プロジェクトID、ブランチ、コミットメッセージ、アクション配列を指定

- **gitlab/get_repository_tree**: リポジトリツリーの取得
  - プロジェクトID、パス、参照を指定

### 3.2 リポジトリ操作

- **gitlab/search_repositories**: リポジトリの検索
  - 検索クエリ、ページ番号、ページサイズを指定

- **gitlab/create_repository**: 新しいリポジトリの作成
  - 名前、ネームスペースID、可視性を指定

- **gitlab/fork_repository**: リポジトリのフォーク
  - プロジェクトID、ターゲットネームスペースを指定

- **gitlab/create_branch**: 新しいブランチの作成
  - プロジェクトID、ブランチ名、参照元を指定

- **gitlab/get_project**: プロジェクト情報の取得

- **gitlab/list_projects**: プロジェクト一覧の取得

- **gitlab/list_group_projects**: グループ内プロジェクト一覧の取得

### 3.3 Issue操作

- **gitlab/create_issue**: 新しいIssueの作成
  - プロジェクトID、タイトル、説明、ラベル、担当者を指定

- **gitlab/get_issue**: Issue情報の取得
  - プロジェクトID、Issue IIDを指定

- **gitlab/list_issues**: Issue一覧の取得
  - プロジェクトID、状態、ラベルでフィルタリング

- **gitlab/update_issue**: Issueの更新
  - タイトル、説明、ラベル、状態イベントを更新

- **gitlab/delete_issue**: Issueの削除

- **gitlab/list_issue_discussions**: Issueのディスカッション一覧

- **gitlab/create_issue_note**: Issueへのコメント追加

- **gitlab/update_issue_note**: Issueコメントの更新

### 3.4 Issueリンク操作

- **gitlab/list_issue_links**: Issueリンク一覧の取得
- **gitlab/get_issue_link**: Issueリンクの詳細取得
- **gitlab/create_issue_link**: Issueリンクの作成
- **gitlab/delete_issue_link**: Issueリンクの削除

### 3.5 Merge Request操作

- **gitlab/create_merge_request**: 新しいMerge Requestの作成
  - プロジェクトID、ソースブランチ、ターゲットブランチ、タイトル、説明、ラベルを指定

- **gitlab/get_merge_request**: Merge Request情報の取得
  - プロジェクトID、Merge Request IIDまたはブランチ名を指定

- **gitlab/list_merge_requests**: Merge Request一覧の取得
  - 状態、ソースブランチ、ターゲットブランチでフィルタリング

- **gitlab/update_merge_request**: Merge Requestの更新
  - タイトル、説明、ラベルを更新

- **gitlab/get_merge_request_diffs**: Merge Requestの差分取得
- **gitlab/list_merge_request_diffs**: Merge Requestの差分一覧取得
- **gitlab/get_branch_diffs**: ブランチ間の差分取得

### 3.6 Merge Requestコメント操作

- **gitlab/create_note**: ノートの作成（IssueまたはMerge Request）
- **gitlab/create_merge_request_thread**: Merge Requestスレッドの作成
- **gitlab/mr_discussions**: Merge Requestのディスカッション一覧
- **gitlab/create_merge_request_note**: Merge Requestへのノート追加
- **gitlab/update_merge_request_note**: Merge Requestノートの更新

### 3.7 パイプライン操作

- **gitlab/list_pipelines**: パイプライン一覧の取得
  - プロジェクトID、スコープでフィルタリング

- **gitlab/get_pipeline**: パイプライン詳細の取得

- **gitlab/create_pipeline**: 新しいパイプラインの作成
  - 参照、変数を指定

- **gitlab/retry_pipeline**: パイプラインの再実行
- **gitlab/cancel_pipeline**: パイプラインのキャンセル

### 3.8 パイプラインジョブ操作

- **gitlab/list_pipeline_jobs**: パイプラインジョブ一覧
- **gitlab/get_pipeline_job**: ジョブ詳細の取得
- **gitlab/get_pipeline_job_output**: ジョブ出力の取得

### 3.9 ラベル操作

- **gitlab/list_labels**: ラベル一覧の取得
- **gitlab/get_label**: ラベル詳細の取得
- **gitlab/create_label**: 新しいラベルの作成
- **gitlab/update_label**: ラベルの更新
- **gitlab/delete_label**: ラベルの削除

### 3.10 マイルストーン操作

- **gitlab/list_milestones**: マイルストーン一覧
- **gitlab/get_milestone**: マイルストーン詳細
- **gitlab/create_milestone**: 新しいマイルストーンの作成
- **gitlab/edit_milestone**: マイルストーンの編集
- **gitlab/delete_milestone**: マイルストーンの削除
- **gitlab/get_milestone_issue**: マイルストーンのIssue一覧
- **gitlab/get_milestone_merge_requests**: マイルストーンのMerge Request一覧
- **gitlab/promote_milestone**: マイルストーンの昇格
- **gitlab/get_milestone_burndown_events**: バーンダウンイベントの取得

### 3.11 Wiki操作

- **gitlab/list_wiki_pages**: Wikiページ一覧
- **gitlab/get_wiki_page**: Wikiページの取得
- **gitlab/create_wiki_page**: Wikiページの作成
- **gitlab/update_wiki_page**: Wikiページの更新
- **gitlab/delete_wiki_page**: Wikiページの削除

### 3.12 ネームスペース操作

- **gitlab/list_namespaces**: ネームスペース一覧
- **gitlab/get_namespace**: ネームスペース詳細
- **gitlab/verify_namespace**: ネームスペースの検証

### 3.13 ユーザー操作

- **gitlab/get_users**: ユーザー情報の取得
  - ユーザー名またはユーザーIDで検索

---

## 4. 本プロジェクトでの使用

### 4.1 設定方法

config.yamlのmcp_serversセクションでGitLab MCPサーバーを設定します。npxコマンドで起動するよう設定します。

### 4.2 必要な環境変数

GITLAB_PERSONAL_ACCESS_TOKENを環境変数として設定する必要があります。GitLab Enterprise Server使用時は、GITLAB_API_URLも設定してください。

### 4.3 ツール呼び出し形式

LLMからのツール呼び出しは「gitlab/ツール名」の形式で指定します。例えば、「gitlab/get_issue」や「gitlab/create_merge_request」などです。

---

**参照元**: GitLab MCP Server（@zereight/mcp-gitlab）
