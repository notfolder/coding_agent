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
  # プランニング機能の有効/無効
  enabled: true
  
  # プランニング戦略
  # 選択肢: "chain_of_thought", "hierarchical", "simple"
  strategy: "chain_of_thought"
  
  # 最大サブタスク数（タスク分解の上限）
  max_subtasks: 10
  
  # タスク分解の詳細度
  # 選択肢: "detailed", "moderate", "minimal"
  decomposition_level: "moderate"
  
  # リフレクション設定
  reflection:
    # リフレクション機能の有効/無効
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

### 9.3 タスク別設定

特定のタスクやリポジトリに対して異なる設定を適用可能：

```yaml
planning:
  enabled: true
  strategy: "chain_of_thought"
  
  # タスクタイプ別の設定オーバーライド
  task_specific:
    # GitHub Issueの場合
    github_issue:
      max_subtasks: 15
      reflection:
        trigger_interval: 5
    
    # GitHub Pull Requestの場合
    github_pr:
      strategy: "hierarchical"
      reflection:
        depth: "deep"
    
    # GitLab Issue/MRの場合
    gitlab:
      decomposition_level: "detailed"
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

### 11.3 メモリ使用量の最適化

#### 11.3.1 計画履歴の管理

**問題：** 修正履歴が蓄積してメモリを消費

**対策：**
- 最新N個の修正履歴のみ保持
- 古い履歴は要約して保存
- ディスクベースのストレージ活用

**設定例：**
```yaml
planning:
  revision:
    # メモリに保持する履歴数
    max_history_in_memory: 5
    
    # ディスクに保存する最大履歴数
    max_history_on_disk: 50
    
    # 履歴の自動要約
    auto_summarize: true
```

#### 11.3.2 コンテキストの圧縮

**実装方針：**
- 既存のcontext_storageモジュールとの統合
- プランニング結果も圧縮対象に
- 重要な情報は保持、冗長な情報は削除

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

### 12.2 機密情報の保護

#### 12.2.1 プランニング結果のログ管理

**リスク：** 計画に機密情報が含まれる可能性

**対策：**
- センシティブな情報のマスキング
- ログレベルによる出力制御
- 機密リポジトリでは詳細ログを無効化

**設定例：**
```yaml
planning:
  logging:
    # ログレベル
    level: "INFO"  # DEBUG/INFO/WARNING/ERROR
    
    # 機密情報のマスキング
    mask_sensitive_data: true
    
    # マスキング対象パターン
    sensitive_patterns:
      - "password"
      - "token"
      - "secret"
      - "api_key"
```

#### 12.2.2 キャッシュデータの暗号化

**対策：**
- プランニング結果のキャッシュを暗号化
- アクセス制御の実装
- 定期的なキャッシュクリア

### 12.3 権限管理

#### 12.3.1 ユーザー別の権限

**実装方針：**
- タスク作成者の権限を継承
- プランニング機能の利用権限
- 危険な操作の実行権限

**設定例：**
```yaml
planning:
  permissions:
    # プランニング機能を使用できるユーザー/グループ
    allowed_users:
      - "admin-team"
      - "developer-group"
    
    # 自動実行が許可されるユーザー
    auto_execution_allowed:
      - "trusted-user"
    
    # 常に人間の承認が必要なユーザー
    always_require_approval:
      - "external-contributor"
```

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

## 14. 段階的な実装ロードマップ

### 14.1 フェーズ1: 基本プランニング機能（MVP）

**目標：** プランニングの基本的なフローを実装

**実装内容：**
1. PlanningEngineの基本実装
   - 目標理解の骨格
   - シンプルなタスク分解
   - 基本的な行動計画生成

2. システムプロンプトの拡張
   - プランニング指示の追加
   - JSON応答フォーマットの定義

3. TaskHandlerへの統合
   - プランニングフェーズの追加
   - 既存の実行フローとの統合

4. 基本設定の追加
   - config.yamlへのplanning設定
   - 有効/無効の切り替え

**成功基準：**
- シンプルなタスク（README更新など）でプランニングが動作
- 計画に従った実行が可能
- 既存機能に影響なし

**期間：** 2週間

### 14.2 フェーズ2: リフレクション機能

**目標：** 実行結果の評価と計画修正機能を追加

**実装内容：**
1. ReflectionEngineの実装
   - アクション評価機能
   - 問題特定機能
   - 修正提案機能

2. TaskHandlerへのリフレクション統合
   - アクション後の評価
   - エラー時のリフレクション
   - 定期リフレクション

3. 計画修正機能
   - PlanningEngine.revise_plan()の実装
   - 修正履歴の管理
   - 最大修正回数の制御

4. リフレクション設定の追加
   - trigger_on_error設定
   - trigger_interval設定
   - max_revisions設定

**成功基準：**
- エラー発生時に適切にリフレクション実行
- 計画修正が機能する
- 修正後の再実行が成功

**期間：** 2週間

### 14.3 フェーズ3: Chain-of-Thought強化

**目標：** タスク分解の精度向上

**実装内容：**
1. Chain-of-Thoughtプロンプトの改善
   - 思考プロセスの段階的展開
   - 中間推論の記録
   - より詳細な分解

2. 複雑度に応じた分解戦略
   - タスクの複雑度自動判定
   - 適応的な分解レベル
   - 階層的タスク構造

3. 依存関係の高度な分析
   - タスク間の依存関係自動検出
   - 並列実行可能性の判定
   - 最適な実行順序の決定

**成功基準：**
- 複雑なタスクも適切に分解
- 依存関係が正しく解決
- 実行効率の向上

**期間：** 2週間

### 14.4 フェーズ4: パフォーマンス最適化

**目標：** 実行速度とコスト効率の改善

**実装内容：**
1. プランニング結果のキャッシュ
   - キャッシュ機構の実装
   - 類似タスク判定
   - キャッシュ管理

2. トークン使用量の最適化
   - 冗長な情報の削減
   - コンテキスト圧縮
   - プロンプトの最適化

3. 並列実行の実装
   - 並列実行可能アクションの識別
   - 並列実行機構
   - 結果の統合

**成功基準：**
- LLM呼び出し回数30%削減
- トークン使用量40%削減
- 処理時間20%短縮

**期間：** 2週間

### 14.5 フェーズ5: 高度な機能

**目標：** 人間フィードバック統合と高度なエラーハンドリング

**実装内容：**
1. 人間フィードバックの統合
   - Issueコメントからのフィードバック抽出
   - フィードバックに基づく計画修正
   - 承認フローの実装

2. 高度なエラーハンドリング
   - 詳細なエラー分類
   - エラーパターンの学習
   - 自動回復戦略

3. セキュリティ強化
   - ツール使用制限
   - 危険操作の検出
   - 権限管理

**成功基準：**
- 人間のフィードバックが適切に反映
- エラー回復率の向上
- セキュリティリスクの低減

**期間：** 3週間

## 15. 利用例とユースケース

### 15.1 基本的な使用例

#### 15.1.1 READMEファイルの更新

**Issueの内容：**
```
タイトル: READMEにインストール手順を追加

本文:
プロジェクトのREADMEファイルに、以下のインストール手順を追加してください：
1. Node.jsのインストール
2. npm installの実行
3. 環境変数の設定

詳細な説明を含めてください。
```

**プランニング結果：**
```json
{
  "phase": "planning",
  "goal_understanding": {
    "main_objective": "READMEファイルにインストール手順を追加する",
    "success_criteria": [
      "Node.jsインストール手順が記載されている",
      "npm installの実行方法が説明されている",
      "環境変数の設定方法が含まれている",
      "詳細な説明がある"
    ],
    "constraints": [
      "既存のREADME構造を維持する",
      "マークダウン形式に従う"
    ],
    "context": "プロジェクトのドキュメント改善"
  },
  "task_decomposition": {
    "reasoning": "まず現在のREADMEの内容を確認し、適切な位置にインストール手順を挿入する必要があります。既存の構造を理解してから、新しいセクションを追加します。",
    "subtasks": [
      {
        "id": "task_1",
        "description": "README.mdファイルの現在の内容を取得",
        "dependencies": [],
        "estimated_complexity": "low",
        "required_tools": ["github_get_file_contents"]
      },
      {
        "id": "task_2",
        "description": "インストール手順セクションの作成",
        "dependencies": ["task_1"],
        "estimated_complexity": "low",
        "required_tools": []
      },
      {
        "id": "task_3",
        "description": "READMEファイルの更新",
        "dependencies": ["task_2"],
        "estimated_complexity": "low",
        "required_tools": ["github_create_or_update_file"]
      },
      {
        "id": "task_4",
        "description": "更新内容の確認",
        "dependencies": ["task_3"],
        "estimated_complexity": "low",
        "required_tools": ["github_get_file_contents"]
      }
    ]
  },
  "action_plan": {
    "execution_order": ["task_1", "task_2", "task_3", "task_4"],
    "actions": [
      {
        "task_id": "task_1",
        "action_type": "tool_call",
        "tool": "github_get_file_contents",
        "purpose": "現在のREADME構造を理解する",
        "expected_outcome": "README.mdの内容が取得される"
      },
      {
        "task_id": "task_3",
        "action_type": "tool_call",
        "tool": "github_create_or_update_file",
        "purpose": "インストール手順を追加したREADMEに更新",
        "expected_outcome": "READMEが正常に更新される"
      },
      {
        "task_id": "task_4",
        "action_type": "tool_call",
        "tool": "github_get_file_contents",
        "purpose": "更新が正しく反映されたか確認",
        "expected_outcome": "更新されたREADMEに新しい手順が含まれている"
      }
    ],
    "total_steps": 4,
    "estimated_complexity": "low"
  },
  "comment": "READMEファイルの更新計画が完成しました。4つのステップで実行します。"
}
```

#### 15.1.2 新機能の実装

**Issueの内容：**
```
タイトル: ユーザー認証機能の追加

本文:
以下の機能を実装してください：
- ログイン/ログアウト機能
- パスワードのハッシュ化
- セッション管理
- テストコードも追加してください
```

**プランニング結果：**
```json
{
  "phase": "planning",
  "goal_understanding": {
    "main_objective": "ユーザー認証機能の実装",
    "success_criteria": [
      "ログイン機能が動作する",
      "ログアウト機能が動作する",
      "パスワードが安全に保存される",
      "セッション管理が実装されている",
      "テストコードが含まれている"
    ],
    "constraints": [
      "セキュリティベストプラクティスに従う",
      "既存のコード構造を維持する"
    ],
    "context": "認証機能の新規実装"
  },
  "task_decomposition": {
    "reasoning": "認証機能は複数のコンポーネントから構成されます。まずプロジェクト構造を理解し、認証モジュールを作成し、既存のコードと統合し、最後にテストを追加します。セキュリティが重要なため、各ステップで慎重に実装します。",
    "subtasks": [
      {
        "id": "task_1",
        "description": "プロジェクト構造の確認",
        "dependencies": [],
        "estimated_complexity": "low",
        "required_tools": ["github_search_code", "github_get_file_contents"]
      },
      {
        "id": "task_2",
        "description": "認証モジュールの設計",
        "dependencies": ["task_1"],
        "estimated_complexity": "medium",
        "required_tools": []
      },
      {
        "id": "task_3",
        "description": "パスワードハッシュ化機能の実装",
        "dependencies": ["task_2"],
        "estimated_complexity": "medium",
        "required_tools": ["github_create_or_update_file"]
      },
      {
        "id": "task_4",
        "description": "セッション管理機能の実装",
        "dependencies": ["task_2"],
        "estimated_complexity": "medium",
        "required_tools": ["github_create_or_update_file"]
      },
      {
        "id": "task_5",
        "description": "ログイン/ログアウトエンドポイントの実装",
        "dependencies": ["task_3", "task_4"],
        "estimated_complexity": "high",
        "required_tools": ["github_create_or_update_file"]
      },
      {
        "id": "task_6",
        "description": "テストコードの作成",
        "dependencies": ["task_5"],
        "estimated_complexity": "medium",
        "required_tools": ["github_create_or_update_file"]
      },
      {
        "id": "task_7",
        "description": "ドキュメントの更新",
        "dependencies": ["task_6"],
        "estimated_complexity": "low",
        "required_tools": ["github_create_or_update_file"]
      }
    ]
  },
  "action_plan": {
    "execution_order": ["task_1", "task_2", "task_3", "task_4", "task_5", "task_6", "task_7"],
    "total_steps": 7,
    "estimated_complexity": "high"
  },
  "comment": "認証機能の実装計画が完成しました。7つのステップで段階的に実装します。"
}
```

### 15.2 エラーリカバリーの例

#### 15.2.1 ファイルが見つからないエラー

**実行フロー：**

1. **最初の実行試行：**
```json
{
  "phase": "execution",
  "current_task": "task_1",
  "function_call": {
    "name": "github_get_file_contents",
    "arguments": {
      "owner": "myorg",
      "repo": "myrepo",
      "path": "src/config.js"
    }
  }
}
```

2. **エラー発生：**
```
Error: File not found: src/config.js
```

3. **リフレクション：**
```json
{
  "phase": "reflection",
  "reflection": {
    "action_evaluated": "github_get_file_contents",
    "status": "failure",
    "error": "File not found: src/config.js",
    "root_cause_analysis": "指定されたパスにファイルが存在しない。パス誤りまたはファイル未作成の可能性。",
    "plan_revision_needed": true
  },
  "plan_revision": {
    "reason": "正しいファイルパスを特定する必要がある",
    "changes": [
      {
        "type": "add_action",
        "action": {
          "action_type": "tool_call",
          "tool": "github_search_code",
          "purpose": "config関連のファイルを検索",
          "before_task": "task_1"
        }
      }
    ]
  },
  "comment": "ファイルが見つからないため、まず正しいパスを検索します"
}
```

4. **修正後の実行：**
```json
{
  "phase": "execution",
  "current_task": "search_config",
  "function_call": {
    "name": "github_search_code",
    "arguments": {
      "owner": "myorg",
      "repo": "myrepo",
      "query": "config filename:*.js"
    }
  }
}
```

5. **成功：**
正しいパス（`config/app.config.js`）が見つかり、処理が継続されます。

### 15.3 人間フィードバックの統合例

#### 15.3.1 実装方針の修正要求

**初期の計画：**
```json
{
  "action_plan": {
    "actions": [
      {
        "task_id": "task_1",
        "tool": "github_create_or_update_file",
        "file": "src/authentication.js",
        "description": "認証ロジックを実装"
      }
    ]
  }
}
```

**人間からのフィードバック（Issueコメント）：**
```
認証ロジックはTypeScriptで実装してください。
また、既存のsrc/utils/auth.tsとの統合も考慮してください。
```

**フィードバック統合後の計画：**
```json
{
  "phase": "reflection",
  "reflection": {
    "feedback_type": "human",
    "feedback_source": "issue_comment",
    "feedback_summary": "TypeScriptで実装し、既存ファイルとの統合を考慮"
  },
  "plan_revision": {
    "reason": "人間からのフィードバックに基づく修正",
    "changes": [
      {
        "type": "modify_action",
        "action_id": "task_1",
        "updates": {
          "file": "src/authentication.ts",
          "description": "TypeScriptで認証ロジックを実装し、src/utils/auth.tsと統合"
        }
      },
      {
        "type": "add_action",
        "action": {
          "task_id": "task_0",
          "tool": "github_get_file_contents",
          "file": "src/utils/auth.ts",
          "description": "既存の認証ユーティリティを確認",
          "before_task": "task_1"
        }
      }
    ]
  },
  "comment": "フィードバックを反映して計画を修正しました。TypeScriptで実装し、既存コードとの統合を行います。"
}
```

## 16. モニタリングとメトリクス

### 16.1 プランニングの品質メトリクス

#### 16.1.1 計画の精度

**測定項目：**
- 計画通りに完了したタスクの割合
- 計画修正が必要だったタスクの割合
- 平均計画修正回数

**目標値：**
```yaml
metrics:
  planning_accuracy:
    target: 80%  # 80%のタスクが最初の計画で完了
  
  revision_rate:
    target: <30%  # 30%以下のタスクのみ修正が必要
  
  avg_revisions:
    target: <1.5  # 平均1.5回以下の修正
```

#### 16.1.2 タスク分解の妥当性

**測定項目：**
- サブタスクの数の適切性
- サブタスクの粒度の一貫性
- 依存関係の正確性

**評価基準：**
- シンプルなタスク: 2-5個のサブタスク
- 中程度のタスク: 5-10個のサブタスク
- 複雑なタスク: 10-15個のサブタスク

### 16.2 実行パフォーマンスメトリクス

#### 16.2.1 処理時間

**測定項目：**
```yaml
performance_metrics:
  planning_time:
    measure: "プランニングフェーズの所要時間"
    unit: "seconds"
    
  execution_time:
    measure: "実行フェーズの所要時間"
    unit: "seconds"
    
  reflection_time:
    measure: "リフレクションフェーズの所要時間"
    unit: "seconds"
    
  total_time:
    measure: "タスク全体の所要時間"
    unit: "seconds"
```

**ダッシュボード表示例：**
```
┌─────────────────────────────────────────┐
│ プランニング平均時間: 12.3秒            │
│ 実行平均時間: 124.5秒                   │
│ リフレクション平均時間: 8.7秒           │
│ 全体平均時間: 145.5秒                   │
└─────────────────────────────────────────┘
```

#### 16.2.2 リソース使用量

**測定項目：**
```yaml
resource_metrics:
  llm_calls:
    measure: "LLM API呼び出し回数"
    breakdown:
      - planning: "プランニング用"
      - execution: "実行用"
      - reflection: "リフレクション用"
  
  tokens_used:
    measure: "使用トークン数"
    breakdown:
      - input: "入力トークン"
      - output: "出力トークン"
  
  api_cost:
    measure: "API使用コスト"
    unit: "USD"
```

### 16.3 品質メトリクス

#### 16.3.1 成功率

**測定項目：**
```yaml
quality_metrics:
  task_completion_rate:
    measure: "タスク完了率"
    calculation: "完了タスク数 / 全タスク数"
    target: ">90%"
  
  first_try_success_rate:
    measure: "初回成功率"
    calculation: "計画修正なしで完了 / 全タスク数"
    target: ">70%"
  
  error_recovery_rate:
    measure: "エラー回復率"
    calculation: "回復成功 / 全エラー数"
    target: ">80%"
```

#### 16.3.2 コード品質

**測定項目：**
- 生成されたコードの構文エラー率
- テストカバレッジ
- コードレビューでの指摘数

### 16.4 ログとトレーシング

#### 16.4.1 ログフォーマット

**プランニングログ：**
```
[2024-01-15 10:30:00] [INFO] [Planning] Task started: issue-123
[2024-01-15 10:30:05] [INFO] [Planning] Goal understanding completed
[2024-01-15 10:30:10] [INFO] [Planning] Task decomposition: 5 subtasks
[2024-01-15 10:30:15] [INFO] [Planning] Action plan generated: 8 actions
```

**リフレクションログ：**
```
[2024-01-15 10:35:00] [INFO] [Reflection] Evaluating action: github_get_file_contents
[2024-01-15 10:35:01] [WARN] [Reflection] Action failed: File not found
[2024-01-15 10:35:02] [INFO] [Reflection] Issue identified: Incorrect file path
[2024-01-15 10:35:03] [INFO] [Reflection] Plan revision suggested
```

#### 16.4.2 トレーシング

**分散トレーシング対応：**
```yaml
tracing:
  enabled: true
  provider: "opentelemetry"
  
  spans:
    - name: "planning.understand_goal"
    - name: "planning.decompose_task"
    - name: "planning.generate_action_plan"
    - name: "execution.execute_action"
    - name: "reflection.evaluate_action"
    - name: "reflection.revise_plan"
```

## 17. まとめ

### 17.1 プランニングプロセスの利点

1. **タスク理解の向上**
   - ユーザーの意図を正確に把握
   - 成功基準の明確化
   - 制約条件の早期識別

2. **実行効率の改善**
   - 計画的なツール使用
   - 依存関係の適切な解決
   - 無駄な試行錯誤の削減

3. **エラー対応の強化**
   - 問題の早期発見
   - 体系的なエラー分析
   - 効果的な計画修正

4. **透明性の向上**
   - 実行計画の可視化
   - 進捗状況の追跡可能性
   - 意思決定プロセスの記録

### 17.2 主要な設計原則

1. **段階的な処理**
   - 理解 → 分解 → 計画 → 実行 → 評価のサイクル
   - 各フェーズの明確な責務分離
   - フェーズ間の適切な情報伝達

2. **適応性**
   - フィードバックに基づく計画修正
   - エラーからの自動回復
   - 人間の介入受け入れ

3. **効率性**
   - トークン使用量の最適化
   - キャッシュの活用
   - 並列実行の検討

4. **安全性**
   - ツール使用の制限
   - 危険操作の検出
   - 人間の承認フロー

### 17.3 今後の拡張可能性

1. **学習機能**
   - 過去の計画パターンの学習
   - 成功/失敗パターンの分析
   - 自動最適化

2. **高度なプランニング戦略**
   - Monte Carlo Tree Search
   - Reinforcement Learning
   - Multi-agent collaboration

3. **統合強化**
   - CI/CDパイプラインとの連携
   - プロジェクト管理ツール統合
   - 他のAIエージェントとの協調

### 17.4 参考文献とリソース

**Chain-of-Thought関連：**
- Wei et al. (2022): "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models"
- Yao et al. (2023): "Tree of Thoughts: Deliberate Problem Solving with Large Language Models"

**プランニング手法：**
- Russell & Norvig: "Artificial Intelligence: A Modern Approach" (Planning章)
- Hierarchical Task Network Planning
- STRIPS Planning System

**LLMエージェント設計：**
- Model Context Protocol (MCP) specification
- ReAct: Reasoning and Acting pattern
- Reflexion: Language Agents with Verbal Reinforcement Learning

---

**文書バージョン:** 1.0  
**最終更新日:** 2024-01-15  
**ステータス:** 仕様確定  
**次のステップ:** 実装フェーズ1の開始
