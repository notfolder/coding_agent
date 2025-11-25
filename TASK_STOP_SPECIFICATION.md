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
| 状態保存 | `contexts/paused/`に保存 | 保存しない |
| ラベル変更 | `coding agent paused`に変更 | 処理中ラベルを削除 |
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
  bot_name: "coding-agent-bot"  # GitHubのボット名

gitlab:
  bot_name: "coding-agent-bot"  # GitLabのボット名
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

### 3.2 チェック頻度の設定
設定ファイルで、アサインチェックの頻度を設定できます：

```yaml
task_stop:
  # タスク停止機能の有効化
  enabled: true
  
  # アサインチェック間隔（LLMループのN回ごとにチェック）
  # 1の場合は毎回チェック、0の場合はチェック無効
  check_interval: 1
  
  # APIレート制限を考慮したチェック間隔（秒）
  # この時間内に複数回チェックが発生しても、実際のAPI呼び出しは1回に制限
  min_check_interval_seconds: 30
```

## 4. アサイン状況の取得方法

### 4.1 GitHub Issue のアサイン取得

**API エンドポイント:**
```
GET /repos/{owner}/{repo}/issues/{issue_number}
```

**レスポンス例:**
```json
{
  "number": 123,
  "title": "Issue title",
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
```
1. Issue情報をAPIで取得
2. assignees配列からloginフィールドを抽出
3. GITHUB_BOT_NAMEが含まれているかチェック
4. 含まれていない場合 → タスク停止
```

### 4.2 GitHub Pull Request のアサイン取得

**API エンドポイント:**
```
GET /repos/{owner}/{repo}/pulls/{pull_number}
```

**レスポンス例:**
```json
{
  "number": 456,
  "title": "PR title",
  "assignees": [
    {
      "login": "coding-agent-bot",
      "id": 67890
    }
  ]
}
```

**チェックロジック:**
Pull Request もIssueと同様に `assignees` 配列でアサイン状況を確認します。

### 4.3 GitLab Issue のアサイン取得

**API エンドポイント:**
```
GET /projects/{project_id}/issues/{issue_iid}
```

**レスポンス例:**
```json
{
  "iid": 123,
  "title": "Issue title",
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
```
1. Issue情報をAPIで取得
2. assigneesまたはassigneeフィールドからusernameを抽出
3. GITLAB_BOT_NAMEが含まれているかチェック
4. 含まれていない場合 → タスク停止
```

### 4.4 GitLab Merge Request のアサイン取得

**API エンドポイント:**
```
GET /projects/{project_id}/merge_requests/{merge_request_iid}
```

**レスポンス例:**
```json
{
  "iid": 456,
  "title": "MR title",
  "assignees": [
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
Merge Request もIssueと同様に `assignees` または `assignee` フィールドでアサイン状況を確認します。

## 5. タスク停止処理の詳細フロー

### 5.1 停止処理の全体フロー

```
1. アサイン状況チェック開始
   ↓
2. API経由でIssue/MR/PRの最新情報を取得
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
7. Context Storage のクリーンアップ（オプション）
   ↓
8. タスク処理を終了（finish()は呼び出さない）
   ↓
9. Consumer処理ループを正常終了
```

### 5.2 停止時のコメント

タスク停止時に以下のコメントをissue/MR/PRに投稿します：

```markdown
## ⛔ タスク停止

コーディングエージェントのアサインが解除されたため、タスクを停止しました。

**停止時刻:** {ISO 8601形式のタイムスタンプ}
**処理状況:** {実行済みアクション数}/{全アクション数} 完了

タスクを再開する場合は、コーディングエージェントを再度アサインし、
`coding agent` ラベルを付与してください。
```

### 5.3 ラベル管理

**停止時のラベル処理:**
1. `coding agent processing` ラベルを削除
2. `coding agent stopped` ラベルを追加（オプション、設定で有効化可能）

**設定例:**
```yaml
task_stop:
  stopped_label: "coding agent stopped"  # 停止時に付与するラベル（空の場合は付与しない）
```

### 5.4 Context Storage の処理

タスク停止時のContext Storage処理は以下の選択肢があります：

**オプション1: クリーンアップ（デフォルト）**
- `contexts/running/{task_uuid}/` ディレクトリを削除
- 再開不可、ストレージ容量を節約

**オプション2: 保持**
- `contexts/running/{task_uuid}/` ディレクトリをそのまま保持
- デバッグ目的で処理履歴を確認可能
- 定期クリーンアップで削除

**設定例:**
```yaml
task_stop:
  cleanup_context: true  # true: 削除, false: 保持
```

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
└── _cleanup_context(task_uuid: str) -> None
    └── Context Storageをクリーンアップ
```

### 6.2 Task クラスへの追加メソッド

`Task` 抽象基底クラスに以下のメソッドを追加します：

```python
@abstractmethod
def get_assignees(self) -> list[str]:
    """タスクにアサインされているユーザー名のリストを取得する.

    Returns:
        アサインされているユーザー名のリスト

    """
```

**GitHub Issue 実装例:**
```python
def get_assignees(self) -> list[str]:
    """Issueにアサインされているユーザー名のリストを取得する."""
    # 最新の情報を取得
    issue = self.mcp_client.call_tool(
        "get_issue",
        {"owner": self.issue["owner"], "repo": self.issue["repo"], "issue_number": self.issue["number"]},
    )
    return [assignee.get("login", "") for assignee in issue.get("assignees", [])]
```

**GitLab Issue 実装例:**
```python
def get_assignees(self) -> list[str]:
    """Issueにアサインされているユーザー名のリストを取得する."""
    # 最新の情報を取得
    issue = self.mcp_client.call_tool(
        "get_issue",
        {"project_id": str(self.project_id), "issue_iid": self.issue_iid},
    )
    assignees = []
    # assignees配列があれば使用
    if issue.get("assignees"):
        assignees = [a.get("username", "") for a in issue.get("assignees", [])]
    # assignee単体フィールドがあれば追加
    elif issue.get("assignee"):
        assignees = [issue["assignee"].get("username", "")]
    return assignees
```

### 6.3 TaskHandler への組み込み

`TaskHandler` クラスの処理ループに、アサインチェックを追加します。

**_handle_with_context_storage メソッドの改修:**
```python
def _handle_with_context_storage(self, task: Task, task_config: dict[str, Any]) -> None:
    from task_stop_manager import TaskStopManager
    
    # Initialize task stop manager
    stop_manager = TaskStopManager(task_config)
    
    # ... 既存の初期化処理 ...
    
    while count < max_count:
        # Check for pause signal (既存)
        if pause_manager.check_pause_signal():
            # ... 一時停止処理 ...
            return
        
        # Check assignee status (新規追加)
        if stop_manager.enabled and not stop_manager.check_assignee_status(task):
            self.logger.info("アサイン解除を検出、タスクを停止します")
            stop_manager.stop_task(task, task.uuid, "アサインが解除されました")
            return  # finish()を呼ばずに終了
        
        # ... 既存の処理ループ ...
```

### 6.4 PlanningCoordinator への組み込み

`PlanningCoordinator` クラスにも同様にアサインチェックを追加します。

**execute_with_planning メソッドの改修:**
```python
def execute_with_planning(self) -> bool:
    from task_stop_manager import TaskStopManager
    
    # Initialize task stop manager
    stop_manager = TaskStopManager(self.config.get("main_config", {}))
    self.stop_manager = stop_manager  # 保持して後で使用
    
    # ... 既存の処理 ...
    
    while iteration < max_iterations and not self._is_complete():
        # Check for pause signal (既存)
        if self._check_pause_signal():
            # ... 一時停止処理 ...
            return True
        
        # Check assignee status (新規追加)
        if self._check_stop_signal():
            self.logger.info("アサイン解除を検出、タスクを停止します")
            self._handle_stop()
            return True  # 失敗ではなく正常終了として扱う
        
        # ... 既存の処理ループ ...
```

**_check_stop_signal メソッド（新規追加）:**
```python
def _check_stop_signal(self) -> bool:
    """Check if stop signal is detected (assignee removed).
    
    Returns:
        True if stop signal is detected, False otherwise
    """
    if self.stop_manager is None:
        return False
    
    if not self.stop_manager.enabled:
        return False
    
    return not self.stop_manager.check_assignee_status(self.task)
```

**_handle_stop メソッド（新規追加）:**
```python
def _handle_stop(self) -> None:
    """Handle stop operation for planning mode."""
    if self.stop_manager is None:
        self.logger.warning("Stop manager not set, cannot stop")
        return
    
    # Stop the task
    self.stop_manager.stop_task(
        self.task,
        self.task.uuid,
        f"アサインが解除されました（{self.action_counter}アクション実行済み）",
    )
```

## 7. 設定ファイルへの追加項目

### 7.1 config.yaml への追加

```yaml
# タスク停止機能の設定
task_stop:
  # タスク停止機能の有効化
  enabled: true
  
  # アサインチェック間隔（LLMループのN回ごとにチェック）
  # 1の場合は毎回チェック、0の場合はチェック無効
  check_interval: 1
  
  # APIレート制限を考慮したチェック間隔（秒）
  # この時間内に複数回チェックが発生しても、実際のAPI呼び出しは1回に制限
  min_check_interval_seconds: 30
  
  # 停止時に付与するラベル（空の場合は付与しない）
  stopped_label: "coding agent stopped"
  
  # Context Storageのクリーンアップ
  cleanup_context: true

github:
  # 既存の設定...
  bot_name: ""  # GitHubでのボットのユーザー名（環境変数GITHUB_BOT_NAMEでも設定可能）

gitlab:
  # 既存の設定...
  bot_name: ""  # GitLabでのボットのユーザー名（環境変数GITLAB_BOT_NAMEでも設定可能）
```

### 7.2 環境変数

```bash
# GitHubでのボットのユーザー名
GITHUB_BOT_NAME=coding-agent-bot

# GitLabでのボットのユーザー名
GITLAB_BOT_NAME=coding-agent-bot
```

## 8. エラーハンドリング

### 8.1 API エラー時の処理

アサイン状況取得時にAPIエラーが発生した場合の処理：

```
1. APIエラーが発生
   ↓
2. エラーログを記録
   ↓
3. リトライ（最大3回、指数バックオフ）
   ├─ 成功 → 通常処理継続
   └─ 失敗 → 処理継続（停止しない）
   ↓
4. 次のチェックタイミングまで待機
```

**リトライ設定:**
```yaml
task_stop:
  api_retry:
    max_retries: 3
    initial_delay_seconds: 1
    max_delay_seconds: 10
    exponential_base: 2
```

**理由:**
APIエラーでタスクを停止すると、一時的なネットワーク障害でもタスクが中断されてしまうため、
エラー時は処理を継続し、次回のチェックで再度確認します。

### 8.2 ボット名未設定時の処理

ボット名が環境変数にも設定ファイルにも設定されていない場合：

```
1. ボット名が未設定
   ↓
2. 警告ログを出力
   ↓
3. タスク停止機能を無効化（enabled = false として扱う）
   ↓
4. 処理継続
```

### 8.3 チェック処理のタイムアウト

API呼び出しがタイムアウトした場合：

```
1. タイムアウト発生（30秒）
   ↓
2. タイムアウトログを記録
   ↓
3. 処理継続（停止しない）
   ↓
4. 次のチェックタイミングまで待機
```

## 9. テストシナリオ

### 9.1 基本的な停止テスト

**シナリオS1: GitHub Issue でのアサイン解除による停止**
1. GitHub Issue に `coding agent` ラベルとボットのアサインを設定
2. タスク処理を開始
3. 処理中に Issue からボットのアサインを解除
4. 次のチェックタイミングでアサイン解除を検出
5. 停止コメントが投稿されることを確認
6. `coding agent processing` ラベルが削除されることを確認
7. タスクが終了することを確認

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

**シナリオS7: API エラー時の継続**
1. タスク処理を開始
2. アサインチェック時にAPIエラーを発生させる（モック）
3. 処理が継続することを確認
4. エラーログが出力されることを確認

**シナリオS8: ボット名未設定時の継続**
1. 環境変数と設定ファイルからボット名を削除
2. タスク処理を開始
3. 警告ログが出力されることを確認
4. 処理が継続することを確認（停止機能が無効化される）

### 9.4 一時停止との連携テスト

**シナリオS9: アサイン解除と一時停止シグナルの同時発生**
1. タスク処理を開始
2. 同じタイミングでアサイン解除と `pause_signal` ファイル作成
3. 一時停止が優先されることを確認（または設定で優先順位を変更可能）

**設定例:**
```yaml
task_stop:
  # 一時停止シグナルとの優先順位
  # "pause_first": 一時停止を優先
  # "stop_first": 停止を優先
  priority: "pause_first"
```

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

### 10.3 停止されたタスクの確認方法

```bash
# 停止されたタスクのラベルで検索（GitHub）
gh issue list --label "coding agent stopped"

# 停止されたタスクのラベルで検索（GitLab）
glab issue list --label "coding agent stopped"
```

### 10.4 監視とアラート

以下のログメッセージを監視することで、タスク停止を検知できます：

```
INFO - アサイン解除を検出、タスクを停止します: {task_uuid}
INFO - タスクを停止しました: {task_uuid}
```

## 11. セキュリティとデータ整合性

### 11.1 アクセス制御
- アサイン解除は Issue/MR/PR への書き込み権限を持つユーザーのみが実行可能
- ボットの権限でアサイン状況を読み取り専用で確認

### 11.2 レート制限対策
- `min_check_interval_seconds` 設定でAPI呼び出し頻度を制限
- キャッシュを使用して同一タスクへの重複チェックを防止

### 11.3 ログとトレーサビリティ
- すべての停止操作をログに記録
- タスクUUIDとタイムスタンプを必ず記録
- Issue/MR/PR へのコメントで停止理由を明示

## 12. まとめ

### 12.1 主要な設計ポイント
1. **アサイン解除による停止トリガー**: ユーザーが直接Issue/MR/PRからタスク停止を指示可能
2. **既存の一時停止機能との統合**: 同じチェックタイミングでアサイン状況を確認
3. **GitHub/GitLab両対応**: プラットフォームに依存しない抽象化層を提供
4. **エラー時の安全な継続**: APIエラー時は停止せずに処理を継続
5. **明確な停止通知**: Issue/MR/PRへのコメントで停止理由を明示

### 12.2 期待される効果
- ユーザーが Issue/MR/PR 上で直接タスクを停止可能に
- 不要なタスク実行を即座に中断可能
- システムリソースの効率的な使用
- 明確な停止理由の記録によるトレーサビリティ向上

### 12.3 実装時の注意点
- API レート制限への配慮
- ボット名の正確な設定
- 一時停止機能との優先順位の明確化
- エラーハンドリングの徹底
- テストケースの網羅的な実装
