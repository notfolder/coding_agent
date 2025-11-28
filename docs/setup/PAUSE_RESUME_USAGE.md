# 一時停止・再開機能の使用方法

## 概要

この機能により、Consumerモードで実行中のタスクを一時停止し、後から同じ状態から再開できます。

---

## 1. 基本的な使い方

### 1.1 タスクの一時停止

実行中のConsumerプロセスを一時停止するには、停止シグナルファイルを作成します。ファイル名はcontexts/pause_signalです。

Consumerは次のLLMループで一時停止シグナルを検出し、現在の状態を保存してから終了します。

### 1.2 一時停止タスクの確認

一時停止中のタスクはcontexts/pausedディレクトリに保存されます。

各タスクのディレクトリには以下のファイルが含まれます：
- **task_state.json**: タスクの状態情報
- **current.jsonl**: LLM会話履歴
- **summary.jsonl**: 会話サマリー（存在する場合）
- **tools.jsonl**: ツール呼び出し履歴
- **planning/**: Planning履歴（Planning有効時）

### 1.3 タスクの再開

一時停止されたタスクは、次回Producerモードを実行した際に自動的にキューに再投入されます。

手順：
1. Producerモードを実行してタスクをキューに再投入
2. Consumerモードで処理を再開

---

## 2. 設定

### 2.1 config.yamlの設定項目

pause_resumeセクションで以下の項目を設定できます：

#### 基本設定

- **enabled**: 一時停止機能の有効化（デフォルト：true）
- **signal_file**: 停止シグナルファイルのパス（デフォルト：contexts/pause_signal）
- **check_interval**: 停止チェック間隔（LLMループのN回ごとにチェック、デフォルト：1）
- **paused_task_expiry_days**: 一時停止タスクの有効期限（日数、デフォルト：30）
- **paused_dir**: 一時停止状態ディレクトリ（デフォルト：contexts/paused）

#### プラットフォーム設定

GitHubおよびGitLabの設定セクションで、一時停止ラベルを設定できます：

- **github.paused_label**: GitHub用の一時停止ラベル（デフォルト：coding agent paused）
- **gitlab.paused_label**: GitLab用の一時停止ラベル（デフォルト：coding agent paused）

---

## 3. ラベル管理

### 3.1 自動ラベル更新

一時停止時と再開時でラベルが自動的に更新されます：

- **一時停止時**: 「coding agent processing」から「coding agent paused」に変更
- **再開時**: 「coding agent paused」から「coding agent processing」に変更

### 3.2 必要なラベルの準備

リポジトリに以下のラベルを事前に作成してください：
- coding agent
- coding agent processing
- coding agent paused
- coding agent done

---

## 4. Planningモードでの一時停止

### 4.1 保存される追加情報

Planningモードが有効な場合、以下の追加情報も保存されます：

- 現在のフェーズ（Planning/Execution/Reflection/Revision）
- 実行済みアクション数
- プラン修正回数
- チェックリストコメントID

これにより、Planning実行中のタスクでも正確な状態から再開できます。

---

## 5. 一時停止タスクの削除

### 5.1 手動削除

タスクを再開せずに破棄したい場合は、以下の手順を実行します：

1. 一時停止ディレクトリから対象タスクのフォルダを削除
   - パス：contexts/paused/{task_uuid}/
2. GitHub/GitLabでタスクをクローズまたはラベルを削除

---

## 6. トラブルシューティング

### 6.1 一時停止が実行されない場合

以下を確認してください：

- **シグナルファイルの場所**: contexts/pause_signalファイルが正しい場所にあることを確認
- **設定の確認**: config.yamlのpause_resume.enabledがtrueであることを確認
- **ログの確認**: Consumerプロセスのログを確認

### 6.2 再開時にエラーが発生する場合

以下を確認してください：

- **状態ファイルの確認**: contexts/paused/{uuid}/task_state.jsonが正しく保存されているか確認
- **タスクの存在確認**: GitHub/GitLabでタスクが削除されていないか確認
- **ログファイルの確認**: ログファイルでエラーの詳細を確認

---

## 7. セキュリティ上の注意

### 7.1 コンテキストデータの保護

contexts/paused/ディレクトリには機密情報が含まれる可能性があるため、適切なアクセス権限を設定してください。

### 7.2 バックアップの推奨

一時停止状態のバックアップを定期的に取ることを推奨します。

---

## 8. 関連ドキュメント

- **一時停止・再開機能仕様**: [PAUSE_RESUME_SPECIFICATION.md](../spec/PAUSE_RESUME_SPECIFICATION.md)
- **タスク停止機能仕様**: [TASK_STOP_SPECIFICATION.md](../spec/TASK_STOP_SPECIFICATION.md)

---

**文書バージョン:** 1.0  
**最終更新日:** 2024-11-28
