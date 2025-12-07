# タスク進捗コメント更新機能 修正仕様書

## 1. 概要

### 1.1 背景と課題
現在の実装では、タスク実行中に多数のコメントが生成され、Issue/MRのコメント欄が非常に長くなってしまう問題がある。

**現在のコメント生成箇所:**
- `_post_phase_comment()`: フェーズ変更ごとに新規コメント投稿
- `_post_llm_call_comment()`: LLM呼び出し完了ごとに新規コメント投稿
- `_post_tool_call_before_comment()`: ツール実行前に新規コメント投稿
- `_post_tool_call_after_comment()`: ツール実行後に新規コメント投稿
- `_post_llm_error_comment()`: LLMエラー時に新規コメント投稿
- `_post_tool_error_comment()`: ツールエラー時に新規コメント投稿

**問題点:**
1. タスク実行中に数十～数百のコメントが生成される
2. Issue/MRが読みづらくなる
3. GitLab/GitHubのUI動作が重くなる可能性がある
4. 重要な情報が埋もれてしまう

### 1.2 修正方針
**タスク起動時に作成した最初のコメントを更新し続ける方式**に変更する。

**目指す動作:**
1. タスク開始時に1つの進捗コメントを投稿
2. 以降、すべての進捗情報はそのコメントを更新して追記
3. エラー発生時も同一コメント内に追記
4. タスク完了/失敗時に最終状態を反映

**メリット:**
- コメント数が大幅に削減（1タスク = 1コメント）
- Issue/MRの可読性向上
- 進捗の一元管理
- タイムライン形式で経過を確認可能

## 2. 設計

### 2.1 進捗コメント管理クラス

新しいクラス `ProgressCommentManager` を作成し、進捗コメントの更新を一元管理する。

**責務:**
- 進捗コメントの初期作成
- 進捗情報の追記・更新
- フォーマット管理（Markdown形式）
- コメントIDの管理

**配置場所:**
- `handlers/progress_comment_manager.py`

### 2.2 コメント構造

進捗コメントは以下のセクション構造を持つ:

```markdown
# 🤖 タスク実行進捗

## 📊 実行状態
- **現在フェーズ**: {phase_name}
- **ステータス**: {status}
- **最新コメント**: {llm_comment}
- **進捗**: {action_counter}/{total_actions} アクション完了
- **LLM呼び出し回数**: {llm_call_count}
- **開始時刻**: {start_time}
- **最終更新**: {last_update_time}

## 🎯 チェックリスト
- [x] **task_1**: リポジトリ構造の確認
- [ ] **task_2**: ファイル作成
- [ ] **task_3**: 実行確認とコミット

## 📝 実行履歴

<details>
<summary>ここをクリックして詳細を表示</summary>

### [HH:MM:SS] 🎯 Planning Phase - ▶️ Started
計画フェーズを開始しました

### [HH:MM:SS] ✅ Planning Phase - ✅ Completed
実行計画の作成が完了しました

### [HH:MM:SS] ⚙️ Execution Phase - ▶️ Started
アクション実行を開始しました

### [HH:MM:SS] 🔧 ツール呼び出し - text_editor
**引数**: {"command": "view", "path": "/workspace/project"}

### [HH:MM:SS] ✅ ツール完了 - text_editor
結果: 成功

### [HH:MM:SS] ❌ エラー発生 - command-executor
**エラー内容**: Command execution failed
**発生したアクション**: task_3
</details>

---
*タスク開始: 2025-12-06 12:34:56 | 最終更新: 2025-12-06 12:45:23*
```

### 2.3 クラス設計

#### ProgressCommentManager

```python
class ProgressCommentManager:
    """タスク実行の進捗コメントを管理するクラス"""
    
    def __init__(
        self,
        task: Any,
        logger: logging.Logger,
        enabled: bool = True,
    ) -> None:
        """初期化
        
        Args:
            task: Taskオブジェクト（comment/update_commentメソッドを持つ）
            logger: ロガー
            enabled: 進捗コメント機能の有効/無効
        """
        
    def create_initial_comment(self, task_info: str = "") -> int | str | None:
        """タスク開始時の初期コメントを作成
        
        Args:
            task_info: タスク情報（省略可能）
            
        Returns:
            作成したコメントのID
        """
        
    def update_status(
        self,
        phase: str,
        status: str,
        action_counter: int = 0,
        total_actions: int = 0,
        llm_call_count: int = 0,
    ) -> None:
        """実行状態セクションを更新
        
        Args:
            phase: 現在フェーズ名
            status: ステータス（running/completed/failed等）
            action_counter: 完了アクション数
            total_actions: 総アクション数
            llm_call_count: LLM呼び出し回数
        """
        
    def add_history_entry(
        self,
        entry_type: str,
        title: str,
        details: str = "",
        timestamp: datetime | None = None,
    ) -> None:
        """実行履歴にエントリを追加
        
        Args:
            entry_type: エントリタイプ（phase/llm_call/tool_call/error/assumption等）
            title: エントリタイトル
            details: 詳細情報
            timestamp: タイムスタンプ（Noneの場合は現在時刻）
        """
    
    def set_llm_comment(self, comment: str | None) -> None:
        """LLMからのコメントを設定
        
        LLM応答にcommentフィールドがある場合のみ呼び出される。
        実行状態セクションの「最新コメント」に反映される。
        
        Args:
            comment: LLM応答のcommentフィールドの内容（Noneの場合は「なし」と表示）
        """
        
    def update_checklist(
        self,
        checklist_items: list[dict[str, Any]],
        completed_count: int,
    ) -> None:
        """チェックリストセクションを更新
        
        Args:
            checklist_items: チェックリスト項目のリスト
            completed_count: 完了済み項目数
        """
        
    def finalize(
        self,
        final_status: str,
        summary: str = "",
    ) -> None:
        """タスク完了/失敗時の最終更新
        
        Args:
            final_status: 最終ステータス（completed/failed）
            summary: サマリー情報
        """
```

### 2.4 PlanningCoordinatorとの統合

`PlanningCoordinator`に`ProgressCommentManager`を統合する。

**変更点:**

1. **初期化時**に`ProgressCommentManager`を作成
2. **既存のコメント投稿メソッド**を`ProgressCommentManager`の呼び出しに置き換え
3. **checklist_comment_id**の役割を進捗コメントIDとして統一

**置き換え対象:**
- `_post_phase_comment()` → `progress_manager.add_history_entry()`
- `_post_llm_call_comment()` → `progress_manager.add_history_entry()` + `progress_manager.update_status()`
- `_post_tool_call_before_comment()` → `progress_manager.add_history_entry()`
- `_post_tool_call_after_comment()` → `progress_manager.add_history_entry()`
- `_post_llm_error_comment()` → `progress_manager.add_history_entry()`
- `_post_tool_error_comment()` → `progress_manager.add_history_entry()`

**チェックリスト更新:**
- 既存の`_update_checklist_on_replan()`等のチェックリスト更新処理を`progress_manager.update_checklist()`に統合

### 2.5 設定

`config.yaml`に進捗コメント機能の設定を追加:

```yaml
# タスク進捗コメント機能
progress_comment:
  enabled: true  # 進捗コメント機能の有効/無効
  
  # 履歴エントリの最大保持数（古いものから削除）
  max_history_entries: 100
```

既存の`llm_call_comments`設定は削除。

## 3. 実装詳細

### 3.1 ProgressCommentManager実装

**ファイル:** `handlers/progress_comment_manager.py`

**主要メソッド:**

1. `_build_comment_content()`: コメント全体を構築
2. `_format_status_section()`: 実行状態セクションのMarkdown生成
   - `llm_comment`がNoneの場合は「最新コメント: なし」
   - `llm_comment`がある場合は「最新コメント: {llm_comment}」（100文字超過で省略）
3. `_format_history_section()`: 実行履歴セクションのMarkdown生成
4. `_format_checklist_section()`: チェックリストセクションのMarkdown生成
5. `_update_comment()`: コメントをIssue/MRに反映（update_comment呼び出し）

**状態管理:**
- `comment_id`: 進捗コメントのID
- `start_time`: タスク開始時刻
- `last_update_time`: 最終更新時刻
- `current_phase`: 現在フェーズ
- `current_status`: 現在ステータス
- `action_counter`: 完了アクション数
- `total_actions`: 総アクション数
- `llm_call_count`: LLM呼び出し回数
- `llm_comment`: LLM応答のcommentフィールド（最新のもの、Noneの場合あり）
- `history_entries`: 実行履歴エントリのリスト
- `checklist_items`: チェックリスト項目のリスト

**LLMコメント処理ルール:**
1. LLM呼び出し後、応答をパースしてcommentフィールドを探す
2. commentフィールドが存在する場合:
   - `set_llm_comment(comment)`を呼び出して状態を更新
   - 実行状態セクションの「最新コメント」に表示
3. commentフィールドが存在しない場合:
   - `set_llm_comment(None)`を呼び出し
   - 実行状態セクションに「最新コメント: なし」と表示
4. commentフィールドは**必須ではない**（フェーズによって有無が異なる）

### 3.2 PlanningCoordinator修正

**変更箇所:**

1. **`__init__()`**:
   - `ProgressCommentManager`のインスタンス化
   - 既存の`llm_call_comments_enabled`等の削除

2. **`run()`**:
   - 開始時に`progress_manager.create_initial_comment()`呼び出し
   - 終了時に`progress_manager.finalize()`呼び出し

3. **各フェーズメソッド**:
   - `_post_phase_comment()`呼び出しを`progress_manager.add_history_entry()`に置き換え
   - 同時に`progress_manager.update_status()`で状態更新

4. **LLM呼び出し処理**:
   - LLM応答（dict or str）から`comment`フィールドを抽出
   - `progress_manager.set_llm_comment(comment_or_none)`でコメント設定
   - commentフィールドがある場合は履歴にも追加: `progress_manager.add_history_entry()`
   - `progress_manager.update_status()`で状態更新（llm_call_count含む）

5. **`_execute_action()`**:
   - ツール呼び出し前後のコメント投稿を`progress_manager.add_history_entry()`に置き換え

6. **エラーハンドリング**:
   - エラーコメント投稿を`progress_manager.add_history_entry()`に置き換え

7. **チェックリスト更新**:
   - `_update_checklist()`メソッドを`progress_manager.update_checklist()`に統合

## 4. テスト方針

### 4.1 単体テスト

**テスト対象:** `ProgressCommentManager`

**テストケース:**
1. 初期コメント作成のテスト
2. 状態セクション更新のテスト
3. 履歴エントリ追加のテスト
4. チェックリスト更新のテスト
5. 最終更新のテスト
6. 履歴エントリ上限超過時の削除動作テスト
7. コメント構築のフォーマットテスト
8. LLMコメントの反映テスト:
   - commentフィールドがある場合の表示テスト
   - commentフィールドがない場合（None）の表示テスト
   - 長いコメント（100文字超）の省略表示テスト

### 4.2 統合テスト

**テスト対象1:** `PlanningCoordinator` + `ProgressCommentManager`

**テストケース:**
1. タスク実行全体でコメントが1つだけ作成されることの確認
2. 各フェーズで適切に進捗コメントが更新されることの確認
3. エラー発生時に進捗コメントに追記されることの確認
4. タスク完了時に最終状態が反映されることの確認

**テスト対象2:** `PrePlanningManager` + `ProgressCommentManager`

**テストケース:**
1. PrePlanningフェーズの開始通知が進捗コメントに追加されることの確認
2. タスク理解完了通知が進捗コメントに追加されることの確認
3. 情報収集完了通知が進捗コメントに追加されることの確認
4. 推測通知が進捗コメントに追加されることの確認
5. PrePlanningManager独自のコメントが作成されないことの確認

**テスト対象3:** `PlanningCoordinator` + `PrePlanningManager` + `ProgressCommentManager`

**テストケース:**
1. タスク開始から完了まで1つの進捗コメントのみ作成されることの確認
2. PrePlanningフェーズからPlanningフェーズへの遷移が進捗コメントに反映されることの確認
3. PrePlanningフェーズとPlanningフェーズの履歴が統一されたコメントに記録されることの確認

### 4.3 手動テスト

実際のGitLab/GitHub環境で:
1. hello_world.py作成タスクを実行して進捗コメント動作確認（PrePlanning含む）
2. エラー発生タスクで履歴セクションの動作確認
3. 長時間実行タスクで履歴エントリ上限の動作確認
4. 推測が発生するタスクで推測通知の動作確認

## 5. PrePlanningManagerへの適用

### 5.1 現状分析

`PrePlanningManager`は独自のコメント投稿処理を持っている:

**現在のコメント投稿メソッド:**
- `_post_start_notification()`: 開始通知（新規コメント）
- `_post_understanding_complete_notification()`: 理解完了通知（新規コメント）
- `_post_collection_complete_notification()`: 収集完了通知（新規コメント）
- `_post_assumption_notification()`: 推測通知（新規コメント）
- `_post_comment()`: 共通コメント投稿処理

**問題点:**
- 計画前情報収集フェーズでも4つ以上のコメントが生成される
- PlanningCoordinatorとは別のコメント投稿方式を使用
- 進捗管理が統一されていない

### 5.2 統合方針

`PrePlanningManager`も`ProgressCommentManager`を使用して、PlanningCoordinatorと統一した進捗管理を行う。

**統合方法:**

1. **コメントの統合**:
   - PrePlanningフェーズもPlanningCoordinatorの進捗コメントに統合
   - PrePlanningManager独自のコメントは作成せず、ProgressCommentManagerに委譲

2. **ProgressCommentManagerの共有**:
   - PlanningCoordinatorが作成したProgressCommentManagerをPrePlanningManagerに渡す
   - PrePlanningManagerはProgressCommentManagerを使って履歴エントリを追加

3. **既存メソッドの置き換え**:
   ```python
   # Before
   self._post_start_notification()
   
   # After
   self.progress_manager.add_history_entry(
       entry_type="phase",
       title="🔍 Pre Planning Phase - ▶️ Started",
       details="タスク内容を理解し、計画に必要な情報を収集しています...",
   )
   ```

### 5.3 PrePlanningManager修正内容

**変更箇所:**

1. **`__init__()`**:
   ```python
   def __init__(
       self,
       config: dict[str, Any],
       llm_client: Any,
       mcp_clients: dict[str, Any],
       task: Any,
       logger: logging.Logger,
       progress_manager: ProgressCommentManager | None = None,  # 追加
   ) -> None:
       # ...
       self.progress_manager = progress_manager
   ```

2. **`_post_start_notification()`の置き換え**:
   ```python
   def _post_start_notification(self) -> None:
       """開始通知を投稿する."""
       if self.progress_manager:
           self.progress_manager.add_history_entry(
               entry_type="phase",
               title="🔍 Pre Planning Phase - ▶️ Started",
               details="タスク内容を理解し、計画に必要な情報を収集しています...",
           )
   ```

3. **`_post_understanding_complete_notification()`の置き換え**:
   ```python
   def _post_understanding_complete_notification(self) -> None:
       """理解完了通知を投稿する."""
       if not self.understanding_result or not self.progress_manager:
           return
           
       request_understanding = self.understanding_result.get("request_understanding", {})
       # ... (既存のフォーマット処理)
       
       details = f"""**タスク種別**: {task_type}
**主な目標**: {primary_goal}
**期待される成果物**:
{deliverables_str}
**スコープ**: {in_scope_str} (対象外: {out_scope_str})
*理解の確信度: {confidence:.0%}*"""
       
       self.progress_manager.add_history_entry(
           entry_type="phase",
           title="📋 Request Understanding - ✅ Completed",
           details=details,
       )
   ```

4. **`_post_collection_complete_notification()`の置き換え**:
   ```python
   def _post_collection_complete_notification(self) -> None:
       """収集完了通知を投稿する."""
       if not self.progress_manager:
           return
           
       # ... (既存の収集結果まとめ処理)
       
       details = f"""**収集完了**: {len(collected_items)}件
**推測適用**: {len(assumed_items)}件
{collected_str}
{assumed_str}"""
       
       self.progress_manager.add_history_entry(
           entry_type="phase",
           title="📦 Information Collection - ✅ Completed",
           details=details,
       )
   ```

5. **`_post_assumption_notification()`の置き換え**:
   ```python
   def _post_assumption_notification(self, assumption: dict[str, Any]) -> None:
       """推測通知を投稿する."""
       if not self.progress_manager:
           return
           
       info_id = assumption.get("info_id", "unknown")
       value = assumption.get("assumed_value", "")
       reasoning = assumption.get("reasoning", "")
       confidence = assumption.get("confidence", 0.0)
       
       details = f"""**項目**: {info_id}
**推測値**: {value}
**理由**: {reasoning}
**確信度**: {confidence:.0%}"""
       
       self.progress_manager.add_history_entry(
           entry_type="assumption",
           title="⚠️ Information Assumed",
           details=details,
       )
   ```

6. **`_post_comment()`の削除**:
   - 独自のコメント投稿メソッドは不要になるため削除

### 5.4 PlanningCoordinatorの修正

PrePlanningManagerに`ProgressCommentManager`を渡すための修正:

```python
def _init_pre_planning_manager(self, pre_planning_config: dict[str, Any]) -> None:
    """PrePlanningManagerを初期化する."""
    from handlers.pre_planning_manager import PrePlanningManager

    self.pre_planning_manager = PrePlanningManager(
        config=pre_planning_config,
        llm_client=self.llm_client,
        mcp_clients=self.mcp_clients,
        task=self.task,
        logger=self.logger,
        progress_manager=self.progress_manager,  # 追加
    )
```

## 6. 成功基準

以下の条件を満たすこと:

1. ✅ 1タスクあたり1つの進捗コメントのみ作成される
2. ✅ PrePlanningフェーズの情報も進捗コメントに統合される
3. ✅ すべてのLLM応答のコメントが進捗コメント内に記録される
4. ✅ すべてのフェーズ・イベントが進捗コメント内に記録される
5. ✅ エラー情報が適切に履歴セクションに追記される
6. ✅ チェックリストが正常に更新される
7. ✅ タスク完了/失敗時に最終状態が反映される
8. ✅ 既存のタスク実行ロジックが正常に動作する
9. ✅ GitLab/GitHub両方で動作する
10. ✅ PrePlanningManagerとPlanningCoordinatorで統一されたコメント管理

## 7. まとめ

本仕様により、タスク実行中のコメント数を大幅に削減し、Issue/MRの可読性を向上させる。

実装完了後は、ユーザーフィードバックを収集し、必要に応じてフォーマットや表示内容を調整する。
