# プランニング機能 - サマリー

## 📋 概要

LLMエージェントのプランニングプロセス仕様を策定しました（コード実装なし）。

### 5つのプランニングフェーズ

1. **目標の理解** - ユーザーの指示を理解
2. **タスクの分解** - Chain-of-Thoughtで細分化  
3. **行動計画の生成** - 実行順序とツール選択
4. **実行** - 計画に基づいて実行
5. **監視と修正** - 結果評価と計画修正

## 📚 ドキュメント

| ドキュメント | 内容 | 行数 |
|-------------|------|------|
| [PLANNING_SPECIFICATION.md](PLANNING_SPECIFICATION.md) | 完全仕様書 | 1,121行 |
| [PLANNING_IMPLEMENTATION_DESIGN.md](PLANNING_IMPLEMENTATION_DESIGN.md) | 実装詳細設計 | - |
| [PLANNING_QUICKSTART.md](PLANNING_QUICKSTART.md) | クイックスタート | 321行 |

## ⚙️ デフォルト設定

```yaml
planning:
  enabled: true                     # デフォルトで有効
  strategy: "chain_of_thought"      # CoT戦略
  max_subtasks: 100                 # 最大100サブタスク
  decomposition_level: "moderate"   # 中程度の分解
  
  reflection:
    enabled: true                   # デフォルトで有効
    trigger_on_error: true         # エラー時に実行
    trigger_interval: 3            # 3アクション毎
  
  history:
    storage_type: "jsonl"          # JSONLファイルベース
    directory: "planning_history"
```

## 💻 実装方式

**結論**: システムプロンプトのみでは実装不可能。コード変更が必要。

### 必要な新規コンポーネント

1. **PlanningCoordinator** - 全体制御とフェーズ遷移
2. **PlanningHistoryStore** - JSONLファイルベース履歴管理
3. **system_prompt_planning.txt** - プランニング専用プロンプト

### 実装工数: 約5週間

- Phase 1: 基本実装（2週間）
- Phase 2: リフレクション（2週間）
- Phase 3: 最適化（1週間）

詳細は [PLANNING_IMPLEMENTATION_DESIGN.md](PLANNING_IMPLEMENTATION_DESIGN.md) を参照。

## 🔄 レビュー対応

### 仕様の簡略化（40%削減）

- 1,883行 → 1,121行
- 17セクション → 14セクション
- 不要なセクション削除（ロードマップ、利用例詳細、モニタリング、権限管理など）

### 主な変更

- ✅ デフォルト値の更新（enabled: true, max_subtasks: 100など）
- ✅ JSONLファイルベース履歴管理
- ✅ user_config_api統合
- ✅ セキュリティセクション簡略化

---

**ステータス**: 仕様策定完了  
**更新日**: 2024-11-23
