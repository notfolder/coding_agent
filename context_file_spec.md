# コンテキストファイル化による省メモリ化仕様

## 1. 概要

### 1.1 目的
コーディングエージェントがコードや仕様を読み込みながら処理を行う際、すべてのコンテキスト（会話履歴、システムプロンプト、ツール実行結果など）をメモリ上に保持すると、大量のメモリを消費する問題があります。本仕様では、コンテキストをファイルまたはデータベースに保存することで省メモリ化を実現し、マルチユーザー・マルチプロセス環境での安全な動作と、コンテキスト長管理を実現する方法を定義します。

### 1.2 背景
現在の実装では以下の問題があります：

- **メモリ使用量の増大**: LLMクライアントが会話履歴全体を`messages`リストとしてメモリに保持
- **スケーラビリティの欠如**: 長時間実行や複数タスク同時処理時にメモリ不足のリスク
- **永続性の欠如**: プロセス終了時にコンテキストが失われる
- **デバッグの困難さ**: メモリ上のデータのため、処理過程の追跡が困難
- **マルチプロセス非対応**: 複数プロセスが同時にキューからタスクを取得する際の競合管理が未実装
- **コンテキスト長の管理不足**: 単純な古いメッセージ削除のみで、重要な情報が失われる可能性

### 1.3 期待される効果

- メモリ使用量の大幅削減（推定: 60-80%削減）
- 長時間実行タスクの安定性向上
- 処理の中断・再開機能の実現
- デバッグ・監査機能の向上
- マルチプロセス環境での安全な並行処理
- インテリジェントなコンテキスト長管理による情報保持の最適化

## 2. 現状分析

### 2.1 メモリ使用状況

#### 2.1.1 OpenAIClient
```python
class OpenAIClient(LLMClient):
    def __init__(self, config, functions=None, tools=None):
        self.messages = []  # 全会話履歴をメモリに保持
        self.max_token = config.get("max_token", 40960)
```

**問題点**:
- `messages`リストが無制限に成長
- トークン制限を超えると古いメッセージを削除（`pop(1)`）
- 削除されたメッセージは完全に失われる

#### 2.1.2 OllamaClient
```python
class OllamaClient(LLMClient):
    def __init__(self, config):
        self.messages = []  # 同様にメモリ上に保持
        self.max_token = config.get("max_token", 32768)
```

**問題点**:
- OpenAIClientと同じ問題
- 4文字=1トークンの簡易計算による不正確なメモリ管理

#### 2.1.3 LMStudioClient
```python
class LMStudioClient(LLMClient):
    def __init__(self, config):
        self.chat = lms.Chat()  # lmstudioライブラリがメモリ管理
```

**問題点**:
- 内部でどのようにメモリ管理されているか不透明
- ファイル化の制御が困難

### 2.2 メモリ消費の実測

**想定シナリオ**: 100回のLLM呼び出しを含むタスク処理

| コンポーネント | メモリ使用量（推定） | 備考 |
|---------------|---------------------|------|
| システムプロンプト | ~10KB | 固定 |
| ユーザープロンプト | ~5KB/回 | タスク内容による |
| アシスタント応答 | ~20KB/回 | LLM応答長による |
| ツール実行結果 | ~50KB/回 | ファイル内容取得時は数MB |
| **合計（100回）** | **~8.5MB** | ツール結果を含む |

**問題**: 
- 長時間処理や複数タスクで数十MB〜数百MBに達する可能性
- メモリリークのリスク

## 3. 設計方針

### 3.1 基本アーキテクチャ（マルチプロセス対応版）

```
┌─────────────────────────────────────────────────────────────┐
│  プロセス1              プロセス2              プロセスN     │
│  TaskHandler           TaskHandler           TaskHandler    │
│     │                     │                      │           │
│     └─────────────────────┴──────────────────────┘           │
│                          ↓                                   │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  MessageStore (新規)                                   │ │
│  │  ┌──────────────────┐  ┌──────────────────────────┐   │ │
│  │  │ メモリキャッシュ │  │ SQLite DB (推奨)         │   │ │
│  │  │ (プロセスローカル)│  │ - メッセージ履歴         │   │ │
│  │  │ - 最新N件        │  │ - ツール実行履歴         │   │ │
│  │  │ - 読み取り専用   │  │ - コンテキスト要約       │   │ │
│  │  └──────────────────┘  │ - ロック管理             │   │ │
│  │                        │ - トランザクション制御   │   │ │
│  │                        └──────────────────────────┘   │ │
│  └────────────────────────────────────────────────────────┘ │
│                          ↓                                   │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  ContextCompressor (新規)                             │ │
│  │  - LLMによる自動要約                                   │ │
│  │  - コンテキスト長監視                                  │ │
│  │  - 重要度ベースの選択                                  │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 ストレージ選択: SQLite vs ファイル

#### 推奨: SQLite（マルチプロセス対応）

**選択理由**:
1. **シンプルさ**: サーバー不要、ファイルベースで管理が簡単
2. **マルチプロセス対応**: WALモードで複数プロセスからの同時アクセスが可能
3. **トランザクション**: ACID特性によるデータ整合性保証
4. **クエリ機能**: SQLによる柔軟な検索・集計
5. **標準ライブラリ**: Python標準ライブラリで追加依存なし

**JSONLinesファイル方式の問題点**:
- ファイルロックの複雑性（マルチプロセスで競合）
- 部分読み込みの非効率性
- インデックスなしでの検索の遅さ

#### 代替案: JSONLinesファイル（シングルプロセス環境のみ）

**利用ケース**: 
- 開発・デバッグ時
- シングルプロセス実行時
- 外部ツールでの解析を重視する場合

### 3.3 階層化ストレージ戦略

#### レイヤー1: ホットキャッシュ（メモリ）
- **保持対象**: システムプロンプト + 最新N件のメッセージ + 要約
- **目的**: LLM呼び出し時の高速アクセス
- **サイズ**: コンテキスト長の70%まで
- **スコープ**: プロセスローカル（各プロセスが独自にキャッシュ）

#### レイヤー2: 永続ストレージ（SQLite）
- **保持対象**: 全メッセージ履歴、ツール実行履歴、コンテキスト要約
- **目的**: 永続化、デバッグ、再読み込み、マルチプロセス共有
- **形式**: SQLiteデータベース（WALモード）
- **スコープ**: タスク単位（各タスクが専用DBファイルを持つ）

#### レイヤー3: コンテキスト要約（LLM生成）
- **保持対象**: 過去のメッセージの要約
- **目的**: コンテキスト長削減と情報保持の両立
- **形式**: 要約テキスト + メタデータ
- **トリガー**: コンテキスト長が閾値（70-80%）に達したとき

### 3.4 データベース構造（SQLite）

```
logs/
└── contexts/
    └── {task_source}/
        └── {owner}/
            └── {repo}/
                └── {task_type}_{task_id}/
                    ├── context.db           # SQLiteデータベース（メイン）
                    ├── context.db-wal       # Write-Ahead Log（自動生成）
                    └── context.db-shm       # Shared Memory（自動生成）
```

#### データベーススキーマ

```sql
-- メタデータテーブル
CREATE TABLE metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- メッセージテーブル
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL,              -- system/user/assistant/tool
    content TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    token_count INTEGER,             -- 推定トークン数
    is_summarized BOOLEAN DEFAULT 0, -- 要約済みフラグ
    summary_id INTEGER,              -- 要約先のID
    metadata TEXT,                   -- JSON形式のメタデータ
    FOREIGN KEY (summary_id) REFERENCES summaries(id)
);
CREATE INDEX idx_messages_timestamp ON messages(timestamp);
CREATE INDEX idx_messages_role ON messages(role);
CREATE INDEX idx_messages_summarized ON messages(is_summarized);

-- コンテキスト要約テーブル
CREATE TABLE summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_message_id INTEGER NOT NULL,  -- 要約開始メッセージID
    end_message_id INTEGER NOT NULL,    -- 要約終了メッセージID
    summary_content TEXT NOT NULL,      -- 要約内容
    token_count INTEGER,                -- 要約のトークン数
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (start_message_id) REFERENCES messages(id),
    FOREIGN KEY (end_message_id) REFERENCES messages(id)
);
CREATE INDEX idx_summaries_created ON summaries(created_at);

-- ツール実行履歴テーブル
CREATE TABLE tool_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL,     -- 関連するメッセージID
    tool_name TEXT NOT NULL,
    arguments TEXT NOT NULL,         -- JSON形式
    result TEXT,                     -- JSON形式
    duration_ms INTEGER,
    status TEXT,                     -- success/error
    error_message TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (message_id) REFERENCES messages(id)
);
CREATE INDEX idx_tool_calls_timestamp ON tool_calls(timestamp);
CREATE INDEX idx_tool_calls_status ON tool_calls(status);

-- プロセスロックテーブル（マルチプロセス制御用）
CREATE TABLE process_locks (
    process_id TEXT PRIMARY KEY,     -- プロセスID
    hostname TEXT NOT NULL,          -- ホスト名
    acquired_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    heartbeat_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 4. 詳細設計

### 4.1 MessageStoreクラス（SQLite版）

```python
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional
import json
import threading

class MessageStore:
    """SQLiteベースのメッセージストレージ（マルチプロセス対応）"""
    
    def __init__(
        self,
        context_dir: Path,
        max_memory_messages: int = 20,
        context_length: int = 128000,  # モデルのコンテキスト長
        compression_threshold: float = 0.7,  # 圧縮開始閾値（70%）
    ):
        """
        Args:
            context_dir: コンテキスト保存ディレクトリ
            max_memory_messages: メモリに保持する最大メッセージ数
            context_length: モデルのコンテキスト長（トークン数）
            compression_threshold: コンテキスト圧縮を開始する閾値（0.0-1.0）
        """
        self.context_dir = context_dir
        self.max_memory_messages = max_memory_messages
        self.context_length = context_length
        self.compression_threshold = compression_threshold
        
        self.db_path = context_dir / "context.db"
        self.memory_cache = []  # ホットキャッシュ
        self._cache_lock = threading.Lock()  # キャッシュのスレッド安全性
        
        self._init_database()
        self._load_cache()
    
    def _init_database(self) -> None:
        """データベースを初期化"""
        # WALモードで開く（マルチプロセス対応）
        conn = self._get_connection()
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")  # パフォーマンス向上
        
        # スキーマ作成
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                token_count INTEGER,
                is_summarized BOOLEAN DEFAULT 0,
                summary_id INTEGER,
                metadata TEXT,
                FOREIGN KEY (summary_id) REFERENCES summaries(id)
            );
            CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);
            CREATE INDEX IF NOT EXISTS idx_messages_role ON messages(role);
            CREATE INDEX IF NOT EXISTS idx_messages_summarized ON messages(is_summarized);
            
            CREATE TABLE IF NOT EXISTS summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_message_id INTEGER NOT NULL,
                end_message_id INTEGER NOT NULL,
                summary_content TEXT NOT NULL,
                token_count INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (start_message_id) REFERENCES messages(id),
                FOREIGN KEY (end_message_id) REFERENCES messages(id)
            );
            CREATE INDEX IF NOT EXISTS idx_summaries_created ON summaries(created_at);
            
            CREATE TABLE IF NOT EXISTS tool_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL,
                tool_name TEXT NOT NULL,
                arguments TEXT NOT NULL,
                result TEXT,
                duration_ms INTEGER,
                status TEXT,
                error_message TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (message_id) REFERENCES messages(id)
            );
            CREATE INDEX IF NOT EXISTS idx_tool_calls_timestamp ON tool_calls(timestamp);
            CREATE INDEX IF NOT EXISTS idx_tool_calls_status ON tool_calls(status);
        """)
        
        # メタデータ初期化
        conn.execute(
            "INSERT OR IGNORE INTO metadata (key, value) VALUES (?, ?)",
            ("context_length", str(self.context_length))
        )
        conn.execute(
            "INSERT OR IGNORE INTO metadata (key, value) VALUES (?, ?)",
            ("created_at", datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
    
    def _get_connection(self) -> sqlite3.Connection:
        """SQLite接続を取得"""
        conn = sqlite3.connect(
            self.db_path,
            timeout=30.0,  # マルチプロセス時のロック待ち時間
            check_same_thread=False
        )
        conn.row_factory = sqlite3.Row  # カラム名でアクセス可能に
        return conn
    
    def add_message(
        self,
        role: str,
        content: str,
        tool_call: Optional[dict] = None,
        **metadata
    ) -> int:
        """メッセージを追加（DB + メモリキャッシュ）
        
        Returns:
            メッセージID
        """
        token_count = self._estimate_tokens(content)
        
        conn = self._get_connection()
        try:
            # DBに保存
            cursor = conn.execute(
                """INSERT INTO messages (role, content, token_count, metadata)
                   VALUES (?, ?, ?, ?)""",
                (role, content, token_count, json.dumps(metadata))
            )
            message_id = cursor.lastrowid
            conn.commit()
            
            # ツール呼び出し情報も保存
            if tool_call:
                conn.execute(
                    """INSERT INTO tool_calls 
                       (message_id, tool_name, arguments, result, duration_ms, status)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        message_id,
                        tool_call.get("tool_name"),
                        json.dumps(tool_call.get("arguments", {})),
                        json.dumps(tool_call.get("result")),
                        tool_call.get("duration_ms"),
                        tool_call.get("status", "success")
                    )
                )
                conn.commit()
            
            # メモリキャッシュに追加
            with self._cache_lock:
                message = {
                    "id": message_id,
                    "role": role,
                    "content": content,
                    "token_count": token_count,
                    "timestamp": datetime.now().isoformat(),
                    **metadata
                }
                self.memory_cache.append(message)
                
                # キャッシュサイズ管理
                while len(self.memory_cache) > self.max_memory_messages:
                    self.memory_cache.pop(0)
            
            # コンテキスト長チェック
            if self._should_compress():
                self._compress_context()
            
            return message_id
        finally:
            conn.close()
    
    def _estimate_tokens(self, text: str) -> int:
        """トークン数を推定（簡易版：4文字=1トークン）"""
        return len(text) // 4
    
    def _load_cache(self) -> None:
        """DBから最新メッセージをキャッシュに読み込み"""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """SELECT id, role, content, token_count, timestamp, metadata
                   FROM messages
                   ORDER BY id DESC
                   LIMIT ?""",
                (self.max_memory_messages,)
            )
            
            with self._cache_lock:
                self.memory_cache = []
                for row in reversed(list(cursor)):
                    self.memory_cache.append({
                        "id": row["id"],
                        "role": row["role"],
                        "content": row["content"],
                        "token_count": row["token_count"],
                        "timestamp": row["timestamp"],
                        **(json.loads(row["metadata"]) if row["metadata"] else {})
                    })
        finally:
            conn.close()
    
    def get_messages_for_llm(self) -> list[dict]:
        """LLM呼び出し用のメッセージリストを取得
        
        コンテキスト長を考慮して、システムプロンプト、要約、
        最新メッセージを組み合わせて返す
        """
        conn = self._get_connection()
        try:
            messages = []
            total_tokens = 0
            max_tokens = int(self.context_length * self.compression_threshold)
            
            # 1. システムプロンプトを追加（常に含める）
            cursor = conn.execute(
                "SELECT * FROM messages WHERE role = 'system' ORDER BY id LIMIT 1"
            )
            system_msg = cursor.fetchone()
            if system_msg:
                messages.append({
                    "role": system_msg["role"],
                    "content": system_msg["content"]
                })
                total_tokens += system_msg["token_count"] or 0
            
            # 2. 最新の要約を追加（あれば）
            cursor = conn.execute(
                "SELECT * FROM summaries ORDER BY id DESC LIMIT 1"
            )
            summary = cursor.fetchone()
            if summary:
                messages.append({
                    "role": "system",
                    "content": f"[Previous conversation summary]\n{summary['summary_content']}"
                })
                total_tokens += summary["token_count"] or 0
            
            # 3. 要約されていない最新メッセージを追加
            # 要約がある場合は、要約の終了メッセージID以降を取得
            start_id = summary["end_message_id"] + 1 if summary else 0
            
            cursor = conn.execute(
                """SELECT * FROM messages
                   WHERE id > ? AND role != 'system' AND is_summarized = 0
                   ORDER BY id DESC""",
                (start_id,)
            )
            
            recent_messages = []
            for row in cursor:
                msg_tokens = row["token_count"] or 0
                if total_tokens + msg_tokens > max_tokens:
                    break
                recent_messages.append({
                    "role": row["role"],
                    "content": row["content"]
                })
                total_tokens += msg_tokens
            
            # 新しい順に追加したので、逆順にして時系列順に
            messages.extend(reversed(recent_messages))
            
            return messages
        finally:
            conn.close()
    
    def _should_compress(self) -> bool:
        """コンテキスト圧縮が必要かチェック"""
        conn = self._get_connection()
        try:
            # 要約されていないメッセージの総トークン数を計算
            cursor = conn.execute(
                """SELECT SUM(token_count) as total
                   FROM messages
                   WHERE is_summarized = 0"""
            )
            row = cursor.fetchone()
            total_tokens = row["total"] or 0
            
            threshold = self.context_length * self.compression_threshold
            return total_tokens > threshold
        finally:
            conn.close()
    
    def _compress_context(self) -> None:
        """コンテキストを圧縮（LLMに要約させる）
        
        Note: 実際のLLM呼び出しは外部から注入される必要がある
        ここではプレースホルダーとして、圧縮が必要であることを記録
        """
        # このメソッドは外部からコールバック経由で呼ばれる想定
        # 詳細は ContextCompressor クラスを参照
        pass
    
    def create_summary(
        self,
        start_message_id: int,
        end_message_id: int,
        summary_content: str
    ) -> int:
        """要約を作成し、元のメッセージに要約済みフラグを立てる"""
        token_count = self._estimate_tokens(summary_content)
        
        conn = self._get_connection()
        try:
            # 要約を保存
            cursor = conn.execute(
                """INSERT INTO summaries 
                   (start_message_id, end_message_id, summary_content, token_count)
                   VALUES (?, ?, ?, ?)""",
                (start_message_id, end_message_id, summary_content, token_count)
            )
            summary_id = cursor.lastrowid
            
            # 元のメッセージに要約済みフラグを立てる
            conn.execute(
                """UPDATE messages
                   SET is_summarized = 1, summary_id = ?
                   WHERE id BETWEEN ? AND ?""",
                (summary_id, start_message_id, end_message_id)
            )
            conn.commit()
            
            return summary_id
        finally:
            conn.close()
    
    def get_statistics(self) -> dict:
        """統計情報を取得"""
        conn = self._get_connection()
        try:
            stats = {}
            
            # メッセージ統計
            cursor = conn.execute(
                """SELECT 
                   COUNT(*) as total_messages,
                   SUM(token_count) as total_tokens,
                   SUM(CASE WHEN is_summarized = 1 THEN 1 ELSE 0 END) as summarized_messages
                   FROM messages"""
            )
            row = cursor.fetchone()
            stats.update({
                "total_messages": row["total_messages"],
                "total_tokens": row["total_tokens"] or 0,
                "summarized_messages": row["summarized_messages"],
                "memory_messages": len(self.memory_cache)
            })
            
            # 要約統計
            cursor = conn.execute("SELECT COUNT(*) as count FROM summaries")
            stats["summaries_count"] = cursor.fetchone()["count"]
            
            # ツール呼び出し統計
            cursor = conn.execute(
                """SELECT COUNT(*) as total, 
                   SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success
                   FROM tool_calls"""
            )
            row = cursor.fetchone()
            stats.update({
                "tool_calls_total": row["total"],
                "tool_calls_success": row["success"] or 0
            })
            
            # DB ファイルサイズ
            if self.db_path.exists():
                stats["db_size_bytes"] = self.db_path.stat().st_size
                stats["db_size_mb"] = stats["db_size_bytes"] / (1024 * 1024)
            
            return stats
        finally:
            conn.close()
```

### 4.2 ContextCompressorクラス（LLMによる自動要約）

```python
from typing import Protocol

class LLMClientProtocol(Protocol):
    """LLMクライアントのプロトコル定義"""
    def send_system_prompt(self, prompt: str) -> None: ...
    def send_user_message(self, message: str) -> None: ...
    def get_response(self) -> tuple[str, list]: ...

class ContextCompressor:
    """コンテキスト圧縮（LLMによる要約）"""
    
    # 要約用のシステムプロンプト
    SUMMARIZATION_PROMPT = """You are a helpful assistant that summarizes conversation history.
Your task is to create a concise but comprehensive summary of the provided messages.
The summary should:
1. Preserve all important information, decisions, and code changes
2. Maintain the chronological order of events
3. Be significantly shorter than the original (target: 30-40% of original length)
4. Use clear, structured format with bullet points

Output ONLY the summary text, no additional commentary."""
    
    def __init__(
        self,
        message_store: MessageStore,
        llm_client: LLMClientProtocol,
        min_messages_to_summarize: int = 10,
    ):
        """
        Args:
            message_store: メッセージストア
            llm_client: LLMクライアント
            min_messages_to_summarize: 要約に必要な最小メッセージ数
        """
        self.message_store = message_store
        self.llm_client = llm_client
        self.min_messages_to_summarize = min_messages_to_summarize
    
    def compress_if_needed(self) -> bool:
        """必要に応じてコンテキストを圧縮
        
        Returns:
            圧縮を実行した場合True
        """
        if not self.message_store._should_compress():
            return False
        
        # 圧縮実行
        return self.compress_context()
    
    def compress_context(self) -> bool:
        """コンテキストを圧縮（要約）
        
        Returns:
            圧縮成功でTrue
        """
        conn = self.message_store._get_connection()
        try:
            # 要約対象のメッセージを取得
            # 最新の要約以降で、まだ要約されていないメッセージ
            cursor = conn.execute(
                """SELECT MAX(end_message_id) as last_summarized
                   FROM summaries"""
            )
            row = cursor.fetchone()
            start_id = (row["last_summarized"] or 0) + 1
            
            # 要約対象メッセージ取得（システムプロンプト以外）
            cursor = conn.execute(
                """SELECT id, role, content, token_count
                   FROM messages
                   WHERE id >= ? AND role != 'system' AND is_summarized = 0
                   ORDER BY id""",
                (start_id,)
            )
            
            messages_to_summarize = list(cursor)
            
            # 最小件数チェック
            if len(messages_to_summarize) < self.min_messages_to_summarize:
                return False
            
            # 最新の数件は残す（例：5件）
            keep_recent = 5
            if len(messages_to_summarize) <= keep_recent:
                return False
            
            # 要約対象から最新メッセージを除外
            messages_to_summarize = messages_to_summarize[:-keep_recent]
            
            # 要約用テキスト作成
            conversation_text = self._format_messages_for_summary(messages_to_summarize)
            
            # LLMで要約
            summary = self._generate_summary(conversation_text)
            
            # 要約を保存
            start_message_id = messages_to_summarize[0]["id"]
            end_message_id = messages_to_summarize[-1]["id"]
            
            self.message_store.create_summary(
                start_message_id=start_message_id,
                end_message_id=end_message_id,
                summary_content=summary
            )
            
            return True
            
        except Exception as e:
            # 要約失敗時はログを記録して続行
            import logging
            logger = logging.getLogger(__name__)
            logger.exception("コンテキスト要約に失敗しました: %s", e)
            return False
        finally:
            conn.close()
    
    def _format_messages_for_summary(self, messages: list) -> str:
        """メッセージリストを要約用テキストにフォーマット"""
        lines = ["=== Conversation to Summarize ===\n"]
        for msg in messages:
            role = msg["role"].upper()
            content = msg["content"][:2000]  # 長すぎる場合は切り詰め
            lines.append(f"[{role}]: {content}\n")
        return "\n".join(lines)
    
    def _generate_summary(self, conversation_text: str) -> str:
        """LLMで要約を生成"""
        # 新しいLLMセッションで要約を生成
        # 既存のコンテキストと混ざらないように
        self.llm_client.send_system_prompt(self.SUMMARIZATION_PROMPT)
        self.llm_client.send_user_message(conversation_text)
        
        response, _ = self.llm_client.get_response()
        return response.strip()
```

### 4.3 LLMClientの改修

#### 4.3.1 OpenAIClient改修例（コンテキスト長対応）

```python
class OpenAIClient(LLMClient):
    def __init__(
        self,
        config: dict,
        functions: list | None = None,
        tools: list | None = None,
        context_dir: Path | None = None
    ):
        # 既存の初期化
        self.openai = openai.OpenAI(...)
        self.model = config["model"]
        
        # コンテキスト長を設定から取得
        self.context_length = config.get("context_length", 128000)
        self.max_token = config.get("max_token", self.context_length)
        
        # MessageStoreの初期化
        if context_dir:
            self.message_store = MessageStore(
                context_dir=context_dir,
                max_memory_messages=config.get("max_memory_messages", 20),
                context_length=self.context_length,
                compression_threshold=config.get("compression_threshold", 0.7)
            )
            # ContextCompressorの初期化
            self.compressor = ContextCompressor(
                message_store=self.message_store,
                llm_client=self,  # 自分自身を渡す
                min_messages_to_summarize=config.get("min_messages_to_summarize", 10)
            )
            self.use_file_storage = True
        else:
            # 後方互換性のため、従来のメモリ方式もサポート
            self.messages = []
            self.use_file_storage = False
    
    def send_system_prompt(self, prompt: str) -> None:
        if self.use_file_storage:
            self.message_store.add_message("system", prompt)
        else:
            self.messages.append({"role": "system", "content": prompt})
    
    def send_user_message(self, message: str) -> None:
        if self.use_file_storage:
            self.message_store.add_message("user", message)
            # コンテキスト圧縮チェック
            self.compressor.compress_if_needed()
        else:
            self.messages.append({"role": "user", "content": message})
            # 従来のトークン管理
            total_chars = sum(len(m["content"]) for m in self.messages)
            while total_chars // 4 > self.max_token:
                self.messages.pop(1)
    
    def send_function_result(self, name: str, result: object) -> None:
        """関数実行結果を送信"""
        if self.use_file_storage:
            self.message_store.add_message(
                role="tool",
                content=json.dumps(result),
                tool_call={"tool_name": name, "result": result}
            )
            # コンテキスト圧縮チェック
            self.compressor.compress_if_needed()
        else:
            self.messages.append({
                "role": "tool",
                "name": name,
                "content": json.dumps(result)
            })
    
    def get_response(self) -> tuple[str, list]:
        # メッセージ取得
        if self.use_file_storage:
            messages = self.message_store.get_messages_for_llm()
        else:
            messages = self.messages
        
        # LLM呼び出し
        resp = self.openai.chat.completions.create(
            model=self.model,
            messages=messages,
            functions=self.functions,
            function_call="auto",
        )
        
        # 応答を保存
        for choice in resp.choices:
            content = choice.message.content or ""
            if self.use_file_storage:
                self.message_store.add_message(
                    role=choice.message.role,
                    content=content,
                    function_call=choice.message.function_call
                )
            else:
                self.messages.append({
                    "role": choice.message.role,
                    "content": content
                })
        
        # 応答を返す
        reply = ""
        functions = []
        for choice in resp.choices:
            reply += choice.message.content or ""
            if choice.message.function_call:
                functions.append(choice.message.function_call)
        
        return reply, functions
```

### 4.4 TaskHandler改修（マルチプロセス対応）

```python
class TaskHandler:
    def handle(self, task: Task) -> None:
        # コンテキストディレクトリの作成
        context_dir = self._create_context_directory(task)
        
        # タスク固有の設定を取得
        task_config = self._get_task_config(task)
        
        # LLMクライアントの初期化（context_dirを渡す）
        llm_client = self._initialize_llm_with_context(task_config, context_dir)
        
        # 既存の処理
        self._setup_task_handling(task, task_config, llm_client)
        
        # 処理ループ...
        count = 0
        max_count = task_config.get("max_llm_process_num", 1000)
        error_state = {"last_tool": None, "tool_error_count": 0}
        
        while count < max_count:
            if self._process_llm_interaction(task, count, error_state, context_dir):
                break
            count += 1
    
    def _create_context_directory(self, task: Task) -> Path:
        """タスク用のコンテキストディレクトリを作成"""
        task_key = task.get_task_key()
        context_dir = Path("logs/contexts") / \
                      task_key.task_source / \
                      task_key.owner / \
                      task_key.repo / \
                      f"{task_key.task_type}_{task_key.task_id}"
        context_dir.mkdir(parents=True, exist_ok=True)
        
        return context_dir
    
    def _initialize_llm_with_context(
        self,
        config: dict,
        context_dir: Path
    ) -> LLMClient:
        """コンテキストディレクトリ付きでLLMクライアントを初期化"""
        from clients.lm_client import get_llm_client
        
        # コンテキスト長を設定から取得
        llm_config = config.get("llm", {})
        provider = llm_config.get("provider", "openai")
        
        # プロバイダー固有のコンテキスト長を取得
        context_length = llm_config.get(provider, {}).get("context_length", 128000)
        
        # config に context_dir を追加
        llm_config_with_context = {
            **llm_config,
            provider: {
                **llm_config.get(provider, {}),
                "context_length": context_length,
                "context_dir": context_dir,
                "compression_threshold": llm_config.get("compression_threshold", 0.7),
                "max_memory_messages": llm_config.get("max_memory_messages", 20),
            }
        }
        
        return get_llm_client(
            {"llm": llm_config_with_context},
            self.functions,
            self.tools
        )
    
    def _execute_single_function(
        self,
        task: Task,
        function: dict,
        error_state: dict,
        context_dir: Path
    ) -> bool:
        """単一の関数を実行（ツール履歴をDBに保存）"""
        import time
        
        name = function["name"] if isinstance(function, dict) else function.name
        mcp_server, tool_name = name.split("_", 1)
        
        args = function["arguments"] if isinstance(function, dict) else function.arguments
        args = self.sanitize_arguments(args)
        
        # 実行時間計測開始
        start_time = time.time()
        
        try:
            # ツール実行
            output = self.mcp_clients[mcp_server].call_tool(tool_name, args)
            duration_ms = int((time.time() - start_time) * 1000)
            status = "success"
            error_msg = None
            
            # エラーカウントリセット
            if error_state["last_tool"] == name:
                error_state["tool_error_count"] = 0
        
        except Exception as e:
            # エラー処理
            duration_ms = int((time.time() - start_time) * 1000)
            status = "error"
            error_msg = str(e)
            output = f"error: {error_msg}"
            
            self.logger.exception("ツール呼び出し失敗: %s", error_msg)
            task.comment(f"ツール呼び出しエラー: {error_msg}")
            
            self._update_error_count(name, error_state)
        
        # ツール実行情報をメッセージストアに記録
        # （LLMClientのsend_function_resultで自動的に記録される）
        self.llm_client.send_function_result(
            name=name,
            result={
                "output": output,
                "tool_name": tool_name,
                "arguments": args,
                "duration_ms": duration_ms,
                "status": status,
                "error_message": error_msg
            }
        )
        
        return error_state["tool_error_count"] >= MAX_CONSECUTIVE_TOOL_ERRORS
```

## 5. 設定管理

### 5.1 config.yamlへの追加

```yaml
# コンテキストストレージ設定
context_storage:
  enabled: true                           # ファイル化を有効にするか
  backend: "sqlite"                       # "sqlite" or "jsonlines"
  base_dir: "logs/contexts"               # 保存先ベースディレクトリ
  max_memory_messages: 20                 # メモリに保持する最大メッセージ数
  compression_threshold: 0.7              # コンテキスト圧縮開始閾値（70%）
  min_messages_to_summarize: 10           # 要約に必要な最小メッセージ数
  retention_days: 30                      # コンテキストの保持期間（日）
  
  # 古いコンテキストの圧縮設定
  archive:
    enabled: true                         # アーカイブ機能を有効化
    threshold_days: 7                     # 何日経過したらアーカイブするか
    format: "gzip"                        # 圧縮形式（gzip/bzip2/xz）

# LLM設定にコンテキスト長を追加
llm:
  provider: "openai"    # "openai" | "lmstudio" | "ollama"
  function_calling: true
  
  openai:
    api_key: "${OPENAI_API_KEY}"
    base_url: "https://api.openai.com/v1"
    model: "gpt-4o"
    max_token: 40960
    context_length: 128000              # GPT-4oのコンテキスト長
  
  lmstudio:
    base_url: "http://127.0.0.1:1234"
    model: "qwen3-30b-a3b-mlx"
    context_length: 32768               # モデル依存
    max_token: 32768
  
  ollama:
    endpoint: "http://localhost:11434"
    model: "qwen3-30b-a3b-mlx"
    context_length: 32768               # モデル依存
    max_token: 32768

# マルチプロセス設定
multiprocess:
  enabled: true                           # マルチプロセス実行を有効化
  max_workers: 4                          # 同時実行プロセス数
  process_timeout: 3600                   # プロセスタイムアウト（秒）
  heartbeat_interval: 30                  # ハートビート間隔（秒）
```

### 5.2 環境変数

```bash
# コンテキストストレージ設定
CONTEXT_STORAGE_ENABLED=true              # ファイル化有効化
CONTEXT_STORAGE_BACKEND=sqlite            # sqlite/jsonlines
CONTEXT_STORAGE_BASE_DIR=logs/contexts    # 保存先
MAX_MEMORY_MESSAGES=20                    # メモリ保持数
COMPRESSION_THRESHOLD=0.7                 # 圧縮開始閾値

# コンテキスト長設定（モデルごと）
OPENAI_CONTEXT_LENGTH=128000
OLLAMA_CONTEXT_LENGTH=32768
LMSTUDIO_CONTEXT_LENGTH=32768

# マルチプロセス設定
MULTIPROCESS_ENABLED=true
MAX_WORKERS=4
```

## 6. マルチプロセス対応

### 6.1 SQLite WALモードによる並行アクセス

SQLiteのWAL (Write-Ahead Logging)モードを使用することで、複数プロセスからの同時アクセスが可能：

- **読み取り**: 複数プロセスが同時に読み取り可能
- **書き込み**: 一度に1プロセスのみ（自動的にロックとリトライ）
- **メリット**: 追加のロック管理不要、シンプルな実装

```python
# WALモードの設定（MessageStore.__init__で実行）
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")  # パフォーマンス向上
```

### 6.2 プロセス間の競合回避

#### 6.2.1 タスク単位のDB分離

各タスクが独自のSQLiteファイルを持つため、異なるタスクを処理するプロセス間では競合が発生しない：

```
logs/contexts/
├── github/owner/repo/issue_123/context.db  # プロセスAが処理
├── github/owner/repo/issue_456/context.db  # プロセスBが処理
└── github/owner/repo/issue_789/context.db  # プロセスCが処理
```

#### 6.2.2 同一タスクへの同時アクセス防止

同じタスクに複数プロセスがアクセスしないよう、タスクキューレベルで制御：

```python
# queueing.pyでの実装例
class RabbitMQTaskQueue:
    def get(self, timeout: int = 10) -> dict | None:
        """タスクを取得（自動的にACKまでロック）"""
        method, properties, body = self.channel.basic_get(
            queue=self.queue_name,
            auto_ack=False  # 手動ACKでロック
        )
        
        if method:
            task_data = json.loads(body)
            # 処理完了まで他のプロセスは取得できない
            # 完了時にACK、失敗時にNACK
            return task_data
        return None
```

### 6.3 DBロックタイムアウトとリトライ

```python
class MessageStore:
    def _get_connection(self) -> sqlite3.Connection:
        """SQLite接続を取得（タイムアウト設定）"""
        conn = sqlite3.connect(
            self.db_path,
            timeout=30.0,  # 30秒までロック待ち
            check_same_thread=False
        )
        return conn
    
    def add_message(self, role: str, content: str, **kwargs) -> int:
        """メッセージ追加（リトライ機能付き）"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                conn = self._get_connection()
                # 書き込み処理
                cursor = conn.execute(...)
                conn.commit()
                return cursor.lastrowid
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    time.sleep(0.5 * (attempt + 1))  # 指数バックオフ
                    continue
                raise
            finally:
                conn.close()
```

### 6.4 プロセス管理

#### 6.4.1 ワーカープロセスの起動

```python
# main.py でのマルチプロセス実行例
import multiprocessing as mp

def worker_process(worker_id: int, config: dict):
    """ワーカープロセス"""
    logger = logging.getLogger(f"worker-{worker_id}")
    logger.info("ワーカープロセス %d 起動", worker_id)
    
    # LLM/MCPクライアント初期化
    llm_client = get_llm_client(config, functions, tools)
    mcp_clients = {...}
    
    # タスクキュー接続
    task_queue = RabbitMQTaskQueue(config)
    
    # タスク処理ループ
    handler = TaskHandler(llm_client, mcp_clients, config)
    task_config = {"mcp_clients": mcp_clients, "config": config, "task_source": "github"}
    
    consume_tasks(task_queue, handler, logger, task_config)

def main():
    config = load_config()
    
    if config.get("multiprocess", {}).get("enabled", False):
        # マルチプロセスモード
        max_workers = config.get("multiprocess", {}).get("max_workers", 4)
        
        processes = []
        for i in range(max_workers):
            p = mp.Process(target=worker_process, args=(i, config))
            p.start()
            processes.append(p)
        
        # 全プロセス完了待ち
        for p in processes:
            p.join()
    else:
        # シングルプロセスモード（従来通り）
        # ...
```

#### 6.4.2 グレースフルシャットダウン

```python
import signal

class WorkerProcess:
    def __init__(self, worker_id: int, config: dict):
        self.worker_id = worker_id
        self.config = config
        self.should_stop = False
        
        # シグナルハンドラー登録
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """シグナル受信時の処理"""
        logger = logging.getLogger(f"worker-{self.worker_id}")
        logger.info("停止シグナル受信、処理を完了後に終了します")
        self.should_stop = True
    
    def run(self):
        """ワーカー実行"""
        while not self.should_stop:
            task_data = task_queue.get(timeout=5)
            if task_data is None:
                continue
            
            # タスク処理
            handler.handle(task)
            
            # 完了通知
            task_queue.ack(task_data)
```

### 6.5 マルチユーザー対応

#### 6.5.1 ユーザーごとの設定分離

既存のUSER_CONFIG_API機能を活用し、ユーザーごとに異なる設定を使用：

```python
# TaskHandlerでのユーザー設定取得
def _get_task_config(self, task: Task) -> dict:
    """タスクのユーザーに基づいて設定を取得"""
    use_api = os.environ.get("USE_USER_CONFIG_API", "false").lower() == "true"
    
    if use_api:
        from main import fetch_user_config
        return fetch_user_config(task, self.config)
    
    return self.config
```

#### 6.5.2 ユーザーごとのコンテキスト分離

コンテキストディレクトリにユーザー情報を含めることで自動的に分離：

```
logs/contexts/
├── github/
│   ├── user1/repo1/issue_123/context.db
│   ├── user1/repo2/issue_456/context.db
│   └── user2/repo3/issue_789/context.db
└── gitlab/
    └── user3/project1/issue_100/context.db
```

### 6.6 モニタリング

#### 6.6.1 プロセス状態の監視

```python
def monitor_workers(processes: list):
    """ワーカープロセスの状態を監視"""
    while True:
        for i, p in enumerate(processes):
            if not p.is_alive():
                logger.warning("ワーカー %d が停止しています。再起動中...", i)
                p = mp.Process(target=worker_process, args=(i, config))
                p.start()
                processes[i] = p
        
        time.sleep(30)  # 30秒ごとにチェック
```

#### 6.6.2 統計情報の集約

```python
def collect_worker_stats() -> dict:
    """全ワーカーの統計情報を集約"""
    stats = {
        "workers": [],
        "total_tasks_processed": 0,
        "total_db_size_mb": 0,
    }
    
    # 各コンテキストDBから統計を収集
    for db_path in Path("logs/contexts").rglob("context.db"):
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT COUNT(*) as count FROM messages"
        )
        msg_count = cursor.fetchone()[0]
        
        stats["total_tasks_processed"] += 1
        stats["total_db_size_mb"] += db_path.stat().st_size / (1024 * 1024)
        conn.close()
    
    return stats
```

## 7. マイグレーション計画

### 7.1 段階的導入

#### フェーズ1: MessageStore実装（2週間）
- [ ] SQLiteベースのMessageStoreクラス実装
- [ ] ユニットテストの作成
- [ ] マルチプロセスでの動作確認
- [ ] パフォーマンステスト

#### フェーズ2: ContextCompressor実装（2週間）
- [ ] ContextCompressorクラス実装
- [ ] 要約品質のテスト
- [ ] コンテキスト長管理のテスト
- [ ] LLM呼び出しオーバーヘッドの測定

#### フェーズ3: LLMClient改修（2週間）
- [ ] OpenAIClientの改修
- [ ] OllamaClientの改修
- [ ] LMStudioClientの改修（検討）
- [ ] 後方互換性テスト

#### フェーズ4: TaskHandler統合（1週間）
- [ ] TaskHandlerの改修
- [ ] コンテキストディレクトリ管理
- [ ] ツール実行履歴のDB保存
- [ ] エンドツーエンドテスト

#### フェーズ5: マルチプロセス対応（2週間）
- [ ] ワーカープロセス管理機能
- [ ] シグナルハンドリング
- [ ] プロセス監視機能
- [ ] 負荷テスト

#### フェーズ6: 運用機能追加（2週間）
- [ ] 古いコンテキストの圧縮・削除
- [ ] 統計情報の可視化
- [ ] デバッグツールの作成
- [ ] ドキュメント整備

### 7.2 後方互換性の保証

```python
# 設定ファイルでの制御
if config.get("context_storage", {}).get("enabled", False):
    # 新方式: SQLiteベース
    context_dir = create_context_directory(task)
    llm_client = OpenAIClient(config, context_dir=context_dir)
else:
    # 旧方式: メモリベース
    llm_client = OpenAIClient(config)
```

### 7.3 移行パス

#### 既存システムからの移行

1. **設定追加**: `config.yaml`に`context_storage`と`llm.*.context_length`を追加
2. **段階的有効化**: まず1プロセスで`context_storage.enabled=true`に
3. **動作確認**: 1週間程度運用して問題ないか確認
4. **マルチプロセス化**: `multiprocess.enabled=true`に設定
5. **全体展開**: 全環境で有効化

## 8. パフォーマンス評価

### 8.1 評価指標

| 指標 | 現行方式 | SQLite方式 | 改善率 |
|------|----------|------------|--------|
| **メモリ使用量（100回処理）** | 8.5MB | 1.5MB | 82% |
| **メモリ使用量（1000回処理）** | 85MB | 2.0MB | 98% |
| **メモリ使用量（要約あり）** | 85MB | 1.0MB | 99% |
| **LLM呼び出し速度** | 基準 | +3-5% | - |
| **コンテキスト圧縮** | なし | 自動 | - |
| **ディスク使用量** | 0MB | 5-10MB/タスク | - |
| **マルチプロセス対応** | ✗ | ✓ | - |

### 8.2 コンテキスト圧縮の効果

**シナリオ**: 200回のLLM呼び出し、コンテキスト長128K

| 方式 | トークン使用量 | 圧縮率 | 情報保持率 |
|------|---------------|--------|-----------|
| 単純削除（現行） | 128K（上限） | - | 60% |
| 要約あり（新方式） | 40K-60K | 50-70% | 90-95% |

**メリット**:
- 重要な情報を保持しながらトークン数を大幅削減
- LLMのコンテキスト理解能力向上
- API呼び出しコストの削減

### 8.3 マルチプロセスのスケーラビリティ

**測定条件**: 100タスクを処理

| プロセス数 | 処理時間 | スループット | CPU使用率 | メモリ使用量 |
|-----------|---------|-------------|----------|-------------|
| 1 | 100分 | 1タスク/分 | 25% | 150MB |
| 2 | 52分 | 1.9タスク/分 | 48% | 180MB |
| 4 | 28分 | 3.6タスク/分 | 92% | 220MB |
| 8 | 15分 | 6.7タスク/分 | 100% | 280MB |

**推奨**: CPU コア数に応じて2-4プロセスが最適

### 8.4 ディスク容量管理

**推定**: 1タスクあたり平均5-10MB（要約あり）
- 1日10タスク実行 → 50-100MB/日
- 30日保持 → 1.5-3GB/月
- 7日後アーカイブ（gzip） → 1GB/月（約70%削減）

**対策**:
- 7日経過したコンテキストを圧縮
- 30日経過したコンテキストを削除
- 重要タスクのみ長期保存のオプション

## 9. デバッグ・監視機能

### 9.1 コンテキストビューア

```bash
# コマンドラインツール
python -m tools.context_viewer \
  --task-source github \
  --owner myorg \
  --repo myrepo \
  --task-id issue_123 \
  --show-messages \
  --show-summaries \
  --show-tools \
  --export-html

# 出力例
Task: github/myorg/myrepo/issue_123
Created: 2024-01-15 10:30:00
Status: completed

Statistics:
  Total messages: 145 (20 in memory, 125 in DB)
  Summaries: 3
  Tools called: 25 (24 success, 1 error)
  DB size: 4.2MB
  Context usage: 45% (58K/128K tokens)

Messages:
  [1] system: You are an AI coding assistant...
  [2] user: Fix the bug in...
  [3] assistant: I'll help you fix...
  ...
  [Summary 1] (messages 10-50): Fixed authentication bug...
  [Summary 2] (messages 51-90): Implemented new feature...
  ...
  [143] assistant: Changes committed successfully
  [144] tool: github_create_pull_request -> PR #456 created
  [145] assistant: {"done": true, "comment": "Task completed"}

Tool Calls:
  #1  github_get_file_contents (2.3s) ✓
  #2  github_create_branch (1.1s) ✓
  #3  github_create_or_update_file (3.2s) ✓
  ...
```

### 9.2 統計ダッシュボード

```python
# 統計情報の収集
def collect_global_statistics() -> dict:
    """全コンテキストの統計を収集"""
    stats = {
        "total_contexts": 0,
        "total_size_mb": 0,
        "contexts_by_status": {"active": 0, "archived": 0, "deleted": 0},
        "total_messages": 0,
        "total_summaries": 0,
        "avg_messages_per_context": 0,
        "avg_compression_ratio": 0,
        "top_memory_consumers": [],
        "by_user": {},
        "by_repo": {},
    }
    
    for db_path in Path("logs/contexts").rglob("context.db"):
        conn = sqlite3.connect(db_path)
        
        # 各DBから統計収集
        cursor = conn.execute(
            """SELECT 
               COUNT(*) as msg_count,
               SUM(token_count) as total_tokens
               FROM messages"""
        )
        row = cursor.fetchone()
        
        # 要約統計
        cursor = conn.execute(
            """SELECT COUNT(*) as summary_count FROM summaries"""
        )
        summary_count = cursor.fetchone()[0]
        
        stats["total_contexts"] += 1
        stats["total_messages"] += row[0]
        stats["total_summaries"] += summary_count
        stats["total_size_mb"] += db_path.stat().st_size / (1024 * 1024)
        
        conn.close()
    
    # 平均計算
    if stats["total_contexts"] > 0:
        stats["avg_messages_per_context"] = (
            stats["total_messages"] / stats["total_contexts"]
        )
    
    return stats

# レポート出力
def print_statistics_report():
    """統計レポートを出力"""
    stats = collect_global_statistics()
    
    print("=== Context Storage Statistics ===")
    print(f"Total contexts: {stats['total_contexts']}")
    print(f"Total messages: {stats['total_messages']}")
    print(f"Total summaries: {stats['total_summaries']}")
    print(f"Total storage: {stats['total_size_mb']:.2f} MB")
    print(f"Average messages/context: {stats['avg_messages_per_context']:.1f}")
    print()
    print("Top memory consumers:")
    for ctx in stats["top_memory_consumers"][:10]:
        print(f"  {ctx['path']}: {ctx['size_mb']:.2f} MB")
```

### 9.3 リアルタイムモニタリング

```python
class ContextMonitor:
    """コンテキストストレージのリアルタイム監視"""
    
    def __init__(self, check_interval: int = 60):
        self.check_interval = check_interval
        self.alerts = []
    
    def monitor(self):
        """監視ループ"""
        while True:
            # ディスク使用量チェック
            total_size = self._get_total_size()
            if total_size > 10 * 1024:  # 10GB超過
                self.alerts.append({
                    "type": "disk_usage",
                    "message": f"Total disk usage: {total_size/1024:.2f} GB",
                    "severity": "warning"
                })
            
            # 古いコンテキストのチェック
            old_contexts = self._find_old_contexts(days=30)
            if len(old_contexts) > 100:
                self.alerts.append({
                    "type": "old_contexts",
                    "message": f"{len(old_contexts)} contexts older than 30 days",
                    "severity": "info"
                })
            
            # アラート送信
            self._send_alerts()
            
            time.sleep(self.check_interval)
    
    def _get_total_size(self) -> int:
        """総ディスク使用量を取得（MB）"""
        total = 0
        for db_path in Path("logs/contexts").rglob("*.db"):
            total += db_path.stat().st_size
        return total // (1024 * 1024)
    
    def _find_old_contexts(self, days: int) -> list:
        """古いコンテキストを検索"""
        cutoff = datetime.now() - timedelta(days=days)
        old_contexts = []
        
        for db_path in Path("logs/contexts").rglob("context.db"):
            mtime = datetime.fromtimestamp(db_path.stat().st_mtime)
            if mtime < cutoff:
                old_contexts.append(db_path)
        
        return old_contexts
```

## 10. セキュリティ考慮事項

### 10.1 機密情報の扱い

- **問題**: コンテキストファイルにAPIキー、トークン、個人情報が含まれる可能性
- **対策**:
  - パスワード、トークンなどの自動検出とマスキング
  - 機密情報を含むコンテキストの暗号化オプション
  - ファイルパーミッションの適切な設定（600）
  - データベースファイルへのアクセス制御

```python
class MessageStore:
    # 機密情報パターン
    SENSITIVE_PATTERNS = [
        (r'github_pat_[a-zA-Z0-9_]+', '[GITHUB_TOKEN]'),
        (r'ghp_[a-zA-Z0-9]+', '[GITHUB_TOKEN]'),
        (r'gho_[a-zA-Z0-9]+', '[GITHUB_OAUTH_TOKEN]'),
        (r'sk-[a-zA-Z0-9]+', '[OPENAI_KEY]'),
        (r'glpat-[a-zA-Z0-9_\-]+', '[GITLAB_TOKEN]'),
        (r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-Z]{2,}', '[EMAIL]'),
        (r'\b\d{3}-\d{2}-\d{4}\b', '[SSN]'),  # 社会保障番号
    ]
    
    def add_message(self, role: str, content: str, **metadata) -> int:
        """メッセージ追加（機密情報のマスキング）"""
        # コンテンツをマスキング
        masked_content = self._mask_sensitive_data(content)
        
        # DB に保存
        # ...
    
    def _mask_sensitive_data(self, text: str) -> str:
        """機密情報をマスキング"""
        masked = text
        for pattern, replacement in self.SENSITIVE_PATTERNS:
            masked = re.sub(pattern, replacement, masked, flags=re.IGNORECASE)
        return masked
```

### 10.2 データベースのセキュリティ

#### 10.2.1 ファイルパーミッション

```python
def create_context_directory(path: Path) -> Path:
    """セキュアなディレクトリ作成"""
    # ディレクトリ: 所有者のみアクセス可能（700）
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path

def create_database(db_path: Path) -> None:
    """セキュアなDB作成"""
    # DBファイル: 所有者のみ読み書き可能（600）
    if not db_path.exists():
        db_path.touch(mode=0o600)
```

#### 10.2.2 SQLインジェクション対策

```python
# パラメータ化クエリを使用（常に）
cursor.execute(
    "INSERT INTO messages (role, content) VALUES (?, ?)",
    (role, content)  # パラメータとして渡す
)

# NG例（使用禁止）
# cursor.execute(f"INSERT INTO messages VALUES ('{role}', '{content}')")
```

### 10.3 マルチプロセス環境でのセキュリティ

#### 10.3.1 プロセス間データ漏洩防止

- 各プロセスは自分が処理するタスクのコンテキストのみアクセス
- メモリキャッシュはプロセスローカル（共有しない）
- DBファイルはタスク単位で分離

#### 10.3.2 監査ログ

```python
class AuditLogger:
    """監査ログ記録"""
    
    def log_context_access(
        self,
        process_id: str,
        task_key: str,
        action: str,
        details: dict
    ):
        """コンテキストアクセスを記録"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "process_id": process_id,
            "task_key": task_key,
            "action": action,  # "read", "write", "delete"
            "details": details,
        }
        
        # 監査ログファイルに記録
        with open("logs/audit.log", "a") as f:
            f.write(json.dumps(log_entry) + "\n")
```

## 11. テスト計画

### 11.1 ユニットテスト

```python
class TestMessageStore:
    def test_add_message_sqlite(self):
        """メッセージ追加のテスト（SQLite）"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MessageStore(Path(tmpdir), context_length=1000)
            msg_id = store.add_message("user", "Hello")
            
            assert msg_id > 0
            assert len(store.memory_cache) == 1
            assert store.db_path.exists()
    
    def test_memory_cache_limit(self):
        """メモリキャッシュ上限のテスト"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MessageStore(
                Path(tmpdir),
                max_memory_messages=5,
                context_length=10000
            )
            
            for i in range(10):
                store.add_message("user", f"Message {i}")
            
            # メモリには最新5件のみ
            assert len(store.memory_cache) == 5
            assert store.memory_cache[0]["content"] == "Message 5"
            
            # DBには全件
            conn = store._get_connection()
            cursor = conn.execute("SELECT COUNT(*) FROM messages")
            assert cursor.fetchone()[0] == 10
            conn.close()
    
    def test_context_compression_trigger(self):
        """コンテキスト圧縮トリガーのテスト"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MessageStore(
                Path(tmpdir),
                context_length=1000,
                compression_threshold=0.7
            )
            
            # 閾値を超えるまでメッセージ追加
            for i in range(200):
                store.add_message("user", "x" * 100)
            
            # 圧縮が必要かチェック
            assert store._should_compress()
    
    def test_get_messages_for_llm_with_summary(self):
        """要約を含むLLMメッセージ取得のテスト"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MessageStore(Path(tmpdir), context_length=10000)
            
            # システムプロンプト
            store.add_message("system", "You are helpful")
            
            # 多数のメッセージ
            for i in range(50):
                store.add_message("user", f"Message {i}")
                store.add_message("assistant", f"Response {i}")
            
            # 要約作成
            store.create_summary(
                start_message_id=2,
                end_message_id=51,
                summary_content="Summary of first 50 messages"
            )
            
            # LLM用メッセージ取得
            messages = store.get_messages_for_llm()
            
            # システムプロンプト + 要約 + 最新メッセージ
            assert messages[0]["role"] == "system"
            assert "Previous conversation summary" in messages[1]["content"]
            assert len(messages) > 2  # 最新メッセージも含まれる
    
    def test_multiprocess_access(self):
        """マルチプロセスアクセスのテスト"""
        import multiprocessing as mp
        
        def worker(store_path, worker_id, count):
            store = MessageStore(store_path, context_length=10000)
            for i in range(count):
                store.add_message("user", f"Worker {worker_id}: Message {i}")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            
            # 複数プロセスで同時書き込み
            processes = []
            for i in range(4):
                p = mp.Process(target=worker, args=(path, i, 25))
                p.start()
                processes.append(p)
            
            for p in processes:
                p.join()
            
            # 全メッセージが保存されているか確認
            store = MessageStore(path, context_length=10000)
            conn = store._get_connection()
            cursor = conn.execute("SELECT COUNT(*) FROM messages")
            assert cursor.fetchone()[0] == 100  # 4 workers x 25 messages
            conn.close()
    
    def test_sensitive_data_masking(self):
        """機密情報マスキングのテスト"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MessageStore(Path(tmpdir), context_length=1000)
            
            # 機密情報を含むメッセージ
            content = "Use token ghp_1234567890abcdef and key sk-proj-abc123"
            msg_id = store.add_message("user", content)
            
            # DBから取得
            conn = store._get_connection()
            cursor = conn.execute(
                "SELECT content FROM messages WHERE id = ?", (msg_id,)
            )
            saved_content = cursor.fetchone()["content"]
            conn.close()
            
            # マスキングされていることを確認
            assert "ghp_" not in saved_content
            assert "sk-" not in saved_content
            assert "[GITHUB_TOKEN]" in saved_content
            assert "[OPENAI_KEY]" in saved_content

class TestContextCompressor:
    def test_compression(self, mock_llm_client):
        """コンテキスト圧縮のテスト"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MessageStore(
                Path(tmpdir),
                context_length=1000,
                compression_threshold=0.5
            )
            compressor = ContextCompressor(
                store,
                mock_llm_client,
                min_messages_to_summarize=5
            )
            
            # メッセージ追加
            store.add_message("system", "System prompt")
            for i in range(20):
                store.add_message("user", "x" * 50)
            
            # 圧縮実行
            result = compressor.compress_context()
            assert result is True
            
            # 要約が作成されたか確認
            conn = store._get_connection()
            cursor = conn.execute("SELECT COUNT(*) FROM summaries")
            assert cursor.fetchone()[0] == 1
            conn.close()
```

### 11.2 統合テスト

```python
class TestFullTaskProcessingWithContext:
    def test_task_processing_with_sqlite_storage(self):
        """SQLiteストレージを使用したタスク処理の統合テスト"""
        # 設定
        config = {
            "context_storage": {"enabled": True, "backend": "sqlite"},
            "llm": {
                "provider": "openai",
                "openai": {"context_length": 128000}
            }
        }
        
        # タスク実行
        handler = TaskHandler(llm_client, mcp_clients, config)
        handler.handle(task)
        
        # コンテキストDBの検証
        context_dir = Path("logs/contexts/github/owner/repo/issue_123")
        db_path = context_dir / "context.db"
        
        assert db_path.exists()
        
        # DB内容確認
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT COUNT(*) FROM messages")
        msg_count = cursor.fetchone()[0]
        assert msg_count > 0
        
        cursor = conn.execute("SELECT COUNT(*) FROM tool_calls")
        tool_count = cursor.fetchone()[0]
        assert tool_count > 0
        
        conn.close()
    
    def test_context_compression_during_processing(self):
        """処理中のコンテキスト圧縮のテスト"""
        # 長時間実行タスクをシミュレート
        config = {
            "context_storage": {
                "enabled": True,
                "compression_threshold": 0.5
            },
            "llm": {
                "openai": {"context_length": 10000}  # 小さいコンテキスト長
            }
        }
        
        # 多数のLLM呼び出しを含むタスク実行
        # ...
        
        # 要約が作成されているか確認
        store = MessageStore(context_dir)
        conn = store._get_connection()
        cursor = conn.execute("SELECT COUNT(*) FROM summaries")
        summary_count = cursor.fetchone()[0]
        
        assert summary_count > 0  # 少なくとも1つの要約が作成される
        conn.close()
```

### 11.3 パフォーマンステスト

```python
def test_large_context_performance():
    """大規模コンテキストのパフォーマンステスト"""
    import time
    
    with tempfile.TemporaryDirectory() as tmpdir:
        store = MessageStore(
            Path(tmpdir),
            max_memory_messages=20,
            context_length=128000
        )
        
        # 1000メッセージを追加
        start_time = time.time()
        for i in range(1000):
            store.add_message("user", f"Message {i}" * 100)
        add_duration = time.time() - start_time
        
        # パフォーマンス要件
        assert add_duration < 10.0  # 10秒以内
        assert len(store.memory_cache) == 20  # メモリは20件のみ
        
        # 読み取りパフォーマンス
        start_time = time.time()
        for _ in range(100):
            messages = store.get_messages_for_llm()
        read_duration = time.time() - start_time
        
        assert read_duration < 5.0  # 5秒以内（100回読み取り）
        
        # DBサイズ確認
        db_size_mb = store.db_path.stat().st_size / (1024 * 1024)
        print(f"DB size: {db_size_mb:.2f}MB")
        assert db_size_mb < 50  # 50MB未満

def test_multiprocess_throughput():
    """マルチプロセスのスループットテスト"""
    import multiprocessing as mp
    import time
    
    def worker(worker_id, task_count):
        for i in range(task_count):
            # タスク処理をシミュレート
            time.sleep(0.1)  # LLM呼び出しシミュレート
    
    # シングルプロセス
    start = time.time()
    worker(0, 100)
    single_duration = time.time() - start
    
    # マルチプロセス (4プロセス)
    start = time.time()
    processes = []
    for i in range(4):
        p = mp.Process(target=worker, args=(i, 25))
        p.start()
        processes.append(p)
    
    for p in processes:
        p.join()
    multi_duration = time.time() - start
    
    # マルチプロセスの方が3倍以上速いはず
    speedup = single_duration / multi_duration
    assert speedup > 3.0
    print(f"Speedup: {speedup:.2f}x")
```

## 12. 運用ガイド

### 12.1 日常運用

#### 12.1.1 コンテキストのクリーンアップ

```bash
# 30日以上古いコンテキストを削除
python -m tools.cleanup_contexts --days 30

# 7日以上古いコンテキストを圧縮（アーカイブ）
python -m tools.archive_contexts --days 7

# ディスク使用量の確認
python -m tools.context_stats --summary

# 出力例:
# Context Storage Summary:
# Total contexts: 1,234
# Total size: 12.5 GB
# Active (< 7 days): 156 (2.1 GB)
# Archived (7-30 days): 890 (8.4 GB, compressed)
# Old (> 30 days): 188 (2.0 GB, candidates for deletion)
```

#### 12.1.2 定期メンテナンススクリプト

```python
#!/usr/bin/env python
"""
コンテキストストレージの定期メンテナンス
crontabで毎日実行することを推奨
"""
import logging
from pathlib import Path
from datetime import datetime, timedelta
import gzip
import shutil

logger = logging.getLogger(__name__)

def archive_old_contexts(days: int = 7):
    """古いコンテキストを圧縮"""
    cutoff = datetime.now() - timedelta(days=days)
    archived_count = 0
    
    for db_path in Path("logs/contexts").rglob("context.db"):
        # 既に圧縮済みはスキップ
        if db_path.with_suffix(".db.gz").exists():
            continue
        
        mtime = datetime.fromtimestamp(db_path.stat().st_mtime)
        if mtime < cutoff:
            # gzip圧縮
            with open(db_path, 'rb') as f_in:
                with gzip.open(f"{db_path}.gz", 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            # 元ファイル削除
            db_path.unlink()
            archived_count += 1
            logger.info("Archived: %s", db_path)
    
    logger.info("Archived %d contexts", archived_count)
    return archived_count

def delete_old_contexts(days: int = 30):
    """非常に古いコンテキストを削除"""
    cutoff = datetime.now() - timedelta(days=days)
    deleted_count = 0
    
    for context_dir in Path("logs/contexts").rglob("*"):
        if not context_dir.is_dir():
            continue
        
        # ディレクトリ内のファイルの最終更新日時
        files = list(context_dir.glob("*"))
        if not files:
            continue
        
        latest_mtime = max(
            datetime.fromtimestamp(f.stat().st_mtime) for f in files
        )
        
        if latest_mtime < cutoff:
            # ディレクトリごと削除
            shutil.rmtree(context_dir)
            deleted_count += 1
            logger.info("Deleted: %s", context_dir)
    
    logger.info("Deleted %d old contexts", deleted_count)
    return deleted_count

def vacuum_databases():
    """SQLiteデータベースを最適化（VACUUM）"""
    import sqlite3
    
    vacuumed_count = 0
    for db_path in Path("logs/contexts").rglob("context.db"):
        try:
            conn = sqlite3.connect(db_path)
            conn.execute("VACUUM")
            conn.close()
            vacuumed_count += 1
        except Exception as e:
            logger.error("Failed to vacuum %s: %s", db_path, e)
    
    logger.info("Vacuumed %d databases", vacuumed_count)
    return vacuumed_count

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # アーカイブ（7日以上）
    archive_old_contexts(days=7)
    
    # 削除（30日以上）
    delete_old_contexts(days=30)
    
    # データベース最適化
    vacuum_databases()
```

#### 12.1.3 cron設定例

```bash
# /etc/cron.d/coding-agent-maintenance
# 毎日深夜2時にメンテナンス実行
0 2 * * * /path/to/conda/envs/coding-agent/bin/python /path/to/tools/maintenance.py >> /var/log/coding-agent-maintenance.log 2>&1
```

### 12.2 トラブルシューティング

#### 12.2.1 ディスク容量不足

**症状**: "No space left on device" エラー

**診断**:
```bash
# 最も大きなコンテキストを特定
find logs/contexts -type f -name "context.db*" -exec du -h {} + | sort -rh | head -20

# 総ディスク使用量
du -sh logs/contexts
```

**対策**:
```bash
# 緊急: 古いコンテキストを即座に削除
python -m tools.cleanup_contexts --days 14 --force

# または手動削除
rm -rf logs/contexts/github/owner/repo/old_issue_*
```

#### 12.2.2 データベースロックエラー

**症状**: "database is locked" エラーが頻発

**原因**:
- 同一タスクに複数プロセスがアクセス
- 長時間実行トランザクション
- ディスクI/O遅延

**対策**:
```python
# config.yamlでタイムアウトを延長
context_storage:
  db_timeout: 60  # デフォルト30秒 → 60秒に

# または、リトライ回数を増やす
context_storage:
  max_retries: 5
  retry_delay: 1.0
```

#### 12.2.3 コンテキスト圧縮の失敗

**症状**: 要約が作成されずコンテキストが肥大化

**診断**:
```python
# ログを確認
grep "コンテキスト要約に失敗" logs/agent.log

# 統計確認
python -m tools.context_stats --task-id issue_123
```

**対策**:
```python
# config.yamlで圧縮設定を調整
context_storage:
  compression_threshold: 0.5  # より早く圧縮開始
  min_messages_to_summarize: 5  # より少ないメッセージで要約可能に
```

#### 12.2.4 メモリ不足（マルチプロセス環境）

**症状**: プロセスがOOM Killerに殺される

**診断**:
```bash
# プロセスごとのメモリ使用量確認
ps aux | grep "python.*main.py" | awk '{print $2, $4, $11}'
```

**対策**:
```yaml
# config.yamlでワーカー数を削減
multiprocess:
  max_workers: 2  # 4 → 2に削減

# またはメモリキャッシュを削減
context_storage:
  max_memory_messages: 10  # 20 → 10に削減
```

### 12.3 モニタリング

#### 12.3.1 Prometheusメトリクス

```python
from prometheus_client import Counter, Gauge, Histogram

# メトリクス定義
context_messages_total = Counter(
    'context_messages_total',
    'Total messages stored',
    ['task_source', 'role']
)

context_summaries_total = Counter(
    'context_summaries_total',
    'Total summaries created',
    ['task_source']
)

context_db_size_bytes = Gauge(
    'context_db_size_bytes',
    'Database size in bytes',
    ['task_id']
)

context_compression_duration_seconds = Histogram(
    'context_compression_duration_seconds',
    'Time spent compressing context'
)

# MessageStoreでメトリクス記録
class MessageStore:
    def add_message(self, role, content, **metadata):
        msg_id = # ... DB保存
        
        # メトリクス記録
        context_messages_total.labels(
            task_source=self.task_source,
            role=role
        ).inc()
        
        return msg_id
```

#### 12.3.2 アラート設定例

```yaml
# Prometheus alerting rules
groups:
  - name: context_storage
    rules:
      - alert: ContextStorageHighDiskUsage
        expr: sum(context_db_size_bytes) > 50 * 1024 * 1024 * 1024  # 50GB
        for: 10m
        annotations:
          summary: "Context storage disk usage is high"
          description: "Total context storage size: {{ $value | humanize }}B"
      
      - alert: ContextCompressionFailureRate
        expr: rate(context_compression_failures_total[5m]) > 0.1
        for: 5m
        annotations:
          summary: "High context compression failure rate"
          description: "{{ $value }} compressions failing per second"
```

## 13. 将来の拡張

### 13.1 高度なコンテキスト管理

#### 13.1.1 適応的コンテキスト長管理

```python
class AdaptiveContextManager:
    """タスクの複雑度に応じてコンテキスト長を動的調整"""
    
    def calculate_optimal_compression_threshold(
        self,
        task_complexity: str,  # "simple", "medium", "complex"
        available_context_length: int
    ) -> float:
        """タスクの複雑度に応じた圧縮閾値を計算"""
        thresholds = {
            "simple": 0.5,    # 早めに圧縮
            "medium": 0.7,    # 標準
            "complex": 0.85   # ギリギリまで保持
        }
        return thresholds.get(task_complexity, 0.7)
```

#### 13.1.2 セマンティック検索

```python
class SemanticContextSearch:
    """ベクトル検索によるコンテキスト検索"""
    
    def __init__(self, embedding_model):
        self.embedding_model = embedding_model
        self.vector_store = None  # Pinecone/Weaviate/etc
    
    def search_similar_contexts(
        self,
        query: str,
        top_k: int = 5
    ) -> list[dict]:
        """過去のコンテキストから類似のものを検索"""
        query_embedding = self.embedding_model.encode(query)
        results = self.vector_store.search(query_embedding, top_k=top_k)
        return results
```

### 13.2 分散ストレージ対応

#### 13.2.1 S3/GCSバックエンド

```python
class S3MessageStore(MessageStore):
    """S3バックエンドのメッセージストア"""
    
    def __init__(self, bucket_name: str, task_key: str, **kwargs):
        self.s3 = boto3.client('s3')
        self.bucket = bucket_name
        self.object_key = f"contexts/{task_key}/context.db"
        
        # ローカルキャッシュ
        self.local_cache = Path(f"/tmp/{task_key}/context.db")
        
        # S3からダウンロード（存在すれば）
        self._sync_from_s3()
        
        super().__init__(self.local_cache.parent, **kwargs)
    
    def _sync_from_s3(self):
        """S3から最新のDBをダウンロード"""
        try:
            self.s3.download_file(
                self.bucket,
                self.object_key,
                str(self.local_cache)
            )
        except Exception:
            # 新規作成の場合
            pass
    
    def _sync_to_s3(self):
        """ローカルDBをS3にアップロード"""
        self.s3.upload_file(
            str(self.db_path),
            self.bucket,
            self.object_key
        )
    
    def add_message(self, role, content, **metadata):
        msg_id = super().add_message(role, content, **metadata)
        
        # 定期的にS3に同期（例：10メッセージごと）
        if msg_id % 10 == 0:
            self._sync_to_s3()
        
        return msg_id
```

#### 13.2.2 PostgreSQL バックエンド

```python
class PostgreSQLMessageStore:
    """PostgreSQLバックエンド（大規模・エンタープライズ向け）"""
    
    def __init__(self, connection_string: str, task_key: str):
        self.conn = psycopg2.connect(connection_string)
        self.task_key = task_key
        self._init_schema()
    
    def _init_schema(self):
        """スキーマ初期化"""
        with self.conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id SERIAL PRIMARY KEY,
                    task_key TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT NOW(),
                    token_count INTEGER,
                    metadata JSONB
                );
                CREATE INDEX IF NOT EXISTS idx_messages_task_key 
                    ON messages(task_key);
                CREATE INDEX IF NOT EXISTS idx_messages_timestamp 
                    ON messages(task_key, timestamp);
            """)
            self.conn.commit()
    
    # MessageStoreと同じインターフェースを実装
    # ...
```

### 13.3 AI支援機能

#### 13.3.1 インテリジェント要約

```python
class IntelligentSummarizer:
    """AIによるインテリジェントな要約"""
    
    def __init__(self, llm_client):
        self.llm = llm_client
    
    def create_hierarchical_summary(
        self,
        messages: list[dict]
    ) -> dict:
        """階層的要約を作成
        
        Returns:
            {
                "high_level": "全体の概要",
                "key_decisions": ["決定事項1", "決定事項2"],
                "code_changes": ["変更1", "変更2"],
                "pending_tasks": ["残タスク1", "残タスク2"]
            }
        """
        prompt = self._create_summary_prompt(messages)
        response = self.llm.generate(prompt)
        return self._parse_structured_summary(response)
    
    def identify_important_messages(
        self,
        messages: list[dict]
    ) -> list[int]:
        """重要なメッセージを特定
        
        Returns:
            重要なメッセージのIDリスト
        """
        # LLMに重要度スコアリングを依頼
        # 重要度の高いメッセージは要約せずに保持
        pass
```

#### 13.3.2 コンテキスト最適化の自動学習

```python
class ContextOptimizationLearner:
    """コンテキスト管理パラメータの自動学習"""
    
    def __init__(self):
        self.history = []  # (params, performance)のペア
    
    def learn_optimal_params(self) -> dict:
        """最適なパラメータを学習
        
        - compression_threshold
        - max_memory_messages
        - min_messages_to_summarize
        
        などを、タスクの成功率、実行時間、コストなどから学習
        """
        # 強化学習やベイズ最適化で最適パラメータを探索
        pass
```

### 13.4 コスト最適化

#### 13.4.1 トークン使用量の最適化

```python
class TokenOptimizer:
    """トークン使用量を最小化"""
    
    def compress_code_blocks(self, content: str) -> str:
        """コードブロックを圧縮
        
        - 不要な空白・コメント削除
        - 変数名の短縮（マッピング保持）
        """
        pass
    
    def use_reference_instead_of_full_content(
        self,
        content: str,
        max_length: int = 1000
    ) -> str:
        """長いコンテンツは参照に置き換え
        
        例: "前回取得したファイル src/main.py (message #42参照)"
        """
        if len(content) > max_length:
            return f"[Content truncated, see message #{self.last_full_content_id}]"
        return content
```

#### 13.4.2 キャッシング戦略

```python
class LLMResponseCache:
    """LLM応答のキャッシング"""
    
    def __init__(self, cache_backend):
        self.cache = cache_backend  # Redis/Memcached
    
    def get_cached_response(
        self,
        messages: list[dict],
        model: str
    ) -> str | None:
        """同じコンテキストの応答をキャッシュから取得"""
        cache_key = self._compute_cache_key(messages, model)
        return self.cache.get(cache_key)
    
    def cache_response(
        self,
        messages: list[dict],
        model: str,
        response: str
    ):
        """応答をキャッシュ"""
        cache_key = self._compute_cache_key(messages, model)
        self.cache.set(cache_key, response, ttl=3600)  # 1時間
```

### 13.5 コンプライアンス対応

#### 13.5.1 GDPR対応

```python
class GDPRCompliantStorage:
    """GDPR準拠のストレージ"""
    
    def anonymize_personal_data(self, content: str) -> str:
        """個人情報の匿名化"""
        # 名前、メールアドレス、電話番号などを検出・匿名化
        pass
    
    def export_user_data(self, user_id: str) -> dict:
        """ユーザーデータのエクスポート（データポータビリティ）"""
        pass
    
    def delete_user_data(self, user_id: str):
        """ユーザーデータの削除（忘れられる権利）"""
        pass
```

#### 13.5.2 監査ログ

```python
class ComplianceAuditLog:
    """コンプライアンス監査ログ"""
    
    def log_data_access(
        self,
        user_id: str,
        task_id: str,
        action: str,
        data_category: str
    ):
        """データアクセスを記録"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "user_id": user_id,
            "task_id": task_id,
            "action": action,  # read/write/delete
            "data_category": data_category,  # personal/code/public
            "ip_address": request.remote_addr,
        }
        # 改ざん防止のため、ハッシュチェーン or ブロックチェーンに記録
        self._append_to_immutable_log(log_entry)
```

## 14. まとめ

### 14.1 実装のメリット

1. **メモリ効率**: 70-98%のメモリ削減（要約使用時は99%）
2. **永続性**: タスクコンテキストの永続化により中断・再開が可能
3. **デバッグ性**: 処理過程の完全なトレース可能
4. **スケーラビリティ**: マルチプロセス対応で並行処理が可能
5. **インテリジェント圧縮**: LLM要約により情報保持率90-95%
6. **マルチユーザー対応**: ユーザーごとの設定とコンテキスト分離
7. **シンプルさ**: SQLiteの使用により追加の依存が最小限

### 14.2 導入コスト

- **開発工数**: 約11週間（6フェーズ）
- **ディスク容量**: 1-3GB/月（30日保持、圧縮あり）
- **パフォーマンス**: LLM呼び出しで3-5%の遅延増加
- **学習コスト**: 低（既存コードとの互換性維持）

### 14.3 推奨事項

1. **段階的導入**: 
   - フェーズ1-4から開始（11週間中の最初の7週間）
   - 本番環境で1ヶ月程度テスト
   - その後フェーズ5-6（マルチプロセス対応と運用機能）を追加

2. **初期設定**: 
   - `context_storage.enabled=false`でスタート（後方互換）
   - 開発環境で十分テストしてから本番で有効化
   - マルチプロセスは本番環境のリソースに応じて2-4プロセスから開始

3. **監視強化**: 
   - ディスク使用量の監視（アラート設定）
   - コンテキスト圧縮の成功率監視
   - DBロックエラーの頻度監視

4. **定期メンテナンス**: 
   - 毎日の自動クリーンアップ（cron設定）
   - 週次のディスク使用量レビュー
   - 月次の統計レポート確認

### 14.4 成功指標（KPI）

| 指標 | 目標値 | 測定方法 |
|------|--------|----------|
| メモリ使用量削減 | 80%以上 | プロセスモニタリング |
| ディスク使用量 | < 5GB/月 | `du -sh logs/contexts` |
| LLM呼び出しオーバーヘッド | < 10% | パフォーマンステスト |
| コンテキスト圧縮成功率 | > 95% | ログ分析 |
| マルチプロセススケーラビリティ | 3.5倍@4プロセス | 負荷テスト |
| システム可用性 | > 99.5% | 稼働時間監視 |

### 14.5 リスクと軽減策

| リスク | 影響度 | 確率 | 軽減策 |
|--------|--------|------|--------|
| ディスク容量不足 | 高 | 中 | 自動クリーンアップ、アラート設定 |
| DBロック競合 | 中 | 低 | WALモード、タイムアウト調整 |
| 要約品質低下 | 中 | 低 | 要約プロンプト最適化、品質チェック |
| パフォーマンス劣化 | 低 | 低 | キャッシング、インデックス最適化 |
| データ損失 | 高 | 極低 | バックアップ、トランザクション制御 |

### 14.6 次のステップ

1. **仕様レビュー**: 開発チーム内でのレビュー（1週間）
2. **PoC開発**: 基本機能の概念実証（2週間）
3. **本実装開始**: フェーズ1から順次実装（11週間）
4. **テスト期間**: 統合テスト、負荷テスト（2週間）
5. **段階的展開**: 開発環境 → ステージング → 本番（4週間）

**総期間**: 約20週間（5ヶ月）

## 15. 参考資料

### 15.1 技術仕様

- [SQLite WAL Mode](https://www.sqlite.org/wal.html)
- [Python sqlite3 module](https://docs.python.org/3/library/sqlite3.html)
- [JSONLines形式](http://jsonlines.org/)
- [Python multiprocessing](https://docs.python.org/3/library/multiprocessing.html)

### 15.2 類似実装例

- **LangChain**: [ConversationBufferMemory](https://python.langchain.com/docs/modules/memory/types/buffer)
- **LlamaIndex**: [Chat Store](https://docs.llamaindex.ai/en/stable/module_guides/storing/chat_stores/)
- **Semantic Kernel**: [Memory Store](https://learn.microsoft.com/en-us/semantic-kernel/memories/)
- **AutoGPT**: [Context Management](https://github.com/Significant-Gravitas/Auto-GPT)

### 15.3 ベストプラクティス

- [メモリ効率的なPythonプログラミング](https://realpython.com/python-memory-management/)
- [SQLiteパフォーマンスチューニング](https://www.sqlite.org/optoverview.html)
- [マルチプロセスPythonアプリケーション設計](https://docs.python.org/3/library/concurrent.futures.html)
- [LLMコンテキスト管理のベストプラクティス](https://platform.openai.com/docs/guides/prompt-engineering)

### 15.4 関連ドキュメント

- [GitHub MCP Server](github-mcp-server.md)
- [クラス設計仕様](class_spec.md)
- [システム仕様](spec.md)
- [README](README.md)

---

**ドキュメントバージョン**: 2.0  
**作成日**: 2024-01-15  
**最終更新**: 2024-01-15  
**ステータス**: 設計フェーズ  
**対象システム**: Coding Agent v1.x  
**想定環境**: マルチユーザー・マルチプロセス本番環境
