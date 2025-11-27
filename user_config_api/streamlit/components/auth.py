"""認証コンポーネント.

ログインフォームと認証処理を提供します。
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# 親ディレクトリをPythonパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.database import get_db_context
from app.services.auth_service import AuthService

from streamlit.utils.session import logout as session_logout
from streamlit.utils.session import set_user


def show_login_form() -> tuple[str, str] | None:
    """ログインフォームを表示する.

    Returns:
        (ユーザー名, パスワード)のタプル、またはNone

    """
    st.title("ユーザーコンフィグ管理")
    st.markdown("---")

    with st.form("login_form"):
        username = st.text_input(
            "ユーザー名",
            placeholder="Active Directoryのユーザー名を入力",
            help="sAMAccountNameを入力してください",
        )
        password = st.text_input(
            "パスワード",
            type="password",
            placeholder="パスワードを入力",
        )
        submitted = st.form_submit_button("ログイン", use_container_width=True)

        if submitted:
            if not username or not password:
                st.error("ユーザー名とパスワードを入力してください")
                return None
            return (username, password)

    return None


def authenticate_user(username: str, password: str) -> bool:
    """ユーザーを認証する.

    Args:
        username: ユーザー名
        password: パスワード

    Returns:
        認証成功の場合True

    """
    with get_db_context() as db:
        auth_service = AuthService(db)
        user = auth_service.authenticate(username, password)

        if user:
            set_user(user)
            return True
        st.error("ユーザー名またはパスワードが正しくありません")
        return False


def show_logout_button() -> bool:
    """ログアウトボタンを表示する.

    Returns:
        ログアウトがクリックされた場合True

    """
    if st.button("ログアウト", key="logout_btn"):
        session_logout()
        st.rerun()
        return True
    return False
