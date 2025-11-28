# 新規コメント検知とコンテキスト反映仕様書

## 1. 概要

### 1.1 目的

本仕様書は、coding_agentがIssueやMerge Request（以下、MR）の処理中に、新しいユーザーコメントを検出し、コンテキストに反映する機能を定義します。

### 1.2 背景

現在のcoding_agentは、タスク開始時にIssue/MRの内容とコメントを取得しますが、処理中に追加された新規コメントは検出されません。ユーザーがタスク処理中に追加情報や修正指示をコメントした場合、agentがそれを認識して対応できるようにする必要があります。

### 1.3 要求事項

- 処理の各段階（一時停止検知と同じタイミング）で新規ユーザーコメントを検出する
- 検出したコメントをLLMコンテキストに追加する
- デフォルトで有効とし、設定不要で動作する
- botが投稿したコメントは検出対象から除外する
- GitHubおよびGitLabの両方に対応する

### 1.4 対象範囲

- Context Storageモードでのタスク処理
- Planningモードでのタスク処理
- GitHub Issue/Pull Request
- GitLab Issue/Merge Request

## 2. 処理フロー設計

### 2.1 検出タイミング

新規コメントの検出は、一時停止シグナル検知処理（PAUSE_RESUME_SPECIFICATION.md参照）と同じタイミングで実行します。

#### 2.1.1 Context Storageモード（Planning無効時）

検出タイミングは以下の通りです：

1. **処理ループの各イテレーション開始時**
   - 一時停止シグナルチェックの直後
   - LLM呼び出し前

処理フローの概要：
```
while count < max_count:
    一時停止シグナルをチェック
    ↓
    停止シグナルをチェック
    ↓
    [新規コメント検出処理] ← ここで検出
    ↓
    コンテキスト圧縮判定
    ↓
    LLM対話処理
    ↓
    完了判定
```

#### 2.1.2 Planningモード（Planning有効時）

検出タイミングは以下の通りです：

1. **プランニング開始前**
   - 一時停止/停止シグナルチェック直後
   
2. **プランニングフェーズ完了後**
   - 実行フェーズ開始前

3. **各アクション実行前**
   - 一時停止/停止シグナルチェック直後

4. **リフレクション実行前**
   - 一時停止/停止シグナルチェック直後

5. **プラン修正実行前**
   - 一時停止/停止シグナルチェック直後

処理フローの概要：
```
[プランニング開始前]
    一時停止/停止シグナルチェック
    ↓
    [新規コメント検出処理] ← ここで検出
    ↓
    プランニングフェーズ実行

[実行ループ]
    while not complete:
        一時停止/停止シグナルチェック
        ↓
        [新規コメント検出処理] ← ここで検出
        ↓
        アクション実行
        ↓
        リフレクション判定
        ↓
        (必要時) リフレクション前にも検出
```

### 2.2 コメント検出処理の詳細

#### 2.2.1 コメント取得

Issue/MRに投稿された全コメントを取得し、前回取得時以降に追加されたコメントを特定します。

**処理手順：**

1. 現在のコメント一覧を取得
   - GitHub: REST API または GraphQL API を使用
   - GitLab: REST API を使用
   
2. 前回取得時のコメントIDリストと比較
   - 新しいコメントを特定
   - コメントIDまたはタイムスタンプで判定

3. 自身（bot）が投稿したコメントを除外
   - bot名（設定ファイルで指定）と照合
   - 一致するコメントは除外

4. 新規コメントをコンテキストに追加

#### 2.2.2 状態管理

コメント検出のための状態は、タスク処理開始時からメモリ内で管理します。

**管理する状態：**

- `last_comment_ids`: 前回チェック時までに取得したコメントIDのセット
- `last_check_timestamp`: 前回チェック時のタイムスタンプ
- `detected_comment_count`: 検出した新規コメントの累計数

**コメントIDの型について：**

コメントIDはプラットフォームによって型が異なります：
- GitHub: 整数型（int）
- GitLab: 整数型（int）

`last_comment_ids`は統一性のため、**文字列に変換して管理**します。これにより、プラットフォーム間の差異を吸収し、一貫した比較処理が可能になります。

**初期化タイミング：**
- タスク処理開始時に初期化
- 既存のコメントを全て`last_comment_ids`に追加（ID文字列化して格納）

#### 2.2.3 コンテキストへの追加

検出した新規コメントは、以下の形式でLLMコンテキストに追加します。

**追加方法：**

1. 新規コメントを検出した場合、LLMクライアントにユーザーメッセージとして送信
2. コメント内容にプレフィックスを付けて識別しやすくする

**メッセージ形式：**
```
[New Comment from @{username}]:
{comment_body}
```

複数の新規コメントがある場合：
```
[New Comments Detected]:

Comment 1 from @{username1} ({timestamp1}):
{comment_body1}

Comment 2 from @{username2} ({timestamp2}):
{comment_body2}
```

## 3. 詳細設計

### 3.1 新規クラス: CommentDetectionManager

**ファイル**: `comment_detection_manager.py`

**責務：**
- Issue/MRの新規コメント検出
- 検出状態の管理
- LLMコンテキストへの追加処理

**主要属性：**
```
- task: 処理対象のタスク
- config: 設定辞書
- logger: ロガー
- enabled: コメント検出機能の有効/無効フラグ
- last_comment_ids: 前回までのコメントIDセット
- last_check_time: 前回チェック時刻
- bot_username: bot自身のユーザー名（除外用）
- detected_count: 検出した新規コメント数
```

**主要メソッド：**

**`__init__(task, config)`**
- タスクと設定を受け取って初期化
- 設定から有効/無効フラグを取得（デフォルト: 有効）
- bot_usernameを設定から取得

**`initialize()`**
- 現在のコメント一覧を取得
- last_comment_idsを初期化
- タスク開始時に呼び出す

**`check_for_new_comments() -> list[dict]`**
- 新規コメントを検出
- 戻り値: 新規コメントのリスト（空リストの場合は新規なし）

処理フロー:
```
1. 機能が無効な場合は空リストを返す
2. 現在のコメント一覧を取得
3. last_comment_idsに含まれないコメントを抽出
4. bot自身のコメントを除外
5. last_comment_idsを更新
6. last_check_timeを更新
7. 新規コメントリストを返す
```

**`format_comment_message(comments: list[dict]) -> str`**
- 検出したコメントをLLMメッセージ形式に整形
- 戻り値: 整形されたメッセージ文字列

**`add_to_context(llm_client, comments: list[dict])`**
- 検出したコメントをLLMコンテキストに追加
- llm_client.send_user_message()を使用

処理フロー:
```
1. コメントリストが空の場合は何もしない
2. format_comment_message()でメッセージを整形
3. llm_client.send_user_message()でコンテキストに追加
4. ログに記録
5. detected_countをインクリメント
```

**`is_bot_comment(comment: dict) -> bool`**
- コメントがbot自身によるものか判定
- 戻り値: botのコメントの場合True

**`get_statistics() -> dict`**
- 検出統計を取得
- 戻り値: 統計情報の辞書

### 3.2 Taskクラスへの追加メソッド

**ファイル**: `handlers/task.py`（抽象基底クラス）

**追加する抽象メソッド：**

**`get_comments() -> list[dict]`**
- Issue/MRの全コメントを取得
- 戻り値: コメント情報のリスト

**コメント情報の構造：**
```python
{
    "id": str | int,          # コメントの一意識別子
    "author": str,            # コメント作成者のユーザー名
    "body": str,              # コメント本文
    "created_at": str,        # 作成日時（ISO 8601形式）
    "updated_at": str | None, # 更新日時（ISO 8601形式、オプション）
}
```

### 3.3 GitHub Task実装への追加

**ファイル**: `handlers/task_getter_github.py`内の各Taskクラス

**実装する具体メソッド：**

**GitHubIssueTaskクラス:**
```python
def get_comments(self) -> list[dict]:
    # GitHub Issue Comments APIを使用
    # GET /repos/{owner}/{repo}/issues/{issue_number}/comments
    # このAPIはIssueに対する通常コメントを取得
```

**GitHubPullRequestTaskクラス:**
```python
def get_comments(self) -> list[dict]:
    # Pull Requestでは以下の3種類のコメントが存在:
    # 1. Issue Comments API (PR会話コメント)
    #    GET /repos/{owner}/{repo}/issues/{pr_number}/comments
    # 2. Review Comments API (コードレビューコメント)
    #    GET /repos/{owner}/{repo}/pulls/{pr_number}/comments
    # 3. Reviews API (レビュー本文)
    #    GET /repos/{owner}/{repo}/pulls/{pr_number}/reviews
    #
    # 新規コメント検出では、主にユーザーからの指示を受け取ることが
    # 目的のため、1. Issue Comments APIのみを使用
    # (レビューコメントはコード固有のフィードバックのため対象外)
```

**API選択の理由：**
- Issue Comments APIは、PR上の一般的な会話（指示、質問、フィードバック）を取得
- Review Comments APIはコードの特定行へのコメントであり、新規指示とは性質が異なる
- 必要に応じて将来的にReview Commentsの取得をオプション追加可能

### 3.4 GitLab Task実装への追加

**ファイル**: `handlers/task_getter_gitlab.py`内の各Taskクラス

**実装する具体メソッド：**

**GitLabIssueTaskクラス:**
```python
def get_comments(self) -> list[dict]:
    # GitLab Issue notes APIを使用してコメントを取得
    # GET /projects/{id}/issues/{issue_iid}/notes
```

**GitLabMergeRequestTaskクラス:**
```python
def get_comments(self) -> list[dict]:
    # GitLab MR notes APIを使用してコメントを取得
    # GET /projects/{id}/merge_requests/{merge_request_iid}/notes
```

### 3.5 TaskHandler統合

**ファイル**: `handlers/task_handler.py`

**`_handle_with_context_storage()` メソッドの変更：**

処理ループ開始前の初期化処理に追加:
```
1. pause_managerを初期化
2. stop_managerを初期化
3. [新規] comment_detection_managerを初期化
4. [新規] comment_detection_manager.initialize()を呼び出し
```

処理ループ内での検出処理（一時停止チェック直後に追加）:
```
while count < max_count:
    # 一時停止シグナルチェック
    if pause_manager.check_pause_signal():
        ...
    
    # 停止シグナルチェック
    if stop_manager.should_check_now() ...:
        ...
    
    # [新規] 新規コメント検出
    new_comments = comment_detection_manager.check_for_new_comments()
    if new_comments:
        comment_detection_manager.add_to_context(task_llm_client, new_comments)
    
    # コンテキスト圧縮チェック
    if compressor.should_compress():
        ...
    
    # LLM対話処理
    ...
```

**`_handle_with_planning()` メソッドの変更：**

PlanningCoordinatorにcomment_detection_managerを渡す処理を追加:
```
# [新規] comment_detection_managerを初期化
comment_detection_manager = CommentDetectionManager(task, task_config)
comment_detection_manager.initialize()

# PlanningCoordinatorにmanagerを設定
coordinator.comment_detection_manager = comment_detection_manager
```

### 3.6 PlanningCoordinator統合

**ファイル**: `handlers/planning_coordinator.py`

**追加属性：**
```
self.comment_detection_manager = None  # TaskHandlerから設定
```

**検出処理の追加箇所：**

`execute_with_planning()` メソッド内の各検出ポイントに追加:

```python
# 一時停止シグナルチェックの直後に追加
if self._check_pause_signal():
    ...
    return True

# [新規] 新規コメント検出
self._check_and_add_new_comments()

# 以降の処理...
```

**追加メソッド：**

**`_check_and_add_new_comments()`**
- 新規コメントを検出してコンテキストに追加
- comment_detection_managerがNoneの場合は何もしない

処理フロー:
```
1. comment_detection_managerがNoneの場合、早期リターン
2. check_for_new_comments()を呼び出し
3. 新規コメントがあればadd_to_context()でコンテキストに追加
4. ログに検出を記録
```

## 4. 設定仕様

### 4.1 config.yamlへの追加項目

```yaml
# 新規コメント検出設定
comment_detection:
  # コメント検出機能の有効/無効（デフォルト: true）
  enabled: true
  
  # bot自身のユーザー名（コメント除外用）
  # 設定されていない場合は、github.usernameまたはgitlab.usernameを使用
  bot_username: null
  
  # 検出間隔（デフォルト: 1 = 毎回チェック）
  # 値が2の場合、2回に1回のみチェック
  check_interval: 1
  
  # 検出時のログレベル（デフォルト: info）
  log_level: "info"
```

### 4.2 デフォルト動作

設定ファイルに`comment_detection`セクションが存在しない場合、以下のデフォルト値が使用されます：

- `enabled`: `true`（機能有効）
- `bot_username`: 各プラットフォーム設定（`github.username`または`gitlab.username`）から取得
- `check_interval`: `1`（毎回チェック）
- `log_level`: `info`

**bot_usernameの解決優先順位：**

1. `comment_detection.bot_username`が設定されている場合はそれを使用
2. GitHubの場合: `github.username`を使用
3. GitLabの場合: `gitlab.username`を使用
4. いずれも設定されていない場合:
   - 警告ログを出力
   - botコメント除外機能を無効化（全コメントを検出対象とする）
   - 将来的にはAPIトークンからの自動検出を検討

**注意:** bot_usernameが未設定の場合、agent自身が投稿したコメントも新規コメントとして検出される可能性があります。この場合、無限ループを防ぐため、直近のagent応答直後のコメントは別途フィルタリングする安全機構を実装します。

これにより、**設定不要でデフォルトで有効**という要件を満たします。

## 5. エラーハンドリング

### 5.1 コメント取得エラー

**エラー状況：**
- APIレート制限
- ネットワークエラー
- 認証エラー

**対処方法：**
1. エラーをログに記録
2. 処理を継続（コメント検出をスキップ）
3. 次回検出タイミングで再試行
4. 連続エラー発生時も処理を継続（検出機能のエラーでタスク処理を中断しない）

### 5.2 コメント解析エラー

**エラー状況：**
- 不正なコメントデータ形式
- 必要なフィールドの欠落

**対処方法：**
1. 問題のあるコメントをスキップ
2. 警告ログを記録
3. 他のコメントの処理を継続

### 5.3 コンテキスト追加エラー

**エラー状況：**
- LLMクライアントエラー
- コンテキストサイズ超過

**対処方法：**
1. エラーをログに記録
2. コメント内容を短縮して再試行
3. それでも失敗した場合は検出のみ記録し、追加をスキップ

## 6. ログとトレーサビリティ

### 6.1 ログ出力

**検出成功時：**
```
INFO - 新規コメントを検出しました: {count}件 (Task: {task_uuid})
```

**コンテキスト追加成功時：**
```
INFO - 新規コメントをコンテキストに追加しました: {count}件 (Task: {task_uuid})
```

**検出スキップ時（新規なし）：**
```
DEBUG - 新規コメントなし (Task: {task_uuid})
```

**エラー発生時：**
```
WARNING - コメント取得中にエラー発生: {error} (Task: {task_uuid})
```

### 6.2 統計情報

タスク完了時に以下の統計を記録します：

- 新規コメント検出回数
- 検出された総コメント数
- コンテキスト追加成功数
- エラー発生数

## 7. テスト戦略

### 7.1 ユニットテスト

**テストファイル**: `tests/unit/test_comment_detection_manager.py`

**テストケース：**

1. **初期化テスト**
   - 正常な初期化
   - 設定なしでのデフォルト値

2. **コメント検出テスト**
   - 新規コメントの検出
   - 新規コメントなしの場合
   - botコメントの除外

3. **コンテキスト追加テスト**
   - 単一コメントの追加
   - 複数コメントの追加
   - 空リストの処理

4. **エラーハンドリングテスト**
   - API取得エラー時の動作
   - 不正データの処理

### 7.2 インテグレーションテスト

**テストファイル**: `tests/integration/test_comment_detection_integration.py`

**テストシナリオ：**

1. **Context Storageモードでの検出**
   - タスク処理中にコメント追加
   - コンテキストへの反映を確認

2. **Planningモードでの検出**
   - 各フェーズでのコメント検出
   - コンテキストへの反映を確認

3. **GitHub/GitLab両方での動作**
   - GitHub Issue/PRでの検出
   - GitLab Issue/MRでの検出

### 7.3 エンドツーエンドテスト

**テストシナリオ：**

1. 実際のIssueで処理開始
2. 処理中にコメントを追加
3. agentがコメントを認識して応答を変更することを確認

## 8. 既存機能への影響

### 8.1 影響範囲

**変更が必要なファイル：**
- `handlers/task.py`: 抽象メソッド追加
- `handlers/task_getter_github.py`: メソッド実装
- `handlers/task_getter_gitlab.py`: メソッド実装
- `handlers/task_handler.py`: マネージャー統合
- `handlers/planning_coordinator.py`: マネージャー統合

**新規作成ファイル：**
- `comment_detection_manager.py`: 検出マネージャー
- `tests/unit/test_comment_detection_manager.py`: ユニットテスト
- `tests/integration/test_comment_detection_integration.py`: インテグレーションテスト

### 8.2 後方互換性

- `get_comments()`メソッドは新規追加のため、既存機能に影響なし
- 設定なしでデフォルト有効のため、既存設定との互換性あり
- エラー時も処理継続のため、既存フローへの影響なし

### 8.3 パフォーマンス影響

**懸念事項：**
- 各検出タイミングでAPI呼び出しが発生
- 長時間タスクでのAPI呼び出し回数増加

**APIレート制限の考慮：**

各プラットフォームのAPIレート制限:
- GitHub: 5,000リクエスト/時間（認証済みリクエスト）
- GitLab: 300リクエスト/分（デフォルト、設定により異なる）

**対策：**

1. **検出間隔の最適化**
   - デフォルトでは全検出タイミングで実行
   - 必要に応じて検出スキップ間隔を設定可能（例: 5回に1回のみ検出）
   - 設定項目: `comment_detection.check_interval`（デフォルト: 1 = 毎回チェック）

2. **エクスポネンシャルバックオフ**
   - APIエラー（429 Too Many Requests）発生時は指数的に待機時間を増加
   - 初回: 1秒、2回目: 2秒、3回目: 4秒...（最大60秒）
   - 成功時にリセット

3. **条件付きリクエスト（If-Modified-Since）**
   - GitHubでは`since`パラメータで最終チェック以降のコメントのみ取得
   - これによりレスポンスサイズとAPI負荷を軽減

4. **キャッシュ活用**
   - 同一チェック間隔内での重複リクエストを防止
   - 最小チェック間隔: 1秒（短時間での連続チェックを防止）

5. **軽量なAPI呼び出し**
   - コメント一覧取得のみ（詳細情報は不要）
   - ページネーションは最新のみ取得（`per_page=100`, `page=1`で最新100件）

**API使用量の見積もり：**

典型的なタスク処理（100イテレーション、全検出タイミングで実行）:
- Context Storageモード: 約100 API呼び出し
- Planningモード（10アクション、3回リフレクション）: 約20 API呼び出し

GitHub制限（5,000/時間）の場合、同時に50タスク程度まで余裕を持って処理可能

## 9. 実装フェーズ

### 9.1 Phase 1: 基本実装

1. CommentDetectionManagerクラスの実装
2. Taskクラスへのget_comments()抽象メソッド追加
3. GitHub/GitLab Taskクラスへの実装
4. ユニットテストの作成

### 9.2 Phase 2: 統合

1. TaskHandlerへの統合（Context Storageモード）
2. PlanningCoordinatorへの統合（Planningモード）
3. インテグレーションテストの作成

### 9.3 Phase 3: 検証・最適化

1. エンドツーエンドテストの実施
2. パフォーマンス検証
3. 必要に応じた最適化

## 10. まとめ

### 10.1 主要な設計ポイント

1. **一時停止検知と同じタイミングで検出**: 既存のフロー制御を活用し、一貫した検出タイミングを実現
2. **デフォルト有効**: 設定不要で動作し、導入コストを最小化
3. **プラットフォーム共通**: GitHub/GitLab両方に対応した抽象化
4. **エラー耐性**: 検出エラーでタスク処理を中断しない設計
5. **状態管理**: メモリ内での効率的な状態管理

### 10.2 期待される効果

- ユーザーが処理中に追加した指示や修正をagentが認識可能
- インタラクティブなタスク処理の実現
- ユーザー体験の向上

### 10.3 実装時の注意点

- APIレート制限への配慮
- 既存機能への影響を最小化
- 十分なテストカバレッジの確保
- ログとトレーサビリティの充実

---

**文書バージョン:** 1.0  
**作成日:** 2024-11-28  
**ステータス:** 詳細設計完了
