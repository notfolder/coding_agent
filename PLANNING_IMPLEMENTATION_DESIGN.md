# プランニング機能の実装方式検討書

## 概要

本ドキュメントは、プランニング機能をシステムプロンプトの変更のみで実装可能か、コード変更が必要かを検討し、必要な場合の詳細設計を示します。

---

## 結論

**システムプロンプトの変更のみでは実装不可能。コード変更が必要。**

### 理由

1. **状態管理が必要**: プランニングフェーズ、実行フェーズ、リフレクションフェーズ間の遷移管理
2. **JSONLファイルベースの履歴管理**: 計画修正の履歴をファイルに永続化
3. **複雑なフロー制御**: 計画作成→実行→評価→修正のループ処理
4. **設定による動作制御**: config.yamlでプランニング機能の有効/無効切り替え

---

## 詳細設計

### 1. アーキテクチャ概要

```
TaskHandler (既存)
    ↓ プランニング有効時
PlanningCoordinator (新規)
    ├── PlanningPhase (新規)
    ├── ExecutionPhase (既存のTaskHandler._process_llm_interactionを活用)
    └── ReflectionPhase (新規)
    
履歴管理:
    └── PlanningHistoryStore (新規) - JSONLファイルベース
```

### 2. 新規コンポーネント

#### 2.1 PlanningCoordinator クラス

**ファイル**: `handlers/planning_coordinator.py`

**責務**:
- プランニング機能の全体制御
- フェーズ遷移の管理
- TaskHandlerとの統合

**主要メソッド**:
```python
class PlanningCoordinator:
    def __init__(self, config, llm_client, mcp_clients, task):
        """初期化"""
        
    def execute_with_planning(self) -> bool:
        """プランニング機能付き実行
        
        Returns:
            完了したかどうか
        """
        # 1. プランニングフェーズ
        if not self._has_existing_plan():
            plan = self._execute_planning_phase()
            self.history_store.save_plan(plan)
        
        # 2. 実行ループ
        while not self._is_complete():
            # 実行
            result = self._execute_action()
            
            # リフレクション判定
            if self._should_reflect(result):
                reflection = self._execute_reflection_phase(result)
                
                if reflection.get('plan_revision_needed'):
                    # 計画修正
                    revised_plan = self._revise_plan(reflection)
                    self.history_store.save_revision(revised_plan, reflection)
        
        return True
```

#### 2.2 PlanningHistoryStore クラス

**ファイル**: `handlers/planning_history_store.py`

**責務**:
- 計画と修正履歴のJSONL形式での永続化
- 履歴の読み込みと検索

**データ形式** (JSONL):
```jsonl
{"type":"plan","timestamp":"2024-01-15T10:30:00Z","plan":{...}}
{"type":"revision","timestamp":"2024-01-15T10:35:00Z","reason":"エラー回復","changes":[...]}
{"type":"reflection","timestamp":"2024-01-15T10:35:01Z","evaluation":{...}}
```

**主要メソッド**:
```python
class PlanningHistoryStore:
    def __init__(self, task_uuid: str):
        """タスクUUIDに基づいてJSONLファイルを初期化"""
        self.filepath = f"planning_history/{task_uuid}.jsonl"
        
    def save_plan(self, plan: dict):
        """初期計画を保存"""
        
    def save_revision(self, revised_plan: dict, reflection: dict):
        """計画修正を保存"""
        
    def save_reflection(self, reflection: dict):
        """リフレクション結果を保存"""
        
    def get_latest_plan(self) -> dict:
        """最新の計画を取得"""
        
    def get_revision_history(self) -> list:
        """修正履歴を取得"""
```

### 3. システムプロンプトの拡張

**ファイル**: `system_prompt_planning.txt` (新規)

プランニング機能有効時に使用する専用システムプロンプト:

```
## プランニングプロセス

あなたはタスクを以下のフェーズで処理します：

### フェーズ1: プランニング (初回のみ)

最初の応答では、以下の形式で計画を提示してください：

{
  "phase": "planning",
  "goal_understanding": {
    "main_objective": "...",
    "success_criteria": [...],
    "constraints": [...]
  },
  "task_decomposition": {
    "reasoning": "Chain-of-Thoughtによる段階的思考...",
    "subtasks": [
      {"id": "task_1", "description": "...", "dependencies": [], "complexity": "low"}
    ]
  },
  "action_plan": {
    "execution_order": ["task_1", "task_2"],
    "actions": [...]
  },
  "comment": "計画が完成しました"
}

### フェーズ2: 実行

計画に従って、function_callで各アクションを実行してください。

### フェーズ3: リフレクション

エラー発生時、または{{reflection_interval}}回のアクション毎に、以下の形式で評価してください：

{
  "phase": "reflection",
  "reflection": {
    "status": "success|failure|partial",
    "evaluation": "...",
    "plan_revision_needed": true|false
  },
  "plan_revision": {
    "reason": "...",
    "changes": [...]
  }
}

### 完了

すべてのタスクが完了したら：

{
  "done": true,
  "comment": "完了しました"
}
```

### 4. 設定の統合

**既存のconfig.yamlに追加**:

```yaml
# プランニング機能
planning:
  enabled: true  # デフォルト: true
  strategy: "chain_of_thought"  # デフォルト
  max_subtasks: 100  # デフォルト: 100
  decomposition_level: "moderate"  # デフォルト
  
  reflection:
    enabled: true  # デフォルト: true
    trigger_on_error: true
    trigger_interval: 3
  
  revision:
    max_revisions: 3
  
  history:
    storage_type: "jsonl"  # JSONLファイルベース
    directory: "planning_history"
```

**user_config_apiでの上書き**:

既存の`fetch_user_config`関数を拡張し、プランニング設定も取得可能にする。

### 5. TaskHandlerへの統合

**ファイル**: `handlers/task_handler.py` (既存を修正)

**変更点**:

```python
class TaskHandler:
    def handle(self, task: Task) -> None:
        """タスクを処理する"""
        task_config = self._get_task_config(task)
        
        # プランニング機能の有効/無効判定
        planning_enabled = task_config.get("planning", {}).get("enabled", True)
        
        if planning_enabled:
            # プランニング機能を使用
            coordinator = PlanningCoordinator(
                config=task_config,
                llm_client=self.llm_client,
                mcp_clients=self.mcp_clients,
                task=task
            )
            coordinator.execute_with_planning()
        else:
            # 既存のロジック（レガシーモード）
            self._handle_legacy(task, task_config)
```

### 6. ディレクトリ構成

```
handlers/
├── task_handler.py (修正)
├── planning_coordinator.py (新規)
├── planning_history_store.py (新規)
└── planning.py (削除 - 不要)

planning_history/ (新規ディレクトリ)
└── {task_uuid}.jsonl

system_prompt_planning.txt (新規)
```

### 7. 実装の優先順位

#### Phase 1: 基本実装 (2週間)

1. **PlanningHistoryStore**
   - JSONLファイル読み書き
   - 基本的な履歴管理

2. **PlanningCoordinator基本構造**
   - プランニングフェーズの実装
   - 既存TaskHandlerとの統合

3. **システムプロンプト**
   - `system_prompt_planning.txt`の作成
   - TaskHandlerでの切り替えロジック

#### Phase 2: リフレクション機能 (2週間)

1. **リフレクション判定ロジック**
   - エラー時の自動リフレクション
   - 定期リフレクション

2. **計画修正機能**
   - リフレクション結果からの修正生成
   - 履歴への記録

#### Phase 3: 最適化 (1週間)

1. **パフォーマンス改善**
   - JSONLファイルの効率的な読み書き
   - 不要な履歴の削除

2. **user_config_api統合**
   - ユーザー別設定の取得

### 8. テスト方針

#### ユニットテスト

- `test_planning_coordinator.py`
- `test_planning_history_store.py`

**テストケース例**:
```python
def test_planning_coordinator_basic_flow():
    """基本的なプランニングフローのテスト"""
    # 1. プランニング実行
    # 2. アクション実行
    # 3. 完了確認
    
def test_planning_history_store_save_load():
    """履歴の保存と読み込みテスト"""
    # 1. 計画保存
    # 2. 修正保存
    # 3. 読み込みと検証
```

#### インテグレーションテスト

実際のタスクでプランニング機能が動作することを確認

### 9. マイグレーション

既存のタスク処理への影響を最小化:

1. **デフォルトでプランニング有効**
2. **既存タスクは自動的にプランニング使用**
3. **レガシーモードも維持**（planning.enabled: false）

### 10. セキュリティ考慮事項

簡略化（レビューコメント反映）:

- ツール使用制限は既存のMCPクライアントで実施
- ログのマスキングは不要（レビューコメントより）
- キャッシュの暗号化は不要（レビューコメントより）

---

## まとめ

### コード変更が必要な理由

1. **状態管理**: フェーズ間の遷移とループ制御
2. **永続化**: JSONLファイルでの履歴管理
3. **動的制御**: 設定による機能有効/無効の切り替え
4. **統合**: 既存TaskHandlerとの連携

### 主な新規ファイル

- `handlers/planning_coordinator.py`
- `handlers/planning_history_store.py`
- `system_prompt_planning.txt`

### 既存ファイルの修正

- `handlers/task_handler.py` (プランニング有効/無効の分岐追加)
- `config.yaml` (プランニング設定追加)

### 実装工数見積もり

- Phase 1 (基本実装): 2週間
- Phase 2 (リフレクション): 2週間  
- Phase 3 (最適化): 1週間
- **合計: 約5週間**

---

**作成日**: 2024年11月23日  
**ステータス**: 詳細設計完了  
**次のステップ**: 実装Phase 1の開始承認待ち
