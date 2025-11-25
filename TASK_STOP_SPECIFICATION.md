# ユーザーコメントによるタスク停止機能 詳細設計

## 1. 概要

### 1.1 目的
本仕様書では、issue や merge request 上でユーザーがコーディングエージェント（GITLAB_BOT_NAME または GITHUB_BOT_NAME）のアサインを外した場合に、タスクを自動的に停止する機能について詳細設計を行います。

### 1.2 背景
現在のcoding_agentシステムでは、`pause_signal`ファイルの作成による一時停止機能（PAUSE_RESUME_SPECIFICATION.md参照）が実装されています。しかし、ユーザーがissueやmerge request上で直接タスクの停止を指示する手段がありません。

本機能は、ユーザーがissueやmerge requestからコーディングエージェントのアサインを解除することで、タスクを即座に停止できるようにすることを目的としています。

### 1.3 対象範囲
- GitHub Issue/Pull Request におけるアサイン解除検出
- GitLab Issue/Merge Request におけるアサイン解除検出
- 処理ループ内でのアサイン状況チェック
- アサイン解除時のタスク停止処理

### 1.4 一時停止との違い
| 項目 | 一時停止（pause_signal） | 停止（アサイン解除） |
|------|------------------------|---------------------|
| トリガー | `contexts/pause_signal`ファイル作成 | アサインの解除 |
| 再開可能性 | 可能（再投入で再開） | 不可（タスク終了） |
| 状態保存 | `contexts/paused/`に保存 | `contexts/completed/`に保存 |
| ラベル変更 | `coding agent paused`に変更 | `coding agent stopped`に変更 |
| 完了通知 | 一時停止メッセージを投稿 | 停止理由をコメント |

## 2. 停止条件の定義

### 2.1 アサイン解除の判定
タスク停止の判定は、以下の条件で行います：

**GitHub の場合:**
- Issue/Pull Request の `assignees` 配列から、`GITHUB_BOT_NAME`（環境変数で指定されるボットのユーザー名）が含まれていない場合

**GitLab の場合:**
- Issue/Merge Request の `assignee` または `assignees` フィールドから、`GITLAB_BOT_NAME`（環境変数で指定されるボットのユーザー名）が含まれていない場合

### 2.2 ボット名の取得
ボット名は以下の環境変数から取得します：

```
GITHUB_BOT_NAME: GitHubでのボットのユーザー名
GITLAB_BOT_NAME: GitLabでのボットのユーザー名
```

環境変数が設定されていない場合は、設定ファイル（config.yaml）の以下のフィールドから取得します：

```yaml
github:
  bot_name: "coding-agent-bot"

gitlab:
  bot_name: "coding-agent-bot"
```

## 3. アサイン状況チェックのタイミング

### 3.1 チェックタイミング
アサイン状況のチェックは、PAUSE_RESUME_SPECIFICATION.md で定義されている一時停止チェックと同じタイミングで実行します：

```
■ Context Storage モード（Planning無効）の処理フロー:
  1. 処理ループの各イテレーション開始時
     ↓
     アサイン状況チェック
     ↓
  2. LLM応答を取得した後、次のアクション実行前
     ↓
  3. ツール実行完了後、LLMへの結果送信前
```

```
■ Planning モードの処理フロー:
  1. Planningフェーズ開始前
     ↓
     アサイン状況チェック
     ↓
  2. Planningフェーズ完了後
     ↓
     アサイン状況チェック
     ↓
  3. 各アクション実行前
     ↓
     アサイン状況チェック
     ↓
  4. リフレクション実行前
     ↓
     アサイン状況チェック
     ↓
  5. プラン修正実行前
     ↓
     アサイン状況チェック
     ↓
```

### 3.2 デフォルト動作
タスク停止機能はデフォルトで有効です。特別な設定がなくても、環境変数またはconfig.yamlにボット名が設定されていれば動作します。

設定ファイルで、アサインチェックの頻度を変更することも可能です（デフォルト値で動作）：

```yaml
# task_stop設定は省略可能（以下はすべてデフォルト値）
task_stop:
  enabled: true           # デフォルト: true（有効）
  check_interval: 1       # デフォルト: 1（毎回チェック）
  min_check_interval_seconds: 30  # デフォルト: 30秒
```

## 4. アサイン状況の取得方法

### 4.1 GitHub Issue のアサイン取得

**取得元:**
`TaskGitHubIssue.issue` オブジェクトの `assignees` フィールドから取得します。
タスク処理開始時に取得済みの情報を使用するため、追加のAPI呼び出しは不要です。

**データ構造:**
```json
{
  "assignees": [
    {
      "login": "user1",
      "id": 12345
    },
    {
      "login": "coding-agent-bot",
      "id": 67890
    }
  ]
}
```

**チェックロジック:**
1. `TaskGitHubIssue.issue["assignees"]` から `login` フィールドを抽出
2. `GITHUB_BOT_NAME` が含まれているかチェック
3. 含まれていない場合 → タスク停止

### 4.2 GitHub Pull Request のアサイン取得

**取得元:**
`TaskGitHubPullRequest.pr` オブジェクトの `assignees` フィールドから取得します。
タスク処理開始時に取得済みの情報を使用するため、追加のAPI呼び出しは不要です。

**チェックロジック:**
1. `TaskGitHubPullRequest.pr["assignees"]` から `login` フィールドを抽出
2. `GITHUB_BOT_NAME` が含まれているかチェック
3. 含まれていない場合 → タスク停止

### 4.3 GitLab Issue のアサイン取得

**取得元:**
`TaskGitLabIssue.issue` オブジェクトの `assignees` または `assignee` フィールドから取得します。
タスク処理開始時に取得済みの情報を使用するため、追加のAPI呼び出しは不要です。

**データ構造:**
```json
{
  "assignees": [
    {
      "username": "user1",
      "id": 12345
    },
    {
      "username": "coding-agent-bot",
      "id": 67890
    }
  ],
  "assignee": {
    "username": "coding-agent-bot",
    "id": 67890
  }
}
```

**チェックロジック:**
1. `TaskGitLabIssue.issue["assignees"]` または `TaskGitLabIssue.issue["assignee"]` から `username` フィールドを抽出
2. `GITLAB_BOT_NAME` が含まれているかチェック
3. 含まれていない場合 → タスク停止

### 4.4 GitLab Merge Request のアサイン取得

**取得元:**
`TaskGitLabMergeRequest.mr` オブジェクトの `assignees` または `assignee` フィールドから取得します。
タスク処理開始時に取得済みの情報を使用するため、追加のAPI呼び出しは不要です。

**チェックロジック:**
1. `TaskGitLabMergeRequest.mr["assignees"]` または `TaskGitLabMergeRequest.mr["assignee"]` から `username` フィールドを抽出
2. `GITLAB_BOT_NAME` が含まれているかチェック
3. 含まれていない場合 → タスク停止

## 5. タスク停止処理の詳細フロー

### 5.1 停止処理の全体フロー

```
1. アサイン状況チェック開始
   ↓
2. タスクオブジェクトからアサイン情報を取得
   ↓
3. アサイン状況を判定
   ├─ ボットがアサインされている場合 → 処理継続
   └─ ボットがアサインされていない場合 → 停止処理へ
   ↓
4. 停止処理開始
   ↓
5. 停止理由をコメントとして投稿
   ↓
6. 処理中ラベル（coding agent processing）を削除
   ↓
7. 停止ラベル（coding agent stopped）を追加
   ↓
8. Context Storage を completed ディレクトリに移動
   ↓
9. タスク処理を終了（finish()は呼び出さない）
   ↓
10. Consumer処理ループを正常終了
```

### 5.2 停止時のコメント

タスク停止時に以下のコメントをissue/MR/PRに投稿します。
処理モードに応じて異なるテンプレートを使用します。

**Planningモードの場合:**
```markdown
## ⛔ タスク停止

コーディングエージェントのアサインが解除されたため、タスクを停止しました。

**停止時刻:** {ISO 8601形式のタイムスタンプ}
**処理状況:** {実行済みアクション数}/{全アクション数} 完了
**フェーズ:** {現在のフェーズ（planning/execution/reflection/revision）}

タスクを再開する場合は、コーディングエージェントを再度アサインし、
`coding agent` ラベルを付与してください。
```

**Context Storageモード（Planning無効）の場合:**
```markdown
## ⛔ タスク停止

コーディングエージェントのアサインが解除されたため、タスクを停止しました。

**停止時刻:** {ISO 8601形式のタイムスタンプ}
**LLM対話回数:** {実行済みのLLM対話回数}

タスクを再開する場合は、コーディングエージェントを再度アサインし、
`coding agent` ラベルを付与してください。
```

**レガシーモードの場合:**
```markdown
## ⛔ タスク停止

コーディングエージェントのアサインが解除されたため、タスクを停止しました。

**停止時刻:** {ISO 8601形式のタイムスタンプ}

タスクを再開する場合は、コーディングエージェントを再度アサインし、
`coding agent` ラベルを付与してください。
```

### 5.3 ラベル管理

**停止時のラベル処理:**
1. `coding agent processing` ラベルを削除
2. `coding agent stopped` ラベルを追加

停止ラベルは config.yaml の github/gitlab セクションに、他のラベルと同じ位置で設定します：

```yaml
github:
  bot_label: "coding agent"
  processing_label: "coding agent processing"
  done_label: "coding agent done"
  paused_label: "coding agent paused"
  stopped_label: "coding agent stopped"  # 停止時に付与するラベル

gitlab:
  bot_label: "coding agent"
  processing_label: "coding agent processing"
  done_label: "coding agent done"
  paused_label: "coding agent paused"
  stopped_label: "coding agent stopped"  # 停止時に付与するラベル
```

### 5.4 Context Storage の処理

タスク停止時は、Context Storage を completed ディレクトリに移動します：
- `contexts/running/{task_uuid}/` → `contexts/completed/{task_uuid}/` に移動
- 通常のタスク完了時と同様の処理を行い、処理履歴を保持
- これにより、停止したタスクの処理履歴を後から確認可能

## 6. 実装の詳細設計

### 6.1 TaskStopManager クラス

新規に `TaskStopManager` クラスを作成し、アサインチェックと停止処理を管理します。

**ファイル:** `task_stop_manager.py`

**クラス構造:**
```
TaskStopManager
├── __init__(config: dict)
├── check_assignee_status(task: Task) -> bool
│   └── タスクのアサイン状況をチェックし、ボットがアサインされているかを返す
├── stop_task(task: Task, task_uuid: str, reason: str) -> None
│   └── タスク停止処理を実行
├── _get_bot_name(task_type: str) -> str | None
│   └── タスクタイプに応じたボット名を取得
├── _check_github_assignees(task: Task) -> bool
│   └── GitHub Issue/PRのアサインをチェック
├── _check_gitlab_assignees(task: Task) -> bool
│   └── GitLab Issue/MRのアサインをチェック
├── _post_stop_comment(task: Task, reason: str) -> None
│   └── 停止コメントを投稿
└── _move_to_completed(task_uuid: str) -> None
    └── Context Storage を completed に移動
```

### 6.2 Task クラスへの追加メソッド

`Task` 抽象基底クラスに `get_assignees()` メソッドを追加します。

**メソッド仕様:**
- **目的:** タスクにアサインされているユーザー名のリストを取得する
- **戻り値:** アサインされているユーザー名のリスト（list[str]）
- **例外:** API呼び出しに失敗した場合は例外をスロー
- **注意:** 呼び出し元でエラーハンドリングを行い、エラー時はタスクを停止せずに処理を継続する

**各タスククラスでの実装方針:**

**TaskGitHubIssue:**
- `self.issue["assignees"]` から `login` フィールドを抽出してリストを返す
- タスクオブジェクト内の既存データを使用するため、追加のAPI呼び出しは不要

**TaskGitHubPullRequest:**
- `self.pr["assignees"]` から `login` フィールドを抽出してリストを返す
- タスクオブジェクト内の既存データを使用するため、追加のAPI呼び出しは不要

**TaskGitLabIssue:**
- `self.issue["assignees"]` または `self.issue["assignee"]` から `username` フィールドを抽出
- `assignees` 配列が空でなければ使用し、空の場合は `assignee` 単体フィールドを確認
- タスクオブジェクト内の既存データを使用するため、追加のAPI呼び出しは不要

**TaskGitLabMergeRequest:**
- `self.mr["assignees"]` または `self.mr["assignee"]` から `username` フィールドを抽出
- `assignees` 配列が空でなければ使用し、空の場合は `assignee` 単体フィールドを確認
- タスクオブジェクト内の既存データを使用するため、追加のAPI呼び出しは不要

### 6.3 TaskHandler への組み込み

`TaskHandler` クラスの処理ループに、アサインチェックを追加します。

**_handle_with_context_storage メソッドの改修内容:**

1. **初期化処理:**
   - `TaskStopManager` をインスタンス化
   - チェック間隔カウンターを初期化

2. **処理ループ内でのチェック:**
   - 各イテレーション開始時にカウンターをインクリメント
   - 一時停止シグナルのチェック（既存処理）を先に実行
   - `check_interval` 設定に基づき、指定回数ごとにアサインチェックを実行
   - `min_check_interval_seconds` 設定に基づき、前回チェックから指定秒数経過後にのみ実行
   - アサイン解除を検出した場合、停止処理を実行してループを終了

3. **停止処理の実行:**
   - 停止コメントを投稿
   - 処理中ラベルを削除し、停止ラベルを追加
   - Context Storage を completed ディレクトリに移動
   - `finish()` は呼び出さずにループを終了

### 6.4 PlanningCoordinator への組み込み

`PlanningCoordinator` クラスにも同様にアサインチェックを追加します。

**execute_with_planning メソッドの改修内容:**

1. **初期化処理:**
   - `TaskStopManager` をインスタンス化し、インスタンス変数に保持

2. **チェックタイミング:**
   - Planningフェーズ開始前・完了後
   - 各アクション実行前
   - リフレクション実行前
   - プラン修正実行前
   - 上記の各タイミングで、一時停止チェックの後にアサインチェックを実行

3. **停止検出時の処理:**
   - `_check_stop_signal()` メソッドでアサイン状況を確認
   - アサイン解除を検出した場合、`_handle_stop()` メソッドを呼び出し
   - 停止コメントには実行済みアクション数を含める
   - 正常終了として `True` を返却（失敗扱いにしない）

### 6.5 チェック頻度の制御

**check_interval の動作:**
- 設定値が 1 の場合（デフォルト）: 毎回チェック
- 設定値が 0 の場合: チェック無効
- 設定値が N（2以上）の場合: N 回のループごとにチェック

**min_check_interval_seconds の動作:**
- 前回のチェックから指定秒数が経過していない場合はチェックをスキップ
- デフォルトは 30 秒
- API レート制限への配慮として機能

**should_check_now() メソッドの処理:**
1. 前回チェック時刻が未設定の場合は現在時刻を設定し、チェックを実行
2. 前回チェックから経過秒数を計算
3. 経過秒数が `min_check_interval_seconds` 以上の場合、時刻を更新してチェックを実行
4. それ以外の場合はチェックをスキップ

## 7. 設定ファイルへの追加項目

### 7.1 config.yaml への追加

停止ラベルは github/gitlab セクションに、他のラベルと同じ位置で設定します：

```yaml
github:
  owner: "notfolder"
  bot_label: "coding agent"
  processing_label: "coding agent processing"
  done_label: "coding agent done"
  paused_label: "coding agent paused"
  stopped_label: "coding agent stopped"  # 停止時に付与するラベル
  bot_name: "coding-agent-bot"           # ボットのユーザー名
  query: 'state:open archived:false sort:updated-desc'

gitlab:
  owner: "notfolder"
  bot_label: "coding agent"
  processing_label: "coding agent processing"
  done_label: "coding agent done"
  paused_label: "coding agent paused"
  stopped_label: "coding agent stopped"  # 停止時に付与するラベル
  bot_name: "coding-agent-bot"           # ボットのユーザー名
  project_id: "coding-agent-project"
  query: ''
```

タスク停止機能の設定は省略可能です（以下はすべてデフォルト値で動作）：

```yaml
# 以下の設定は省略可能（デフォルト値で動作）
task_stop:
  enabled: true                    # デフォルト: true
  check_interval: 1                # デフォルト: 1（毎回チェック）
  min_check_interval_seconds: 30   # デフォルト: 30秒
```

### 7.2 環境変数

```bash
# GitHubでのボットのユーザー名
GITHUB_BOT_NAME=coding-agent-bot

# GitLabでのボットのユーザー名
GITLAB_BOT_NAME=coding-agent-bot
```

環境変数が設定されている場合は config.yaml の `bot_name` より優先されます。

## 8. エラーハンドリング

### 8.1 API エラー時の処理

アサイン状況取得時にエラーが発生した場合の処理：

```
1. エラーが発生
   ↓
2. エラーログを記録
   ↓
3. 処理継続（停止しない）
   ↓
4. 次のチェックタイミングで再度確認
```

**理由:**
エラー発生時にタスクを停止すると、一時的な問題でもタスクが中断されてしまうため、
エラー時は処理を継続し、次回のチェックで再度確認します。

リトライ処理は、既存のAPI呼び出し実装（`requests` ライブラリのタイムアウト設定等）と同様の方式を使用します。

## 9. テストシナリオ

### 9.1 基本的な停止テスト

**シナリオS1: GitHub Issue でのアサイン解除による停止**
1. GitHub Issue に `coding agent` ラベルとボットのアサインを設定
2. タスク処理を開始
3. 処理中に Issue からボットのアサインを解除
4. 次のチェックタイミングでアサイン解除を検出
5. 停止コメントが投稿されることを確認
6. `coding agent processing` ラベルが削除されることを確認
7. `coding agent stopped` ラベルが追加されることを確認
8. タスクが終了することを確認

**シナリオS2: GitHub Pull Request でのアサイン解除による停止**
1. GitHub Pull Request に `coding agent` ラベルとボットのアサインを設定
2. タスク処理を開始
3. 処理中に PR からボットのアサインを解除
4. 停止処理が実行されることを確認

**シナリオS3: GitLab Issue でのアサイン解除による停止**
1. GitLab Issue に `coding agent` ラベルとボットのアサインを設定
2. タスク処理を開始
3. 処理中に Issue からボットのアサインを解除
4. 停止処理が実行されることを確認

**シナリオS4: GitLab Merge Request でのアサイン解除による停止**
1. GitLab Merge Request に `coding agent` ラベルとボットのアサインを設定
2. タスク処理を開始
3. 処理中に MR からボットのアサインを解除
4. 停止処理が実行されることを確認

### 9.2 Planning モードでの停止テスト

**シナリオS5: Planningフェーズ中のアサイン解除**
1. Planning モードでタスクを開始
2. Planning フェーズ中にアサインを解除
3. Planning フェーズ完了後のチェックで停止されることを確認

**シナリオS6: アクション実行中のアサイン解除**
1. Planning モードでタスクを開始し、プラン作成完了
2. アクション実行中にアサインを解除
3. 次のアクション実行前に停止されることを確認
4. チェックリストに停止時点の進捗が反映されていることを確認

### 9.3 エラーケースのテスト

**シナリオS7: エラー発生時の継続**
1. タスク処理を開始
2. アサインチェック時にエラーを発生させる（モック）
3. 処理が継続することを確認
4. エラーログが出力されることを確認

### 9.4 一時停止との連携テスト

**シナリオS8: アサイン解除と一時停止シグナルの同時発生**
1. タスク処理を開始
2. 同じタイミングでアサイン解除と `pause_signal` ファイル作成
3. 一時停止が優先されることを確認（一時停止シグナルが先にチェックされる）

## 10. 運用ガイドライン

### 10.1 タスク停止の実行方法

**GitHub の場合:**
1. 対象の Issue または Pull Request を開く
2. 右サイドバーの「Assignees」セクションをクリック
3. コーディングエージェントのボットユーザーの「×」をクリックして解除
4. 次のチェックタイミング（最大30秒以内）でタスクが停止

**GitLab の場合:**
1. 対象の Issue または Merge Request を開く
2. 右サイドバーの「Assignee」セクションをクリック
3. コーディングエージェントのボットユーザーを解除
4. 次のチェックタイミング（最大30秒以内）でタスクが停止

### 10.2 停止されたタスクの再開方法

タスクを再開する場合は、以下の手順で新しいタスクとして開始します：

1. Issue/MR/PR に `coding agent` ラベルを付与
2. コーディングエージェントを再度アサイン
3. Producer モードでタスクを検出・投入
4. Consumer モードで新しいタスクとして処理開始
