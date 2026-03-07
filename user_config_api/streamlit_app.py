"""Streamlit管理画面メインエントリポイント.

ユーザーコンフィグ管理のログイン画面を提供します。
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# 親ディレクトリをPythonパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from app.database import init_db
from streamlit_custom.components import auth as custom_auth
from streamlit_custom.utils import session as custom_session

# ページ設定
st.set_page_config(
    page_title="ログイン - ユーザーコンフィグ管理",
    page_icon="🔐",
    layout="centered",
)

# データベース初期化
init_db()

# セッション初期化
custom_session.initialize_session()

# 認証済みの場合はダッシュボードまたはパスワード変更画面へリダイレクト
if custom_session.check_authentication():
    user = custom_session.get_current_user()
    if user and user.get("password_must_change"):
        # パスワード変更が必要な場合は強制変更画面へ
        st.switch_page("pages/00_force_change_password.py")
    else:
        st.switch_page("pages/01_dashboard.py")

# ログインフォーム表示
credentials = custom_auth.show_login_form()

if credentials:
    username, password = credentials
    if custom_auth.authenticate_user(username, password):
        st.success("ログインに成功しました")
        # パスワード変更要求フラグをチェック
        user = custom_session.get_current_user()
        if user and user.get("password_must_change"):
            st.switch_page("pages/00_force_change_password.py")
        else:
            st.switch_page("pages/01_dashboard.py")
