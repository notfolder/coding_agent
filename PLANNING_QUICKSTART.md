# プランニング機能クイックスタートガイド

> **Note**: 本ガイドは[プランニングプロセス仕様書](PLANNING_SPECIFICATION.md)の簡易版です。詳細な仕様については完全版を参照してください。実装方式については[実装詳細設計書](PLANNING_IMPLEMENTATION_DESIGN.md)を参照してください。

## 概要

プランニング機能は、LLMエージェントが複雑なタスクを以下の5つのフェーズで処理します：

1. **目標の理解** - タスクの意図を把握
2. **タスクの分解** - Chain-of-Thoughtで細分化
3. **行動計画の生成** - 実行順序とツール選択
4. **実行** - 計画に基づいて実行
5. **監視と修正** - 結果評価と計画修正

## 基本設定

### config.yamlへの追加

```yaml
# プランニング機能の基本設定（全てデフォルト値）
planning:
  # 機能の有効化（デフォルト: true）
  enabled: true
  
  # プランニング戦略（デフォルト: chain_of_thought）
  strategy: "chain_of_thought"
  
  # 最大サブタスク数（デフォルト: 100）
  max_subtasks: 100
  
  # タスク分解の詳細度（デフォルト: moderate）
  decomposition_level: "moderate"
  
  # リフレクション設定
  reflection:
    enabled: true                 # デフォルト: true
    trigger_on_error: true        # エラー時に自動リフレクション
    trigger_interval: 3           # 3アクション毎にリフレクション
  
  # 計画修正設定
  revision:
    max_revisions: 3              # 最大3回まで修正
  
  # 履歴管理（JSONLファイルベース）
  history:
    storage_type: "jsonl"
    directory: "planning_history"
```

### 環境変数での設定

```bash
# プランニング機能を有効化（デフォルトでtrue）
export PLANNING_ENABLED=true

# リフレクション機能を有効化（デフォルトでtrue）
export REFLECTION_ENABLED=true

# 最大計画修正回数
export MAX_PLAN_REVISIONS=3
```

## JSON応答フォーマット

### プランニングフェーズ

```json
{
  "phase": "planning",
  "goal_understanding": {
    "main_objective": "READMEにインストール手順を追加",
    "success_criteria": ["手順が明確", "詳細な説明"],
    "constraints": ["既存構造を維持"]
  },
  "task_decomposition": {
    "reasoning": "まずREADMEを取得し、内容を理解してから編集します",
    "subtasks": [
      {
        "id": "task_1",
        "description": "READMEの取得",
        "dependencies": [],
        "estimated_complexity": "low"
      }
    ]
  },
  "action_plan": {
    "execution_order": ["task_1", "task_2"],
    "actions": [...]
  }
}
```

### 実行フェーズ

```json
{
  "phase": "execution",
  "current_task": "task_1",
  "function_call": {
    "name": "github_get_file_contents",
    "arguments": {
      "owner": "myorg",
      "repo": "myrepo",
      "path": "README.md"
    }
  }
}
```

### リフレクションフェーズ

```json
{
  "phase": "reflection",
  "reflection": {
    "action_evaluated": "github_get_file_contents",
    "status": "success",
    "evaluation": "ファイルが正常に取得されました"
  }
}
```

### 完了

```json
{
  "phase": "completion",
  "summary": {
    "goal_achieved": true,
    "tasks_completed": 4,
    "key_outcomes": ["READMEが更新されました"]
  },
  "done": true
}
```

## エラーハンドリング例

### ファイルが見つからない場合

```json
{
  "phase": "reflection",
  "reflection": {
    "status": "failure",
    "error": "File not found",
    "plan_revision_needed": true
  },
  "plan_revision": {
    "reason": "正しいファイルパスを特定する必要がある",
    "changes": [
      {
        "type": "add_action",
        "action": {
          "tool": "github_search_code",
          "purpose": "正しいパスを検索"
        }
      }
    ]
  }
}
```

## システムプロンプトへの追加

既存のシステムプロンプトに以下を追加：

```
## プランニングプロセス

タスクを受け取ったら、以下の手順で処理してください：

1. **目標の理解**: タスクの目的、成功基準、制約を特定
2. **タスクの分解**: Chain-of-Thoughtで段階的に分解
3. **行動計画**: 実行順序とツールを決定
4. **実行**: 計画に従って実行
5. **リフレクション**: 結果を評価し、必要に応じて修正

最初の応答では完全な計画をJSON形式で提示してください。
```

## 使用例

### シンプルなタスク（README更新）

**Input (Issue):**
```
READMEにインストール手順を追加してください
```

**Planning:**
1. 目標理解: READMEの更新
2. 分解: ファイル取得 → 編集 → 更新 → 確認
3. 計画: 4ステップの実行計画

**Execution:**
- README.md取得
- インストール手順追加
- ファイル更新
- 結果確認

**Result:** ✅ 完了

### 中程度のタスク（新機能追加）

**Input (Issue):**
```
ユーザー認証機能を追加してください
```

**Planning:**
1. 目標理解: 認証機能の実装
2. 分解: 7個のサブタスクに分解
3. 計画: 依存関係を考慮した実行計画

**Execution with Reflection:**
- コード実装
- エラー発生 → リフレクション
- 計画修正
- 再実行
- テスト追加

**Result:** ✅ 完了（1回の計画修正を含む）

## トラブルシューティング

### プランニングが実行されない

**原因:** `planning.enabled` が `false`

**解決:**
```yaml
planning:
  enabled: true
```

### 計画修正が多すぎる

**原因:** 複雑すぎるタスクまたは不適切な分解

**解決:**
```yaml
planning:
  decomposition_level: "detailed"  # より詳細な分解
  revision:
    max_revisions: 5  # 修正回数を増やす
```

### リフレクションが実行されない

**原因:** リフレクション設定が無効

**解決:**
```yaml
planning:
  reflection:
    enabled: true
    trigger_on_error: true
```

## パフォーマンスヒント

### トークン効率化

```yaml
planning:
  # シンプルなタスクは簡易プランニング
  decomposition_level: "moderate"
  
  # キャッシュを有効化
  cache:
    enabled: true
    ttl: 86400
```

### 処理時間短縮

```yaml
planning:
  # リフレクション頻度を調整
  reflection:
    trigger_interval: 5  # 5アクション毎に変更
  
  # 早期終了を有効化
  execution:
    early_termination:
      enabled: true
```

## セキュリティ設定

### ツール使用制限

```yaml
planning:
  security:
    # 使用可能なツールを制限
    allowed_tools:
      - "github_get_*"
      - "github_create_or_update_file"
    
    # 危険な操作は禁止
    forbidden_tools:
      - "github_delete_*"
```

### 承認フロー

```yaml
planning:
  revision:
    # 計画修正時に人間の承認を要求
    require_human_approval: true
    approval_timeout: 3600
```

## 次のステップ

1. **詳細を学ぶ**: [完全な仕様書](PLANNING_SPECIFICATION.md)を読む
2. **実装を開始**: フェーズ1（基本プランニング機能）から始める
3. **テストを実行**: 提供されているテストケースで動作確認
4. **フィードバック**: 問題や改善案をIssueで報告

## 関連リンク

- [プランニングプロセス仕様書](PLANNING_SPECIFICATION.md) - 完全な仕様
- [README](README.md) - プロジェクト概要
- [クラス設計](class_spec.md) - アーキテクチャ詳細
