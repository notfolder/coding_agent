"""強制パスワード変更ページ.

password_must_change=Trueのユーザーが初回ログイン時にパスワードを変更するページです。
パスワード変更が完了するまで他の画面へのアクセスをブロックします。
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# 親ディレクトリをPythonパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.auth.password_policy import PasswordPolicy
from app.config import get_password_auth_config
from app.database import get_db_context
from app.services.user_service import UserService
from streamlit_custom.components.auth import show_logout_button
from streamlit_custom.utils.session import (
    check_authentication,
    get_current_user,
    set_user,
)

# ページ設定
st.set_page_config(
    page_title="パスワード変更 - ユーザーコンフィグ管理",
    page_icon="🔑",
    layout="centered",
)

# 認証チェック
if not check_authentication():
    st.warning("ログインが必要です")
    st.page_link("streamlit_app.py", label="ログインページへ", icon="🔐")
    st.stop()

# 現在のユーザー情報取得
user = get_current_user()

# password_must_changeがFalseの場合はダッシュボードへリダイレクト
if not user or not user.get("password_must_change"):
    st.switch_page("pages/01_dashboard.py")

# ヘッダー
col1, col2 = st.columns([4, 1])
with col1:
    st.title("パスワード変更")
with col2:
    show_logout_button()

st.markdown("---")

# 警告メッセージ
st.warning("⚠️ 初回ログインのため、パスワードを変更してください。変更が完了するまで他の画面にアクセスできません。")

# パスワードポリシーの表示
pw_config = get_password_auth_config()
policy = PasswordPolicy.from_config(pw_config)
st.info(f"パスワードポリシー: {policy.get_description()}")

st.markdown("---")

user_id = user.get("id")

with st.form("force_change_password_form"):
    st.markdown("### パスワード変更")

    current_password = st.text_input(
        "現在のパスワード",
        type="password",
        placeholder="現在のパスワードを入力",
    )
    new_password = st.text_input(
        "新しいパスワード",
        type="password",
        placeholder="新しいパスワードを入力",
    )
    confirm_password = st.text_input(
        "新しいパスワード（確認）",
        type="password",
        placeholder="新しいパスワードを再度入力",
    )

    submitted = st.form_submit_button("パスワードを変更する", use_container_width=True)

    if submitted:
        # 入力チェック
        if not current_password or not new_password or not confirm_password:
            st.error("すべての項目を入力してください")
        elif new_password != confirm_password:
            st.error("新しいパスワードと確認パスワードが一致しません")
        else:
            with get_db_context() as db:
                user_service = UserService(db)
                try:
                    user_service.change_password(user_id, current_password, new_password)
                    # セッション情報を更新
                    updated_user = user_service.get_user_by_id(user_id)
                    if updated_user:
                        set_user(updated_user)
                    st.success("パスワードを変更しました")
                    st.switch_page("pages/01_dashboard.py")
                except ValueError as e:
                    st.error(str(e))
