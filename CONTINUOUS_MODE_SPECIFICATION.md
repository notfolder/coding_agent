# Docker Compose 継続動作モード仕様書

## 1. 概要

### 1.1 目的
現在のcoding_agentは、cronによる定期実行でproducerとconsumerを動作させています。本仕様では、docker-composeを使用して、producerとconsumerをそれぞれ独立したコンテナとして継続的に動作させるモードを設計します。

### 1.2 背景
- cronベースの実行では、実行間隔の間に発生したタスクの処理に遅延が生じる
- docker-composeによる継続動作により、リアルタイムに近いタスク処理が可能になる
- コンテナ化により、スケーラビリティと運用管理が向上する

### 1.3 要求事項
- producerは設定ファイルで指定された時間（分単位）待機してからループ実行する
- consumerはsleep無しで、処理が終了次第すぐに次のタスクを取得してループ実行する
- 両モードとも、gracefulな停止をサポートする
- 既存のcron実行との互換性を維持する

### 1.4 対象範囲
- main.pyへの継続動作モード（`--continuous`オプション）の追加
- docker-compose.ymlへのproducerおよびconsumerサービスの追加
- 設定ファイルへの継続動作モード用設定項目の追加
- gracefulシャットダウン機構の実装

## 2. 現状分析

### 2.1 現在の実行方式

#### 2.1.1 cronベースの実行
```bash
# crontabでの設定例
*/5 * * * * /path/to/python main.py --mode producer
*/5 * * * * /path/to/python main.py --mode consumer
```

#### 2.1.2 main.pyのモード
- `--mode producer`: タスクを取得してキューに追加し、終了
- `--mode consumer`: キューからタスクを取得して処理し、キューが空になったら終了
- モード指定なし: producerとconsumerを順次実行

### 2.2 現在のdocker-compose.yml構成
- `user-config-api`: ユーザー設定APIサービス
- `web`: GitLab CEサービス
- `rabbitmq`: メッセージキューサービス

## 3. 継続動作モードの詳細設計

### 3.1 コマンドラインオプション

#### 3.1.1 新規オプション
main.pyに`--continuous`オプションを追加します。

**オプション仕様:**
- `--continuous`: 継続動作モードを有効化
- `--mode producer --continuous`: producerを継続動作させる
- `--mode consumer --continuous`: consumerを継続動作させる

**動作の違い:**
- `--continuous`なし: 現行通り、処理完了後に終了
- `--continuous`あり: 処理完了後も終了せず、ループを継続

### 3.2 Producer継続動作モード

#### 3.2.1 動作フロー

```
[起動]
  ↓
[初期化処理]
  ├─ ログ設定
  ├─ 設定ファイル読み込み
  ├─ MCPクライアント初期化
  └─ タスクキュー初期化
  ↓
[メインループ開始]
  ↓
  ┌─────────────────────────────────┐
  │                                 │
  │  [タスク取得・キュー追加処理]   │
  │    ↓                            │
  │  [指定時間待機]                 │
  │    ↓                            │
  │  [停止シグナルチェック]         │
  │    ├─ シグナル検出 → ループ終了 │
  │    └─ シグナルなし → ループ継続 │
  │                                 │
  └─────────────────────────────────┘
  ↓
[クリーンアップ処理]
  ↓
[終了]
```

#### 3.2.2 待機時間の設定

**設定方法:**
- 設定ファイル: `continuous.producer.interval_minutes`
- デフォルト値: 5分

**設定例:**
```yaml
# config.yamlへの追加
continuous:
  producer:
    # タスク取得間隔（分）
    interval_minutes: 5
```

#### 3.2.3 待機処理の実装方針

1. 指定分数を秒数に変換
2. 1秒単位でsleepしながら停止シグナルをチェック
3. 停止シグナル検出時は即座にループを終了
4. 待機時間経過後、次のタスク取得処理を実行

**擬似コード:**
```
待機処理:
  1. 待機秒数を計算（interval_minutes × 60）
  2. 経過時間を0に初期化
  3. ループ:
     a. 1秒sleep
     b. 経過時間を1秒加算
     c. 停止シグナルをチェック
        - シグナル検出: falseを返してループ終了
     d. 経過時間が待機秒数に達したらtrueを返す
```

### 3.3 Consumer継続動作モード

#### 3.3.1 動作フロー

```
[起動]
  ↓
[初期化処理]
  ├─ ログ設定
  ├─ 設定ファイル読み込み
  ├─ MCPクライアント初期化
  ├─ タスクキュー初期化
  └─ TaskHandler初期化
  ↓
[メインループ開始]
  ↓
  ┌─────────────────────────────────────┐
  │                                     │
  │  [停止シグナルチェック]             │
  │    ├─ シグナル検出 → ループ終了     │
  │    └─ シグナルなし → 処理継続       │
  │    ↓                                │
  │  [キューからタスク取得（タイムアウト付き）] │
  │    ├─ タスクあり → タスク処理へ     │
  │    └─ タイムアウト → ループ継続     │
  │    ↓                                │
  │  [タスク処理実行]                   │
  │    ↓                                │
  │  [ループ継続]                       │
  │                                     │
  └─────────────────────────────────────┘
  ↓
[クリーンアップ処理]
  ↓
[終了]
```

#### 3.3.2 キュー取得のタイムアウト設定

**設定方法:**
- 設定ファイル: `continuous.consumer.queue_timeout_seconds`
- デフォルト値: 30秒

**設定例:**
```yaml
# config.yamlへの追加
continuous:
  consumer:
    # キュー取得タイムアウト（秒）
    queue_timeout_seconds: 30
```

#### 3.3.3 sleepなし動作の実装方針

1. キューからのタスク取得時にタイムアウトを設定
2. タスクが存在する場合は即座に処理を開始
3. タイムアウト時はシグナルチェック後、再度キュー取得を試行
4. タスク処理完了後、sleepせずに次のタスク取得へ

**RabbitMQのタイムアウト対応:**
- RabbitMQTaskQueueクラスのget()メソッドにタイムアウト引数を追加
- basic_getを使用し、タイムアウト制御はループ内でのポーリングで実装
- タイムアウト時間を小さな間隔（例: 1秒）で分割し、停止シグナルチェックと組み合わせる
- タイムアウト時はNoneを返す

**InMemoryTaskQueueのタイムアウト対応:**
- 既存のget(timeout=)をそのまま利用
- タイムアウト時はNoneを返す

### 3.4 Gracefulシャットダウン

#### 3.4.1 停止シグナル

**停止ファイル:** `contexts/pause_signal`（既存の一時停止機能と同じファイルを使用）

継続動作モードでは、`contexts/pause_signal`ファイルの存在をチェックし、ファイルが存在する場合はgracefulシャットダウンを開始します。このファイルは既存の一時停止機能でも使用されており、継続動作モードでは一時停止ではなくプロセス終了として動作します。

#### 3.4.2 シャットダウン時の動作

**Producerの場合:**
1. 現在のタスク取得処理を完了
2. 取得したタスクをキューに追加
3. ログに停止メッセージを出力
4. プロセスを終了

**Consumerの場合:**
1. 現在処理中のタスクを完了させる
2. タスク完了後、新しいタスクを取得しない
3. ログに停止メッセージを出力
4. プロセスを終了

### 3.5 設定ファイルの拡張

#### 3.5.1 新規設定項目

```yaml
# config.yamlへの追加
continuous:
  # 継続動作モードの有効化（デフォルト: false）
  # 注: この設定よりコマンドラインオプション --continuous が優先される
  enabled: false
  
  producer:
    # タスク取得間隔（分）
    interval_minutes: 5
    
    # 起動時の初回実行を遅延させるか（デフォルト: false）
    # trueの場合、起動直後にinterval_minutes待機してから最初のタスク取得を行う
    delay_first_run: false
  
  consumer:
    # キュー取得タイムアウト（秒）
    queue_timeout_seconds: 30
    
    # タスク処理間の最小待機時間（秒、デフォルト: 0）
    # レート制限などが必要な場合に設定
    min_interval_seconds: 0
```

**注:** 停止シグナルファイルは`contexts/pause_signal`を使用します（config.yamlの`pause_resume.signal_file`設定と同じパス）。

### 3.6 docker-compose.ymlの拡張

#### 3.6.1 新規サービス定義

```yaml
# docker-compose.ymlへの追加
services:
  # 既存サービス（user-config-api, web, rabbitmq）は省略
  
  # Producer サービス
  coding-agent-producer:
    build: .
    container_name: coding-agent-producer
    command: ["python", "main.py", "--mode", "producer", "--continuous"]
    depends_on:
      - rabbitmq
      - user-config-api
    environment:
      # 必須環境変数
      - TASK_SOURCE=${TASK_SOURCE:-github}
      - GITHUB_PERSONAL_ACCESS_TOKEN=${GITHUB_PERSONAL_ACCESS_TOKEN}
      - GITLAB_PERSONAL_ACCESS_TOKEN=${GITLAB_PERSONAL_ACCESS_TOKEN:-}
      
      # RabbitMQ設定
      - RABBITMQ_HOST=rabbitmq
      - RABBITMQ_PORT=5672
      - RABBITMQ_USER=guest
      - RABBITMQ_PASSWORD=guest
      
      # LLM設定
      - LLM_PROVIDER=${LLM_PROVIDER:-openai}
      - OPENAI_API_KEY=${OPENAI_API_KEY:-}
      - OPENAI_BASE_URL=${OPENAI_BASE_URL:-https://api.openai.com/v1}
      - OPENAI_MODEL=${OPENAI_MODEL:-gpt-4o}
      
      # ログ設定
      - LOGS=/app/logs/producer.log
      - DEBUG=${DEBUG:-false}
    volumes:
      - ./logs:/app/logs
      - ./contexts:/app/contexts
    restart: unless-stopped
    # gracefulシャットダウンの猶予時間
    stop_grace_period: 30s
  
  # Consumer サービス
  coding-agent-consumer:
    build: .
    container_name: coding-agent-consumer
    command: ["python", "main.py", "--mode", "consumer", "--continuous"]
    depends_on:
      - rabbitmq
      - user-config-api
    environment:
      # 必須環境変数
      - TASK_SOURCE=${TASK_SOURCE:-github}
      - GITHUB_PERSONAL_ACCESS_TOKEN=${GITHUB_PERSONAL_ACCESS_TOKEN}
      - GITLAB_PERSONAL_ACCESS_TOKEN=${GITLAB_PERSONAL_ACCESS_TOKEN:-}
      
      # RabbitMQ設定
      - RABBITMQ_HOST=rabbitmq
      - RABBITMQ_PORT=5672
      - RABBITMQ_USER=guest
      - RABBITMQ_PASSWORD=guest
      
      # LLM設定
      - LLM_PROVIDER=${LLM_PROVIDER:-openai}
      - OPENAI_API_KEY=${OPENAI_API_KEY:-}
      - OPENAI_BASE_URL=${OPENAI_BASE_URL:-https://api.openai.com/v1}
      - OPENAI_MODEL=${OPENAI_MODEL:-gpt-4o}
      
      # ログ設定
      - LOGS=/app/logs/consumer.log
      - DEBUG=${DEBUG:-false}
    volumes:
      - ./logs:/app/logs
      - ./contexts:/app/contexts
    restart: unless-stopped
    # gracefulシャットダウンの猶予時間（タスク処理完了を待つ）
    # 注: タスク処理に時間がかかる場合（LLM呼び出し、ファイル操作等）、
    # 処理中のタスクを完了させるために十分な時間を確保する必要があります。
    # デフォルト: 300秒（5分）
    # - 短時間タスクが多い場合: 60s〜120s に短縮可能
    # - 長時間タスクがある場合: 600s 以上に延長を推奨
    # max_llm_process_numの設定値と平均処理時間を考慮して調整してください。
    stop_grace_period: 300s
```

#### 3.6.2 Consumerのスケールアウト

複数のConsumerを起動する場合:

```yaml
# docker-compose.override.yml（スケールアウト用）
services:
  coding-agent-consumer:
    deploy:
      replicas: 3
```

または、コマンドラインで指定:

```bash
docker-compose up -d --scale coding-agent-consumer=3
```

### 3.7 ヘルスチェック

#### 3.7.1 ヘルスチェックの実装方針

1. 定期的にヘルスチェックファイルを更新
2. ヘルスチェックファイルの最終更新時刻を確認
3. 一定時間以上更新がない場合、コンテナを異常と判定

**ヘルスチェックファイル:**
- Producer: `/app/healthcheck/producer.health`
- Consumer: `/app/healthcheck/consumer.health`

#### 3.7.2 docker-composeでのヘルスチェック設定

```yaml
services:
  coding-agent-producer:
    # ... 他の設定 ...
    healthcheck:
      test: ["CMD", "python", "-c", "import os, time; f='/app/healthcheck/producer.health'; exit(0 if os.path.exists(f) and time.time() - os.path.getmtime(f) < 600 else 1)"]
      interval: 60s
      timeout: 10s
      retries: 3
      start_period: 30s
  
  coding-agent-consumer:
    # ... 他の設定 ...
    healthcheck:
      test: ["CMD", "python", "-c", "import os, time; f='/app/healthcheck/consumer.health'; exit(0 if os.path.exists(f) and time.time() - os.path.getmtime(f) < 600 else 1)"]
      interval: 60s
      timeout: 10s
      retries: 3
      start_period: 30s
```

## 4. 既存機能との互換性

### 4.1 cronベース実行との互換性

- `--continuous`オプションなしの場合、現行通りの動作を維持
- 設定ファイルの`continuous.enabled`がtrueでも、`--continuous`オプションがない場合は単発実行
- 既存のcron設定をそのまま使用可能

### 4.2 一時停止・リジューム機能との連携

- 継続動作モードでも、`contexts/pause_signal`による停止制御は有効
- シグナル検出時の動作:
  - Producer: タスク取得後、キュー追加前にシグナルチェックし、検出時はプロセスを終了
  - Consumer: タスク処理完了後、次のタスク取得前にシグナルチェックし、検出時はプロセスを終了

### 4.3 ファイルロック機能

- Producerモードでは、既存のFileLock機能を継続して使用
- 複数Producerの同時実行を防止
- Consumerは複数インスタンスの同時実行を許可（RabbitMQによる排他制御）

## 5. ログとモニタリング

### 5.1 ログ出力

#### 5.1.1 継続動作モード固有のログ

**起動時:**
```
INFO - 継続動作モードで起動しました（Producer）
INFO - タスク取得間隔: 5分
```

**ループ実行時:**
```
INFO - タスク取得処理を開始します（ループ回数: 10）
INFO - 3件のタスクをキューに追加しました
INFO - 次のタスク取得まで5分待機します
```

**シャットダウン時:**
```
INFO - 停止シグナルを検出しました
INFO - 現在の処理を完了後、終了します
INFO - 継続動作モードを終了しました（Producer）
```

#### 5.1.2 ログローテーション

- 既存のDailyRotatingFileHandlerを継続使用
- Producerとconsumerで別々のログファイルを使用
  - `/app/logs/producer.log`
  - `/app/logs/consumer.log`

### 5.2 メトリクス

#### 5.2.1 収集するメトリクス

**Producer:**
- ループ実行回数
- タスク取得数（累計、直近）
- キュー追加成功/失敗数
- 最終タスク取得時刻

**Consumer:**
- ループ実行回数
- タスク処理数（累計、直近）
- タスク成功/失敗数
- 平均処理時間
- キュー待機時間

#### 5.2.2 メトリクス出力方式

1. **ログ出力**: 定期的にINFOレベルで統計情報を出力
2. **ヘルスチェックファイル**: JSON形式でメトリクスを記録

## 6. エラーハンドリング

### 6.1 Producer のエラーハンドリング

#### 6.1.1 タスク取得エラー

1. GitHub/GitLab API エラー:
   - 一時的なエラー（5xx）: 指数バックオフでリトライ
   - 認証エラー（401, 403）: ログ出力して終了
   - レート制限（429）: Retry-After ヘッダーに従い待機

2. MCP クライアントエラー:
   - 接続エラー: リトライ後、エラーログ出力して継続
   - タイムアウト: リトライ後、エラーログ出力して継続

#### 6.1.2 キュー追加エラー

1. RabbitMQ 接続エラー:
   - 既存の再接続機能（_reconnect）で対応
   - 再接続失敗時は指数バックオフでリトライ

### 6.2 Consumer のエラーハンドリング

#### 6.2.1 タスク処理エラー

1. LLM API エラー:
   - 既存のリトライ機能で対応
   - 最大リトライ回数超過時はタスクにエラーコメントを追加

2. MCP ツール実行エラー:
   - 既存のエラーハンドリングで対応
   - タスクにエラーを通知

#### 6.2.2 キュー取得エラー

1. RabbitMQ 接続エラー:
   - 再接続を試行
   - 再接続失敗時は指数バックオフでリトライ

### 6.3 回復不能エラー

以下のエラーはプロセスを終了し、Docker の restart ポリシーで再起動:

1. 設定ファイル読み込みエラー
2. MCPクライアント初期化エラー
3. 認証エラー（トークン無効）
4. 致命的な内部エラー

## 7. テストシナリオ

### 7.1 基本動作テスト

#### シナリオ1: Producer継続動作
1. `--mode producer --continuous`で起動
2. タスクが取得されることを確認
3. 指定間隔で待機することを確認
4. 待機後に再度タスク取得が行われることを確認
5. `contexts/pause_signal`でgracefulに終了することを確認

#### シナリオ2: Consumer継続動作
1. `--mode consumer --continuous`で起動
2. キューにタスクがない場合、タイムアウト後にループ継続を確認
3. タスク追加後、即座に処理開始を確認
4. タスク完了後、sleepなしで次のタスク取得を確認
5. `contexts/pause_signal`でgracefulに終了することを確認

### 7.2 スケーラビリティテスト

#### シナリオ3: 複数Consumer
1. docker-compose upで複数のConsumerを起動（replicas: 3）
2. 複数タスクをキューに追加
3. 各Consumerが異なるタスクを処理することを確認
4. タスクの重複処理がないことを確認

## 8. 運用ガイドライン

### 8.1 起動方法

#### 8.1.1 docker-composeでの起動

```bash
# 全サービス起動
docker-compose up -d

# Producer/Consumerのみ起動
docker-compose up -d coding-agent-producer coding-agent-consumer

# Consumerのスケールアウト
docker-compose up -d --scale coding-agent-consumer=3
```

#### 8.1.2 手動起動（デバッグ用）

```bash
# Producer継続動作
python main.py --mode producer --continuous

# Consumer継続動作
python main.py --mode consumer --continuous
```

### 8.2 停止方法

```bash
# docker-composeで停止
docker-compose stop coding-agent-producer coding-agent-consumer

# または停止ファイルを作成
touch contexts/pause_signal
```

### 8.3 ログ確認

```bash
# Producerログ
docker-compose logs -f coding-agent-producer

# Consumerログ
docker-compose logs -f coding-agent-consumer

# ファイルでの確認
tail -f logs/producer.log
tail -f logs/consumer.log
```

## 9. まとめ

### 9.1 主要な設計ポイント

1. **Producerの待機間隔設定**: 設定ファイルで分単位で指定可能
2. **Consumerのsleepなし動作**: タイムアウト付きキュー取得で即時処理を実現
3. **Gracefulシャットダウン**: `contexts/pause_signal`ファイルによる停止に対応
4. **既存機能との互換性**: cronベース実行、一時停止機能との共存
5. **スケーラビリティ**: Consumerの水平スケール対応

### 9.2 期待される効果

- タスク処理のリアルタイム性向上
- 運用管理の簡素化（docker-compose による一元管理）
- スケーラビリティの向上（Consumer の水平スケール）
- 監視・モニタリングの容易化

### 9.3 実装時の注意点

- 既存のmain.pyへの変更は最小限に抑える
- 新機能は`--continuous`オプション有効時のみ動作
- テストは単発実行と継続動作の両方で実施

本仕様に基づいて実装を進めることで、cronベースの定期実行から、docker-composeによる継続動作モードへの移行が可能になります。
