# Issue から MR/PR への変換仕様書

## 1. 概要

### 1.1 目的

本仕様書は、GitHub/GitLab の Issue で依頼された内容を自動的に Merge Request (MR) / Pull Request (PR) として作成する機能の詳細設計を定義します。この機能により、Issue の内容に基づいて LLM がブランチ名を決定し、新しいタスクとして MR/PR を作成・処理することが可能になります。

### 1.2 スコープ

本仕様は以下をカバーします：

- Issue 内容からブランチ名を LLM で自動決定する仕組み
- Issue の内容とコメントを MR/PR に転記する処理
- 新規タスクとして MR/PR 処理を開始する方法
- GitHub と GitLab の両プラットフォーム対応
- エラーハンドリングと異常系処理

### 1.3 前提条件

- coding agent のラベルが付与された Issue が存在すること
- エージェントに MR/PR 作成権限があること
- LLM クライアントが JSON 形式での応答が可能であること
- MCP サーバーが正常に稼働していること

---

## 2. 機能概要

### 2.1 処理フロー図

```mermaid
flowchart TD
    subgraph Detection[検知フェーズ]
        A[Issue検知] --> B{MR/PR変換要求?}
        B -->|Yes| C[変換処理開始]
        B -->|No| D[通常のIssue処理]
    end
    
    subgraph BranchNaming[ブランチ名決定フェーズ]
        C --> E[Issue内容をLLMに送信]
        E --> F[LLMがブランチ名を生成]
        F --> G[ブランチ名の検証]
        G --> H{有効なブランチ名?}
        H -->|No| I[ブランチ名の修正]
        I --> G
        H -->|Yes| J[ブランチ作成]
    end
    
    subgraph MRCreation[MR/PR作成フェーズ]
        J --> K[MR/PRの作成]
        K --> L[Issue内容の転記]
        L --> M[コメントの転記]
        M --> N[ラベルの設定]
    end
    
    subgraph TaskStart[タスク開始フェーズ]
        N --> O[新規タスクとして登録]
        O --> P[元Issueにリンクコメント]
        P --> Q[MR/PRタスク処理開始]
    end
    
    Q --> R[完了]
```

### 2.2 主要コンポーネント

1. **IssueToMRConverter**: Issue から MR/PR への変換を制御するメインクラス
2. **BranchNameGenerator**: LLM を使用してブランチ名を生成するクラス
3. **ContentTransferManager**: Issue の内容とコメントを MR/PR に転記するクラス
4. **ConversionTaskFactory**: 変換後の MR/PR タスクを生成するファクトリークラス

---

## 3. ブランチ名決定機能

### 3.1 概要

LLM を使用して Issue の内容からブランチ名を自動生成します。ブランチ名は Git の命名規則に従い、Issue の内容を適切に反映したものとなります。

### 3.2 入力情報

LLM に以下の情報を提供してブランチ名を生成させます：

- **Issue タイトル**: Issue の題名
- **Issue 本文**: Issue の詳細説明
- **ラベル**: Issue に付与されているラベル一覧
- **リポジトリ名**: 対象リポジトリの名前
- **既存ブランチ一覧**: 重複を避けるための既存ブランチ情報

### 3.3 ブランチ名生成ルール

LLM に以下のルールを指示してブランチ名を生成させます：

#### 3.3.1 命名規則

- プレフィックスは Issue のタイプに応じて決定する
  - 機能追加: `feature/`
  - バグ修正: `fix/`
  - ドキュメント: `docs/`
  - リファクタリング: `refactor/`
  - テスト追加: `test/`
  - その他: `task/`
- 英語の小文字とハイフンのみを使用する
- 最大長は 50 文字とする
- Issue 番号を含めることを推奨する（例: `feature/123-add-user-auth`）

#### 3.3.2 禁止文字

以下の文字は使用不可として処理する：

- スペース
- 特殊文字（`~`, `^`, `:`, `?`, `*`, `[`, `\`）
- 連続するスラッシュ（`//`）
- 末尾のスラッシュ

### 3.4 ブランチ名の検証

LLM が生成したブランチ名に対して以下の検証を実施します：

1. **形式チェック**: Git の命名規則に準拠しているか
2. **重複チェック**: 既存のブランチ名と重複していないか
3. **長さチェック**: 最大長を超えていないか
4. **予約語チェック**: 禁止されたブランチ名（`main`, `master`, `develop` 等）でないか

### 3.5 LLM への指示形式

LLM に対して以下の形式で指示を行います：

**システムプロンプト拡張**:
- Issue の内容を分析し、適切なブランチ名を提案する役割を説明
- ブランチ名の命名規則を明記
- 出力形式（JSON）を指定

**期待する出力形式**:

LLM は以下の JSON 形式で応答することを期待します：

```json
{
  "branch_name": "feature/123-add-user-authentication",
  "reasoning": "Issue #123 はユーザー認証機能の追加を要求しているため、feature プレフィックスを使用し、内容を簡潔に表現しました。"
}
```

---

## 4. MR/PR 作成処理

### 4.1 概要

ブランチ名が決定した後、MR/PR を作成し、Issue の内容とコメントを転記します。

### 4.2 処理ステップ

#### 4.2.1 ブランチの作成

1. 対象リポジトリのデフォルトブランチ（`main` または `master`）から新規ブランチを作成する
2. ブランチ作成が失敗した場合は、ブランチ名を修正して再試行する

#### 4.2.2 初期コミットの作成

新規ブランチに初期コミットを作成する。この段階では、空コミットまたはプレースホルダーファイルの追加を行う。

#### 4.2.3 MR/PR の作成

以下の情報を設定して MR/PR を作成する：

- **タイトル**: Issue のタイトルをそのまま使用、または「WIP:」プレフィックスを付与
- **本文**: Issue の内容を転記（詳細は 4.3 参照）
- **ソースブランチ**: 作成した新規ブランチ
- **ターゲットブランチ**: デフォルトブランチ
- **ドラフトフラグ**: true（作業中として作成）

### 4.3 内容転記の詳細

MR/PR の本文には以下の情報を含めます：

#### 4.3.1 転記内容の構造

```markdown
## 📋 元 Issue からの転記

### Issue 情報
- **Issue 番号**: #123
- **作成者**: @username
- **作成日時**: 2025-01-01 12:00:00

### Issue 内容
{Issue の本文をそのまま転記}

---

## 💬 Issue コメント

### コメント 1
- **投稿者**: @commenter1
- **投稿日時**: 2025-01-02 10:00:00

{コメント内容}

### コメント 2
- **投稿者**: @commenter2
- **投稿日時**: 2025-01-03 15:30:00

{コメント内容}

---

## 🤖 自動生成情報
このMR/PRは Issue #{issue_number} から自動生成されました。
```

#### 4.3.2 コメント転記の制限

- 最大転記コメント数は設定で制御可能とする（デフォルト: 50件）
- ボットによる自動コメントは除外するオプションを提供
- コメントが長すぎる場合は、要約または省略して転記

### 4.4 ラベルの設定

MR/PR に以下のラベルを設定する：

1. `coding agent`: エージェントによる処理対象を示す
2. 元 Issue に付与されていたラベル（オプションで転記）
3. `from-issue`: Issue から変換されたことを示すラベル（オプション）

---

## 5. 新規タスクとしての処理

### 5.1 概要

作成された MR/PR を新規タスクとして登録し、通常の MR/PR タスク処理を開始します。

### 5.2 タスク登録処理

#### 5.2.1 タスクキーの生成

MR/PR のタスクキーを生成し、タスク管理システムに登録します。

- GitHub の場合: `GitHubPullRequestTaskKey` を使用
- GitLab の場合: `GitLabMergeRequestTaskKey` を使用

#### 5.2.2 元 Issue との関連付け

新規タスクと元 Issue の関連を保持するため、以下の情報を記録します：

- 元 Issue のタスクキー
- 変換日時
- 変換を実行したエージェント情報

### 5.3 元 Issue へのリンクコメント

元の Issue に対して、MR/PR が作成されたことを通知するコメントを投稿します。

**コメント形式**:

```markdown
## 🚀 MR/PR を作成しました

この Issue の内容に基づいて、以下の MR/PR を作成しました：

- **MR/PR**: #{mr_number}
- **ブランチ**: `{branch_name}`
- **リンク**: {mr_url}

以降の処理は MR/PR 上で進めます。
```

### 5.4 元 Issue のステータス更新

MR/PR 作成後、元の Issue に対して以下の処理を行います：

1. **ラベル変更**: `coding agent` → `coding agent converted` または独自のラベルに変更
2. **アサイン解除**: オプションで元 Issue からのアサインを解除
3. **Issue クローズ**: オプションで元 Issue を自動的にクローズ（設定で制御）

---

## 6. プラットフォーム別実装

### 6.1 GitHub 対応

#### 6.1.1 使用する API / ツール

- **ブランチ作成**: `github_create_branch` または GitHub REST API
- **PR 作成**: `github_create_pull_request` MCP ツール
- **コメント取得**: `get_issue_comments` MCP ツール
- **コメント投稿**: `add_issue_comment` MCP ツール

#### 6.1.2 GitHub 固有の処理

- Pull Request のドラフトモード設定
- Issue と PR の自動リンク（`Closes #123` 形式）

### 6.2 GitLab 対応

#### 6.2.1 使用する API / ツール

- **ブランチ作成**: GitLab API を使用
- **MR 作成**: GitLab MCP サーバーまたは REST API
- **コメント取得**: GitLab API を使用
- **コメント投稿**: GitLab API を使用

#### 6.2.2 GitLab 固有の処理

- Merge Request の WIP ステータス設定
- Issue と MR の関連付け設定

---

## 7. 設定オプション

### 7.1 config.yaml の設定項目

`issue_to_mr_conversion` セクションで以下を設定します：

| 設定項目 | 説明 | デフォルト値 |
|---------|------|-------------|
| enabled | Issue → MR/PR 変換機能の有効/無効 | false |
| trigger_label | 変換をトリガーするラベル | "create-mr" |
| auto_draft | PR/MR をドラフトとして作成するか | true |
| transfer_comments | コメントを転記するか | true |
| max_comments | 転記するコメントの最大数 | 50 |
| exclude_bot_comments | ボットコメントを除外するか | true |
| close_source_issue | 元 Issue を自動クローズするか | false |
| transfer_labels | ラベルを転記するか | true |
| branch_prefix_mapping | ラベルとブランチプレフィックスのマッピング | (下記参照) |

#### 7.1.1 branch_prefix_mapping の設定例

```yaml
issue_to_mr_conversion:
  branch_prefix_mapping:
    enhancement: "feature/"
    bug: "fix/"
    documentation: "docs/"
    refactoring: "refactor/"
    default: "task/"
```

### 7.2 環境変数

| 環境変数 | 説明 |
|---------|------|
| ISSUE_TO_MR_ENABLED | 機能の有効/無効 (true/false) |
| ISSUE_TO_MR_TRIGGER_LABEL | トリガーラベル |

---

## 8. エラーハンドリング

### 8.1 ブランチ作成エラー

#### 8.1.1 ブランチ名重複

既存のブランチ名と重複する場合：

1. ブランチ名にサフィックス（`-2`, `-3` 等）を追加して再試行
2. 最大 5 回まで再試行
3. 全て失敗した場合は処理を中断し、Issue にエラーコメントを投稿

#### 8.1.2 権限エラー

ブランチ作成権限がない場合：

1. Issue にエラーコメントを投稿
2. 処理を中断
3. ログにエラー詳細を記録

### 8.2 MR/PR 作成エラー

#### 8.2.1 作成失敗

MR/PR の作成に失敗した場合：

1. 作成したブランチを削除（クリーンアップ）
2. Issue にエラーコメントを投稿
3. ログにエラー詳細を記録

### 8.3 コメント転記エラー

コメントの転記に失敗した場合：

1. エラーをログに記録
2. 転記をスキップして処理を継続
3. MR/PR に警告コメントを追加

### 8.4 LLM ブランチ名生成エラー

LLM がブランチ名を適切に生成できない場合：

1. フォールバックとして Issue 番号ベースのデフォルト名を使用
2. 例: `task/{issue_number}-auto-generated`
3. Issue に警告コメントを投稿

---

## 9. トリガー方式

### 9.1 ラベルベースのトリガー

特定のラベル（例: `create-mr`）が Issue に付与された場合に変換処理を開始します。

### 9.2 コメントベースのトリガー

Issue のコメントに特定のコマンド（例: `/create-mr`）が投稿された場合に変換処理を開始します。

#### 9.2.1 コメントコマンド形式

```
/create-mr [オプション]

オプション:
  --branch <name>   : ブランチ名を指定（LLM 生成をスキップ）
  --no-comments     : コメント転記をスキップ
  --no-draft        : ドラフトではなく通常の PR として作成
```

### 9.3 両方のラベルが存在する場合

`coding agent` ラベルと `create-mr` ラベルの両方が存在する場合、まず MR/PR への変換を実行してから、MR/PR に対して通常のタスク処理を開始します。

---

## 10. アーキテクチャ

### 10.1 クラス図

```mermaid
classDiagram
    class IssueToMRConverter {
        -task: Task
        -llm_client: LLMClient
        -mcp_client: MCPToolClient
        -config: dict
        +convert() TaskResult
        -_generate_branch_name() str
        -_create_branch() bool
        -_create_mr_pr() dict
        -_transfer_content() bool
        -_notify_source_issue() bool
    }
    
    class BranchNameGenerator {
        -llm_client: LLMClient
        -config: dict
        +generate(issue_info: dict) str
        -_build_prompt() str
        -_validate_name(name: str) bool
        -_sanitize_name(name: str) str
    }
    
    class ContentTransferManager {
        -source_task: Task
        -target_task: Task
        +transfer_content() bool
        +transfer_comments() bool
        -_format_content() str
        -_format_comments() str
    }
    
    class ConversionTaskFactory {
        -config: dict
        -mcp_clients: dict
        +create_from_mr(mr_info: dict) Task
    }
    
    IssueToMRConverter --> BranchNameGenerator
    IssueToMRConverter --> ContentTransferManager
    IssueToMRConverter --> ConversionTaskFactory
```

### 10.2 シーケンス図

```mermaid
sequenceDiagram
    participant TH as TaskHandler
    participant IC as IssueToMRConverter
    participant BNG as BranchNameGenerator
    participant LLM as LLMClient
    participant MCP as MCPToolClient
    participant CTM as ContentTransferManager
    participant CTF as ConversionTaskFactory

    TH->>IC: convert(issue_task)
    IC->>BNG: generate(issue_info)
    BNG->>LLM: ブランチ名生成リクエスト
    LLM-->>BNG: ブランチ名応答
    BNG->>BNG: validate_name()
    BNG-->>IC: branch_name
    
    IC->>MCP: create_branch(branch_name)
    MCP-->>IC: success
    
    IC->>MCP: create_pull_request(pr_info)
    MCP-->>IC: pr_data
    
    IC->>CTM: transfer_content(issue, pr)
    CTM->>MCP: update_pull_request(content)
    MCP-->>CTM: success
    CTM->>MCP: get_issue_comments()
    MCP-->>CTM: comments
    CTM-->>IC: success
    
    IC->>MCP: add_issue_comment(notification)
    MCP-->>IC: success
    
    IC->>CTF: create_from_mr(pr_data)
    CTF-->>IC: new_task
    
    IC-->>TH: TaskResult(new_task)
```

---

## 11. 将来の拡張

### 11.1 検討中の機能

- **テンプレート対応**: MR/PR の本文テンプレートをカスタマイズ可能にする
- **複数 Issue の統合**: 関連する複数の Issue を 1 つの MR/PR にまとめる機能
- **自動マイルストーン設定**: Issue のマイルストーンを MR/PR に引き継ぐ
- **レビュアー自動設定**: 元 Issue の関係者を自動的にレビュアーに設定

### 11.2 互換性の考慮

将来の機能拡張時にも、既存の設定やワークフローとの後方互換性を維持します。

---

## 12. 関連ドキュメント

- [基本仕様](spec.md)
- [クラス設計](class_spec.md)
- [プランニングプロセス仕様](PLANNING_SPECIFICATION.md)
- [プロジェクトエージェントルール仕様](PROJECT_AGENT_RULES_SPECIFICATION.md)
- [コメント検知仕様](COMMENT_DETECTION_SPECIFICATION.md)

---

**文書バージョン:** 1.0  
**最終更新日:** 2025-11-29  
**ステータス:** 設計完了
