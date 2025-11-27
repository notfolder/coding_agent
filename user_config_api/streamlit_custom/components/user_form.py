"""ユーザーフォームコンポーネント.

ユーザー追加・編集フォームを提供します。
"""

from __future__ import annotations

import re
from typing import Any

import streamlit as st


def validate_username(username: str) -> tuple[bool, str]:
    """ユーザー名のバリデーションを行う.

    Args:
        username: バリデーション対象のユーザー名

    Returns:
        (有効かどうか, エラーメッセージ)のタプル

    """
    if not username:
        return False, "ユーザー名を入力してください"

    if len(username) < 2:
        return False, "ユーザー名は2文字以上で入力してください"

    if len(username) > 255:
        return False, "ユーザー名は255文字以内で入力してください"

    # 英数字、ハイフン、アンダースコア、ドットのみ許可
    if not re.match(r"^[a-zA-Z0-9._-]+$", username):
        return False, "ユーザー名は英数字、ハイフン、アンダースコア、ドットのみ使用できます"

    return True, ""


def show_user_form(
    user: dict[str, Any] | None = None,
    key_prefix: str = "user_form",
) -> dict[str, Any] | None:
    """ユーザー追加・編集フォームを表示する.

    Args:
        user: 編集対象のユーザー情報（Noneの場合は新規作成モード）
        key_prefix: Streamlitウィジェットキーのプレフィックス

    Returns:
        フォーム送信時にユーザー情報辞書、キャンセル時にNone

    """
    is_edit_mode = user is not None
    title = "ユーザー編集" if is_edit_mode else "ユーザー追加"

    st.subheader(title)

    with st.form(f"{key_prefix}_form"):
        # ユーザー名
        username = st.text_input(
            "ユーザー名（GitHub/GitLab）",
            value=user.get("username", "") if user else "",
            help="GitHub/GitLabのユーザー名を入力してください",
            disabled=is_edit_mode,  # 編集時はユーザー名変更不可
        )

        # LDAP UID
        ldap_uid = st.text_input(
            "AD UID",
            value=user.get("ldap_uid", "") if user else "",
            help="Active DirectoryのsAMAccountNameを入力してください",
        )

        # LDAPメールアドレス
        ldap_email = st.text_input(
            "ADメールアドレス",
            value=user.get("ldap_email", "") if user else "",
            help="Active Directoryのメールアドレスを入力してください",
        )

        # 表示名
        display_name = st.text_input(
            "表示名",
            value=user.get("display_name", "") if user else "",
            help="画面に表示する名前を入力してください",
        )

        # 管理者フラグ
        is_admin = st.checkbox(
            "管理者権限を付与",
            value=user.get("is_admin", False) if user else False,
            help="チェックすると管理者権限が付与されます",
        )

        # アクティブフラグ
        is_active = st.checkbox(
            "アクティブ",
            value=user.get("is_active", True) if user else True,
            help="チェックを外すとユーザーは無効化されます",
        )

        col1, col2 = st.columns(2)
        with col1:
            submitted = st.form_submit_button("保存", use_container_width=True)
        with col2:
            cancelled = st.form_submit_button("キャンセル", use_container_width=True)

        if cancelled:
            return None

        if submitted:
            # バリデーション
            if not is_edit_mode:
                valid, error_msg = validate_username(username)
                if not valid:
                    st.error(error_msg)
                    return None

            return {
                "id": user.get("id") if user else None,
                "username": username,
                "ldap_uid": ldap_uid or None,
                "ldap_email": ldap_email or None,
                "display_name": display_name or None,
                "is_admin": is_admin,
                "is_active": is_active,
            }

    return None


def show_delete_confirmation(user: dict[str, Any], key_prefix: str = "delete") -> bool:
    """削除確認ダイアログを表示する.

    Args:
        user: 削除対象のユーザー情報
        key_prefix: Streamlitウィジェットキーのプレフィックス

    Returns:
        確認された場合True

    """
    st.warning(
        f"ユーザー「{user.get('username', '')}」を削除しますか？"
        "\n\nこの操作は取り消せません。",
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("削除する", key=f"{key_prefix}_confirm", use_container_width=True):
            return True
    with col2:
        if st.button(
            "キャンセル", key=f"{key_prefix}_cancel", use_container_width=True,
        ):
            return False

    return False
