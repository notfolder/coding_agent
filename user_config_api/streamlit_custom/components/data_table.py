"""データテーブルコンポーネント.

ページネーション付きデータテーブルを提供します。
"""

from __future__ import annotations

import math
from typing import Any

import streamlit as st


def show_search_filter(placeholder: str = "検索...", key: str = "search") -> str:
    """検索フィルタを表示する.

    Args:
        placeholder: プレースホルダーテキスト
        key: Streamlitウィジェットのキー

    Returns:
        入力された検索文字列

    """
    return st.text_input(
        "検索",
        placeholder=placeholder,
        key=key,
        label_visibility="collapsed",
    )


def show_pagination(total: int, page: int, per_page: int, key: str = "page") -> int:
    """ページネーションコントロールを表示する.

    Args:
        total: 総件数
        page: 現在のページ番号（1始まり）
        per_page: 1ページあたりの件数
        key: Streamlitウィジェットのキー

    Returns:
        選択されたページ番号

    """
    total_pages = max(1, math.ceil(total / per_page))

    # ページ番号が範囲外の場合は補正
    page = max(1, min(page, total_pages))

    col1, col2, col3, col4, col5 = st.columns([1, 1, 2, 1, 1])

    with col1:
        if st.button("<<", key=f"{key}_first", disabled=page <= 1):
            return 1

    with col2:
        if st.button("<", key=f"{key}_prev", disabled=page <= 1):
            return page - 1

    with col3:
        st.markdown(
            f"<div style='text-align: center;'>ページ {page} / {total_pages}</div>",
            unsafe_allow_html=True,
        )

    with col4:
        if st.button(">", key=f"{key}_next", disabled=page >= total_pages):
            return page + 1

    with col5:
        if st.button(">>", key=f"{key}_last", disabled=page >= total_pages):
            return total_pages

    return page


def show_data_table(
    data: list[dict[str, Any]],
    columns: list[str],
    column_labels: dict[str, str] | None = None,
    page: int = 1,
    per_page: int = 20,
    show_actions: bool = True,
    key_prefix: str = "table",
) -> tuple[int | None, str | None, dict[str, Any] | None]:
    """データテーブルを表示する.

    Args:
        data: データのリスト（辞書のリスト）
        columns: 表示するカラム名のリスト
        column_labels: カラム名のラベル辞書（オプション）
        page: 現在のページ番号
        per_page: 1ページあたりの件数
        show_actions: 操作ボタンを表示するか
        key_prefix: Streamlitウィジェットキーのプレフィックス

    Returns:
        (選択された行インデックス, アクション種別, 行データ)のタプル
        アクションがない場合は(None, None, None)

    """
    if not data:
        st.info("データがありません")
        return None, None, None

    # ラベルのデフォルト値
    if column_labels is None:
        column_labels = {}

    # ページネーション計算
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    page_data = data[start_idx:end_idx]

    # ヘッダー行
    header_cols = st.columns(len(columns) + (2 if show_actions else 0))
    for i, col_name in enumerate(columns):
        header_cols[i].markdown(f"**{column_labels.get(col_name, col_name)}**")
    if show_actions:
        header_cols[-2].markdown("**編集**")
        header_cols[-1].markdown("**削除**")

    st.markdown("---")

    # データ行
    selected_action: tuple[int | None, str | None, dict[str, Any] | None] = (
        None,
        None,
        None,
    )

    for row_idx, row in enumerate(page_data):
        actual_idx = start_idx + row_idx
        cols = st.columns(len(columns) + (2 if show_actions else 0))

        for i, col_name in enumerate(columns):
            value = row.get(col_name, "")
            # Booleanの表示変換
            if isinstance(value, bool):
                value = "Yes" if value else ""
            cols[i].write(value)

        if show_actions:
            if cols[-2].button(
                "編集", key=f"{key_prefix}_edit_{actual_idx}", use_container_width=True,
            ):
                selected_action = (actual_idx, "edit", row)
            if cols[-1].button(
                "削除", key=f"{key_prefix}_del_{actual_idx}", use_container_width=True,
            ):
                selected_action = (actual_idx, "delete", row)

    return selected_action
