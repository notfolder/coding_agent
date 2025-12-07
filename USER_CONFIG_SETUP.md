# User Config API セットアップガイド

本ドキュメントは、ユーザー設定API（user_config_api）のセットアップ手順をまとめたものです。

---

## 1. 概要

User Config APIは、ユーザーごとのLLM設定を管理するためのWebアプリケーションです。

### 1.1 主要機能

- **ユーザー管理**: ユーザーの追加、編集、削除
- **LLM設定管理**: プロバイダー、モデル、APIキー、システムプロンプトの設定
- **Active Directory認証**: AD統合認証（オプション）
- **REST API**: コーディングエージェント向けの設定取得API
- **Streamlit管理画面**: ブラウザベースの管理UI
- **トークン使用量追跡**: ユーザーごとのLLM使用量の可視化

### 1.2 サービス構成

- **FastAPI (user-config-api)**: REST APIサーバー（ポート8080）
- **Streamlit (user-config-web)**: Web管理画面（ポート8501）
- **PostgreSQL**: タスク情報データベース（メインのcoding_agentと共有）
- **SQLite**: ユーザー設定データベース（独立）

---

## 2. セットアップ手順

### 2.1 環境変数の設定

`user_config_api/.env.sample`をコピーして`user_config_api/.env`ファイルを作成します：

```bash
cd user_config_api
cp .env.sample .env
```

`.env`ファイルを編集し、以下の**必須項目**を設定します：

```bash
# 必須: APIキー（強力なランダム文字列を使用）
API_SERVER_KEY=your-strong-random-api-key-here

# 必須: 暗号化キー（32バイトのランダムバイト列）
# 生成方法: python -c "import os; print(os.urandom(32).hex())"
ENCRYPTION_KEY=your-32-byte-hex-encryption-key-here

# AD認証設定（AD使用時のみ必須）
AD_BIND_PASSWORD=your-ad-service-account-password

# モック認証使用フラグ（開発環境用、本番環境では false）
USE_MOCK_AD=false

# データベース設定（Docker Compose使用時は不要）
# DATABASE_URL=sqlite:///./data/users.db
# TASK_DB_URL=postgresql://user:password@localhost:5432/coding_agent
```

### 2.2 暗号化キーの生成

**重要**: `ENCRYPTION_KEY`は32バイトのランダムバイト列をhex形式で指定します。

```bash
# Pythonで生成
python -c "import os; print(os.urandom(32).hex())"
```

生成された文字列を`.env`の`ENCRYPTION_KEY`に設定します。

### 2.3 Docker Composeでの起動

プロジェクトルートから以下を実行：

```bash
# User Config APIと管理画面を起動
docker-compose up -d user-config-api user-config-web

# ログ確認
docker-compose logs -f user-config-api user-config-web
```

### 2.4 初期管理者の作成

初回起動時に管理者ユーザーを作成します：

```bash
# コンテナ内でコマンド実行
docker-compose exec user-config-api python -m app.commands.create_admin \
  --username admin \
  --ldap-uid admin \
  --ldap-email admin@example.com
```

パスワードを入力すると、管理者ユーザーが作成されます。

### 2.5 アクセス確認

#### Web管理画面

ブラウザで http://localhost:8501 にアクセスします。

- 初期管理者でログイン
- ダッシュボードが表示されることを確認

#### REST API

```bash
# ヘルスチェック
curl http://localhost:8080/health

# 設定取得（要認証）
curl -H "Authorization: Bearer your-api-key-here" \
  http://localhost:8080/config/github/testuser
```

---

## 3. Active Directory連携（オプション）

### 3.1 AD設定

`user_config_api/config.yaml`を編集：

```yaml
ldap:
  server: ldap://your-ad-server.example.com
  base_dn: dc=example,dc=com
  bind_dn: cn=service-account,ou=Users,dc=example,dc=com
  user_search_base: ou=Users,dc=example,dc=com
  user_search_filter: (sAMAccountName={username})
```

### 3.2 サービスアカウント

AD認証用のサービスアカウントのパスワードを環境変数で設定：

```bash
AD_BIND_PASSWORD=your-ad-service-account-password
```

### 3.3 テスト用LDAP環境

開発環境でテスト用のLDAP環境を起動する場合：

```bash
# LDAP環境を含めて起動
docker-compose --profile ldap up -d

# LDAP Account Managerにアクセス
# http://localhost:8090
```

---

## 4. ユーザー管理

### 4.1 ユーザーの追加

Web管理画面で：

1. サイドバーから **User Management** を選択
2. **Add New User** ボタンをクリック
3. 以下を入力：
   - **Username**: GitHubまたはGitLabのユーザー名
   - **Platform**: `github` または `gitlab`
   - **LDAP UID**: AD認証時のUID
   - **Email**: メールアドレス
   - **Role**: `admin` または `user`
4. **Save** ボタンをクリック

### 4.2 LLM設定の編集

1. ユーザーを選択
2. **Edit** ボタンをクリック
3. LLM設定を編集：
   - **Provider**: `openai`, `ollama`, `lmstudio`
   - **Model**: モデル名
   - **API Key**: APIキー（暗号化して保存）
   - **Base URL**: エンドポイントURL
   - **System Prompt**: カスタムプロンプト
4. **Save** ボタンをクリック

### 4.3 ユーザーの無効化

1. ユーザーを選択
2. **Active** トグルをOFFにする
3. **Save** ボタンをクリック

無効化されたユーザーはログインできず、API経由での設定取得もできません。

---

## 5. トークン使用量の確認

### 5.1 ダッシュボード

Web管理画面のダッシュボードで以下を確認できます：

- **今日の使用量**: 本日のトークン数
- **今週の使用量**: 今週のトークン数
- **今月の使用量**: 今月のトークン数
- **使用量グラフ**: 時系列の使用量推移

### 5.2 ユーザー別使用量

1. サイドバーから **Token Usage** を選択
2. ユーザーごとの使用量を確認
3. 期間を選択してフィルタリング

---

## 6. コーディングエージェントとの連携

### 6.1 メインプロジェクトの設定

コーディングエージェントのプロジェクトルートの`.env`に以下を追加：

```bash
# ユーザー設定API使用フラグ
USE_USER_CONFIG_API=true

# ユーザー設定APIURL
USER_CONFIG_API_URL=http://user-config-api:8080

# ユーザー設定APIキー（user_config_api/.envのAPI_SERVER_KEYと同じ値）
USER_CONFIG_API_KEY=your-strong-random-api-key-here
```

### 6.2 動作確認

タスクを実行すると、タスクの作成者（Issue/PR作成者）のユーザー設定が自動的に適用されます：

1. GitHubでIssueを作成（作成者: `testuser`）
2. `coding agent`ラベルを付与
3. タスクが処理される際、`testuser`のLLM設定が使用される

ログで確認：

```bash
docker-compose logs consumer | grep "API経由でLLM設定を取得"
```

---

## 7. バックアップとリストア

### 7.1 データベースのバックアップ

```bash
# ユーザー設定データベースのバックアップ
docker-compose exec user-config-api cp /app/data/users.db /app/data/users.db.backup

# ホストにコピー
docker cp user-config-api:/app/data/users.db.backup ./users.db.backup
```

### 7.2 リストア

```bash
# ホストからコンテナにコピー
docker cp ./users.db.backup user-config-api:/app/data/users.db

# サービスを再起動
docker-compose restart user-config-api user-config-web
```

---

## 8. トラブルシューティング

### 8.1 管理画面にアクセスできない

- Docker Composeでサービスが起動しているか確認：`docker-compose ps`
- ポート8501が他のプロセスで使用されていないか確認
- ログを確認：`docker-compose logs user-config-web`

### 8.2 ログインできない

- 管理者ユーザーが作成されているか確認
- AD認証の場合、AD設定が正しいか確認
- モック認証モード（`USE_MOCK_AD=true`）で動作するか確認

### 8.3 API経由で設定が取得できない

- `API_SERVER_KEY`が正しく設定されているか確認
- ユーザーがアクティブ状態か確認
- APIのログを確認：`docker-compose logs user-config-api`

### 8.4 暗号化エラー

- `ENCRYPTION_KEY`が32バイト（64文字のhex）であることを確認
- データベースを削除して再作成（暗号化キーを変更した場合）

```bash
docker-compose down
docker volume rm coding_agent_user-config-data
docker-compose up -d user-config-api user-config-web
```

---

## 9. セキュリティ

### 9.1 APIキーの管理

- **強力なランダム文字列を使用**: 最低32文字以上
- **定期的に変更**: 3～6ヶ月ごとに変更を推奨
- **環境変数で管理**: ファイルに直接記載しない

### 9.2 暗号化キーの管理

- **絶対に変更しない**: 変更すると既存データが復号化できなくなる
- **安全に保管**: バックアップを安全な場所に保管
- **ローテーション**: 必要な場合は全データを再暗号化

### 9.3 本番環境の設定

- **HTTPS必須**: TLS 1.2以上を使用
- **モック認証無効**: `USE_MOCK_AD=false`
- **ファイアウォール**: 必要なポートのみを公開
- **定期バックアップ**: データベースを定期的にバックアップ

---

## 10. 関連ドキュメント

- **詳細仕様**: [docs/spec/USER_CONFIG_WEB_SPECIFICATION.md](docs/spec/USER_CONFIG_WEB_SPECIFICATION.md)
- **API仕様**: [docs/spec/USER_MANAGEMENT_API_SPEC.md](docs/spec/USER_MANAGEMENT_API_SPEC.md)
- **トークン追跡仕様**: [docs/spec/TOKEN_USAGE_TRACKING_SPECIFICATION.md](docs/spec/TOKEN_USAGE_TRACKING_SPECIFICATION.md)
- **テストガイド**: [user_config_api/TESTING.md](user_config_api/TESTING.md)

---

**文書バージョン:** 1.0  
**最終更新日:** 2024-12-07  
**ステータス:** 最新版
