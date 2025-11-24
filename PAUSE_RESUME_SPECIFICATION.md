# 運用上の一時停止とリジューム仕様

## 1. 概要

### 1.1 目的
現在のcoding_agentは、consumerモードで動作を開始すると、タスクが完了するまで停止せずに実行し続けます。本仕様では、consumerモードで実行中のタスクを一時停止し、後から同じ状態からリジューム（再開）できる機能を設計します。

### 1.2 要求事項
- consumerモード実行中に外部シグナルで一時停止を指示できること
- 実行中のタスクの状態を永続化し、後から復元できること
- producerモードで一時停止されたタスクを検出し、キューに再投入できること
- consumerモードで一時停止状態のタスクを受け取り、中断した箇所から処理を再開できること

### 1.3 対象範囲
- consumerモードでのタスク一時停止機能
- タスク状態の永続化機構
- producerモードでの一時停止タスク検出と再投入機能
- consumerモードでのタスク復元と継続実行機能

## 2. 現状の処理フロー分析

### 2.1 通常のタスク処理フロー

#### 2.1.1 Producerモード
1. `TaskGetter`がGitHub/GitLabからタスク一覧を取得
2. 各タスクに対して`task.prepare()`を実行（ラベル付与等）
3. タスク情報（TaskKey + UUID + ユーザー情報）をキューに追加

#### 2.1.2 Consumerモード
1. キューからタスク情報を取得
2. `TaskGetter.from_task_key()`でTaskインスタンスを復元
3. `task.check()`で処理可能状態を確認
4. `TaskHandler.handle()`でタスクを実行
   - Planning機能有効時: `_handle_with_planning()`
   - Context Storage有効時: `_handle_with_context_storage()`
   - 無効時: `_handle_legacy()`
5. タスク完了時に`task.finish()`を実行（ラベル更新等）

### 2.2 現在の状態管理

#### 2.2.1 Context Storage機構
- タスク実行中の状態は`contexts/running/{task_uuid}/`ディレクトリに保存
  - `current.jsonl`: 会話履歴（メッセージストア）
  - `summary.jsonl`: 圧縮された会話サマリー
  - `tools.jsonl`: ツール呼び出し履歴
  - `planning/{task_uuid}.jsonl`: プランニング履歴（Planning有効時）
  - `metadata.json`: タスクメタデータ
- タスク完了時に`contexts/completed/{task_uuid}/`に移動

#### 2.2.2 タスクキュー
- RabbitMQ使用時: 永続化されたメッセージキュー
- InMemoryQueue使用時: プロセスメモリ内のキュー（非永続化）

## 3. 一時停止とリジューム機能の詳細設計

### 3.1 一時停止の契機

#### 3.1.1 停止ファイルによる一時停止
consumerプロセスが定期的に特定のファイルの存在をチェックし、ファイルが検出された場合に一時停止処理を開始します。

**停止ファイルパス:**
```
contexts/pause_signal
```

**ファイル形式:**
- 空ファイル、またはタイムスタンプを含むテキストファイル
- ファイルが存在する場合、consumerは現在のタスクを一時停止する

**チェックタイミング:**
- LLM応答を取得した後、次のアクション実行前
- ツール実行完了後、LLMへの結果送信前
- 処理ループの各イテレーション開始時

### 3.2 一時停止処理の詳細

#### 3.2.1 一時停止時の処理フロー

```
1. 停止ファイル検出
   ↓
2. 現在実行中のタスク情報を取得
   ↓
3. タスク状態をデータベース（またはファイル）に記録
   - タスクキー情報（TaskKey）
   - UUID
   - ユーザー情報
   - 一時停止時刻
   - 処理ステータス（paused）
   ↓
4. Context Storageの内容をそのまま保持
   - contexts/running/{task_uuid}/ のディレクトリ構造を維持
   ↓
5. タスクにコメントを追加（一時停止通知）
   ↓
6. 処理中ラベルを保持（またはpaused状態を示すラベルに変更）
   ↓
7. consumer処理を正常終了
```

#### 3.2.2 一時停止状態の永続化

**保存場所:**
```
contexts/paused/{task_uuid}/
├── task_state.json      # タスク状態情報
├── current.jsonl        # 会話履歴（runningから移動）
├── summary.jsonl        # サマリー（runningから移動）
├── tools.jsonl          # ツール履歴（runningから移動）
├── planning/            # Planning履歴（runningから移動）
│   └── {task_uuid}.jsonl
└── metadata.json        # メタデータ（runningから移動）
```

**task_state.jsonの構造:**
```json
{
  "task_key": {
    "task_type": "github_issue",
    "owner": "notfolder",
    "repo": "coding_agent",
    "number": 123
  },
  "uuid": "550e8400-e29b-41d4-a716-446655440000",
  "user": "example_user",
  "paused_at": "2025-11-24T14:19:17.561Z",
  "status": "paused",
  "resume_count": 0,
  "last_error": null,
  "context_path": "contexts/paused/{task_uuid}",
  "planning_state": {
    "enabled": true,
    "current_phase": "execution",
    "action_counter": 3,
    "revision_counter": 1,
    "checklist_comment_id": 12345
  }
}
```

#### 3.2.3 一時停止時のラベル管理

一時停止時は専用の`paused_label`を新規作成し、ラベルの状態を変更します。

**ラベル管理方針:**
- 一時停止時: `coding agent processing` → `coding agent paused`に変更
- 新規ラベル: `coding agent paused`を作成
- 利点: 一時停止状態と実行中状態を明確に区別できる
- 再開時: `coding agent paused` → `coding agent processing`に戻す

### 3.3 Producerモードでの一時停止タスク検出

#### 3.3.1 検出方法

```
1. contexts/paused/ ディレクトリをスキャン
   ↓
2. 各サブディレクトリからtask_state.jsonを読み込み
   ↓
3. status="paused"のタスクを抽出
   ↓
4. タスクの存在確認（GitHub/GitLabで削除されていないか）
   ↓
5. 有効な一時停止タスクをキューに再投入
```

#### 3.3.2 再投入時のデータ構造

キューに投入するタスク情報に一時停止フラグを追加:
```json
{
  "task_type": "github_issue",
  "owner": "notfolder",
  "repo": "coding_agent",
  "number": 123,
  "uuid": "550e8400-e29b-41d4-a716-446655440000",
  "user": "example_user",
  "is_resumed": true,
  "paused_context_path": "contexts/paused/{task_uuid}"
}
```

#### 3.3.3 Producer処理フロー改修

**通常タスクの処理（既存処理）:**
1. TaskGetterファクトリーメソッドでインスタンスを生成
2. GitHub/GitLabからタスク一覧を取得
3. 各タスクに対してprepare()を実行（ラベル付与等）
4. タスク辞書を作成（TaskKey、UUID、ユーザー情報）
5. is_resumedフラグをfalseに設定
6. タスクキューに投入

**一時停止タスクの検出と再投入（新規処理）:**
1. contexts/paused/ディレクトリ内の一時停止タスクを検出
2. 各一時停止タスクのtask_state.jsonを読み込み
3. GitHub/GitLabでタスクが有効か確認（削除されていないか）
4. タスクが有効な場合:
   - task_keyからタスク辞書を作成
   - UUIDとユーザー情報を設定
   - is_resumedフラグをtrueに設定
   - paused_context_pathを設定
   - タスクキューに再投入
5. ログに再投入情報を記録

### 3.4 Consumerモードでのタスク復元と継続実行

#### 3.4.1 復元処理フロー

```
1. キューからタスク情報を取得
   ↓
2. is_resumedフラグをチェック
   ↓
3. is_resumed=trueの場合:
   a. paused_context_pathから状態を復元
   b. contexts/paused/{uuid}/ → contexts/running/{uuid}/ に移動
   c. Context StorageからMessageStore等を復元
   d. TaskContextManagerを初期化（既存の会話履歴を読み込み）
   e. Planning有効時: PlanningCoordinatorの状態も復元
   ↓
4. is_resumed=falseの場合:
   a. 通常の新規タスク処理
   ↓
5. TaskHandler.handle()で処理を実行
   - Planning有効: _handle_with_planning()
   - Planning無効 + Context Storage有効: _handle_with_context_storage()
   - それ以外: _handle_legacy()
   ↓
6. 処理中に停止ファイルを定期的にチェック
   ↓
7. 停止ファイル検出時:
   a. 現在の状態を保存
   b. contexts/running/{uuid}/ → contexts/paused/{uuid}/ に移動
   c. 一時停止処理を実行
   ↓
8. 完了時:
   a. contexts/running/{uuid}/ → contexts/completed/{uuid}/ に移動
   b. task.finish()実行
```

#### 3.4.2 Context Storageの復元

**TaskContextManagerの初期化プロセス:**

1. タスクUUID、設定、ユーザー情報を受け取る
2. resume_from_pausedフラグをチェック
3. フラグがtrueの場合（一時停止状態から復元）:
   - contexts/paused/{task_uuid}のパスを特定
   - contexts/running/{task_uuid}への移動先パスを準備
   - ディレクトリが存在する場合、pausedからrunningに移動
   - context_dirをrunningディレクトリに設定
   - 既存のストア（MessageStore、SummaryStore、ToolStore）を読み込み
4. フラグがfalseの場合（新規タスク）:
   - contexts/running/{task_uuid}に新規ディレクトリを作成
   - 空の状態で各ストアを初期化

#### 3.4.3 LLM会話の継続

一時停止からの復元時、MessageStoreには既存の会話履歴が含まれているため、LLMクライアントは自動的にこれまでの文脈を認識します:

1. MessageStoreから全メッセージを読み込み
2. LLMクライアント初期化時にメッセージ履歴を設定
3. 新しいLLM応答は既存の会話の続きとして処理される

#### 3.4.4 停止チェック機構の実装

**一時停止シグナルのチェック:**
1. contexts/pause_signalファイルの存在を確認
2. ファイルが存在する場合:
   - ログに一時停止シグナル検出を記録
   - trueを返して一時停止処理を開始
3. ファイルが存在しない場合、falseを返して処理継続

**タスクの一時停止処理:**
1. 現在の状態をtask_state辞書に格納:
   - task_key情報（タスク種別、オーナー、リポジトリ、番号等）
   - UUID
   - ユーザー情報
   - 一時停止時刻（ISO形式）
   - ステータス: "paused"
   - 再開回数（resume_count）
   - コンテキストパス
2. contexts/running/{uuid}/からcontexts/paused/{uuid}/へディレクトリを移動:
   - paused親ディレクトリが存在しない場合は作成
   - runningディレクトリが存在する場合に移動を実行
3. task_state.jsonをpausedディレクトリに保存
4. タスクにコメントを追加: "タスクを一時停止しました。後で再開されます。"
5. 停止シグナルファイル（contexts/pause_signal）を削除

#### 3.4.5 Consumer処理ループの改修

**Context Storageモード（Planning無効）の処理フロー:**

1. is_resumedフラグをチェック
2. TaskContextManagerを初期化（resume_from_pausedフラグを設定）
3. 処理ストアを取得（MessageStore、SummaryStore、ToolStore）
4. 関数とツールの定義を収集（MCP Clientsから）
5. タスク固有のLLMクライアントを作成（MessageStoreとContext Dirを設定）
6. ContextCompressorを作成
7. 復元時のみ:
   - タスクにコメント追加: "一時停止されたタスクを再開します。"
8. 処理ループ開始（最大回数まで繰り返し）:
   - 一時停止シグナルをチェック
   - シグナル検出時: 一時停止処理を実行して終了
   - コンテキスト圧縮が必要かチェック
   - 必要な場合: 圧縮を実行し統計を更新
   - LLM対話処理を実行
   - 完了判定があれば処理ループを終了
   - LLM呼び出し統計を更新
9. タスク完了処理を実行
10. ContextManagerのcomplete()を呼び出し（runningからcompletedへ移動）
11. エラー発生時: fail()を呼び出してログ記録

**Planningモード（Planning有効）の処理フロー:**

1. is_resumedフラグをチェック
2. TaskContextManagerを初期化（resume_from_pausedフラグを設定）
3. Planning設定を取得し、main_configを追加
4. PlanningCoordinatorを初期化（LLM Client、MCP Clients、Task、ContextManagerを渡す）
5. 一時停止状態から復元する場合:
   - タスクにコメント追加: "一時停止されたタスクを再開します（Planning実行中）。"
   - task_state.jsonからPlanning状態を読み込み:
     - current_phase（現在のフェーズ）
     - action_counter（実行済みアクション数）
     - revision_counter（修正回数）
     - checklist_comment_id（チェックリストコメントID）
   - Coordinatorの状態を復元
   - Planning履歴ストアから既存プランを読み込み
6. Planning実行（一時停止チェック組み込み版）を開始:
   - Planningフェーズ中に一時停止チェック
   - 各アクション実行前に一時停止チェック
   - リフレクション前に一時停止チェック
   - プラン修正前に一時停止チェック
   - 一時停止検出時: Planning状態を含めて一時停止処理
7. 成功時: タスク完了処理とContextManager.complete()実行
8. 失敗時: ContextManager.fail()を呼び出し
9. エラー発生時: fail()を呼び出してログ記録

**Planning状態を含む一時停止処理:**
1. 通常の一時停止処理を実行（ディレクトリ移動、task_state.json作成）
2. task_state.jsonにPlanning状態を追加:
   - enabled: true
   - current_phase: 現在のフェーズ
   - action_counter: 実行済みアクション数
   - revision_counter: プラン修正回数
   - checklist_comment_id: チェックリストコメントID
3. ファイルを保存

### 3.5 エラーハンドリングと回復

#### 3.5.1 復元失敗時の処理

復元処理中にエラーが発生した場合:
1. エラーログを記録
2. タスクにエラーコメントを追加
3. contexts/paused/ の状態を維持（削除しない）
4. タスクをキューに再投入しない（手動確認が必要）
5. 管理者に通知（ログ、コメント等）

### 3.6 設定ファイルへの追加項目

```yaml
# config.yamlへの追加
pause_resume:
  # 一時停止機能の有効化
  enabled: true
  
  # 停止シグナルファイルのパス
  signal_file: "contexts/pause_signal"
  
  # 停止チェック間隔（LLMループのN回ごとにチェック）
  check_interval: 1
  
  # 一時停止タスクの有効期限（日数）
  paused_task_expiry_days: 30
  
  # 一時停止状態ディレクトリ
  paused_dir: "contexts/paused"

github:
  # 既存の設定...
  paused_label: "coding agent paused"  # 新規追加

gitlab:
  # 既存の設定...
  paused_label: "coding agent paused"  # 新規追加
```

## 4. Planning モードにおける一時停止・リジュームの特別な考慮事項

### 4.1 Planning特有の状態管理

Planning機能が有効な場合、以下の追加状態を管理する必要があります:

**保存が必要な状態:**
1. **current_phase**: 現在のフェーズ（"planning", "execution", "reflection", "revision"）
2. **current_plan**: 現在の実行プラン（planning_history/{task_uuid}.jsonlに既に保存されている）
3. **action_counter**: 実行済みアクション数（0始まりのインデックス）
4. **revision_counter**: プラン修正回数
5. **checklist_comment_id**: チェックリストコメントのID（進捗更新に必要）

**自動的に永続化されている状態:**
1. **planning_history**: `contexts/running/{task_uuid}/planning/{task_uuid}.jsonl`に保存
   - プラン、リフレクション、修正履歴が含まれる
2. **message_store**: `contexts/running/{task_uuid}/current.jsonl`に保存
   - LLMとの会話履歴

### 4.2 Planning実行フローと一時停止タイミング

```
[Planning Phase]
  ↓
  一時停止チェック
  ↓
[Execution Loop] ← アクション毎に一時停止チェック
  ├─ アクション実行
  │   ↓
  │   一時停止チェック
  │   ↓
  ├─ チェックリスト更新
  │   ↓
  │   一時停止チェック
  │   ↓
  ├─ リフレクション判定
  │   ├─ [Reflection Phase] (必要時)
  │   │   ↓
  │   │   一時停止チェック
  │   │   ↓
  │   └─ [Revision Phase] (必要時)
  │       ↓
  │       一時停止チェック
  │       ↓
  └─ 次のアクションへ（ループ継続）
```

**一時停止チェックのタイミング:**
- Planningフェーズ開始前・完了後
- 各アクション実行前
- リフレクション実行前
- プラン修正実行前

### 4.3 Planning状態の復元プロセス

**Planning状態の復元手順:**

1. Planning履歴の読み込み:
   - ContextManagerからPlanningStoreを取得
   - 既存プランの有無を確認
   - 最新のプランエントリーを取得
   - current_planに設定（planまたはupdated_planフィールド）

2. task_state.jsonからPlanning固有状態を復元:
   - planning_state辞書を取得
   - current_phaseを復元（デフォルト: "planning"）
   - action_counterを復元（実行済みアクション数）
   - revision_counterを復元（プラン修正回数）
   - checklist_comment_idを復元（チェックリストのコメントID）

3. チェックリストの再表示（または更新）:
   - checklist_comment_idが存在する場合:
     - 既存のコメントを更新して現在の進捗を反映
     - action_counter - 1番目までのアクションを完了としてマーク
   - checklist_comment_idが存在しない場合:
     - チェックリストコメントIDが失われているため新規投稿
     - 現在のプランからチェックリストを生成

4. 実行フェーズに応じた処理の継続:
   - current_phase = "planning"の場合: Planningフェーズの続きから開始
   - current_phase = "execution"の場合: action_counter番目のアクションから実行を継続
   - current_phase = "reflection"または"revision"の場合: 該当フェーズから再開

### 4.4 チェックリスト管理の考慮事項

**一時停止時の処理:**
1. 現在のチェックリストコメントIDを保存
2. 一時停止を示すコメントを追加（オプション）

**復元時の処理:**
1. 保存されたチェックリストコメントIDを使用
2. 既存のチェックリストコメントを更新して進捗を復元
3. コメントIDが失われている場合は新規チェックリストを投稿

**更新時の処理:**
- `task.update_comment(comment_id, content)`を使用
- GitHubとGitLabで動作が異なる可能性があるため、互換性を確認

### 4.5 Planningモードでのエラーハンドリング

**一時停止中のプラン修正:**
- 一時停止中にプランが修正された場合、revision_counterが増加
- 再開時に最新のプランを使用

**アクション実行エラー:**
- エラー発生時にリフレクションが実行される可能性
- 一時停止前のエラー状態を保存し、復元時に適切に処理

**リフレクション・修正中の一時停止:**
- リフレクションフェーズ中の一時停止にも対応
- 修正フェーズ中の一時停止にも対応
- 各フェーズの状態をcurrent_phaseに記録

### 4.6 Planningモード固有のテストシナリオ

**シナリオP1: Planningフェーズ中の一時停止**
1. タスク開始、Planningフェーズに入る
2. プラン作成中に一時停止
3. 再開後、Planningフェーズを継続
4. プランが作成され、Executionフェーズに移行

**シナリオP2: アクション実行中の一時停止**
1. タスク開始、3つのアクションを含むプランを作成
2. アクション1を実行完了
3. アクション2実行中に一時停止
4. 再開後、アクション2から継続
5. アクション3を実行し完了

**シナリオP3: リフレクション中の一時停止**
1. タスク開始、複数アクションを実行
2. リフレクションがトリガー
3. リフレクション実行中に一時停止
4. 再開後、リフレクションフェーズから継続
5. 必要に応じてプラン修正

**シナリオP4: プラン修正中の一時停止**
1. タスク実行中にエラー発生
2. リフレクションが実行され、プラン修正が必要と判定
3. プラン修正中に一時停止
4. 再開後、修正されたプランで実行継続

**シナリオP5: チェックリスト復元**
1. タスク実行中、チェックリストをIssue/MRに投稿
2. アクション2完了時に一時停止
3. 再開時、チェックリストが正しく更新される
4. 進捗表示が正確に反映される

## 5. テストシナリオ

### 5.1 基本的な一時停止とリジューム

**シナリオ1: 単一タスクの一時停止と再開**
1. Consumerモードでタスクを開始
2. 処理途中で停止ファイルを作成
3. Consumerが一時停止処理を実行し正常終了することを確認
4. contexts/paused/にタスク状態が保存されていることを確認
5. Producerを実行し、一時停止タスクがキューに再投入されることを確認
6. Consumerを再起動し、タスクが継続実行されることを確認
7. タスクが正常完了することを確認

**シナリオ2: 複数回の一時停止とリジューム**
1. タスクを開始
2. 一時停止
3. 再開
4. 再度一時停止
5. 最終的に再開して完了
6. resume_countが正しくカウントされていることを確認

### 5.2 エラーケースのテスト

**シナリオ3: 一時停止中のタスク削除**
1. タスクを一時停止
2. GitHub/GitLabでタスク（Issue/PR）を削除
3. Producerを実行
4. 削除されたタスクがキューに再投入されないことを確認

**シナリオ4: contexts/paused/ の破損**
1. タスクを一時停止
2. contexts/paused/{uuid}/内のファイルを一部削除
3. Producerを実行
4. エラーログが記録されることを確認
5. 破損したタスクが再投入されないことを確認

### 5.3 同時実行とキュー管理

**シナリオ5: 複数Consumer環境での一時停止**
1. 複数のConsumerプロセスを起動
2. いずれかのConsumerでタスクを一時停止
3. 他のConsumerは影響を受けずに動作することを確認
4. 一時停止タスクの再開が正しく動作することを確認

## 6. セキュリティとデータ整合性

### 6.1 データ整合性の保証
- ファイル移動操作はアトミックに実行（shutil.moveを使用）
- task_state.jsonの書き込み前にバリデーションを実施
- Context Storageディレクトリの整合性チェック

### 6.2 ログとトレーサビリティ
- 一時停止/復元のすべての操作をログに記録
- タスクIDとタイムスタンプを必ず記録
- エラー発生時の詳細な情報を保存

## 7. 運用ガイドライン

### 7.1 一時停止の実行方法

**停止ファイルの作成:**
```bash
# 一時停止を指示
touch contexts/pause_signal

# 現在のConsumerが一時停止処理を完了するまで待機
# ログで確認: "タスクを一時停止しました"
```

### 7.2 一時停止タスクの確認

```bash
# 一時停止中のタスク一覧を表示
ls -la contexts/paused/

# 特定タスクの状態を確認
cat contexts/paused/{task_uuid}/task_state.json
```

### 7.3 手動でのタスク再開

```bash
# Producer実行で自動的に再投入される
python main.py --mode producer

# その後Consumerで処理
python main.py --mode consumer
```

### 7.4 一時停止タスクの削除

タスクを再開せずに破棄したい場合:
```bash
# 一時停止ディレクトリから削除
rm -rf contexts/paused/{task_uuid}/

# GitHub/GitLabでタスクをクローズ
```

## 8. まとめ

本仕様では、coding_agentのconsumerモードにおける一時停止とリジューム機能の詳細設計を行いました。

### 8.1 主要な設計ポイント
1. **停止ファイルによる一時停止**: シンプルで確実な停止トリガー機構
2. **Context Storageの活用**: 既存のディレクトリ構造を拡張（contexts/paused/）
3. **Producerとの連携**: 一時停止タスクの自動検出とキュー再投入
4. **状態の継続性**: MessageStoreを通じた会話履歴の完全な復元
5. **ラベル管理**: 専用のpausedラベルによる明確な状態管理
6. **Planningモード対応**: Planning特有の状態（フェーズ、アクションカウンター、チェックリストID等）を保存・復元

### 8.2 期待される効果
- 長時間実行タスクの柔軟な管理
- システムメンテナンス時の安全な停止
- リソース調整や緊急対応時の迅速な一時停止
- タスクの途中状態を失わずに運用継続

### 8.3 実装時の注意点
- ファイル操作の原子性を確保
- エラーハンドリングの徹底
- ログとトレーサビリティの確保
- 既存機能への影響を最小化
- Planningモード有効時の追加状態管理を忘れずに実装
- チェックリストコメントIDの適切な保存と復元

### 8.4 Planning モード対応の重要性
Planning機能が有効な場合、単なる会話履歴の保存だけでなく、以下の追加要素の管理が必要です:
- 実行フェーズ（Planning/Execution/Reflection/Revision）の保存
- アクション実行進捗（action_counter）の保持
- プラン修正回数（revision_counter）の記録
- チェックリストコメントの継続的更新
- Planning履歴（既にcontexts/running/{uuid}/planning/に保存済み）の活用

これらの状態を適切に管理することで、Planning実行中のタスクでも中断・再開をシームレスに実現できます。

本仕様に基づいて段階的に実装を進めることで、通常モードとPlanningモードの両方で堅牢で運用しやすい一時停止・リジューム機能が実現できます。
