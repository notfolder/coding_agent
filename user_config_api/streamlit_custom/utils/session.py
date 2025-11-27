"""Streamlitセッション管理.

認証状態やユーザー情報のセッション管理を提供します。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import streamlit as st

if TYPE_CHECKING:
    from app.models.user import User


def initialize_session() -> None:
    """セッション状態を初期化する.

    初回アクセス時にセッション変数を初期化します。
    """
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "user" not in st.session_state:
        st.session_state.user = None
    if "messages" not in st.session_state:
        st.session_state.messages = []


def check_authentication() -> bool:
    """認証状態をチェックする.

    Returns:
        認証済みの場合True

    """
    initialize_session()
    return st.session_state.authenticated


def get_current_user() -> dict[str, Any] | None:
    """現在のユーザー情報を取得する.

    Returns:
        ユーザー情報辞書、または None

    """
    initialize_session()
    return st.session_state.user


def set_user(user: User) -> None:
    """ユーザー情報をセッションに保存する.

    Args:
        user: Userオブジェクト

    """
    initialize_session()
    st.session_state.authenticated = True
    st.session_state.user = {
        "id": user.id,
        "username": user.username,
        "ldap_uid": user.ldap_uid,
        "ldap_email": user.ldap_email,
        "display_name": user.display_name,
        "is_admin": user.is_admin,
    }


def logout() -> None:
    """ログアウトする.

    セッション状態をクリアします。
    """
    initialize_session()
    st.session_state.authenticated = False
    st.session_state.user = None
    st.session_state.messages = []


def require_admin() -> bool:
    """管理者権限をチェックする.

    Returns:
        管理者の場合True

    Note:
        管理者でない場合、エラーメッセージを表示します。

    """
    if not check_authentication():
        st.error("ログインが必要です")
        return False

    user = get_current_user()
    if not user or not user.get("is_admin"):
        st.error("管理者権限が必要です")
        return False

    return True


def add_message(message: str, message_type: str = "info") -> None:
    """フラッシュメッセージを追加する.

    Args:
        message: メッセージ文字列
        message_type: メッセージタイプ（info, success, warning, error）

    """
    initialize_session()
    st.session_state.messages.append({"message": message, "type": message_type})


def show_messages() -> None:
    """フラッシュメッセージを表示する.

    表示後、メッセージはクリアされます。
    """
    initialize_session()
    messages = st.session_state.messages
    st.session_state.messages = []

    for msg in messages:
        msg_type = msg.get("type", "info")
        text = msg.get("message", "")
        if msg_type == "success":
            st.success(text)
        elif msg_type == "warning":
            st.warning(text)
        elif msg_type == "error":
            st.error(text)
        else:
            st.info(text)
