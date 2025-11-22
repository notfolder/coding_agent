# コンテキストファイル化による省メモリ化仕様

## 1. 概要

### 1.1 目的

コーディングエージェントがコードや仕様を読み込みながら処理を行う際、すべてのコンテキスト（会話履歴、システムプロンプト、ツール実行結果など）をメモリ上に保持すると、大量のメモリを消費します。本仕様では、**JSONLinesファイルベース**でコンテキストを永続化することで省メモリ化を実現し、**1タスク=1プロセス**の前提でシンプルな実装を行います。

### 1.2 設計前提

- **1タスク=1プロセス**: 同一タスクに複数プロセスが同時アクセスしない
  - ファイルロック不要
  - シンプルな実装が可能
- **SQLiteでタスク状態管理**: ルートディレクトリに全タスクの状態をDB化
- **UUID単位のディレクトリ**: 各タスクは独立したディレクトリで管理
- **running/completed分離**: 実行状態による物理的分離

### 1.3 期待される効果

- **メモリ削減**: 60-80%のメモリ使用量削減（要約使用時90%以上）
- **永続性**: プロセス終了後もコンテキストが保持される
- **デバッグ性**: 人間が直接ファイルを確認可能
- **シンプルさ**: ロック不要で実装が容易

## 2. ディレクトリ構造

### 2.1 全体構成

```
logs/contexts/
├── tasks.db                    # 全タスクの状態管理DB（SQLite）
├── running/                    # 実行中タスク
│   └── {uuid}/                 # タスクUUID単位のディレクトリ
│       ├── metadata.json       # タスクメタデータ（静的）
│       ├── messages.jsonl      # メッセージ履歴
│       ├── summaries.jsonl     # コンテキスト要約履歴
│       └── tools.jsonl         # ツール実行履歴
└── completed/                  # 完了済みタスク
    └── {uuid}/                 # 完了したタスク
        └── (running/と同じ構造)
```

### 2.2 tasks.db（SQLite）

#### 目的

- 全タスクの状態を一元管理
- タスク検索・集計を高速化
- 実行中タスクの監視

#### テーブル定義

**tasksテーブル**:
```sql
CREATE TABLE tasks (
    uuid TEXT PRIMARY KEY,              -- タスクUUID
    task_source TEXT NOT NULL,          -- "github" or "gitlab"
    owner TEXT NOT NULL,                -- リポジトリオーナー
    repo TEXT NOT NULL,                 -- リポジトリ名
    task_type TEXT NOT NULL,            -- "issue" or "pull_request"
    task_id TEXT NOT NULL,              -- タスクID（issue番号等）
    status TEXT NOT NULL,               -- "running" or "completed" or "failed"
    created_at TEXT NOT NULL,           -- 作成日時（ISO 8601）
    started_at TEXT,                    -- 開始日時
    completed_at TEXT,                  -- 完了日時
    process_id INTEGER,                 -- プロセスID
    hostname TEXT,                      -- 実行ホスト名
    llm_provider TEXT,                  -- LLMプロバイダー
    model TEXT,                         -- モデル名
    context_length INTEGER,             -- コンテキスト長
    llm_call_count INTEGER DEFAULT 0,   -- LLM呼び出し回数
    tool_call_count INTEGER DEFAULT 0,  -- ツール呼び出し回数
    total_tokens INTEGER DEFAULT 0,     -- 総トークン数
    compression_count INTEGER DEFAULT 0, -- 圧縮回数
    error_message TEXT,                 -- エラーメッセージ（失敗時）
    user TEXT                           -- ユーザー名
);

CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_created_at ON tasks(created_at);
CREATE INDEX idx_tasks_user ON tasks(user);
```

#### 更新タイミング

- タスク開始時: INSERT（status='running'）
- LLM呼び出し後: UPDATE（llm_call_count, total_tokens等）
- ツール実行後: UPDATE（tool_call_count）
- 圧縮実行後: UPDATE（compression_count）
- タスク完了時: UPDATE（status='completed', completed_at）
- エラー発生時: UPDATE（status='failed', error_message）

## 3. ファイル仕様

### 3.1 metadata.json

タスクの基本情報を記録する静的ファイル。タスク開始時に一度だけ作成。

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
    "compression_threshold": 0.7,
    "max_memory_messages": 20
  },
  "user": "notfolder"
}
```

### 3.2 messages.jsonl

メッセージ履歴をJSONLines形式で記録。1行1メッセージ。

#### 形式

```jsonl
{"seq":1,"role":"system","content":"You are an AI...","timestamp":"2024-01-15T10:30:01Z","tokens":250}
{"seq":2,"role":"user","content":"Fix the bug...","timestamp":"2024-01-15T10:30:02Z","tokens":120}
{"seq":3,"role":"assistant","content":"I'll help...","timestamp":"2024-01-15T10:30:15Z","tokens":450}
{"seq":4,"role":"tool","tool_name":"github_get_file","content":"{...}","timestamp":"2024-01-15T10:30:20Z","tokens":1200}
```

#### フィールド

- `seq`: シーケンス番号（1から開始）
- `role`: メッセージの役割（system/user/assistant/tool）
- `content`: メッセージ内容
- `timestamp`: 作成日時（ISO 8601）
- `tokens`: 推定トークン数（4文字=1トークン）
- `tool_name`: ツール名（role="tool"の場合）
- `summarized`: 要約済みフラグ（要約対象となった場合true）

### 3.3 summaries.jsonl

コンテキスト要約の履歴。

#### 形式

```jsonl
{"id":1,"start_seq":10,"end_seq":50,"summary":"Fixed auth bug...","original_tokens":12000,"summary_tokens":800,"ratio":0.067,"timestamp":"2024-01-15T10:32:00Z"}
```

#### フィールド

- `id`: 要約ID（1から開始）
- `start_seq`: 要約対象開始シーケンス
- `end_seq`: 要約対象終了シーケンス
- `summary`: 要約テキスト
- `original_tokens`: 元のトークン数
- `summary_tokens`: 要約後のトークン数
- `ratio`: 圧縮率（summary_tokens/original_tokens）
- `timestamp`: 要約作成日時

### 3.4 tools.jsonl

ツール実行履歴。

#### 形式

```jsonl
{"seq":1,"tool":"github_get_file_contents","args":{"path":"main.py"},"result":"...","status":"success","duration_ms":234,"timestamp":"2024-01-15T10:30:20Z"}
```

#### フィールド

- `seq`: 実行シーケンス番号
- `tool`: ツール名
- `args`: 引数
- `result`: 実行結果（成功時）
- `status`: "success" or "error"
- `error`: エラーメッセージ（失敗時）
- `duration_ms`: 実行時間（ミリ秒）
- `timestamp`: 実行日時

## 4. クラス設計

### 4.1 TaskContextManagerクラス

タスクコンテキスト全体を管理する新規クラス。

#### 責務

- タスク開始時のUUID生成とディレクトリ作成
- tasks.dbへのタスク登録・更新
- MessageStore、SummaryStore、ToolStoreの統合管理
- タスク完了時のディレクトリ移動

#### 主要メソッド

**`__init__(task_key, config)`**
- タスクキーと設定を受け取り初期化
- UUIDを生成
- `running/{uuid}/`ディレクトリを作成
- `metadata.json`を作成
- tasks.dbにタスクを登録（status='running'）
- MessageStore等のサブストアを初期化

**`update_status(status, error_message=None)`**
- tasks.dbのstatusを更新
- error_messageがあればそれも記録

**`update_statistics(llm_calls=0, tool_calls=0, tokens=0, compressions=0)`**
- tasks.dbの統計カウンターを更新
- llm_call_count, tool_call_count等をインクリメント

**`complete()`**
- tasks.dbのstatusを'completed'に更新
- completed_atを記録
- ディレクトリを`running/{uuid}/`から`completed/{uuid}/`へ移動

**`fail(error_message)`**
- tasks.dbのstatusを'failed'に更新
- error_messageを記録
- ディレクトリを`completed/`へ移動

**`get_message_store()`**
- MessageStoreインスタンスを返す

**`get_summary_store()`**
- SummaryStoreインスタンスを返す

**`get_tool_store()`**
- ToolStoreインスタンスを返す

### 4.2 MessageStoreクラス

メッセージ履歴を管理する新規クラス。

#### 責務

- messages.jsonlへの読み書き
- メモリキャッシュ管理（最新N件）
- LLM用メッセージリストの生成
- トークン数の計算と管理

#### 主要メソッド

**`__init__(context_dir, config)`**
- コンテキストディレクトリと設定を受け取り初期化
- messages.jsonlのパスを設定
- メモリキャッシュを初期化（空のリスト）
- 設定から`max_memory_messages`と`context_length`を取得

**`add_message(role, content, tool_name=None)`**
- 新しいメッセージを追加
- シーケンス番号を採番（現在の最大seq + 1）
- トークン数を計算（len(content) // 4）
- messages.jsonlに1行追記
- メモリキャッシュに追加
- キャッシュサイズが`max_memory_messages`を超えたら古いものを削除
- 戻り値: メッセージのシーケンス番号

**`get_messages_for_llm(summary_store)`**
- LLM呼び出し用のメッセージリストを生成
- 処理手順:
  1. システムプロンプト取得（seq=1のメッセージ、必ず含める）
  2. 最新の要約を取得（summary_storeから、あれば1件）
  3. 要約以降の未要約メッセージを取得
  4. トークン数を計算しながら`context_length * 0.7`以内に収める
  5. [システムプロンプト, 要約（あれば）, 未要約メッセージ群]の順でリスト化
- 戻り値: メッセージのリスト（dict形式）

**`load_recent_messages(n)`**
- messages.jsonlから最新n件を読み込み
- メモリキャッシュに格納
- 起動時の初期化で使用

**`mark_as_summarized(start_seq, end_seq)`**
- 指定範囲のメッセージに要約済みフラグをマーク
- 注: JSONLinesは追記型なので実際にはファイル更新しない
- メモリキャッシュ上でのみフラグ管理

**`get_unsummarized_token_count()`**
- 未要約メッセージの総トークン数を計算
- messages.jsonl全体を読み、`summarized`フラグがないメッセージを集計
- 戻り値: トークン数の合計

**`count_messages()`**
- 総メッセージ数を返す
- messages.jsonlの行数をカウント

### 4.3 SummaryStoreクラス

コンテキスト要約を管理する新規クラス。

#### 責務

- summaries.jsonlへの読み書き
- 最新の要約の取得
- 要約の作成と保存

#### 主要メソッド

**`__init__(context_dir)`**
- コンテキストディレクトリを受け取り初期化
- summaries.jsonlのパスを設定

**`add_summary(start_seq, end_seq, summary_text, original_tokens, summary_tokens)`**
- 新しい要約を追加
- IDを採番（現在の最大id + 1）
- 圧縮率を計算（summary_tokens / original_tokens）
- summaries.jsonlに1行追記
- 戻り値: 要約ID

**`get_latest_summary()`**
- 最新の要約を取得
- summaries.jsonlの最終行を読み取り
- 戻り値: 要約のdict、なければNone

**`count_summaries()`**
- 総要約数を返す
- summaries.jsonlの行数をカウント

### 4.4 ToolStoreクラス

ツール実行履歴を管理する新規クラス。

#### 責務

- tools.jsonlへの読み書き
- ツール実行記録の保存

#### 主要メソッド

**`__init__(context_dir)`**
- コンテキストディレクトリを受け取り初期化
- tools.jsonlのパスを設定

**`add_tool_call(tool_name, args, result, status, duration_ms, error=None)`**
- 新しいツール実行を記録
- シーケンス番号を採番
- tools.jsonlに1行追記
- 戻り値: シーケンス番号

**`count_tool_calls()`**
- 総ツール実行数を返す
- tools.jsonlの行数をカウント

### 4.5 ContextCompressorクラス

コンテキスト圧縮を管理する新規クラス。

#### 責務

- コンテキスト長の監視
- 圧縮トリガーの判定
- LLMによる要約の実行

#### 主要メソッド

**`__init__(message_store, summary_store, llm_client, config)`**
- 各ストアとLLMクライアントを受け取り初期化
- 設定から`context_length`と`compression_threshold`を取得
- `min_messages_to_summarize`を設定（デフォルト10）

**`should_compress()`**
- 圧縮が必要か判定
- 判定ロジック:
  1. 未要約メッセージのトークン数を取得
  2. `context_length * compression_threshold`と比較
  3. 超えている場合はTrue
  4. 未要約メッセージ数が`min_messages_to_summarize`未満ならFalse
- 戻り値: bool

**`compress()`**
- コンテキストを圧縮（要約）
- 処理手順:
  1. 最新の要約を取得（summary_storeから）
  2. 要約以降の未要約メッセージを取得（最新5件は除外）
  3. 要約プロンプトを作成
  4. LLMに要約を依頼
  5. 要約結果を取得
  6. summary_storeに保存
  7. message_storeで対象メッセージを要約済みにマーク
- 戻り値: 要約ID

**`create_summary_prompt(messages)`**
- メッセージリストから要約プロンプトを生成
- 形式: "以下の会話履歴を要約してください。\n[USER]: ...\n[ASSISTANT]: ..."
- 戻り値: プロンプト文字列

## 5. 既存クラスの変更

### 5.1 TaskHandlerクラス

#### 変更点

**`__init__`メソッド**
- 変更なし（既存通り）

**`handle(task)`メソッド**
- 処理の最初に`TaskContextManager`を初期化
- 処理の最後に`context_manager.complete()`または`context_manager.fail()`を呼び出す

#### 追加処理

**タスク開始時**:
```
1. task_keyを取得（task.get_task_key()）
2. TaskContextManager初期化
   context_manager = TaskContextManager(task_key, config)
3. UUIDをログに記録
   logger.info(f"Task started: {context_manager.uuid}")
```

**タスク処理中**:
```
- LLM呼び出し前: 変更なし
- LLM呼び出し後: 
  1. message_store.add_message()でメッセージ追加
  2. context_manager.update_statistics()で統計更新
  3. compressor.should_compress()で圧縮判定
  4. 必要なら compressor.compress()実行
  
- ツール実行後:
  1. tool_store.add_tool_call()でツール実行記録
  2. context_manager.update_statistics()で統計更新
```

**タスク完了時**:
```
- 成功時: context_manager.complete()
- 失敗時: context_manager.fail(error_message)
```

### 5.2 LLMClientクラス（OpenAIClient等）

#### 変更点

**`__init__`メソッド**
- `message_store`を引数として受け取る
- 既存の`self.messages`リストを削除
- `self.message_store = message_store`を設定

**`send_system_prompt(prompt)`メソッド**
- `self.messages.append(...)`を削除
- `self.message_store.add_message("system", prompt)`に変更

**`send_user_message(message)`メソッド**
- `self.messages.append(...)`を削除
- `self.message_store.add_message("user", message)`に変更
- 既存のトークン管理ロジック削除（message_storeが管理）

**`send_function_result(name, result)`メソッド**
- `self.messages.append(...)`を削除
- `self.message_store.add_message("tool", json.dumps(result), tool_name=name)`に変更

**`get_response()`メソッド**
- `messages = self.messages`を削除
- `messages = self.message_store.get_messages_for_llm(summary_store)`に変更
  - summary_storeは引数として渡す必要がある
- LLM呼び出し後、応答をmessage_storeに追加:
  `self.message_store.add_message("assistant", reply_content)`

#### 追加引数

- `summary_store`を`get_response()`の引数に追加
  - または、`__init__`で受け取ってインスタンス変数として保持

### 5.3 TaskGetterクラス（TaskGetterFromGitHub等）

#### 変更点

なし（タスク取得のロジックは変更不要）

## 6. 処理フロー

### 6.1 タスク開始フロー

```
1. キューからタスク取得
   task = task_queue.get()

2. TaskHandler.handle(task)呼び出し
   
3. TaskHandler内:
   a. task_key = task.get_task_key()
   b. context_manager = TaskContextManager(task_key, config)
      - UUID生成
      - running/{uuid}/ディレクトリ作成
      - metadata.json作成
      - tasks.dbにINSERT（status='running'）
      - MessageStore, SummaryStore, ToolStore初期化
   
   c. message_store = context_manager.get_message_store()
      summary_store = context_manager.get_summary_store()
      tool_store = context_manager.get_tool_store()
   
   d. llm_client初期化（message_storeを渡す）
   
   e. compressor = ContextCompressor(message_store, summary_store, llm_client, config)
```

### 6.2 LLM呼び出しフロー

```
1. llm_client.send_system_prompt(system_prompt)
   → message_store.add_message("system", system_prompt)
   
2. llm_client.send_user_message(user_prompt)
   → message_store.add_message("user", user_prompt)
   
3. llm_client.get_response(summary_store)
   a. messages = message_store.get_messages_for_llm(summary_store)
      - システムプロンプト取得
      - 最新要約取得（あれば）
      - 未要約メッセージ取得
      - トークン数調整
   
   b. LLM API呼び出し
      response = openai.chat.completions.create(messages=messages, ...)
   
   c. 応答をmessage_storeに追加
      message_store.add_message("assistant", response_content)
   
   d. 統計更新
      context_manager.update_statistics(llm_calls=1, tokens=used_tokens)
   
4. 圧縮判定
   if compressor.should_compress():
       compressor.compress()
       context_manager.update_statistics(compressions=1)
```

### 6.3 ツール実行フロー

```
1. ツール実行
   start_time = time.time()
   result = mcp_client.call_tool(tool_name, args)
   duration_ms = (time.time() - start_time) * 1000
   
2. 実行記録
   tool_store.add_tool_call(
       tool_name=tool_name,
       args=args,
       result=result,
       status="success",
       duration_ms=duration_ms
   )
   
3. 統計更新
   context_manager.update_statistics(tool_calls=1)
   
4. 結果をLLMに送信
   llm_client.send_function_result(tool_name, result)
   → message_store.add_message("tool", json.dumps(result), tool_name=tool_name)
```

### 6.4 タスク完了フロー

```
1. 正常完了時:
   a. context_manager.complete()
      - tasks.db UPDATE（status='completed', completed_at=now）
      - ディレクトリ移動: running/{uuid}/ → completed/{uuid}/
   
2. エラー時:
   a. context_manager.fail(error_message)
      - tasks.db UPDATE（status='failed', error_message=msg）
      - ディレクトリ移動: running/{uuid}/ → completed/{uuid}/
```

## 7. コンテキスト圧縮の詳細

### 7.1 圧縮トリガー条件

以下の全てを満たす場合に圧縮を実行:

1. 未要約メッセージのトークン数 > `context_length * compression_threshold`
2. 未要約メッセージ数 >= `min_messages_to_summarize`（デフォルト10）

### 7.2 圧縮対象の選択

- 最新の要約以降のメッセージ
- ただし直近5件は除外（要約対象外として残す）
- システムプロンプト（seq=1）は除外

### 7.3 要約プロンプト

```
あなたは会話履歴を要約するアシスタントです。
以下のメッセージ履歴を簡潔かつ包括的に要約してください。

要約には以下を含めてください：
1. 重要な決定事項
2. 実施したコード変更
3. 発生した問題とその解決
4. 残存タスク

元の30-40%の長さを目標としてください。

=== 要約対象メッセージ ===
[USER]: Fix the authentication bug
[ASSISTANT]: I'll help you fix the bug...
[TOOL]: github_get_file_contents -> (file content)
...

要約のみを出力してください。
```

### 7.4 圧縮後の処理

1. 要約テキストを取得
2. トークン数を計算
3. summary_storeに保存
4. 対象メッセージを要約済みとしてマーク
5. 次回のLLM呼び出し時、要約がコンテキストに含まれる

## 8. tasks.dbの運用

### 8.1 初期化

アプリケーション起動時、`logs/contexts/tasks.db`が存在しない場合:

1. SQLiteデータベースを作成
2. tasksテーブルを作成
3. インデックスを作成

### 8.2 クエリ例

**実行中タスクの一覧**:
```sql
SELECT uuid, task_source, owner, repo, task_type, task_id, started_at
FROM tasks
WHERE status = 'running'
ORDER BY started_at DESC;
```

**ユーザーごとのタスク数**:
```sql
SELECT user, status, COUNT(*) as count
FROM tasks
GROUP BY user, status;
```

**失敗タスクの検索**:
```sql
SELECT uuid, error_message, created_at
FROM tasks
WHERE status = 'failed'
ORDER BY created_at DESC
LIMIT 10;
```

### 8.3 クリーンアップ

30日以上前の完了タスクを削除:

```sql
DELETE FROM tasks
WHERE status = 'completed'
  AND completed_at < datetime('now', '-30 days');
```

対応するディレクトリも削除が必要。

## 9. 設定ファイル

### 9.1 config.yaml への追加

```yaml
# コンテキストストレージ設定
context_storage:
  enabled: true                    # コンテキストファイル化を有効化
  base_dir: "logs/contexts"        # ベースディレクトリ
  max_memory_messages: 20          # メモリキャッシュサイズ
  compression_threshold: 0.7       # 圧縮開始閾値（70%）
  min_messages_to_summarize: 10    # 要約に必要な最小メッセージ数

# LLM設定（既存）にcontext_lengthを追加
llm:
  provider: "openai"
  openai:
    model: "gpt-4o"
    context_length: 128000         # モデルのコンテキスト長
    api_key: "${OPENAI_API_KEY}"
  ollama:
    model: "qwen3-30b"
    context_length: 32768          # モデルのコンテキスト長
```

### 9.2 環境変数

```bash
# 既存の環境変数に加えて
CONTEXT_STORAGE_ENABLED=true
CONTEXT_STORAGE_MAX_MEMORY=20
COMPRESSION_THRESHOLD=0.7
```

## 10. デバッグとモニタリング

### 10.1 タスク状態確認

**SQLiteクエリ**:
```bash
sqlite3 logs/contexts/tasks.db "SELECT * FROM tasks WHERE uuid='...'"
```

**ファイル確認**:
```bash
# メッセージ履歴
cat logs/contexts/running/{uuid}/messages.jsonl | jq

# 最新10件
tail -10 logs/contexts/running/{uuid}/messages.jsonl | jq

# 要約履歴
cat logs/contexts/running/{uuid}/summaries.jsonl | jq
```

### 10.2 統計情報

**タスク数**:
```sql
SELECT status, COUNT(*) FROM tasks GROUP BY status;
```

**平均実行時間**:
```sql
SELECT AVG(julianday(completed_at) - julianday(started_at)) * 24 * 60 as avg_minutes
FROM tasks
WHERE status = 'completed';
```

**トークン使用量**:
```sql
SELECT SUM(total_tokens) as total, AVG(total_tokens) as average
FROM tasks
WHERE status = 'completed';
```

## 11. エラーハンドリング

### 11.1 タスク処理中のエラー

```
try:
    context_manager = TaskContextManager(task_key, config)
    # タスク処理...
    context_manager.complete()
except Exception as e:
    logger.exception("Task processing failed")
    context_manager.fail(str(e))
    raise
```

### 11.2 ファイルI/Oエラー

- ディレクトリ作成失敗: 例外を上位に伝播
- JSONLines書き込み失敗: 例外を上位に伝播
- 読み込み失敗: 空のリストを返す、またはデフォルト値

### 11.3 SQLiteエラー

- 接続失敗: 例外を上位に伝播
- INSERT/UPDATE失敗: リトライ（最大3回）
- テーブル不存在: 自動作成

## 12. 実装の優先順位

### フェーズ1: 基本機能（2週間）

1. TaskContextManagerクラス
2. MessageStoreクラス
3. tasks.dbの作成と基本操作
4. TaskHandlerの統合

### フェーズ2: 要約機能（2週間）

1. SummaryStoreクラス
2. ContextCompressorクラス
3. 要約トリガーとLLM呼び出し

### フェーズ3: 完全統合（1週間）

1. ToolStoreクラス
2. LLMClient統合
3. 全体的なテスト

### フェーズ4: 運用機能（1週間）

1. デバッグツール
2. クリーンアップスクリプト
3. モニタリング機能

合計: 6週間

## 13. まとめ

### 主要な設計決定

1. **1タスク=1プロセス**: ロック不要でシンプル
2. **SQLiteで状態管理**: 全タスクを一元管理
3. **UUID単位のディレクトリ**: 完全な分離
4. **JSONLines**: 人間が読める、追記型で高速
5. **running/completed分離**: 状態による物理的分離

### 実装のポイント

- 既存コードへの影響を最小化
- シンプルで理解しやすい実装
- デバッグとモニタリングが容易
- 拡張性を考慮（将来の改善に対応可能）

---

**ドキュメントバージョン**: 3.0  
**最終更新**: 2024-01-15  
**ステータス**: 実装準備完了  
**対象**: 1タスク=1プロセス環境
