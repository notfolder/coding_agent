# プランニングプロセス仕様書 (Planning Process Specification)

## 1. 概要

### 1.1 目的

本仕様書は、LLMエージェントが複雑なタスクを効果的に処理するためのプランニングプロセスを定義します。このプロセスにより、エージェントは以下を実現します：

- ユーザーの意図を正確に理解
- 複雑なタスクを実行可能な単位に分解
- 効率的な実行計画の策定
- 実行結果の監視と評価
- エラーや問題発生時の適切な対応

### 1.2 スコープ

本仕様は以下をカバーします：

- プランニングプロセスの5つのフェーズの詳細
- 各フェーズの入出力形式
- JSON応答フォーマット
- 設定オプション
- エラーハンドリング戦略
- パフォーマンスとセキュリティの考慮事項

### 1.3 前提条件

- LLMエージェントは既存のMCPサーバーと連携可能
- タスクはGitHub IssueまたはGitLab Issue/MRとして提供される
- LLMはJSON形式での応答が可能
- システムプロンプトによる動作制御が可能

## 2. プランニングプロセスの5つのフェーズ

### 1. 目標の理解 (Goal Understanding)

エージェントはユーザーからの指示や達成すべき目標を理解します。

**入力:**
- Issue/PR/MRの内容
- ユーザーコメント
- リポジトリコンテキスト

**処理:**
- 要求の意図を分析
- 成功基準の特定
- 制約条件の識別

**出力:**
```json
{
  "goal_understanding": {
    "main_objective": "メインの目標を明確に記述",
    "success_criteria": ["成功条件1", "成功条件2"],
    "constraints": ["制約条件1", "制約条件2"],
    "context": "タスクの背景情報"
  }
}
```

### 2. タスクの分解 (Task Decomposition)

複雑な目標を実行可能な小さなサブタスク（ステップ）に分割します。Chain-of-Thought (CoT) などの技術を使用します。

**手法:**
- Chain-of-Thought (CoT): 思考プロセスを段階的に展開
- Hierarchical Task Network: 階層的なタスク構造
- Dependency Analysis: 依存関係の分析

**出力:**
```json
{
  "task_decomposition": {
    "reasoning": "タスク分解の理由と考え方（Chain-of-Thought）",
    "subtasks": [
      {
        "id": "task_1",
        "description": "サブタスクの説明",
        "dependencies": [],
        "estimated_complexity": "low|medium|high",
        "required_tools": ["tool_1", "tool_2"]
      }
    ]
  }
}
```

### 3. 行動系列の生成 (Action Sequence Generation)

分解されたサブタスクに基づき、実行順序とツール使用計画を策定します。

**考慮事項:**
- タスク間の依存関係
- ツールの利用可能性
- 実行効率
- エラー回復戦略

**出力:**
```json
{
  "action_plan": {
    "execution_order": ["task_1", "task_2", "task_3"],
    "actions": [
      {
        "task_id": "task_1",
        "action_type": "tool_call",
        "tool": "github_get_file_contents",
        "purpose": "このアクションの目的",
        "expected_outcome": "期待される結果",
        "fallback_strategy": "失敗時の代替手段"
      }
    ]
  }
}
```

### 4. 実行 (Execution)

計画された行動を順番に実行します。

**実行フロー:**
1. アクションの選択
2. 前提条件の確認
3. ツールの実行
4. 結果の記録
5. 次のアクションへ

### 5. 監視と修正 (Monitoring and Reflection)

実行結果を評価し、予期せぬ結果やエラーが発生した場合は計画を見直します。

**監視対象:**
- アクションの成功/失敗
- 期待される結果との差異
- 副作用や予期しない影響
- リソース使用状況

**リフレクションタイプ:**

#### 自動リフレクション (Automatic Reflection)
```json
{
  "reflection": {
    "action_id": "task_1_action_1",
    "status": "success|failure|partial",
    "evaluation": "結果の評価",
    "alignment_with_plan": "計画との整合性",
    "issues_identified": ["問題1", "問題2"],
    "plan_revision_needed": true|false
  }
}
```

#### 人間フィードバック (Human Reflection)
- Issueコメントでの指摘
- PRレビューでのフィードバック
- 明示的な修正要求

**計画修正プロセス:**
1. 問題の特定
2. 根本原因の分析
3. 代替アプローチの検討
4. 計画の更新
5. 実行の継続

## JSON応答フォーマット

### プランニングフェーズ

```json
{
  "phase": "planning",
  "goal_understanding": { /* ... */ },
  "task_decomposition": { /* ... */ },
  "action_plan": { /* ... */ },
  "comment": "プランニング完了。実行を開始します。"
}
```

### 実行フェーズ

```json
{
  "phase": "execution",
  "current_task": "task_1",
  "function_call": {
    "name": "github_get_file_contents",
    "arguments": { /* ... */ }
  },
  "comment": "ファイル内容を取得しています"
}
```

### リフレクションフェーズ

```json
{
  "phase": "reflection",
  "reflection": { /* ... */ },
  "plan_revision": {
    "reason": "修正の理由",
    "changes": ["変更内容1", "変更内容2"],
    "updated_action_plan": { /* ... */ }
  },
  "comment": "計画を修正しました"
}
```

### 完了

```json
{
  "phase": "completion",
  "summary": {
    "goal_achieved": true|false,
    "tasks_completed": 5,
    "tasks_failed": 0,
    "key_outcomes": ["成果1", "成果2"],
    "lessons_learned": ["学び1", "学び2"]
  },
  "done": true,
  "comment": "すべてのタスクが完了しました"
}
```

## 設定オプション

```yaml
planning:
  enabled: true                    # プランニング機能の有効化
  strategy: "chain_of_thought"     # プランニング戦略
  max_subtasks: 10                 # 最大サブタスク数
  reflection:
    enabled: true                  # リフレクション機能の有効化
    trigger_on_error: true         # エラー時の自動リフレクション
    trigger_interval: 3            # N回のアクション毎にリフレクション
  revision:
    max_revisions: 3               # 最大計画修正回数
    require_human_approval: false  # 人間の承認を要求するか
```

## 7. アーキテクチャ設計

### 7.1 コンポーネント構成

プランニングプロセスは以下のコンポーネントで構成されます：

#### 7.1.1 PlanningEngine（プランニングエンジン）

**責務：**
- 目標の理解
- タスクの分解
- 行動計画の生成
- 計画の修正

**インターフェース：**
- `understand_goal(task_prompt, context) -> goal_understanding`
- `decompose_task(goal, available_tools) -> subtasks`
- `generate_action_plan(subtasks, context) -> action_plan`
- `revise_plan(current_plan, feedback) -> revised_plan`

**入力：**
- タスクプロンプト（Issue/MRの内容）
- コンテキスト情報（リポジトリ情報、過去の履歴など）
- 利用可能なツール一覧

**出力：**
- 構造化された計画（JSON形式）
- 実行順序
- 期待される結果

#### 7.1.2 ReflectionEngine（リフレクションエンジン）

**責務：**
- アクション実行結果の評価
- 問題の特定
- 計画修正の提案
- 人間フィードバックの統合

**インターフェース：**
- `evaluate_action(action, result) -> evaluation`
- `identify_issues(evaluation) -> issues`
- `suggest_revision(issues) -> revision_suggestion`
- `incorporate_human_feedback(feedback) -> feedback_analysis`

**入力：**
- アクション実行結果
- 期待される結果
- 人間からのフィードバック

**出力：**
- 評価結果
- 特定された問題
- 修正提案

#### 7.1.3 ExecutionCoordinator（実行コーディネーター）

**責務：**
- プランニングと実行の統合
- フェーズ遷移の管理
- 状態管理

**インターフェース：**
- `execute_with_planning(task) -> result`
- `get_current_phase() -> phase`
- `transition_phase(from_phase, to_phase) -> bool`

### 7.2 データフロー

```
┌─────────────────────────────────────────────────────────────┐
│ 1. タスク入力（Issue/MR）                                    │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. PlanningEngine: 目標の理解                                │
│    - Issue内容の分析                                         │
│    - 成功基準の特定                                          │
│    - 制約条件の識別                                          │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. PlanningEngine: タスクの分解                              │
│    - Chain-of-Thoughtによる分解                             │
│    - サブタスクの生成                                        │
│    - 依存関係の分析                                          │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. PlanningEngine: 行動計画の生成                            │
│    - 実行順序の決定                                          │
│    - ツール選択                                              │
│    - 期待結果の定義                                          │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. ExecutionCoordinator: 実行ループ                          │
│    ┌──────────────────────────────────────────────┐         │
│    │ 5.1 アクション実行                            │         │
│    │ 5.2 結果取得                                  │         │
│    │ 5.3 ReflectionEngine: 評価                   │         │
│    │ 5.4 問題あり？                                │         │
│    │   YES → PlanningEngine: 計画修正 → 5.1へ    │         │
│    │   NO  → 次のアクションへ                      │         │
│    └──────────────────────────────────────────────┘         │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. 完了 & 結果サマリー                                       │
└─────────────────────────────────────────────────────────────┘
```

### 7.3 状態遷移図

```
[初期状態]
    ↓
[目標理解フェーズ]
    ↓
[タスク分解フェーズ]
    ↓
[行動計画生成フェーズ]
    ↓
[実行フェーズ] ←──────┐
    ↓                  │
[リフレクションフェーズ]│
    ↓                  │
  問題検出？            │
    ├─ YES ─→ [計画修正]┘
    └─ NO
       ↓
  全アクション完了？
    ├─ NO ─→ [実行フェーズ]へ戻る
    └─ YES
       ↓
[完了フェーズ]
```

## 8. システムプロンプト拡張仕様

### 8.1 プランニング対応システムプロンプト

既存のシステムプロンプトに以下の指示を追加する必要があります：

#### 8.1.1 プランニングフェーズの指示

```
## プランニングプロセス

タスクを受け取ったら、まず以下のプランニングプロセスを実行してください：

### 1. 目標の理解
- タスクの主要な目的を特定
- 成功基準を明確化
- 制約条件を識別
- 必要なコンテキスト情報を収集

### 2. タスクの分解（Chain-of-Thought）
- 思考プロセスを段階的に展開
- 複雑なタスクを実行可能な単位に分割
- サブタスク間の依存関係を分析
- 各サブタスクの複雑度を評価

### 3. 行動計画の生成
- 実行順序を決定
- 各ステップで使用するツールを選択
- 期待される結果を定義
- エラー時の代替手段を準備

### 4. 計画の提示
最初の応答では、完全な計画をJSON形式で提示してください。
```

#### 8.1.2 実行フェーズの指示

```
## 実行ルール

計画に基づいて実行する際は：

1. 計画に従って順序通りに実行
2. 各アクション後に結果を評価
3. 期待と異なる結果の場合は報告
4. 必要に応じて計画を修正
```

#### 8.1.3 リフレクションの指示

```
## リフレクションルール

各アクション実行後：

1. 結果を期待値と比較
2. 問題や予期しない動作を特定
3. 計画との整合性を確認
4. 必要に応じて計画修正を提案

以下の場合は必ずリフレクションを実行：
- ツール実行がエラーになった場合
- 期待と異なる結果が得られた場合
- 3回のアクション毎（定期リフレクション）
```

### 8.2 JSON応答フォーマットの拡張

システムプロンプトに以下のJSON応答例を追加：

```
**プランニング応答:**
{
  "phase": "planning",
  "goal_understanding": {
    "main_objective": "...",
    "success_criteria": [...],
    "constraints": [...],
    "context": "..."
  },
  "task_decomposition": {
    "reasoning": "...",
    "subtasks": [...]
  },
  "action_plan": {
    "execution_order": [...],
    "actions": [...]
  },
  "comment": "Planning completed."
}

**リフレクション応答:**
{
  "phase": "reflection",
  "reflection": {
    "action_evaluated": "...",
    "status": "success|failure|partial",
    "evaluation": "...",
    "issues_identified": [...],
    "plan_revision_needed": true|false
  },
  "plan_revision": {
    "reason": "...",
    "changes": [...]
  },
  "comment": "..."
}
```

## 9. 設定仕様

### 9.1 config.yaml への追加項目

```yaml
# プランニング機能の設定
planning:
  # プランニング機能の有効/無効（デフォルト: true）
  enabled: true
  
  # プランニング戦略（デフォルト: chain_of_thought）
  # 選択肢: "chain_of_thought", "hierarchical", "simple"
  strategy: "chain_of_thought"
  
  # 最大サブタスク数（デフォルト: 100）
  max_subtasks: 100
  
  # タスク分解の詳細度（デフォルト: moderate）
  # 選択肢: "detailed", "moderate", "minimal"
  decomposition_level: "moderate"
  
  # リフレクション設定
  reflection:
    # リフレクション機能の有効/無効（デフォルト: true）
    enabled: true
    
    # エラー発生時に自動的にリフレクション実行
    trigger_on_error: true
    
    # N回のアクション毎に定期的にリフレクション実行
    # 0の場合は定期リフレクション無効
    trigger_interval: 3
    
    # リフレクションの深さ
    # 選択肢: "deep", "moderate", "shallow"
    depth: "moderate"
  
  # 計画修正設定
  revision:
    # 最大計画修正回数
    max_revisions: 3
    
    # 人間の承認を要求するか
    # trueの場合、計画修正時にIssueにコメントして確認を待つ
    require_human_approval: false
    
    # 承認待ちのタイムアウト（秒）
    approval_timeout: 3600
  
  # プランニング結果のキャッシュ
  cache:
    # キャッシュ機能の有効/無効
    enabled: true
    
    # キャッシュの有効期限（秒）
    ttl: 86400
```

### 9.2 環境変数による設定上書き

以下の環境変数で設定を上書き可能：

- `PLANNING_ENABLED`: プランニング機能の有効/無効（true/false）
- `PLANNING_STRATEGY`: プランニング戦略
- `PLANNING_MAX_SUBTASKS`: 最大サブタスク数
- `REFLECTION_ENABLED`: リフレクション機能の有効/無効
- `REFLECTION_INTERVAL`: リフレクション実行間隔
- `MAX_PLAN_REVISIONS`: 最大計画修正回数

### 9.3 user_config_apiによる設定上書き

既存のuser_config_api機能を使用してユーザー別にプランニング設定を上書き可能。

**API応答例**:
```json
{
  "status": "success",
  "data": {
    "llm": {...},
    "planning": {
      "enabled": true,
      "strategy": "chain_of_thought",
      "max_subtasks": 100,
      "reflection": {
        "enabled": true,
        "trigger_interval": 5
      }
    }
  }
}
```

## 10. エラーハンドリング仕様

### 10.1 プランニングフェーズのエラー

#### 10.1.1 目標理解エラー

**エラー状況：**
- タスクの内容が不明確
- 必要な情報が不足
- 矛盾する要求が含まれる

**対処方法：**
1. ユーザーに明確化を要求するコメントを投稿
2. 推測可能な範囲で計画を作成し、確認を求める
3. エラーをログに記録

**JSON応答例：**
```json
{
  "phase": "planning",
  "error": {
    "type": "unclear_goal",
    "message": "タスクの目標が明確ではありません",
    "clarification_needed": [
      "具体的な実装範囲を教えてください",
      "期待される動作を明確にしてください"
    ]
  },
  "comment": "タスクの内容について確認が必要です。上記の点を明確にしていただけますか？"
}
```

#### 10.1.2 タスク分解エラー

**エラー状況：**
- タスクが複雑すぎて分解できない
- 利用可能なツールでは実現不可能
- 依存関係の解決ができない

**対処方法：**
1. より粗い粒度での分解を試行
2. 実現可能な部分と不可能な部分を明示
3. 代替アプローチを提案

**JSON応答例：**
```json
{
  "phase": "planning",
  "error": {
    "type": "decomposition_failed",
    "message": "タスクの完全な分解ができませんでした",
    "partial_plan": {
      "feasible_subtasks": [...],
      "infeasible_subtasks": [...],
      "alternative_approaches": [...]
    }
  },
  "comment": "一部のタスクは実現が困難です。代替案を提示します。"
}
```

### 10.2 実行フェーズのエラー

#### 10.2.1 ツール実行エラー

**エラー状況：**
- MCPツールの呼び出しが失敗
- 期待と異なる結果が返される
- タイムアウトが発生

**対処方法：**
1. リフレクションを実行して原因を分析
2. 代替ツールまたは方法を試行
3. 計画を修正して再試行
4. 3回連続失敗で人間に報告

**リフレクション応答例：**
```json
{
  "phase": "reflection",
  "reflection": {
    "action_evaluated": "github_get_file_contents",
    "status": "failure",
    "error": "ファイルが見つかりません",
    "root_cause_analysis": "指定されたパスが正しくない可能性",
    "plan_revision_needed": true
  },
  "plan_revision": {
    "reason": "ファイルパスの確認が必要",
    "changes": [
      {
        "type": "add_action",
        "action": {
          "action_type": "tool_call",
          "tool": "github_list_files",
          "purpose": "正しいファイルパスを特定"
        }
      }
    ]
  },
  "comment": "ファイルパスの確認を行います"
}
```

#### 10.2.2 予期しない結果

**エラー状況：**
- ツール実行は成功したが結果が期待と異なる
- 副作用が発生
- 前提条件が満たされていなかった

**対処方法：**
1. 結果の詳細な分析
2. 前提条件の再確認
3. 計画の修正または中断
4. 状況をユーザーに報告

### 10.3 リフレクションフェーズのエラー

#### 10.3.1 評価不能エラー

**エラー状況：**
- 結果の良し悪しが判断できない
- 必要な情報が不足
- 評価基準が不明確

**対処方法：**
1. 追加情報の収集
2. ユーザーへの確認要求
3. 保守的な判断（問題ありと見なす）

### 10.4 計画修正の上限超過

**エラー状況：**
- 最大計画修正回数（max_revisions）を超過
- 同じエラーが繰り返し発生
- 収束しない修正ループ

**対処方法：**
1. 処理を一時停止
2. 状況の詳細をユーザーに報告
3. 人間の介入を要求
4. タスクを "coding agent help needed" ラベルに変更

**JSON応答例：**
```json
{
  "phase": "completion",
  "status": "requires_human_intervention",
  "summary": {
    "goal_achieved": false,
    "tasks_completed": 3,
    "tasks_failed": 2,
    "revision_attempts": 3,
    "reason": "計画修正の上限に達しました",
    "current_state": "...",
    "recommendations": [
      "手動でファイルパスを確認してください",
      "必要な権限が付与されているか確認してください"
    ]
  },
  "comment": "自動処理が困難なため、人間の介入が必要です。上記の推奨事項をご確認ください。"
}
```

## 11. パフォーマンス考慮事項

### 11.1 トークン効率

#### 11.1.1 プランニング結果のキャッシュ

**目的：** 同じようなタスクに対して重複したプランニングを避ける

**実装方針：**
- タスクの内容をハッシュ化してキャッシュキーを生成
- 類似タスクの判定アルゴリズム（編集距離、コサイン類似度など）
- キャッシュのTTL（Time To Live）設定

**効果：**
- LLM呼び出し回数の削減（約30-50%削減見込み）
- 処理時間の短縮
- コスト削減

#### 11.1.2 プランニングの粒度調整

**問題：** 過度に詳細な計画はトークンを消費

**対策：**
- タスクの複雑度に応じた粒度調整
- 簡単なタスクは簡易プランニング
- 複雑なタスクのみ詳細プランニング

**設定例：**
```yaml
planning:
  decomposition_level: "moderate"  # detailed/moderate/minimal
  
  # タスク複雑度の自動判定
  auto_adjust_level: true
  
  # 複雑度の判定基準
  complexity_threshold:
    simple: 100    # 100トークン以下は簡易
    moderate: 500  # 500トークン以下は中程度
    complex: 9999  # それ以上は詳細
```

#### 11.1.3 リフレクション頻度の最適化

**問題：** 全アクション後のリフレクションは非効率

**対策：**
- 重要なアクション後のみリフレクション実行
- エラー発生時は必ずリフレクション
- 定期リフレクションの間隔を調整可能に

**推奨設定：**
- 簡単なタスク：エラー時のみ
- 中程度のタスク：5アクション毎
- 複雑なタスク：3アクション毎

### 11.2 実行時間の最適化

#### 11.2.1 並列実行の検討

**適用可能な場合：**
- 依存関係のない複数のサブタスク
- 複数ファイルの読み込み
- 独立したツール呼び出し

**実装方針：**
```json
{
  "action_plan": {
    "actions": [
      {
        "task_id": "task_1",
        "parallel_group": 1,
        "can_parallelize": true,
        "tool": "github_get_file_contents"
      },
      {
        "task_id": "task_2",
        "parallel_group": 1,
        "can_parallelize": true,
        "tool": "github_get_file_contents"
      },
      {
        "task_id": "task_3",
        "parallel_group": 2,
        "dependencies": ["task_1", "task_2"],
        "tool": "github_create_or_update_file"
      }
    ]
  }
}
```

#### 11.2.2 早期終了の最適化

**実装方針：**
- 明らかな失敗は早期に検出して中断
- 成功の十分条件が満たされたら完了
- タイムアウト設定

**設定例：**
```yaml
planning:
  execution:
    # アクション毎のタイムアウト（秒）
    action_timeout: 60
    
    # タスク全体のタイムアウト（秒）
    total_timeout: 3600
    
    # 早期終了の判定
    early_termination:
      enabled: true
      # 連続失敗回数での中断
      max_consecutive_failures: 3
```

### 11.3 ストレージ管理

#### 11.3.1 JSONLファイルベースの履歴管理

**実装方針：**
- 計画修正履歴はメモリに保持せず、JSONLファイルに永続化
- タスクUUID毎にファイルを分割
- 軽量で読み書き効率の良いJSONL形式を使用

**ファイル構造：**
```
planning_history/
├── {task_uuid_1}.jsonl
├── {task_uuid_2}.jsonl
└── {task_uuid_3}.jsonl
```

**JSONLフォーマット：**
```jsonl
{"type":"plan","timestamp":"2024-01-15T10:30:00Z","plan":{...}}
{"type":"revision","timestamp":"2024-01-15T10:35:00Z","reason":"エラー回復","changes":[...]}
{"type":"reflection","timestamp":"2024-01-15T10:35:01Z","evaluation":{...}}
```

**メリット：**
- メモリ使用量の削減
- 履歴の永続化と追跡可能性
- 必要に応じて過去の履歴を参照可能

## 12. セキュリティ考慮事項

### 12.1 プランニング結果の検証

#### 12.1.1 ツール使用の制限

**リスク：** LLMが危険なツールや操作を計画する可能性

**対策：**
- ホワイトリスト方式でツールを制限
- 危険な操作（削除、権限変更など）は明示的な許可が必要
- 人間の承認フローの実装

**設定例：**
```yaml
planning:
  security:
    # 使用可能なツールのホワイトリスト
    allowed_tools:
      - "github_get_*"
      - "github_create_or_update_file"
      - "github_search_*"
    
    # 禁止されたツール
    forbidden_tools:
      - "github_delete_*"
      - "*_admin_*"
    
    # 承認が必要な操作
    require_approval:
      - "github_create_or_update_file"  # メインブランチへの変更
      - "github_merge_*"
```

#### 12.1.2 計画内容のサニタイゼーション

**対策：**
- プランニング結果のバリデーション
- 危険なパターンの検出
- 異常な計画の拒否

**検証項目：**
- 無限ループの可能性
- リソース枯渇攻撃
- 権限昇格の試み
- 機密情報の漏洩

## 13. テスト戦略

### 13.1 ユニットテスト

#### 13.1.1 PlanningEngineのテスト

**テストケース：**
1. 目標理解の正確性
   - 明確な目標 → 正しく理解される
   - 曖昧な目標 → 明確化要求が出される
   - 複数の目標 → すべて抽出される

2. タスク分解の妥当性
   - 単純なタスク → 適切な数のサブタスクに分解
   - 複雑なタスク → 階層的に分解される
   - 分解不可能なタスク → エラーが返される

3. 行動計画の生成
   - 依存関係の正しい解決
   - 実行順序の妥当性
   - ツール選択の適切性

**テストデータ例：**
```python
# tests/unit/test_planning_engine.py
test_cases = [
    {
        "name": "simple_task",
        "input": "READMEにインストール手順を追加してください",
        "expected_subtasks": 3,  # ファイル取得、編集、更新
        "expected_tools": ["github_get_file_contents", "github_create_or_update_file"]
    },
    {
        "name": "complex_task",
        "input": "新機能の実装とテストの追加、ドキュメント更新を行ってください",
        "expected_subtasks": 8-12,
        "expected_tools": ["github_*"]
    }
]
```

#### 13.1.2 ReflectionEngineのテスト

**テストケース：**
1. 成功判定の正確性
   - 成功ケース → 正しく成功と判定
   - 失敗ケース → 失敗を検出
   - 部分成功 → 適切に評価

2. 問題特定の能力
   - エラーメッセージから根本原因を特定
   - 副作用を検出
   - 計画との不一致を発見

3. 修正提案の妥当性
   - 適切な代替手段の提案
   - 実現可能な修正内容
   - 最小限の変更

### 13.2 インテグレーションテスト

#### 13.2.1 完全なプランニングサイクル

**テストシナリオ：**
1. シンプルなタスク（README更新）
   - プランニング → 実行 → 完了
   - エラーなし
   - 期待される結果が得られる

2. 中程度のタスク（新機能追加）
   - プランニング → 実行 → リフレクション → 修正 → 完了
   - 1-2回の計画修正
   - 最終的に成功

3. 複雑なタスク（アーキテクチャ変更）
   - プランニング → 複数回の実行とリフレクション → 完了
   - 複数回の計画修正
   - 人間のフィードバック統合

**検証項目：**
- 各フェーズの正しい遷移
- 状態管理の正確性
- エラーハンドリングの動作
- ログ出力の妥当性

#### 13.2.2 エラーリカバリー

**テストシナリオ：**
1. ツール実行エラー
   - ファイルが存在しない → リフレクション → 計画修正 → 再試行

2. 予期しない結果
   - 期待と異なる出力 → 評価 → 計画修正 → 代替手段

3. 計画修正の上限
   - 3回の修正失敗 → 人間の介入要求

### 13.3 エンドツーエンドテスト

#### 13.3.1 実際のGitHub/GitLab環境

**テスト環境：**
- テスト用リポジトリの作成
- 自動生成されたIssue/MR
- 実際のMCPサーバーとの連携

**テストケース：**
1. 実際のコーディングタスク
   - バグ修正
   - 機能追加
   - リファクタリング

2. ドキュメント更新タスク
   - README更新
   - APIドキュメント生成
   - チュートリアル作成

3. 複合タスク
   - コード + テスト + ドキュメント
   - 複数ファイルの変更
   - PR作成まで

**成功基準：**
- タスクが正しく完了する
- 生成されたコードが動作する
- ドキュメントが正確
- 適切なコメントが投稿される

### 13.4 パフォーマンステスト

**測定項目：**
1. プランニング時間
   - 目標理解: < 5秒
   - タスク分解: < 10秒
   - 行動計画生成: < 5秒

2. トークン使用量
   - プランニング: < 2000トークン
   - リフレクション: < 500トークン/回
   - 全体: < 10000トークン/タスク

3. 処理時間
   - シンプルなタスク: < 1分
   - 中程度のタスク: < 5分
   - 複雑なタスク: < 15分


## 14. まとめ

### プランニングプロセスの利点

1. **タスク理解の向上** - ユーザーの意図を正確に把握、成功基準の明確化
2. **実行効率の改善** - 計画的なツール使用、依存関係の適切な解決
3. **エラー対応の強化** - 問題の早期発見、効果的な計画修正
4. **透明性の向上** - 実行計画の可視化、進捗状況の追跡可能性

### 主要な設計原則

1. **段階的な処理** - 理解 → 分解 → 計画 → 実行 → 評価のサイクル
2. **適応性** - フィードバックに基づく計画修正、エラーからの自動回復
3. **効率性** - トークン使用量の最適化、JSONLファイルベースの履歴管理
4. **安全性** - ツール使用の制限、危険操作の検出

### 参考文献

**Chain-of-Thought:**
- Wei et al. (2022): "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models"
- Yao et al. (2023): "Tree of Thoughts: Deliberate Problem Solving with Large Language Models"

**LLMエージェント設計:**
- Model Context Protocol (MCP) specification
- ReAct: Reasoning and Acting pattern
- Reflexion: Language Agents with Verbal Reinforcement Learning

---

**文書バージョン:** 1.0  
**最終更新日:** 2024-11-23  
**ステータス:** 仕様確定
