"""ユーザーフォームコンポーネント.

ユーザー追加・編集フォームを提供します。
"""

from __future__ import annotations

import re
from typing import Any

import streamlit as st

from app.config import get_password_auth_config
from app.auth.password_policy import PasswordPolicy


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

    # パスワードポリシー取得
    pw_config = get_password_auth_config()
    policy = PasswordPolicy.from_config(pw_config)

    with st.form(f"{key_prefix}_form"):
        # ユーザー名
        username = st.text_input(
            "ユーザー名（GitHub/GitLab）",
            value=user.get("username", "") if user else "",
            help="GitHub/GitLabのユーザー名を入力してください",
            disabled=is_edit_mode,  # 編集時はユーザー名変更不可
        )

        # 認証タイプ（新規作成時も編集時も選択可能）
        current_auth_type = user.get("auth_type", "ldap") if user else "ldap"
        auth_type_index = 0 if current_auth_type == "ldap" else 1
        auth_type = st.radio(
            "認証タイプ",
            options=["ldap", "password"],
            index=auth_type_index,
            format_func=lambda x: "LDAP / Active Directory" if x == "ldap" else "パスワード認証",
            horizontal=True,
            help="ユーザーの認証方法を選択してください",
        )

        # LDAP UID（LDAP認証タイプの場合のみ）
        ldap_uid = st.text_input(
            "AD UID",
            value=user.get("ldap_uid", "") if user else "",
            help="Active DirectoryのsAMAccountNameを入力してください（LDAP認証の場合）",
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

        # パスワード設定
        initial_password = ""
        confirm_password = ""
        # 新規作成でpassword認証、または編集でauth_typeがpasswordに変更された場合
        show_password_input = False
        if not is_edit_mode and auth_type == "password":
            # 新規作成でpassword認証
            show_password_input = True
            password_label = "初期パスワード"
            password_help = "ユーザーが初回ログイン時に変更するパスワードを設定します"
        elif is_edit_mode and auth_type == "password" and current_auth_type == "ldap":
            # 編集でLDAP→password認証に変更
            show_password_input = True
            password_label = "新しいパスワード"
            password_help = "パスワード認証に変更するための新しいパスワードを設定します"
            st.warning("認証タイプをLDAPからパスワード認証に変更します。新しいパスワードを設定してください。")
        
        if show_password_input:
            st.info(f"パスワードポリシー: {policy.get_description()}")
            initial_password = st.text_input(
                password_label,
                type="password",
                placeholder="パスワードを入力",
                help=password_help,
            )
            confirm_password = st.text_input(
                f"{password_label}（確認）",
                type="password",
                placeholder="パスワードを再度入力",
            )
        elif is_edit_mode and auth_type == "ldap" and current_auth_type == "password":
            # 編集でpassword→LDAP認証に変更
            st.warning("認証タイプをパスワード認証からLDAPに変更します。パスワード情報はクリアされます。")

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

            # パスワード認証タイプの場合のバリデーション
            auth_type_changed = is_edit_mode and auth_type != current_auth_type
            if (not is_edit_mode and auth_type == "password") or \
               (is_edit_mode and auth_type == "password" and current_auth_type == "ldap"):
                if not initial_password:
                    st.error("パスワードを入力してください")
                    return None
                if initial_password != confirm_password:
                    st.error("パスワードと確認パスワードが一致しません")
                    return None

            result: dict[str, Any] = {
                "id": user.get("id") if user else None,
                "username": username,
                "ldap_uid": ldap_uid or None,
                "ldap_email": ldap_email or None,
                "display_name": display_name or None,
                "is_admin": is_admin,
                "is_active": is_active,
                "auth_type": auth_type,
            }
            # パスワードが入力された場合（新規作成またはLDAP→password変更時）
            if initial_password:
                result["initial_password"] = initial_password
            return result

    return None


def show_delete_confirmation(user: dict[str, Any], key_prefix: str = "delete") -> bool:
    """削除確認ダイアログを表示する.

    Args:
        user: 削除対象のユーザー情報
        key_prefix: Streamlitウィジェットキーのプレフィックス

    Returns:
        削除ボタンがクリックされた場合True、キャンセルの場合False

    """
    st.warning(
        f"ユーザー「{user.get('username', '')}」を削除しますか？"
        "\n\nこの操作は取り消せません。",
    )

    col1, col2 = st.columns(2)
    with col1:
        confirm_clicked = st.button("削除する", key=f"{key_prefix}_confirm", use_container_width=True, type="primary")
    with col2:
        cancel_clicked = st.button(
            "キャンセル", key=f"{key_prefix}_cancel", use_container_width=True,
        )

    # ボタンがクリックされた場合のみTrueまたはFalseを返す
    # どちらもクリックされていない場合は、親のコードで処理を継続
    if confirm_clicked:
        return True
    if cancel_clicked:
        return False
    
    # ボタンがクリックされていない場合はNoneを返す（表示のみ）
    return None
