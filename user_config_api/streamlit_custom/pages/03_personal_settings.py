"""個人設定ページ.

ユーザーが自身のLLM設定を変更するページです。
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
    page_title="個人設定 - ユーザーコンフィグ管理",
    page_icon="⚙️",
    layout="wide",
)

# 認証チェック
if not check_authentication():
    st.warning("ログインが必要です")
    st.page_link("streamlit_app.py", label="ログインページへ", icon="🔐")
    st.stop()

# 現在のユーザー情報
user = get_current_user()
user_id = user.get("id")

# ヘッダー
col1, col2 = st.columns([4, 1])
with col1:
    st.title("個人設定")
with col2:
    show_logout_button()

st.markdown("---")

# ユーザー情報表示
st.markdown("### アカウント情報")
col1, col2, col3 = st.columns(3)

with col1:
    st.text_input("ユーザー名", value=user.get("username", ""), disabled=True)

with col2:
    st.text_input("メールアドレス", value=user.get("ldap_email", ""), disabled=True)

with col3:
    role = "管理者" if user.get("is_admin") else "一般ユーザー"
    st.text_input("権限", value=role, disabled=True)

st.markdown("---")
st.markdown("### モデル設定")
st.markdown("使用するLLMモデル名を設定できます。")

# 現在の設定を取得
current_model = ""
with get_db_context() as db:
    user_service = UserService(db)
    user_config = user_service.get_user_config(user_id)
    if user_config:
        current_model = user_config.llm_model or ""

# モデル設定フォーム
with st.form("model_settings_form"):
    llm_model = st.text_input(
        "LLMモデル名",
        value=current_model,
        placeholder="gpt-4o, gpt-4-turbo, etc.",
        help="使用するLLMモデル名を入力してください。空の場合はデフォルト設定が使用されます。",
    )

    st.markdown("※ 使用するLLMモデル名を入力してください")

    col1, col2 = st.columns(2)

    with col1:
        submitted = st.form_submit_button("保存", use_container_width=True)

    with col2:
        reset = st.form_submit_button("デフォルトに戻す", use_container_width=True)

    if submitted:
        with get_db_context() as db:
            user_service = UserService(db)
            user_service.update_user_config(
                user_id,
                llm_model=llm_model or None,
            )
            st.success("設定を保存しました")
            st.rerun()

    if reset:
        with get_db_context() as db:
            user_service = UserService(db)
            # 設定を削除してデフォルトに戻す
            user_service.delete_user_config(user_id)
            st.success("設定をデフォルトに戻しました")
            st.rerun()

# 現在の設定表示
st.markdown("---")
st.markdown("### 現在の設定")

if current_model:
    st.info(f"カスタム設定: モデル = **{current_model}**")
else:
    st.info("デフォルト設定を使用しています")
