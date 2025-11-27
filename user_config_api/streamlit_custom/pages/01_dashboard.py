"""ダッシュボードページ.

ログイン後のメインダッシュボードを表示します。
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# 親ディレクトリをPythonパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.database import get_db_context
from app.services.user_service import UserService
from ..components.auth import show_logout_button
from ..utils.session import check_authentication, get_current_user

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
