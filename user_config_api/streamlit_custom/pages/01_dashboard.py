"""ダッシュボードページ.

ログイン後のメインダッシュボードを表示します。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# 親ディレクトリをPythonパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.database import get_db_context
from app.services.token_usage_service import TokenUsageService
from app.services.user_service import UserService
from streamlit_custom.components.auth import show_logout_button
from streamlit_custom.utils.session import check_authentication, get_current_user

# ページ設定
st.set_page_config(
    page_title="ダッシュボード - ユーザーコンフィグ管理",
    page_icon="🏠",
    layout="wide",
)

# 認証チェック
if not check_authentication():
    st.warning("ログインが必要です")
    st.page_link("streamlit_app.py", label="ログインページへ", icon="🔐")
    st.stop()

# 現在のユーザー情報
user = get_current_user()

# ヘッダー
col1, col2 = st.columns([4, 1])
with col1:
    st.title("ダッシュボード")
with col2:
    show_logout_button()

st.markdown("---")

# ウェルカムメッセージ
display_name = user.get("display_name") or user.get("username", "ユーザー")
st.markdown(f"### ようこそ、{display_name} さん")

# 統計情報
with get_db_context() as db:
    user_service = UserService(db)
    total_users = user_service.count_users()
    active_users = user_service.count_users(active_only=True)
    configured_users = user_service.count_users_with_config()

col1, col2, col3 = st.columns(3)

with col1:
    st.metric(
        label="総ユーザー数",
        value=total_users,
        help="登録されている全ユーザー数",
    )

with col2:
    st.metric(
        label="アクティブユーザー数",
        value=active_users,
        help="有効なユーザー数",
    )

with col3:
    st.metric(
        label="設定済みユーザー数",
        value=configured_users,
        help="LLM設定が完了しているユーザー数",
    )

# トークン使用量セクション
st.markdown("---")
st.markdown("### トークン使用量")

# 現在のユーザーのトークン使用量を取得
# TokenUsageServiceはエラー時にデフォルト値（0）を返すよう設計されている
token_service = TokenUsageService()
username = user.get("username", "")

# キャッシュを使用してトークン使用量を取得（5分間キャッシュ）
@st.cache_data(ttl=300)
def get_cached_token_usage(user: str) -> dict:
    """キャッシュされたトークン使用量を取得する."""
    return token_service.get_user_token_usage(user)

token_usage = get_cached_token_usage(username)

# トークン使用量メトリクス
token_col1, token_col2, token_col3 = st.columns(3)

with token_col1:
    st.metric(
        label="今日のトークン",
        value=f"{token_usage['today']:,}",
        help="本日のトークン使用量",
    )

with token_col2:
    st.metric(
        label="今週のトークン",
        value=f"{token_usage['this_week']:,}",
        help="今週のトークン使用量",
    )

with token_col3:
    st.metric(
        label="今月のトークン",
        value=f"{token_usage['this_month']:,}",
        help="今月のトークン使用量",
    )

# トークン使用量履歴グラフ
st.markdown("### トークン使用量推移")

# 期間選択とグラフタイプ選択
graph_col1, graph_col2 = st.columns(2)

with graph_col1:
    period_options = {"7日": 7, "30日": 30, "90日": 90}
    selected_period = st.selectbox(
        "期間選択",
        options=list(period_options.keys()),
        index=1,  # デフォルトは30日
        key="token_history_period",
    )
    days = period_options[selected_period]

with graph_col2:
    chart_type = st.selectbox(
        "グラフタイプ",
        options=["折れ線", "棒"],
        index=0,
        key="token_chart_type",
    )

# 履歴データを取得（キャッシュ使用）
@st.cache_data(ttl=300)
def get_cached_history(user: str, num_days: int) -> dict:
    """キャッシュされた履歴データを取得する."""
    return token_service.get_user_daily_history(user, num_days)

history_data = get_cached_history(username, days)

# DataFrameに変換
if history_data["history"]:
    df = pd.DataFrame(history_data["history"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")

    # グラフ表示
    if chart_type == "折れ線":
        st.line_chart(df["tokens"])
    else:
        st.bar_chart(df["tokens"])
else:
    st.info("トークン使用履歴がありません")

# 管理者向け全ユーザートークン使用状況
if user.get("is_admin"):
    st.markdown("---")
    st.markdown("### 全ユーザートークン使用状況")

    # キャッシュを使用して全ユーザーデータを取得（5分間キャッシュ）
    @st.cache_data(ttl=300)
    def get_cached_all_users() -> list:
        """キャッシュされた全ユーザートークン使用量を取得する."""
        return token_service.get_all_users_token_usage()

    all_users_usage = get_cached_all_users()

    if all_users_usage:
        # DataFrameに変換して表示
        users_df = pd.DataFrame(all_users_usage)
        users_df.columns = ["ユーザー名", "今日", "今週", "今月", "累計"]

        # カンマ区切りでフォーマット
        for col in ["今日", "今週", "今月", "累計"]:
            users_df[col] = users_df[col].apply(lambda x: f"{x:,}")

        st.dataframe(
            users_df,
            use_container_width=True,
            hide_index=True,
        )

        # ユーザー選択によるグラフ表示
        st.markdown("#### ユーザー別履歴グラフ")

        selected_user = st.selectbox(
            "ユーザーを選択",
            options=[u["username"] for u in all_users_usage],
            key="admin_user_select",
        )

        if selected_user:
            selected_user_history = token_service.get_user_daily_history(
                selected_user, days,
            )

            if selected_user_history["history"]:
                user_df = pd.DataFrame(selected_user_history["history"])
                user_df["date"] = pd.to_datetime(user_df["date"])
                user_df = user_df.set_index("date")

                st.write(f"**{selected_user}** のトークン使用量推移")
                if chart_type == "折れ線":
                    st.line_chart(user_df["tokens"])
                else:
                    st.bar_chart(user_df["tokens"])
            else:
                st.info(f"{selected_user} のトークン使用履歴がありません")
    else:
        st.info("トークン使用データがありません")

# ナビゲーション
st.markdown("---")
st.markdown("### メニュー")

col1, col2 = st.columns(2)

with col1:
    if user.get("is_admin"):
        st.page_link(
            "pages/02_user_management.py",
            label="ユーザー管理",
            icon="👥",
            help="ユーザーの追加・編集・削除を行います",
        )
    else:
        st.info("ユーザー管理は管理者のみ利用可能です")

with col2:
    st.page_link(
        "pages/03_personal_settings.py",
        label="個人設定",
        icon="⚙️",
        help="LLMモデルなどの個人設定を行います",
    )

# ユーザー情報
st.markdown("---")
st.markdown("### アカウント情報")

info_col1, info_col2 = st.columns(2)

with info_col1:
    st.text_input("ユーザー名", value=user.get("username", ""), disabled=True)
    st.text_input("メールアドレス", value=user.get("ldap_email", ""), disabled=True)

with info_col2:
    st.text_input("表示名", value=user.get("display_name", ""), disabled=True)
    role = "管理者" if user.get("is_admin") else "一般ユーザー"
    st.text_input("権限", value=role, disabled=True)
