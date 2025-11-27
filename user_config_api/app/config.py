"""設定ファイル読み込み.

config.yamlからアプリケーション設定を読み込みます。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """config.yamlを読み込む.

    Args:
        config_path: 設定ファイルのパス（Noneの場合は自動検出）

    Returns:
        設定辞書

    """
    if config_path is None:
        # Dockerコンテナ内での実行を優先
        paths = [
            Path("/app/config.yaml"),
            Path("config.yaml"),
            Path(__file__).parent.parent.parent / "config.yaml",
        ]
        for path in paths:
            if path.exists():
                config_path = path
                break
        else:
            return {}
    else:
        config_path = Path(config_path)

    try:
        with config_path.open() as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def get_api_key(config: dict[str, Any] | None = None) -> str:
    """APIキーを取得する.

    環境変数を優先し、なければconfig.yamlから取得します。

    Args:
        config: 設定辞書（Noneの場合は読み込む）

    Returns:
        APIキー文字列

    """
    # 環境変数から取得
    env_api_key = os.environ.get("API_SERVER_KEY")
    if env_api_key:
        return env_api_key

    # config.yamlから取得
    if config is None:
        config = load_config()

    config_api_key = config.get("api_server", {}).get("api_key", "")
    if config_api_key:
        return config_api_key

    return "default-api-key"


def get_database_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """データベース設定を取得する.

    Args:
        config: 設定辞書（Noneの場合は読み込む）

    Returns:
        データベース設定辞書

    """
    if config is None:
        config = load_config()

    default_config = {
        "url": "sqlite:///./data/users.db",
        "echo": False,
        "pool_size": 5,
        "max_overflow": 10,
    }

    # 環境変数を優先
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        default_config["url"] = db_url

    # config.yamlから取得
    db_config = config.get("database", {})
    default_config.update(db_config)

    return default_config


def get_ad_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Active Directory設定を取得する.

    Args:
        config: 設定辞書（Noneの場合は読み込む）

    Returns:
        AD設定辞書

    """
    if config is None:
        config = load_config()

    return config.get("active_directory", {})


def get_llm_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """LLM設定を取得する.

    Args:
        config: 設定辞書（Noneの場合は読み込む）

    Returns:
        LLM設定辞書

    """
    if config is None:
        config = load_config()

    return config.get("llm", {})


def get_system_prompt(config: dict[str, Any] | None = None) -> str:
    """システムプロンプトを取得する.

    Args:
        config: 設定辞書（Noneの場合は読み込む）

    Returns:
        システムプロンプト文字列

    """
    if config is None:
        config = load_config()

    # config.yamlから直接取得
    if "system_prompt" in config:
        return config["system_prompt"]

    # system_prompt.txtから読み込み
    paths = [
        Path("/app/system_prompt.txt"),
        Path("system_prompt.txt"),
        Path(__file__).parent.parent.parent.parent / "system_prompt.txt",
    ]

    for path in paths:
        try:
            if path.exists():
                with path.open() as f:
                    return f.read().strip()
        except Exception:
            continue

    return "あなたは優秀なコーディングアシスタントです。"
