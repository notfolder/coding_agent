# IssueおよびMerge Requestの新規コメント読み込み仕様書

## 1. 概要

### 1.1 目的

本仕様書は、coding_agentがIssueやMerge Requestに新たに追加されたユーザーコメントを読み込み、適切に反応するための機能を定義します。特に一時停止状態からの再開時に、新規コメントをコンテキストに追加し、ユーザーからのフィードバックに対応できるようにします。

### 1.2 背景

現在のcoding_agentは、タスク開始時に一度だけコメントを取得し、その後の新規コメントは検出していません。これにより、以下の課題が発生しています：

1. **フィードバックへの対応遅延**: ユーザーが追加した指示や修正依頼に気付かない
2. **コンテキストの不完全性**: 一時停止後の再開時に、停止中に追加されたコメントが反映されない
3. **対話性の欠如**: ユーザーとの双方向コミュニケーションが困難

### 1.3 要求事項

- 一時停止からの再開時に新規ユーザーコメントを検出・読み込みできること
- 新規コメントをコンテキストに追加しLLMが参照できること
- GitHub Issue、GitHub Pull Request、GitLab Issue、GitLab Merge Requestに対応すること
- デフォルト動作として設定不要で機能すること
- 既存の機能に影響を与えないこと

### 1.4 対象範囲

本仕様の対象範囲：

- 一時停止・再開時の新規コメント取得機能
- コメントのコンテキストへの追加機構
- GitHub/GitLab両プラットフォーム対応
- 設定オプションによる動作制御

本仕様の対象外：

- リアルタイムコメント監視（ポーリング方式）
- Webhook による即時通知対応
- コメント以外のタスク更新検出（タイトル・本文変更等）

## 2. 現状分析

### 2.1 現在のコメント取得方式

#### 2.1.1 GitHub Issue (TaskGitHubIssue)

`get_prompt()` メソッドで `get_issue_comments` ツールを使用してコメントを取得し、プロンプトに含めている。

現在の取得タイミング：
- タスク処理開始時の `get_prompt()` 呼び出し時のみ

#### 2.1.2 GitHub Pull Request (TaskGitHubPullRequest)

`get_prompt()` メソッドで `get_pull_request_comments` を使用してコメントを取得。

現在の取得タイミング：
- タスク処理開始時の `get_prompt()` 呼び出し時のみ

#### 2.1.3 GitLab Issue (TaskGitLabIssue)

`get_prompt()` メソッドで `list_issue_discussions` ツールを使用してコメントを取得。

現在の取得タイミング：
- タスク処理開始時の `get_prompt()` 呼び出し時のみ

#### 2.1.4 GitLab Merge Request (TaskGitLabMergeRequest)

`get_prompt()` メソッドで `list_merge_request_notes` を使用してコメントを取得。

現在の取得タイミング：
- タスク処理開始時の `get_prompt()` 呼び出し時のみ

### 2.2 一時停止・再開のフロー

現在の `PauseResumeManager` での処理：

#### 一時停止時 (`pause_task`)
1. タスク状態を `task_state.json` に保存
2. コンテキストディレクトリを `running/` から `paused/` に移動
3. ラベルを `processing` から `paused` に変更
4. 一時停止通知コメントを追加

#### 再開時 (`restore_task_context`)
1. `task_state.json` からタスク状態を読み込み
2. コンテキストディレクトリを `paused/` から `running/` に移動
3. ラベルを `paused` から `processing` に変更
4. 再開通知コメントを追加

**現状の問題点**: 再開時に新規コメントの取得処理がない

## 3. 新規コメント取得機能の詳細設計

### 3.1 設計方針

#### 3.1.1 デフォルト有効化

新規コメント取得機能はデフォルトで有効とし、追加設定なしで動作するようにします。

理由：
- ユーザーフィードバックへの対応は基本機能として必要
- 設定の複雑さを最小化
- 既存ユーザーへのスムーズな導入

#### 3.1.2 取得タイミング

新規コメントを取得するタイミング：

1. **一時停止からの再開時**（必須）
   - `restore_task_context()` 実行後、タスク処理継続前
   - 一時停止中に追加されたコメントを検出

2. **定期的な取得**（オプション）
   - 長時間実行タスクでの定期コメントチェック
   - デフォルト無効、設定で有効化可能

### 3.2 コンポーネント設計

#### 3.2.1 CommentFetcher クラス

**ファイル**: `handlers/comment_fetcher.py` (新規作成)

**責務**:
- IssueやMerge Requestからコメントを取得
- 新規コメント（最後の取得以降のコメント）を識別
- GitHub/GitLab両対応の抽象化

**主要属性**:

```
- task: Task オブジェクト
- last_fetched_comment_ids: 最後に取得したコメントIDのセット
- last_fetch_timestamp: 最後の取得時刻
```

**主要メソッド**:

**`__init__(task: Task)`**
- Taskオブジェクトを受け取りCommentFetcherを初期化
- last_fetched_comment_ids を空のセットで初期化
- last_fetch_timestamp を None で初期化

**`fetch_all_comments() -> list[Comment]`**
- タスクから全コメントを取得
- GitHub/GitLabの違いを内部で吸収
- Comment オブジェクトのリストを返す

**`fetch_new_comments() -> list[Comment]`**
- 最後の取得以降の新規コメントのみを取得
- last_fetched_comment_ids に含まれないコメントを返す
- 取得後に last_fetched_comment_ids と last_fetch_timestamp を更新

**`initialize_from_context(comment_state: dict) -> None`**
- 一時停止時に保存されたコメント状態から復元
- last_fetched_comment_ids と last_fetch_timestamp を復元

**`get_state_for_persistence() -> dict`**
- 一時停止時に保存するためのコメント状態を返す
- last_fetched_comment_ids と last_fetch_timestamp を辞書形式で返す

#### 3.2.2 Comment データクラス

**ファイル**: `handlers/comment_fetcher.py` 内に定義

**属性**:

```
- id: str                # コメントの一意識別子（文字列に統一）
- body: str              # コメント本文
- author: str            # 投稿者のユーザー名
- created_at: datetime   # 投稿日時
- is_bot: bool           # ボット（エージェント）による投稿か
```

**注意**: コメントIDは GitHub/GitLab からの取得時に整数で返される場合がありますが、
比較やシリアライゼーションの一貫性を保つため、内部では文字列に変換して統一します。

**メソッド**:

**`is_user_comment() -> bool`**
- ユーザー（非ボット）によるコメントかどうかを判定
- エージェント自身のコメントを除外するために使用

**`to_prompt_format() -> str`**
- LLMプロンプト用の文字列形式に変換
- 投稿者、日時、本文を含む整形された文字列を返す

### 3.3 PauseResumeManager への統合

#### 3.3.1 一時停止処理の拡張 (`pause_task`)

一時停止時に、現在のコメント状態を保存します。

**追加処理**:

```
1. 既存の一時停止処理を実行
   ↓
2. CommentFetcher から現在のコメント状態を取得
   - last_fetched_comment_ids
   - last_fetch_timestamp
   ↓
3. task_state.json に comment_state を追加保存
```

**task_state.json の拡張構造**:

```json
{
  "task_key": { ... },
  "uuid": "...",
  "user": "...",
  "paused_at": "...",
  "status": "paused",
  "resume_count": 0,
  "context_path": "...",
  "planning_state": { ... },
  "comment_state": {
    "last_fetched_comment_ids": ["123", "456", "789"],
    "last_fetch_timestamp": "2025-11-27T10:30:00Z"
  }
}
```

#### 3.3.2 再開処理の拡張 (`restore_task_context`)

再開時に新規コメントを取得し、コンテキストに追加します。

**追加処理**:

```
1. 既存の再開処理を実行
   ↓
2. task_state.json から comment_state を読み込み
   ↓
3. CommentFetcher を初期化し、comment_state から状態を復元
   ↓
4. fetch_new_comments() で新規コメントを取得
   ↓
5. 新規コメントが存在する場合:
   a. コメントをユーザーコメントのみにフィルタリング
   b. コンテキストに新規コメントを追加
   c. ログに新規コメント検出を記録
   ↓
6. 新規コメントの情報を返す
```

**戻り値の拡張**:

現在の `restore_task_context()` は `planning_state` のみを返していますが、`new_comments` も含めて返すように拡張します。

```python
def restore_task_context(self, task, task_uuid) -> dict[str, Any]:
    """
    Returns:
        {
            "planning_state": {...} | None,
            "new_comments": [Comment, ...] | []
        }
    """
```

### 3.4 コンテキストへの新規コメント追加

#### 3.4.1 追加方法

新規コメントは以下の形式でコンテキストに追加されます：

**追加先**: MessageStore の現在のコンテキスト

**追加形式**:

```
[再開時の新規コメント通知]
一時停止中に以下の新しいコメントが追加されました:

---
投稿者: @username1
日時: 2025-11-27 10:30:00 UTC
内容:
このバグ、もう少し詳しく調べてもらえますか？

---
投稿者: @username2
日時: 2025-11-27 11:00:00 UTC
内容:
追加情報です：エラーログはこちらです...

---
上記のコメントを考慮してタスクを継続してください。
```

#### 3.4.2 追加タイミング

```
1. restore_task_context() 完了
   ↓
2. 新規コメントがある場合、MessageStore に追加
   ↓
3. LLM 処理開始前にコンテキストに含まれる状態にする
   ↓
4. LLM は新規コメントを認識した状態で処理を継続
```

### 3.5 TaskHandler への統合

#### 3.5.1 _handle_with_context_storage の拡張

**追加処理**:

```
1. is_resumed フラグをチェック
   ↓
2. is_resumed=true の場合:
   a. PauseResumeManager.restore_task_context() を呼び出し
   b. 返された new_comments を取得
   c. new_comments が存在する場合:
      - MessageStore に新規コメント通知を追加
      - ログに記録
   ↓
3. 以降は既存の処理を継続
```

#### 3.5.2 _handle_with_planning の拡張

Planning モードでも同様に新規コメントを処理します：

```
1. is_resumed フラグをチェック
   ↓
2. is_resumed=true の場合:
   a. restore_task_context() で planning_state と new_comments を取得
   b. new_comments が存在する場合:
      - MessageStore に新規コメント通知を追加
      - Planning に影響する可能性があることをログに記録
   ↓
3. Planning 処理を継続
   - LLM は新規コメントを参照可能
   - 必要に応じてプラン修正が可能
```

## 4. GitHub/GitLab 対応

### 4.1 GitHub Issue

**コメント取得方法**:
- MCP ツール: `get_issue_comments`
- 引数: owner, repo, issue_number

**コメントの識別子**:
- `id` フィールド（整数）

**ボット判定**:
- コメント投稿者がエージェントの設定名と一致するか
- または `user.type == "Bot"` の判定

### 4.2 GitHub Pull Request

**コメント取得方法**:
- GitHubClient: `get_pull_request_comments()`
- 引数: owner, repo, pull_number

**コメントの識別子**:
- `id` フィールド（整数）

**ボット判定**:
- GitHub Issue と同様

### 4.3 GitLab Issue

**コメント取得方法**:
- MCP ツール: `list_issue_discussions`
- 引数: project_id, issue_iid

**コメントの識別子**:
- ノートの `id` フィールド

**ボット判定**:
- `system` フラグが true のノートは除外
- 投稿者がエージェント設定名と一致するか判定

### 4.4 GitLab Merge Request

**コメント取得方法**:
- GitLabClient: `list_merge_request_notes()`
- 引数: project_id, merge_request_iid

**コメントの識別子**:
- ノートの `id` フィールド

**ボット判定**:
- GitLab Issue と同様

### 4.5 プラットフォーム抽象化

CommentFetcher 内で Task のタイプに応じて適切なコメント取得メソッドを選択します：

```
Task タイプの判定:
  ↓
GitHub Issue の場合:
  - get_issue_comments を使用
  ↓
GitHub Pull Request の場合:
  - get_pull_request_comments を使用
  ↓
GitLab Issue の場合:
  - list_issue_discussions を使用
  ↓
GitLab Merge Request の場合:
  - list_merge_request_notes を使用
```

## 5. 設定オプション

### 5.1 デフォルト設定

新規コメント取得機能はデフォルトで有効です。追加設定なしで機能します。

### 5.2 config.yaml への追加項目

```yaml
# 新規コメント取得機能の設定（全てオプション）
new_comment_handling:
  # 新規コメント取得機能の有効/無効（デフォルト: true）
  enabled: true
  
  # ボットコメントを除外するかどうか（デフォルト: true）
  exclude_bot_comments: true
  
  # 定期コメントチェック機能（デフォルト: false）
  periodic_check:
    enabled: false
    # チェック間隔（アクション実行回数）
    interval: 10
  
  # コメント取得の制限設定
  limits:
    # コンテキストに追加する最大コメント数（デフォルト: 50）
    max_comments: 50
  
  # コメント通知のフォーマット設定
  notification_format:
    # 日本語/英語の選択（デフォルト: auto - タスクの言語に合わせる）
    language: "auto"
    # 詳細レベル: "full" (全情報), "summary" (要約のみ)
    detail_level: "full"
```

### 5.3 環境変数による設定上書き

以下の環境変数で設定を上書き可能：

- `NEW_COMMENT_ENABLED`: 新規コメント取得機能の有効/無効
- `NEW_COMMENT_EXCLUDE_BOT`: ボットコメント除外の有効/無効
- `NEW_COMMENT_PERIODIC_CHECK`: 定期チェックの有効/無効
- `NEW_COMMENT_CHECK_INTERVAL`: 定期チェックの間隔
- `NEW_COMMENT_MAX_COMMENTS`: コンテキストに追加する最大コメント数

## 6. エラーハンドリング

### 6.1 コメント取得失敗

**発生状況**:
- API レート制限
- ネットワークエラー
- 認証エラー

**対処方法**:

```
1. エラーをログに記録
   ↓
2. 警告コメントをタスクに追加（オプション）
   - "新規コメントの取得に失敗しました。最新のコメントが反映されていない可能性があります。"
   ↓
3. 処理は継続（既存のコンテキストで継続）
   - 新規コメント取得失敗でタスク処理を中断しない
```

### 6.2 コメント状態復元失敗

**発生状況**:
- task_state.json の comment_state が破損
- 形式が不正

**対処方法**:

```
1. エラーをログに記録
   ↓
2. 全コメントを再取得
   - 状態を初期化し、全コメントを新規として扱う
   - または、一時停止時刻以降のコメントのみを新規として扱う
   ↓
3. 処理を継続
```

### 6.3 大量のコメント

**発生状況**:
- 一時停止中に大量のコメントが追加された場合

**対処方法**:

```
1. コメント数をチェック
   ↓
2. 最大件数（デフォルト: 50件、設定可能）を超える場合:
   a. 最新50件のみをコンテキストに追加
   b. 残りは要約形式で通知
      - "他に X 件のコメントがあります"
   ↓
3. 処理を継続
```

**注意**: 最大件数は `new_comment_handling.max_comments` 設定で変更可能です（デフォルト: 50件）。

## 7. テストシナリオ

### 7.1 基本機能テスト

**シナリオ1: 一時停止中の新規コメント検出**

```
前提条件:
- タスクが実行中
- コメントが 3 件存在

テスト手順:
1. タスクを一時停止
2. 新しいコメントを 2 件追加（手動）
3. タスクを再開

期待結果:
- 新規コメント 2 件が検出される
- コンテキストに新規コメントが追加される
- LLM が新規コメントを参照できる
```

**シナリオ2: ボットコメントの除外**

```
前提条件:
- タスクが一時停止中
- 一時停止通知コメント（エージェント投稿）が 1 件

テスト手順:
1. 新しいユーザーコメントを 1 件追加
2. タスクを再開

期待結果:
- ユーザーコメントのみが新規コメントとして検出
- エージェントの一時停止通知コメントは除外
```

### 7.2 プラットフォーム別テスト

**シナリオ3: GitHub Issue でのテスト**

```
テスト手順:
1. GitHub Issue でタスクを開始
2. 一時停止
3. Issue に新規コメントを追加
4. 再開

期待結果:
- get_issue_comments で正しくコメントが取得される
- 新規コメントが識別される
```

**シナリオ4: GitLab Merge Request でのテスト**

```
テスト手順:
1. GitLab MR でタスクを開始
2. 一時停止
3. MR に新規コメントを追加
4. 再開

期待結果:
- list_merge_request_notes で正しくコメントが取得される
- 新規コメントが識別される
```

### 7.3 エラーケーステスト

**シナリオ5: API エラー時の動作**

```
前提条件:
- コメント取得 API がエラーを返す状態

テスト手順:
1. タスクを一時停止
2. API がエラーを返すように設定
3. タスクを再開

期待結果:
- エラーがログに記録される
- タスク処理は継続される（中断しない）
- 警告メッセージが適切に表示される
```

**シナリオ6: 大量コメント時の動作**

```
前提条件:
- 一時停止中に 100 件のコメントが追加

テスト手順:
1. タスクを再開

期待結果:
- 最新 N 件のコメントがコンテキストに追加
- 残りのコメントは要約形式で通知
- メモリ使用量が適切に制限される
```

### 7.4 Planning モードとの統合テスト

**シナリオ7: Planning 実行中の一時停止と再開**

```
前提条件:
- Planning モードでタスク実行中
- 計画が作成され、一部のアクションが完了

テスト手順:
1. タスクを一時停止
2. 「この方針で進めてください」というコメントを追加
3. タスクを再開

期待結果:
- Planning 状態が正しく復元される
- 新規コメントがコンテキストに追加される
- LLM がコメントを参照して処理を継続できる
```

## 8. 実装ガイドライン

### 8.1 ファイル構成

```
coding_agent/
├── handlers/
│   ├── comment_fetcher.py      (新規作成)
│   ├── task_handler.py         (修正)
│   └── ...
├── pause_resume_manager.py     (修正)
└── config.yaml                 (修正)
```

### 8.2 実装順序

```
Phase 1: 基本機能（必須）
  1. Comment データクラスの実装
  2. CommentFetcher クラスの実装
  3. PauseResumeManager への統合
  4. TaskHandler への統合
  5. ユニットテストの作成

Phase 2: プラットフォーム対応
  1. GitHub Issue 対応
  2. GitHub Pull Request 対応
  3. GitLab Issue 対応
  4. GitLab Merge Request 対応
  5. 各プラットフォームのテスト

Phase 3: 拡張機能（オプション）
  1. 設定オプションの実装
  2. 定期コメントチェック機能
  3. 大量コメント対応
  4. インテグレーションテスト
```

### 8.3 コーディング規約

- 型ヒントを必ず使用する
- 日本語コメントを適切に追加する
- 既存のコードスタイルに従う
- エラーハンドリングを適切に実装する

## 9. セキュリティ考慮事項

### 9.1 コメント内容の検証

コメント本文のセキュリティ対策として以下を実施します：

**基本的な入力サニタイゼーション**:
- コメント本文は LLM に渡す前に基本的なサニタイゼーションを実施
- 制御文字やゼロ幅文字の除去
- 極端に長いコメント（例: 10万文字以上）の切り詰め

**プロンプトインジェクション対策**:
- コメント本文は明確に「ユーザーからのコメント」としてマークアップ
- システムプロンプトと区別できる形式で LLM に渡す
- 明らかなインジェクション攻撃パターン（例: "ignore previous instructions"）を検出した場合はログに警告を出力

**制限事項**:
- 完全なプロンプトインジェクション対策は LLM 側のガードレールに依存
- 悪意のあるコード片がコメントに含まれる場合、LLM が実行しないことは保証できない
  - これは既存の get_prompt() 実装と同様のリスクレベル

### 9.2 API 認証情報

- コメント取得に使用する認証情報は既存の設定を再利用
- 追加の認証情報保存は行わない

### 9.3 データ永続化

- comment_state に含まれるのはコメント ID と時刻のみ
- コメント本文は永続化しない（必要時に API から取得）

## 10. まとめ

### 10.1 主要な設計ポイント

1. **デフォルト有効**: 追加設定なしで新規コメント取得機能が動作
2. **再開時の取得**: 一時停止からの再開時に新規コメントを自動検出
3. **プラットフォーム抽象化**: GitHub/GitLab の違いを CommentFetcher 内で吸収
4. **コンテキスト統合**: 新規コメントを MessageStore に追加し LLM が参照可能
5. **非破壊的**: 既存機能に影響を与えず、オプションで無効化も可能

### 10.2 期待される効果

- ユーザーフィードバックへの迅速な対応
- 一時停止・再開時の文脈の連続性確保
- 対話的なタスク処理の実現
- ユーザー体験の向上

### 10.3 実装時の注意点

- エラーハンドリングを徹底し、コメント取得失敗がタスク処理を中断しないこと
- 大量のコメントに対する適切な制限を設けること
- 既存のテストが影響を受けないこと
- 各プラットフォーム固有の API 仕様を正確に実装すること

### 10.4 今後の拡張可能性

1. **リアルタイム監視**: Webhook や長時間ポーリングによる即時検出
2. **コメント分類**: コメントの種類（質問、承認、修正依頼等）の自動分類
3. **優先度付け**: 重要なコメントの優先表示
4. **マルチタスク対応**: 複数タスク間でのコメント監視

---

**文書バージョン**: 1.0  
**作成日**: 2025-11-27  
**ステータス**: 詳細設計完了
