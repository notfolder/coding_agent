# 一時停止・リジューム機能の使用方法

## 概要

この機能により、consumerモードで実行中のタスクを一時停止し、後から同じ状態から再開できます。

## 基本的な使い方

### 1. タスクの一時停止

実行中のconsumerプロセスを一時停止するには、以下のコマンドで停止シグナルファイルを作成します：

```bash
touch contexts/pause_signal
```

consumerは次のLLMループで一時停止シグナルを検出し、現在の状態を保存してから終了します。

### 2. 一時停止タスクの確認

一時停止中のタスクは `contexts/paused/` ディレクトリに保存されます：

```bash
ls -la contexts/paused/
```

各タスクのディレクトリには以下のファイルが含まれます：
- `task_state.json` - タスクの状態情報
- `current.jsonl` - LLM会話履歴
- `summary.jsonl` - 会話サマリー（存在する場合）
- `tools.jsonl` - ツール呼び出し履歴
- `planning/` - Planning履歴（Planning有効時）

### 3. タスクの再開

一時停止されたタスクは、次回producerモードを実行した際に自動的にキューに再投入されます：

```bash
python main.py --mode producer
```

その後、consumerモードで処理を再開します：

```bash
python main.py --mode consumer
```

## 設定

`config.yaml` の設定項目：

```yaml
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
  # ... 既存の設定 ...
  paused_label: "coding agent paused"

gitlab:
  # ... 既存の設定 ...
  paused_label: "coding agent paused"
```

## ラベル管理

一時停止時と再開時でラベルが自動的に更新されます：

- **一時停止時**: `coding agent processing` → `coding agent paused`
- **再開時**: `coding agent paused` → `coding agent processing`

## Planningモードでの一時停止

Planningモードが有効な場合、以下の追加情報も保存されます：

- 現在のフェーズ（Planning/Execution/Reflection/Revision）
- 実行済みアクション数
- プラン修正回数
- チェックリストコメントID

これにより、Planning実行中のタスクでも正確な状態から再開できます。

## 一時停止タスクの削除

タスクを再開せずに破棄したい場合：

```bash
# 一時停止ディレクトリから削除
rm -rf contexts/paused/{task_uuid}/

# GitHub/GitLabでタスクをクローズ
```

## トラブルシューティング

### 一時停止が実行されない

- `contexts/pause_signal` ファイルが正しい場所にあることを確認
- `config.yaml` の `pause_resume.enabled` が `true` であることを確認
- consumerプロセスのログを確認

### 再開時にエラーが発生する

- `contexts/paused/{uuid}/task_state.json` が正しく保存されているか確認
- GitHub/GitLabでタスクが削除されていないか確認
- ログファイルでエラーの詳細を確認

## セキュリティ上の注意

- `contexts/paused/` ディレクトリには機密情報が含まれる可能性があるため、適切なアクセス権限を設定してください
- 一時停止状態のバックアップを定期的に取ることを推奨します
