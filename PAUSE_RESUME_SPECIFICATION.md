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

#### 3.1.2 シグナルによる一時停止（拡張案）
将来の拡張として、OSシグナル（SIGUSR1等）による一時停止も検討可能です。

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

**オプション1: 既存のprocessing_labelを維持**
- 利点: 既存の仕組みと互換性が高い
- 欠点: 一時停止状態と実行中状態の区別が困難

**オプション2: 専用のpausedラベルを使用（推奨）**
- `coding agent paused`ラベルを新規作成
- 一時停止時に`coding agent processing` → `coding agent paused`に変更
- 利点: 状態が明確に識別できる
- 欠点: 新しいラベルが必要

**採用案: オプション2**
- 設定ファイルに`paused_label`を追加
- 一時停止時にラベルを切り替える

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

```python
def produce_tasks(config, mcp_clients, task_source, task_queue, logger):
    # 通常タスクの取得と投入（既存処理）
    task_getter = TaskGetter.factory(config, mcp_clients, task_source)
    tasks = task_getter.get_task_list()
    for task in tasks:
        task.prepare()
        task_dict = task.get_task_key().to_dict()
        task_dict["uuid"] = str(uuid.uuid4())
        task_dict["user"] = task.get_user()
        task_dict["is_resumed"] = False
        task_queue.put(task_dict)
    
    # 一時停止タスクの検出と再投入（新規処理）
    paused_tasks = detect_paused_tasks(config)
    for paused_task_info in paused_tasks:
        # GitHub/GitLabでタスクが有効か確認
        task = task_getter.from_task_key(paused_task_info["task_key"])
        if task and task.check_exists():
            task_dict = paused_task_info["task_key"]
            task_dict["uuid"] = paused_task_info["uuid"]
            task_dict["user"] = paused_task_info["user"]
            task_dict["is_resumed"] = True
            task_dict["paused_context_path"] = paused_task_info["context_path"]
            task_queue.put(task_dict)
            logger.info(f"一時停止タスクを再投入: {task_dict}")
```

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

```python
# TaskContextManagerの初期化時に既存ディレクトリをチェック
def __init__(self, task_key, task_uuid, config, user, resume_from_paused=False):
    self.task_uuid = task_uuid
    self.config = config
    
    if resume_from_paused:
        # 一時停止状態から復元
        paused_dir = Path(f"contexts/paused/{task_uuid}")
        running_dir = Path(f"contexts/running/{task_uuid}")
        
        # ディレクトリを移動
        if paused_dir.exists():
            shutil.move(str(paused_dir), str(running_dir))
        
        self.context_dir = running_dir
        # 既存のストアを読み込み
        self._load_existing_stores()
    else:
        # 新規タスク
        self.context_dir = Path(f"contexts/running/{task_uuid}")
        self.context_dir.mkdir(parents=True, exist_ok=True)
```

#### 3.4.3 LLM会話の継続

一時停止からの復元時、MessageStoreには既存の会話履歴が含まれているため、LLMクライアントは自動的にこれまでの文脈を認識します:

1. MessageStoreから全メッセージを読み込み
2. LLMクライアント初期化時にメッセージ履歴を設定
3. 新しいLLM応答は既存の会話の続きとして処理される

#### 3.4.4 停止チェック機構の実装

```python
def _check_pause_signal(self, context_manager):
    """一時停止シグナルをチェック"""
    pause_signal_path = Path("contexts/pause_signal")
    if pause_signal_path.exists():
        self.logger.info("一時停止シグナルを検出しました")
        return True
    return False

def _pause_task(self, task, context_manager):
    """タスクを一時停止する"""
    # 1. 現在の状態を保存
    task_state = {
        "task_key": task.get_task_key().to_dict(),
        "uuid": task.uuid,
        "user": task.user,
        "paused_at": datetime.utcnow().isoformat(),
        "status": "paused",
        "resume_count": getattr(task, 'resume_count', 0),
        "context_path": f"contexts/paused/{task.uuid}"
    }
    
    # 2. contexts/running → contexts/paused に移動
    running_dir = Path(f"contexts/running/{task.uuid}")
    paused_dir = Path(f"contexts/paused/{task.uuid}")
    paused_dir.parent.mkdir(parents=True, exist_ok=True)
    
    if running_dir.exists():
        shutil.move(str(running_dir), str(paused_dir))
    
    # 3. task_state.jsonを保存
    task_state_path = paused_dir / "task_state.json"
    with task_state_path.open('w') as f:
        json.dump(task_state, f, indent=2)
    
    # 4. タスクにコメント追加
    task.comment("タスクを一時停止しました。後で再開されます。")
    
    # 5. ラベル更新（processing → paused）
    task.update_label_to_paused()
    
    # 6. 停止シグナルファイルを削除
    Path("contexts/pause_signal").unlink(missing_ok=True)
```

#### 3.4.5 Consumer処理ループの改修

**Context Storageモード（Planning無効）:**
```python
def _handle_with_context_storage(self, task, task_config):
    """Handle task with file-based context storage (一時停止対応版)"""
    from context_storage import TaskContextManager
    
    # is_resumedフラグをチェック
    is_resumed = getattr(task, 'is_resumed', False)
    
    # Context Managerを初期化
    context_manager = TaskContextManager(
        task_key=task.get_task_key(),
        task_uuid=task.uuid,
        config=task_config,
        user=task.user,
        resume_from_paused=is_resumed
    )
    
    try:
        # 既存の処理ストア取得とLLMクライアント初期化
        message_store = context_manager.get_message_store()
        # ...
        
        # 復元時のみ: タスクにコメント追加
        if is_resumed:
            task.comment("一時停止されたタスクを再開します。")
            task.update_label_to_processing()  # paused → processing
        
        # 処理ループ
        count = 0
        max_count = task_config.get("max_llm_process_num", 1000)
        error_state = {"last_tool": None, "tool_error_count": 0}
        
        while count < max_count:
            # 一時停止チェック
            if self._check_pause_signal(context_manager):
                self._pause_task(task, context_manager)
                return  # 処理を終了（例外は投げない）
            
            # コンテキスト圧縮チェック
            if compressor.should_compress():
                self.logger.info("Context compression triggered")
                compressor.compress()
                context_manager.update_statistics(compressions=1)
            
            # LLM対話処理
            if self._process_llm_interaction_with_client(
                task, count, error_state, task_llm_client, 
                message_store, tool_store, context_manager
            ):
                break
            
            count += 1
            context_manager.update_statistics(llm_calls=1)
        
        # タスク完了
        task.finish()
        context_manager.complete()
        
    except Exception as e:
        self.logger.exception("Task processing failed")
        context_manager.fail(str(e))
        raise
```

**Planningモード（Planning有効）:**
```python
def _handle_with_planning(self, task, task_config):
    """Handle task with planning-based approach (一時停止対応版)"""
    from context_storage import TaskContextManager
    from handlers.planning_coordinator import PlanningCoordinator
    
    # is_resumedフラグをチェック
    is_resumed = getattr(task, 'is_resumed', False)
    
    # Context Managerを初期化
    context_manager = TaskContextManager(
        task_key=task.get_task_key(),
        task_uuid=task.uuid,
        config=task_config,
        user=task.user,
        resume_from_paused=is_resumed
    )
    
    try:
        # Planning設定取得
        planning_config = task_config.get("planning", {})
        planning_config["main_config"] = self.config
        
        # PlanningCoordinatorを初期化
        coordinator = PlanningCoordinator(
            config=planning_config,
            llm_client=self.llm_client,
            mcp_clients=self.mcp_clients,
            task=task,
            context_manager=context_manager,
        )
        
        # 一時停止状態から復元する場合、Planning状態を復元
        if is_resumed:
            task.comment("一時停止されたタスクを再開します（Planning実行中）。")
            task.update_label_to_processing()  # paused → processing
            
            # task_state.jsonからPlanning状態を読み込み
            planning_state = self._load_planning_state(task.uuid)
            if planning_state:
                coordinator.current_phase = planning_state.get("current_phase", "planning")
                coordinator.action_counter = planning_state.get("action_counter", 0)
                coordinator.revision_counter = planning_state.get("revision_counter", 0)
                coordinator.checklist_comment_id = planning_state.get("checklist_comment_id")
                # 既存のプランを履歴から読み込み
                if coordinator.history_store.has_plan():
                    plan_entry = coordinator.history_store.get_latest_plan()
                    if plan_entry:
                        coordinator.current_plan = plan_entry.get("plan") or plan_entry.get("updated_plan")
        
        # Planning実行（一時停止チェック組み込み版）
        success = self._execute_planning_with_pause_check(coordinator, task, context_manager)
        
        if success:
            task.finish()
            context_manager.complete()
            self.logger.info("Task completed successfully with planning")
        else:
            context_manager.fail("Planning execution failed")
            self.logger.error("Task failed with planning")
            
    except Exception as e:
        context_manager.fail(str(e))
        self.logger.exception("Planning-based task processing failed")
        raise

def _execute_planning_with_pause_check(self, coordinator, task, context_manager):
    """Planning実行（一時停止チェック組み込み）"""
    try:
        # 既存のPlanning実行ループを拡張
        # coordinator.execute_with_planning()の内部ロジックを
        # 一時停止チェックを挟みながら実行
        
        # Planning phase
        if coordinator.current_phase == "planning":
            if self._check_pause_signal(context_manager):
                self._pause_task_with_planning(task, context_manager, coordinator)
                return False
            
            if not coordinator.history_store.has_plan():
                coordinator.current_plan = coordinator._execute_planning_phase()
                if coordinator.current_plan:
                    coordinator.history_store.save_plan(coordinator.current_plan)
                    coordinator._post_plan_as_checklist(coordinator.current_plan)
                    coordinator.current_phase = "execution"
                else:
                    return False
        
        # Execution loop
        max_iterations = coordinator.config.get("max_subtasks", 100)
        iteration = 0
        
        while iteration < max_iterations and not coordinator._is_complete():
            # 一時停止チェック
            if self._check_pause_signal(context_manager):
                self._pause_task_with_planning(task, context_manager, coordinator)
                return False
            
            iteration += 1
            
            # Execute next action
            result = coordinator._execute_action()
            
            if result is None:
                break
            
            if result.get("status") == "error":
                if not coordinator.config.get("continue_on_error", False):
                    return False
            
            # Update progress
            coordinator._update_checklist_progress(coordinator.action_counter - 1)
            
            # Reflection check
            if coordinator._should_reflect(result):
                reflection = coordinator._execute_reflection_phase(result)
                if reflection and reflection.get("plan_revision_needed"):
                    revised_plan = coordinator._revise_plan(reflection)
                    if revised_plan:
                        coordinator.current_plan = revised_plan
            
            if result.get("done"):
                break
        
        coordinator._mark_checklist_complete()
        return True
        
    except Exception as e:
        self.logger.exception("Planning execution with pause check failed: %s", e)
        return False

def _pause_task_with_planning(self, task, context_manager, coordinator):
    """Planning状態を含めてタスクを一時停止する"""
    # 通常の一時停止処理
    self._pause_task(task, context_manager)
    
    # Planning状態を追加保存
    paused_dir = Path(f"contexts/paused/{task.uuid}")
    task_state_path = paused_dir / "task_state.json"
    
    if task_state_path.exists():
        with task_state_path.open('r') as f:
            task_state = json.load(f)
        
        # Planning状態を追加
        task_state["planning_state"] = {
            "enabled": True,
            "current_phase": coordinator.current_phase,
            "action_counter": coordinator.action_counter,
            "revision_counter": coordinator.revision_counter,
            "checklist_comment_id": coordinator.checklist_comment_id,
        }
        
        with task_state_path.open('w') as f:
            json.dump(task_state, f, indent=2)

def _load_planning_state(self, task_uuid):
    """一時停止されたPlanning状態を読み込む"""
    paused_dir = Path(f"contexts/paused/{task_uuid}")
    task_state_path = paused_dir / "task_state.json"
    
    if task_state_path.exists():
        with task_state_path.open('r') as f:
            task_state = json.load(f)
        return task_state.get("planning_state")
    
    return None
```

### 3.5 エラーハンドリングと回復

#### 3.5.1 一時停止失敗時の処理

一時停止処理中にエラーが発生した場合:
1. エラーログを記録
2. 可能であればタスク状態を保存
3. contexts/running/ の状態を維持（削除しない）
4. タスクにエラーコメントを追加
5. 次回のproducer実行時に再度一時停止処理を試行

#### 3.5.2 復元失敗時の処理

復元処理中にエラーが発生した場合:
1. エラーログを記録
2. タスクにエラーコメントを追加
3. contexts/paused/ の状態を維持（削除しない）
4. タスクをキューに再投入しない（手動確認が必要）
5. 管理者に通知（ログ、コメント等）

#### 3.5.3 不完全な一時停止状態のクリーンアップ

定期的に実行するクリーンアップ処理:
1. contexts/paused/ 内の古いタスク（例: 30日以上）を検出
2. 対応するGitHub/GitLabタスクが存在するか確認
3. 存在しない場合、contexts/failed/ に移動
4. 存在する場合、ユーザーに確認を求めるコメントを追加

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

## 4. 実装の優先順位と段階的展開

### 4.1 Phase 1: 基本的な一時停止機能
1. 停止ファイル検出機構の実装
2. タスク状態の永続化（contexts/paused/への保存）
3. 一時停止時のラベル更新
4. Consumer処理の正常終了

### 4.2 Phase 2: 復元と継続実行機能
1. Producerでの一時停止タスク検出
2. タスク情報のキュー再投入
3. Consumerでの状態復元（Context Storage移動）
4. 会話履歴の継続とLLM処理の再開

### 4.3 Phase 3: Planning モード対応
1. Planning状態（current_phase, action_counter等）の永続化
2. Planning実行ループへの一時停止チェック組み込み
3. 一時停止時のチェックリストコメントID保存
4. 復元時のPlanning状態復元とアクション継続
5. プラン修正カウンター（revision_counter）の保持

### 4.4 Phase 4: エラーハンドリングと運用改善
1. 一時停止失敗時のリトライ機構
2. 復元失敗時の通知とログ記録
3. 古い一時停止タスクのクリーンアップ
4. 管理コマンドの追加（一時停止タスク一覧表示等）

### 4.5 Phase 5: 高度な機能（オプション）
1. OSシグナルによる一時停止対応
2. 複数タスク同時一時停止
3. 一時停止理由の記録とレポート機能
4. Web UIでの一時停止管理

## 5. Planning モードにおける一時停止・リジュームの特別な考慮事項

### 5.1 Planning特有の状態管理

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

### 5.2 Planning実行フローと一時停止タイミング

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

### 5.3 Planning状態の復元プロセス

```python
# 1. Planning履歴の読み込み
history_store = context_manager.get_planning_store()
if history_store.has_plan():
    plan_entry = history_store.get_latest_plan()
    coordinator.current_plan = plan_entry.get("plan") or plan_entry.get("updated_plan")

# 2. task_state.jsonからPlanning固有状態を復元
planning_state = task_state.get("planning_state", {})
coordinator.current_phase = planning_state.get("current_phase", "planning")
coordinator.action_counter = planning_state.get("action_counter", 0)
coordinator.revision_counter = planning_state.get("revision_counter", 0)
coordinator.checklist_comment_id = planning_state.get("checklist_comment_id")

# 3. チェックリストの再表示（または更新）
if coordinator.checklist_comment_id:
    # 既存のコメントを更新して現在の進捗を反映
    coordinator._update_checklist_progress(coordinator.action_counter - 1)
else:
    # チェックリストコメントIDが失われている場合は新規投稿
    coordinator._post_plan_as_checklist(coordinator.current_plan)

# 4. 実行フェーズに応じた処理の継続
if coordinator.current_phase == "planning":
    # Planningフェーズの続きから開始
    coordinator._execute_planning_phase()
elif coordinator.current_phase == "execution":
    # アクションカウンターの位置から実行を継続
    # action_counter番目のアクションから再開
    pass
```

### 5.4 チェックリスト管理の考慮事項

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

### 5.5 Planningモードでのエラーハンドリング

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

### 5.6 Planningモード固有のテストシナリオ

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

## 6. テストシナリオ

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

### 6.2 エラーケースのテスト

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

### 6.3 同時実行とキュー管理

**シナリオ5: 複数Consumer環境での一時停止**
1. 複数のConsumerプロセスを起動
2. いずれかのConsumerでタスクを一時停止
3. 他のConsumerは影響を受けずに動作することを確認
4. 一時停止タスクの再開が正しく動作することを確認

## 7. セキュリティとデータ整合性

### 7.1 データ整合性の保証
- ファイル移動操作はアトミックに実行（shutil.moveを使用）
- task_state.jsonの書き込み前にバリデーションを実施
- Context Storageディレクトリの整合性チェック

### 7.2 アクセス制御
- contexts/ディレクトリへのアクセス権限を適切に設定
- 停止ファイルの作成権限を管理者に制限

### 7.3 ログとトレーサビリティ
- 一時停止/復元のすべての操作をログに記録
- タスクIDとタイムスタンプを必ず記録
- エラー発生時の詳細な情報を保存

## 8. 運用ガイドライン

### 8.1 一時停止の実行方法

**方法1: 停止ファイルの作成**
```bash
# 一時停止を指示
touch contexts/pause_signal

# 現在のConsumerが一時停止処理を完了するまで待機
# ログで確認: "タスクを一時停止しました"
```

**方法2: 設定での一時停止（将来実装）**
```bash
# config.yamlで設定
pause_resume:
  enabled: true
  auto_pause: true  # 次回のタスク開始前に自動停止
```

### 8.2 一時停止タスクの確認

```bash
# 一時停止中のタスク一覧を表示
ls -la contexts/paused/

# 特定タスクの状態を確認
cat contexts/paused/{task_uuid}/task_state.json
```

### 8.3 手動でのタスク再開

```bash
# Producer実行で自動的に再投入される
python main.py --mode producer

# その後Consumerで処理
python main.py --mode consumer
```

### 8.4 一時停止タスクの削除

タスクを再開せずに破棄したい場合:
```bash
# 一時停止ディレクトリから削除
rm -rf contexts/paused/{task_uuid}/

# GitHub/GitLabでタスクをクローズ
```

## 9. パフォーマンスへの影響

### 9.1 停止チェックのオーバーヘッド
- ファイル存在チェックは軽量（数ミリ秒）
- check_interval設定で頻度を調整可能
- 推奨: 1（毎回チェック）～5（5回に1回チェック）

### 9.2 状態保存のオーバーヘッド
- Context Storageは既に会話履歴を保存しているため、追加のオーバーヘッドは最小限
- ディレクトリ移動操作は高速（同一ファイルシステム内）
- task_state.jsonの書き込みは小さなファイル（数KB）

### 9.3 復元のオーバーヘッド
- ディレクトリ移動操作は高速
- MessageStoreからの読み込みは既存機能と同等
- 復元操作による顕著な遅延は発生しない見込み

## 10. 将来の拡張案

### 10.1 高度な一時停止機能
- 特定の条件（エラー率が高い、特定のツールで失敗等）での自動一時停止
- 一時停止理由の分類（ユーザー指示、エラー、リソース不足等）
- スケジュール設定による自動一時停止/再開

### 10.2 管理ツール
- 一時停止タスクのCLI管理ツール（一覧表示、再開、削除等）
- Web UIでの一時停止状態の可視化
- 一時停止タスクのメトリクス収集とレポート

### 10.3 分散環境対応
- 複数Consumerでのタスク一時停止の排他制御
- 分散ロック機構の導入
- タスク状態のデータベース管理（ファイルベースからDBベースへ）

## 11. まとめ

本仕様では、coding_agentのconsumerモードにおける一時停止とリジューム機能の詳細設計を行いました。

### 11.1 主要な設計ポイント
1. **停止ファイルによる一時停止**: シンプルで確実な停止トリガー機構
2. **Context Storageの活用**: 既存のディレクトリ構造を拡張（contexts/paused/）
3. **Producerとの連携**: 一時停止タスクの自動検出とキュー再投入
4. **状態の継続性**: MessageStoreを通じた会話履歴の完全な復元
5. **ラベル管理**: 専用のpausedラベルによる明確な状態管理
6. **Planningモード対応**: Planning特有の状態（フェーズ、アクションカウンター、チェックリストID等）を保存・復元

### 11.2 期待される効果
- 長時間実行タスクの柔軟な管理
- システムメンテナンス時の安全な停止
- リソース調整や緊急対応時の迅速な一時停止
- タスクの途中状態を失わずに運用継続

### 11.3 実装時の注意点
- ファイル操作の原子性を確保
- エラーハンドリングの徹底
- ログとトレーサビリティの確保
- 既存機能への影響を最小化
- Planningモード有効時の追加状態管理を忘れずに実装
- チェックリストコメントIDの適切な保存と復元

### 11.4 Planning モード対応の重要性
Planning機能が有効な場合、単なる会話履歴の保存だけでなく、以下の追加要素の管理が必要です:
- 実行フェーズ（Planning/Execution/Reflection/Revision）の保存
- アクション実行進捗（action_counter）の保持
- プラン修正回数（revision_counter）の記録
- チェックリストコメントの継続的更新
- Planning履歴（既にcontexts/running/{uuid}/planning/に保存済み）の活用

これらの状態を適切に管理することで、Planning実行中のタスクでも中断・再開をシームレスに実現できます。

本仕様に基づいて段階的に実装を進めることで、通常モードとPlanningモードの両方で堅牢で運用しやすい一時停止・リジューム機能が実現できます。
