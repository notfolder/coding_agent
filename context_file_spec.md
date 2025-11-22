# コンテキストファイル化による省メモリ化仕様

## 1. 概要

### 1.1 目的

コーディングエージェントがコードや仕様を読み込みながら処理を行う際、すべてのコンテキスト（会話履歴、システムプロンプト、ツール実行結果など）をメモリ上に保持すると、大量のメモリを消費します。本仕様では、**JSONLinesファイルベース**でコンテキストを永続化することで省メモリ化を実現し、マルチユーザー・マルチプロセス環境での安全な動作と、LLMによるインテリジェントなコンテキスト長管理を定義します。

### 1.2 背景と課題

現在の実装における問題点：

- **メモリ使用量の増大**: LLMクライアントが会話履歴全体をメモリ上の`messages`リストで保持
- **スケーラビリティの欠如**: 長時間実行や複数タスク同時処理時にメモリ不足のリスク
- **永続性の欠如**: プロセス終了時にコンテキストが失われ、中断・再開ができない
- **デバッグの困難さ**: メモリ上のデータのため、処理過程の追跡や監査が困難
- **マルチプロセス非対応**: 複数プロセスが同時にキューからタスクを取得する際の競合管理が未実装
- **コンテキスト長管理の不足**: 古いメッセージの単純削除により重要情報が失われる

### 1.3 設計方針

1. **JSONLinesファイルベース**: 
   - シンプルで人間が読める形式
   - 外部ツール（jq, grep等）での解析が容易
   - 追記型で高速な書き込み
   - 将来的なSQLite移行を考慮した設計

2. **UUIDベースのディレクトリ管理**:
   - 各タスクに一意のUUIDを割り当て
   - UUID単位でディレクトリを作成し、関連ファイルを集約
   - タスク間の完全な分離を実現

3. **実行状態による物理的分離**:
   - `running/`: 実行中タスクのコンテキスト
   - `completed/`: 完了済みタスクのコンテキスト
   - 状態遷移時にディレクトリを移動

4. **マルチプロセス対応**:
   - ファイルロックによる排他制御
   - UUIDによるタスク分離で競合を最小化
   - 状態ファイルによる処理状況の可視化

5. **LLMによるコンテキスト圧縮**:
   - モデルのコンテキスト長を設定から取得
   - 閾値（例: 70%）到達時にLLMに要約を依頼
   - 要約結果を新たなコンテキストとして利用

### 1.4 期待される効果

- **メモリ効率**: 60-80%のメモリ削減（要約使用時は90%以上）
- **永続性**: タスクの中断・再開が可能
- **可視性**: 人間が直接ファイルを確認してデバッグ可能
- **スケーラビリティ**: マルチプロセス対応で並行処理が可能
- **保守性**: シンプルな実装で運用負荷が低い
- **拡張性**: 将来的なSQLite移行が容易

## 2. ディレクトリ構造

### 2.1 全体構成

```
logs/contexts/
├── running/                    # 実行中タスク
│   ├── {uuid-1}/              # タスクUUID単位のディレクトリ
│   │   ├── metadata.json      # タスクメタデータ
│   │   ├── state.json         # 実行状態
│   │   ├── messages.jsonl     # メッセージ履歴
│   │   ├── summaries.jsonl    # コンテキスト要約履歴
│   │   ├── tools.jsonl        # ツール実行履歴
│   │   └── .lock              # ファイルロック
│   └── {uuid-2}/
│       └── ...
└── completed/                  # 完了済みタスク
    ├── {uuid-3}/
    │   └── (running/と同じ構造)
    └── {uuid-4}/
        └── ...
```

### 2.2 ディレクトリの役割

#### 2.2.1 `running/` ディレクトリ

- **目的**: 現在実行中のタスクのコンテキストを格納
- **アクセス**: プロセスが頻繁に読み書き
- **ライフサイクル**: タスク開始時に作成、完了時に`completed/`へ移動
- **ファイルロック**: `.lock`ファイルで排他制御

#### 2.2.2 `completed/` ディレクトリ

- **目的**: 完了したタスクのコンテキストをアーカイブ
- **アクセス**: 主に参照のみ（デバッグ、監査、統計）
- **保持期間**: 設定可能（デフォルト30日）
- **圧縮**: 古いものは自動的にgzip圧縮可能

### 2.3 UUID生成とディレクトリ作成

#### UUID生成ルール

- **形式**: UUID v4（ランダム生成）
- **生成タイミング**: タスク取得直後、コンテキスト初期化前
- **用途**: ディレクトリ名、ログ出力、トレーシング

#### ディレクトリ作成手順

1. UUID生成
2. `running/{uuid}/`ディレクトリ作成
3. `metadata.json`作成（タスク情報記録）
4. `state.json`作成（初期状態: `initializing`）
5. `.lock`ファイル作成（プロセスID記録）

## 3. ファイル仕様

### 3.1 metadata.json

タスクの基本情報を記録する静的ファイル。

#### 目的

- タスクの識別情報と設定を保持
- デバッグ時の情報参照
- 統計集計時のフィルタリング

#### 内容

```json
{
  "uuid": "550e8400-e29b-41d4-a716-446655440000",
  "task_key": {
    "task_source": "github",
    "owner": "notfolder",
    "repo": "coding_agent",
    "task_type": "issue",
    "task_id": "27"
  },
  "created_at": "2024-01-15T10:30:00.123456Z",
  "process_id": 12345,
  "hostname": "worker-node-1",
  "config": {
    "llm_provider": "openai",
    "model": "gpt-4o",
    "context_length": 128000,
    "compression_threshold": 0.7
  },
  "user": "notfolder"
}
```

#### フィールド説明

| フィールド | 型 | 必須 | 説明 |
|-----------|---|------|------|
| uuid | string | ✓ | タスクの一意識別子 |
| task_key | object | ✓ | タスクの識別情報（ソース、リポジトリ等） |
| created_at | string | ✓ | タスク作成日時（ISO 8601） |
| process_id | integer | ✓ | 処理プロセスのPID |
| hostname | string | ✓ | 実行ホスト名 |
| config | object | ✓ | 実行時の設定（LLM、コンテキスト長等） |
| user | string | - | タスク作成ユーザー |

### 3.2 state.json

タスクの実行状態を記録する動的ファイル。プロセスが定期的に更新。

#### 目的

- 実行状況のリアルタイム把握
- 異常終了時の状態復元
- プロセス監視とヘルスチェック

#### 内容

```json
{
  "status": "processing",
  "started_at": "2024-01-15T10:30:01.000000Z",
  "updated_at": "2024-01-15T10:35:22.456789Z",
  "completed_at": null,
  "llm_call_count": 45,
  "tool_call_count": 12,
  "total_tokens_used": 45678,
  "current_context_tokens": 32000,
  "compression_count": 2,
  "last_activity": "tool_execution",
  "error": null
}
```

#### ステータス値

- `initializing`: 初期化中
- `processing`: 処理中（LLMとの対話）
- `compressing`: コンテキスト圧縮中
- `completing`: 完了処理中
- `completed`: 正常完了
- `failed`: エラー終了
- `timeout`: タイムアウト

#### 更新タイミング

- LLM呼び出し前後
- ツール実行前後
- コンテキスト圧縮時
- 最低でも30秒ごと（ハートビート）

### 3.3 messages.jsonl

LLMとの会話履歴をJSONLines形式で記録。

#### 目的

- 全ての会話履歴を時系列で保存
- LLMへの入力コンテキスト生成の元データ
- デバッグ時の詳細な追跡

#### 形式

1行1メッセージのJSON形式。ファイル末尾に追記。

```jsonl
{"seq":1,"role":"system","content":"You are an AI coding assistant...","timestamp":"2024-01-15T10:30:01.123Z","token_count":250}
{"seq":2,"role":"user","content":"Fix the bug in...","timestamp":"2024-01-15T10:30:02.456Z","token_count":120}
{"seq":3,"role":"assistant","content":"I'll help you fix...","timestamp":"2024-01-15T10:30:15.789Z","token_count":450}
{"seq":4,"role":"tool","content":"{\"output\":\"...\"}","timestamp":"2024-01-15T10:30:20.123Z","token_count":1200,"tool_name":"github_get_file_contents"}
```

#### フィールド説明

| フィールド | 型 | 必須 | 説明 |
|-----------|---|------|------|
| seq | integer | ✓ | シーケンス番号（1から開始） |
| role | string | ✓ | メッセージの役割（system/user/assistant/tool） |
| content | string | ✓ | メッセージ内容 |
| timestamp | string | ✓ | 作成日時（ISO 8601） |
| token_count | integer | ✓ | 推定トークン数（4文字=1トークン） |
| tool_name | string | - | ツール実行時のツール名 |
| function_call | object | - | 関数呼び出し情報 |
| is_summarized | boolean | - | 要約済みフラグ（デフォルト: false） |

#### 機密情報のマスキング

書き込み前に以下のパターンをマスキング：

- GitHubトークン: `ghp_*`, `github_pat_*` → `[GITHUB_TOKEN]`
- OpenAI APIキー: `sk-*` → `[OPENAI_KEY]`
- GitLabトークン: `glpat-*` → `[GITLAB_TOKEN]`
- メールアドレス: `*@*.*` → `[EMAIL]`

### 3.4 summaries.jsonl

LLMによるコンテキスト要約の履歴。

#### 目的

- コンテキスト圧縮の記録
- 要約内容の再利用
- 圧縮効果の測定

#### 形式

```jsonl
{"summary_id":1,"start_seq":10,"end_seq":50,"summary":"Fixed authentication bug by updating...","created_at":"2024-01-15T10:32:00.000Z","original_tokens":12000,"summary_tokens":800,"compression_ratio":0.067}
{"summary_id":2,"start_seq":51,"end_seq":90,"summary":"Implemented new feature for...","created_at":"2024-01-15T10:34:30.000Z","original_tokens":15000,"summary_tokens":950,"compression_ratio":0.063}
```

#### フィールド説明

| フィールド | 型 | 必須 | 説明 |
|-----------|---|------|------|
| summary_id | integer | ✓ | 要約のID（1から開始） |
| start_seq | integer | ✓ | 要約対象の開始シーケンス番号 |
| end_seq | integer | ✓ | 要約対象の終了シーケンス番号 |
| summary | string | ✓ | LLMが生成した要約テキスト |
| created_at | string | ✓ | 要約作成日時 |
| original_tokens | integer | ✓ | 元のトークン数 |
| summary_tokens | integer | ✓ | 要約後のトークン数 |
| compression_ratio | float | ✓ | 圧縮率（summary_tokens/original_tokens） |

### 3.5 tools.jsonl

ツール（MCP）実行の履歴。

#### 目的

- ツール実行の詳細記録
- エラー発生時の調査
- パフォーマンス分析

#### 形式

```jsonl
{"seq":1,"tool_name":"github_get_file_contents","arguments":{"owner":"notfolder","repo":"coding_agent","path":"main.py"},"result":"...file content...","status":"success","duration_ms":234,"timestamp":"2024-01-15T10:30:20.123Z"}
{"seq":2,"tool_name":"github_create_branch","arguments":{"owner":"notfolder","repo":"coding_agent","branch":"fix-bug"},"result":null,"status":"error","error":"Branch already exists","duration_ms":123,"timestamp":"2024-01-15T10:31:15.456Z"}
```

#### フィールド説明

| フィールド | 型 | 必須 | 説明 |
|-----------|---|------|------|
| seq | integer | ✓ | ツール実行のシーケンス番号 |
| tool_name | string | ✓ | 実行したツール名 |
| arguments | object | ✓ | ツールへの引数 |
| result | string/object | - | 実行結果（成功時） |
| status | string | ✓ | 実行結果（success/error） |
| error | string | - | エラーメッセージ（失敗時） |
| duration_ms | integer | ✓ | 実行時間（ミリ秒） |
| timestamp | string | ✓ | 実行日時 |

### 3.6 .lock ファイル

プロセス間の排他制御用ロックファイル。

#### 目的

- 同一タスクへの複数プロセスアクセス防止
- プロセスの生存確認（ヘルスチェック）
- 異常終了時のクリーンアップ判断

#### 内容

```json
{
  "process_id": 12345,
  "hostname": "worker-node-1",
  "acquired_at": "2024-01-15T10:30:00.000Z",
  "heartbeat_at": "2024-01-15T10:35:30.000Z"
}
```

#### ロック取得手順

1. `.lock`ファイルの存在確認
2. 存在する場合:
   - 内容を読み取り
   - `heartbeat_at`が60秒以上古い場合は失効と判断
   - プロセスが実際に存在するか確認（kill -0）
   - 失効していれば上書き、有効なら取得失敗
3. 存在しない場合:
   - 新規作成（アトミック操作）

#### ロック更新

- 30秒ごとに`heartbeat_at`を更新
- `state.json`更新と同時に実施

#### ロック解放

- タスク完了時に削除
- completed/へ移動時に削除

## 4. コンテキスト管理

### 4.1 メッセージストアの役割

メッセージストアは、JSONLinesファイルとメモリキャッシュを組み合わせてコンテキストを管理します。

#### 責務

- メッセージの追加（メモリ + ファイル）
- LLM用メッセージリストの生成（コンテキスト長考慮）
- 古いメッセージの要約トリガー
- 統計情報の提供

#### メモリキャッシュ

**目的**: LLM呼び出し時の高速アクセス

**内容**:
- システムプロンプト（常に保持）
- 最新の要約（あれば1件）
- 最新Nメッセージ（設定可能、デフォルト20件）

**更新タイミング**:
- メッセージ追加時
- 要約作成時
- プロセス起動時（ファイルから復元）

#### ファイルストレージ

**目的**: 全履歴の永続化

**書き込み**: 
- メッセージ追加ごとに`messages.jsonl`に追記
- バッファリングせず即時書き込み（データ損失防止）

**読み込み**:
- プロセス起動時に最新N件をキャッシュに読み込み
- LLM用メッセージ生成時に必要に応じて追加読み込み

### 4.2 LLM用メッセージリストの生成

#### 生成ロジック

コンテキスト長制限内で最大限の情報を含めるため、以下の優先順位で構築：

1. **システムプロンプト**（必須）
   - 常に先頭に配置
   - トークン数: 約200-500

2. **最新の要約**（あれば）
   - 過去の会話の要約を1件
   - トークン数: 約500-1000

3. **最新メッセージ群**
   - 要約以降のメッセージを新しい順に追加
   - コンテキスト長の閾値（例: 70%）を超えないまで

#### トークン数計算

**推定方式**: 4文字 = 1トークン（簡易計算）

**実装**:
- 各メッセージ追加時にトークン数を計算して記録
- LLM用リスト生成時に累積トークン数を計算

#### コンテキスト長の取得

設定ファイル（config.yaml）からモデルごとのコンテキスト長を取得：

```yaml
llm:
  openai:
    model: "gpt-4o"
    context_length: 128000
  ollama:
    model: "qwen3-30b"
    context_length: 32768
```

### 4.3 コンテキスト圧縮（要約）

#### トリガー条件

以下のいずれかを満たす場合に圧縮を実行：

- 未要約メッセージの累積トークン数が閾値を超過
  - 閾値 = `context_length * compression_threshold`
  - デフォルト: `context_length * 0.7`
- 未要約メッセージ数が一定数以上（最低10件）

#### 要約対象の選択

- 最新の要約（あれば）以降のメッセージ
- ただし、直近5件は残す（要約対象外）
- システムプロンプトは除外

#### 要約プロンプト

LLMに以下のようなプロンプトで要約を依頼：

```
あなたは会話履歴を要約する補助AIです。
以下のメッセージ履歴を簡潔かつ包括的に要約してください。

要約には以下を含めること：
1. 重要な決定事項
2. 実施したコード変更
3. 発生した問題とその解決
4. 残存タスク

元の30-40%の長さを目標としてください。

=== 要約対象メッセージ ===
[USER]: Fix the bug in authentication
[ASSISTANT]: I'll help you fix the authentication bug...
[TOOL]: github_get_file_contents -> (file content)
...

要約のみを出力してください。説明は不要です。
```

#### 要約結果の保存

1. LLMから要約テキストを取得
2. トークン数を計算
3. `summaries.jsonl`に追記
4. 元のメッセージに`is_summarized: true`フラグをマーク
   - 注: JSONLinesは追記型のため、実際にはフラグ更新は不要
   - メモリ上の管理でのみ使用

#### 圧縮効果の測定

- 元のトークン数 vs 要約後のトークン数
- 圧縮率の記録（compression_ratio）
- 目標: 60-70%削減

### 4.4 状態遷移とディレクトリ移動

#### タスクライフサイクル

```
[開始] 
  ↓
(running/{uuid}/ 作成)
  ↓
[initializing] ← state.json
  ↓
[processing] ← LLMとの対話、ツール実行
  ↓
[compressing] ← コンテキスト圧縮（必要時）
  ↓
[completing] ← 完了処理
  ↓
(completed/{uuid}/ へ移動)
  ↓
[completed]
```

#### ディレクトリ移動手順

タスク完了時に`running/`から`completed/`へ移動：

1. `state.json`のステータスを`completing`に更新
2. 最終的な統計情報を`state.json`に書き込み
3. `.lock`ファイルを削除
4. ディレクトリ全体を`completed/{uuid}/`へ移動（アトミック操作）
5. 移動完了後、`state.json`のステータスを`completed`に更新

#### 異常終了時の処理

プロセスが異常終了した場合（`.lock`の heartbeat が60秒以上更新されない）：

- 別プロセスがクリーンアップ
- `state.json`のステータスを`failed`に更新
- `error`フィールドにエラー内容を記録
- `completed/`へ移動

## 5. マルチプロセス対応

### 5.1 タスク分離による競合回避

#### 基本方針

- **UUID単位の完全分離**: 各タスクは独立したディレクトリで管理
- **同一タスクへの排他制御**: `.lock`ファイルによるロック
- **異なるタスクは並行実行**: 競合なし

#### タスクキューとの連携

1. プロセスがキューからタスクを取得
2. UUID生成
3. `running/{uuid}/`ディレクトリ作成
4. `.lock`ファイル作成（ロック取得）
5. タスク処理
6. 完了後、`completed/`へ移動
7. `.lock`ファイル削除（ロック解放）

### 5.2 ファイルロックの詳細

#### ロック取得のアルゴリズム

**目的**: 同一タスクへの複数プロセスアクセスを防止

**手順**:

1. `.lock`ファイルが存在するか確認
2. 存在しない → 新規作成して取得成功
3. 存在する → 内容を確認:
   - `heartbeat_at`が60秒以内 → ロック有効、取得失敗
   - `heartbeat_at`が60秒以上前 → 失効と判断:
     - プロセスIDのプロセスが存在するか確認
     - 存在しない → 失効確定、ロック取得
     - 存在する → ロック有効、取得失敗

#### ロック更新（ハートビート）

- **間隔**: 30秒ごと
- **実装**: `state.json`更新と同時に実行
- **内容**: `heartbeat_at`タイムスタンプを更新

#### ロック解放

- タスク完了時
- `completed/`へのディレクトリ移動時
- 異常終了時（別プロセスが検出して削除）

### 5.3 ファイルI/O の排他制御

#### JSONLinesファイルへの追記

**課題**: 複数プロセスが同時に追記すると行が混在する可能性

**対策**: 
- 基本的にUUIDで分離されているため競合なし
- 万が一の場合に備え、1行単位のアトミック書き込み
- Pythonの`open()`はデフォルトでバッファリングされるが、`flush()`で即座にディスクへ

#### state.jsonの更新

**課題**: 頻繁に更新されるため、読み書き競合の可能性

**対策**:
- ロックファイル（`.state.lock`）を使用
- 読み取り前にロック取得、読み書き後に解放
- タイムアウト付きロック取得（5秒）

### 5.4 プロセス監視とクリーンアップ

#### 監視プロセスの役割

定期的に`running/`配下をスキャンし、以下を実施：

**死活監視**:
- `.lock`ファイルのheartbeatを確認
- 60秒以上更新されていない場合、プロセス存在確認
- プロセスが存在しない場合、異常終了と判断

**クリーンアップ**:
- `state.json`にエラー情報を記録
- `completed/`へ移動
- ステータスを`failed`に更新

#### クリーンアップの実行頻度

- **デフォルト**: 5分ごと
- **設定可能**: 環境変数またはconfig.yamlで調整

## 6. マルチユーザー対応

### 6.1 ユーザーごとの設定分離

#### USER_CONFIG_API連携

既存のUSER_CONFIG_API機能を活用：

- タスク取得時にユーザー名を特定
- APIからユーザー固有の設定を取得
- LLM設定、コンテキスト長等がユーザーごとに異なる

#### コンテキストディレクトリの分離

ユーザー情報は`metadata.json`に記録：

```json
{
  "user": "notfolder",
  "config": {
    "llm_provider": "openai",
    "context_length": 128000
  }
}
```

ディレクトリ自体はUUID単位で分離されているため、ユーザーごとの物理分離は不要。

### 6.2 統計とレポート

#### ユーザーごとの集計

`metadata.json`の`user`フィールドを利用して集計：

- ユーザーごとのタスク数
- ユーザーごとのトークン使用量
- ユーザーごとの平均実行時間

#### プライバシー保護

- 機密情報のマスキング（既述）
- ユーザー間のコンテキスト共有は不可
- 管理者のみが全タスクにアクセス可能

## 7. パフォーマンスと最適化

### 7.1 メモリ使用量の削減

#### 削減効果の見積もり

| シナリオ | 従来方式 | ファイル方式 | 削減率 |
|---------|---------|------------|--------|
| 100回LLM呼び出し | 8.5MB | 1.5MB | 82% |
| 1000回LLM呼び出し | 85MB | 2.0MB | 98% |
| 要約使用時 | 85MB | 1.0MB | 99% |

#### メモリキャッシュのチューニング

**max_memory_messages**パラメータ:
- デフォルト: 20件
- 少ないとファイル読み込み頻度増加
- 多いとメモリ使用量増加
- 推奨: 10-30件

### 7.2 ディスク使用量

#### 推定値

- 1タスクあたり: 5-10MB（要約なし）
- 1タスクあたり: 2-5MB（要約あり）
- 1日10タスク: 20-100MB/日
- 30日保持: 600MB-3GB/月

#### 削減策

- 30日経過後の自動削除
- 7日経過後のgzip圧縮（70%削減）
- 重要タスクのみ長期保存

### 7.3 ファイルI/Oパフォーマンス

#### 書き込み

- **追記型**: 既存ファイルを読まず末尾に追加のみ
- **バッファなし**: データ損失を防ぐため即座にflush
- **影響**: LLM呼び出し時間に比べて無視できるレベル

#### 読み込み

- **起動時**: 最新N件のみ読み込み（高速）
- **LLM用リスト生成時**: 必要分のみ読み込み
- **最適化**: システムプロンプトと要約はキャッシュ

## 8. 運用

### 8.1 日常運用

#### ディスク容量監視

**アラート設定**:
- 総容量が10GBを超えたら警告
- 総容量が50GBを超えたらクリティカル

**対応**:
- 古いタスクの削除
- 圧縮の実施

#### クリーンアップスクリプト

**実行頻度**: 毎日深夜（cronで自動実行）

**処理内容**:
1. 30日以上経過した`completed/`タスクを削除
2. 7日以上経過した`completed/`タスクをgzip圧縮
3. `running/`の失効ロックをクリーンアップ
4. 統計レポート生成

### 8.2 トラブルシューティング

#### ディスク容量不足

**症状**: "No space left on device"

**診断**:
```bash
du -sh logs/contexts/running
du -sh logs/contexts/completed
```

**対応**:
- 緊急削除: 14日以上経過したタスクを削除
- 圧縮: 全てのcompletedタスクをgzip圧縮

#### ファイルロック問題

**症状**: タスクが処理されない

**診断**:
- `running/*/`に滞留している`.lock`ファイルを確認
- `heartbeat_at`が古いか確認

**対応**:
- プロセスが存在しなければ`.lock`を手動削除
- 監視プロセスの動作確認

#### 要約失敗

**症状**: コンテキストが肥大化

**診断**:
- `state.json`の`compression_count`が0
- ログに要約エラーが記録

**対応**:
- LLMの接続確認
- 要約プロンプトの見直し
- 手動での要約実行

### 8.3 監視とアラート

#### 監視項目

1. **ディスク使用量**
   - `running/`のサイズ
   - `completed/`のサイズ

2. **タスク滞留**
   - `running/`配下のタスク数
   - 長時間（6時間以上）実行中のタスク

3. **失敗率**
   - `completed/`配下の`failed`ステータス比率

4. **平均実行時間**
   - タスク開始から完了までの時間

#### アラート

- ディスク使用量 > 10GB: 警告
- 失敗率 > 10%: 警告
- 滞留タスク > 100件: 警告

### 8.4 バックアップとリストア

#### バックアップ対象

- `completed/`全体（完了タスクのアーカイブ）
- `running/`は除外（一時的なデータ）

#### バックアップ頻度

- 毎日1回（深夜）
- 世代管理: 7世代保持

#### リストア

- 特定タスクの調査時
- システム障害からの復旧時

## 9. デバッグとトラブルシューティング

### 9.1 コンテキストビューア

#### 目的

人間が直接ファイルを確認してデバッグ可能にする。

#### 使用方法

**コマンドラインツール**:
```bash
# 特定タスクの詳細表示
python -m tools.context_viewer --uuid {uuid}

# メッセージ履歴表示
python -m tools.context_viewer --uuid {uuid} --messages

# 要約履歴表示
python -m tools.context_viewer --uuid {uuid} --summaries

# ツール実行履歴表示
python -m tools.context_viewer --uuid {uuid} --tools
```

**出力例**:
```
Task UUID: 550e8400-e29b-41d4-a716-446655440000
Status: completed
Repository: github/notfolder/coding_agent
Task: issue #27
Started: 2024-01-15 10:30:00
Completed: 2024-01-15 10:45:23
Duration: 15分23秒

Statistics:
  LLM calls: 45
  Tool calls: 12
  Total tokens: 45,678
  Compressions: 2
  
Messages: 150 (showing last 10)
  [148] user: Commit the changes
  [149] tool: github_create_commit -> Success
  [150] assistant: {"done": true, "comment": "Completed"}
  
Summaries: 2
  [1] seq 10-50: Fixed authentication bug...
  [2] seq 51-90: Implemented new feature...
```

#### 手動確認

JSONLinesファイルは人間が読める形式のため、直接確認も可能：

```bash
# メッセージ履歴を確認
cat logs/contexts/completed/{uuid}/messages.jsonl | jq

# 最新10件のメッセージ
tail -10 logs/contexts/completed/{uuid}/messages.jsonl | jq

# 特定の role のメッセージのみ
grep '"role":"assistant"' logs/contexts/completed/{uuid}/messages.jsonl | jq
```

### 9.2 統計ツール

#### 全体統計

```bash
python -m tools.context_stats --summary
```

**出力例**:
```
Context Storage Statistics
==========================

Total contexts: 1,234
  - Running: 12
  - Completed: 1,222

Disk usage:
  - Running: 120 MB
  - Completed: 5.4 GB (2.1 GB after compression)

Average per task:
  - Messages: 85
  - Tokens: 42,000
  - Duration: 12分30秒
  - Compressions: 1.8

By user:
  - notfolder: 890 tasks (72%)
  - user2: 244 tasks (20%)
  - user3: 100 tasks (8%)
```

#### タスク検索

```bash
# ユーザーでフィルタ
python -m tools.context_stats --user notfolder

# 日付範囲でフィルタ
python -m tools.context_stats --from 2024-01-01 --to 2024-01-31

# 失敗タスクのみ
python -m tools.context_stats --status failed
```

### 9.3 ログとトレース

#### ログ出力

各処理でUUIDを含めてログ出力：

```
2024-01-15 10:30:01 INFO [uuid:550e8400] Task started: github/notfolder/coding_agent#27
2024-01-15 10:30:05 INFO [uuid:550e8400] LLM call #1: 250 tokens
2024-01-15 10:30:20 INFO [uuid:550e8400] Tool execution: github_get_file_contents
2024-01-15 10:32:00 INFO [uuid:550e8400] Context compression triggered
2024-01-15 10:32:15 INFO [uuid:550e8400] Compression completed: 12000 -> 800 tokens
2024-01-15 10:45:23 INFO [uuid:550e8400] Task completed successfully
```

#### トレースID

UUIDをトレースIDとして使用し、全ログとファイルを追跡可能。

## 10. 将来の拡張

### 10.1 SQLiteへの移行

#### 移行の容易性

JSONLinesベースで設計しているため、SQLiteへの移行は比較的容易：

**メリット**:
- トランザクション保証
- 高速なクエリ（インデックス）
- WALモードでマルチプロセス対応

**移行手順**:
1. MessageStoreインターフェースは維持
2. バックエンドをJSONLines → SQLiteに切り替え
3. 既存データのマイグレーションツール作成

**データモデル**:

現在のJSONLinesのフィールドはSQLiteテーブルに直接マッピング可能：

- `messages.jsonl` → `messages`テーブル
- `summaries.jsonl` → `summaries`テーブル
- `tools.jsonl` → `tool_calls`テーブル

### 10.2 高度な機能

#### セマンティック検索

過去のコンテキストから類似タスクを検索：

- メッセージ内容のベクトル化（Embedding）
- ベクトルDBへの保存（Pinecone/Weaviate）
- 類似タスクの参照による品質向上

#### インテリジェント要約

現在の要約は全メッセージを対象としているが、さらに高度化：

- 重要度スコアリング（LLMまたは機械学習）
- 重要メッセージは要約せず保持
- 階層的要約（要約の要約）

#### コスト最適化

- LLM応答のキャッシング（同じコンテキストで同じ応答を再利用）
- トークン使用量の最小化（コードの圧縮、参照化）

## 11. セキュリティ

### 11.1 機密情報保護

#### マスキング

`messages.jsonl`書き込み前に自動マスキング：

- GitHubトークン
- APIキー
- メールアドレス
- その他の機密パターン

#### ファイルパーミッション

- ディレクトリ: 700（所有者のみ）
- ファイル: 600（所有者のみ読み書き）

### 11.2 アクセス制御

#### ユーザー分離

- 各ユーザーは自分のタスクのみアクセス可能
- 管理者は全タスクにアクセス可能

#### 監査ログ

- コンテキストへのアクセスを記録
- 誰がいつどのファイルにアクセスしたか

## 12. まとめ

### 12.1 主要な設計決定

1. **JSONLinesベース**: シンプルで人間が読める、外部ツールで解析容易
2. **UUID管理**: タスクごとに一意のディレクトリ、完全な分離
3. **running/completed分離**: 状態による物理的な分離で管理が容易
4. **LLM要約**: コンテキスト長を賢く管理、情報保持率90%以上
5. **ファイルロック**: マルチプロセス対応、競合を最小化

### 12.2 期待される効果

- **メモリ削減**: 60-99%（要約使用時）
- **永続性**: 中断・再開が可能
- **デバッグ性**: ファイルを直接確認可能
- **スケーラビリティ**: マルチプロセス対応
- **シンプルさ**: 追加の依存なし、運用が容易

### 12.3 実装スケジュール

フルスタック実装のため、以下のフェーズで進める：

1. **Phase 1（2週間）**: MessageStore実装
   - JSONLinesファイルI/O
   - メモリキャッシュ
   - ディレクトリ管理

2. **Phase 2（2週間）**: ContextCompressor実装
   - コンテキスト長監視
   - LLM要約機能
   - 要約の保存と利用

3. **Phase 3（2週間）**: LLMClient統合
   - OpenAIClient改修
   - OllamaClient改修
   - コンテキスト長対応

4. **Phase 4（1週間）**: TaskHandler統合
   - UUID生成とディレクトリ作成
   - 状態管理
   - ディレクトリ移動

5. **Phase 5（2週間）**: マルチプロセス対応
   - ファイルロック実装
   - ハートビート機構
   - 監視とクリーンアップ

6. **Phase 6（2週間）**: 運用ツール
   - コンテキストビューア
   - 統計ツール
   - クリーンアップスクリプト

**合計: 約11週間（3ヶ月弱）**

### 12.4 成功指標

| 指標 | 目標値 | 測定方法 |
|------|--------|---------|
| メモリ削減率 | 80%以上 | プロセス監視 |
| ディスク使用量 | < 5GB/月 | `du`コマンド |
| タスク失敗率 | < 5% | `state.json`集計 |
| 要約成功率 | > 95% | `summaries.jsonl`集計 |
| 平均実行時間増加 | < 10% | タスク完了時間比較 |

---

**ドキュメントバージョン**: 2.0  
**作成日**: 2024-01-15  
**最終更新**: 2024-01-15  
**ステータス**: 詳細設計完了  
**対象システム**: Coding Agent v1.x  
**想定環境**: マルチユーザー・マルチプロセス本番環境
