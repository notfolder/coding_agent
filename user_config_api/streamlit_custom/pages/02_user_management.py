"""ユーザー管理ページ.

管理者がユーザーの追加・編集・削除を行うページです。
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
from ..components.data_table import show_data_table, show_pagination, show_search_filter
from ..components.user_form import show_delete_confirmation, show_user_form
from ..utils.session import check_authentication, get_current_user, require_admin

# ページ設定
st.set_page_config(
    page_title="ユーザー管理 - ユーザーコンフィグ管理",
    page_icon="👥",
    layout="wide",
)

# 認証チェック
if not check_authentication():
    st.warning("ログインが必要です")
    st.page_link("streamlit_app.py", label="ログインページへ", icon="🔐")
    st.stop()

# 管理者権限チェック
if not require_admin():
    st.stop()

# セッション状態の初期化
if "um_page" not in st.session_state:
    st.session_state.um_page = 1
if "um_search" not in st.session_state:
    st.session_state.um_search = ""
if "um_active_only" not in st.session_state:
    st.session_state.um_active_only = False
if "um_mode" not in st.session_state:
    st.session_state.um_mode = "list"  # list, add, edit, delete
if "um_selected_user" not in st.session_state:
    st.session_state.um_selected_user = None

# ヘッダー
col1, col2 = st.columns([4, 1])
with col1:
    st.title("ユーザー管理")
with col2:
    show_logout_button()

st.markdown("---")


def reset_to_list_mode() -> None:
    """リスト表示モードにリセットする."""
    st.session_state.um_mode = "list"
    st.session_state.um_selected_user = None


# メインコンテンツ
if st.session_state.um_mode == "list":
    # ユーザー追加ボタン
    if st.button("+ ユーザー追加", type="primary"):
        st.session_state.um_mode = "add"
        st.rerun()

    # 検索・フィルタ
    col1, col2 = st.columns([3, 1])
    with col1:
        search = st.text_input(
            "検索",
            value=st.session_state.um_search,
            placeholder="ユーザー名または表示名で検索...",
            key="search_input",
        )
        if search != st.session_state.um_search:
            st.session_state.um_search = search
            st.session_state.um_page = 1
            st.rerun()

    with col2:
        active_only = st.checkbox(
            "アクティブのみ",
            value=st.session_state.um_active_only,
            key="active_only_checkbox",
        )
        if active_only != st.session_state.um_active_only:
            st.session_state.um_active_only = active_only
            st.session_state.um_page = 1
            st.rerun()

    # ユーザー一覧を取得
    per_page = 20
    with get_db_context() as db:
        user_service = UserService(db)
        users = user_service.get_all_users(
            active_only=st.session_state.um_active_only,
            search=st.session_state.um_search or None,
            limit=per_page,
            offset=(st.session_state.um_page - 1) * per_page,
        )
        total_users = user_service.count_users(active_only=st.session_state.um_active_only)

    # データをリスト形式に変換
    user_data = [
        {
            "id": u.id,
            "username": u.username,
            "display_name": u.display_name or "",
            "is_admin": u.is_admin,
            "is_active": u.is_active,
            "ldap_uid": u.ldap_uid,
            "ldap_email": u.ldap_email,
        }
        for u in users
    ]

    # データテーブル表示
    columns = ["username", "display_name", "is_admin", "is_active"]
    column_labels = {
        "username": "ユーザー名",
        "display_name": "表示名",
        "is_admin": "管理者",
        "is_active": "有効",
    }

    idx, action, row_data = show_data_table(
        user_data,
        columns,
        column_labels=column_labels,
        page=st.session_state.um_page,
        per_page=per_page,
        key_prefix="user_table",
    )

    if action == "edit" and row_data:
        st.session_state.um_mode = "edit"
        st.session_state.um_selected_user = row_data
        st.rerun()
    elif action == "delete" and row_data:
        st.session_state.um_mode = "delete"
        st.session_state.um_selected_user = row_data
        st.rerun()

    # ページネーション
    st.markdown("---")
    new_page = show_pagination(
        total_users,
        st.session_state.um_page,
        per_page,
        key="user_pagination",
    )
    if new_page != st.session_state.um_page:
        st.session_state.um_page = new_page
        st.rerun()

elif st.session_state.um_mode == "add":
    # ユーザー追加フォーム
    if st.button("← 戻る"):
        reset_to_list_mode()
        st.rerun()

    result = show_user_form(key_prefix="add_user")

    if result:
        with get_db_context() as db:
            user_service = UserService(db)
            try:
                user_service.create_user(
                    result["username"],
                    ldap_uid=result["ldap_uid"],
                    ldap_email=result["ldap_email"],
                    display_name=result["display_name"],
                    is_admin=result["is_admin"],
                    is_active=result["is_active"],
                )
                st.success(f"ユーザー「{result['username']}」を作成しました")
                reset_to_list_mode()
                st.rerun()
            except ValueError as e:
                st.error(str(e))

elif st.session_state.um_mode == "edit":
    # ユーザー編集フォーム
    if st.button("← 戻る"):
        reset_to_list_mode()
        st.rerun()

    selected_user = st.session_state.um_selected_user
    if selected_user:
        result = show_user_form(user=selected_user, key_prefix="edit_user")

        if result:
            with get_db_context() as db:
                user_service = UserService(db)
                try:
                    user_service.update_user(
                        result["id"],
                        ldap_uid=result["ldap_uid"],
                        ldap_email=result["ldap_email"],
                        display_name=result["display_name"],
                        is_admin=result["is_admin"],
                        is_active=result["is_active"],
                    )
                    st.success(f"ユーザー「{result['username']}」を更新しました")
                    reset_to_list_mode()
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

elif st.session_state.um_mode == "delete":
    # 削除確認
    if st.button("← 戻る"):
        reset_to_list_mode()
        st.rerun()

    selected_user = st.session_state.um_selected_user
    if selected_user:
        confirmed = show_delete_confirmation(selected_user, key_prefix="delete_user")

        if confirmed:
            with get_db_context() as db:
                user_service = UserService(db)
                # 論理削除（is_active=Falseにする）
                user_service.delete_user(selected_user["id"], soft_delete=True)
                st.success(f"ユーザー「{selected_user['username']}」を無効化しました")
                reset_to_list_mode()
                st.rerun()
