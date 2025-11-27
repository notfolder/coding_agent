"""暗号化ユーティリティ.

AES-256-GCMを使用したデータ暗号化・復号化機能を提供します。
"""

from __future__ import annotations

import base64
import os
import secrets

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def get_encryption_key() -> bytes:
    """暗号化キーを取得する.

    環境変数ENCRYPTION_KEYから取得します。
    キーが設定されていない場合は、開発用のデフォルトキーを使用します。

    Returns:
        32バイトの暗号化キー

    """
    key_str = os.environ.get("ENCRYPTION_KEY")
    if key_str:
        # Base64エンコードされたキーをデコード
        try:
            key = base64.b64decode(key_str)
            if len(key) == 32:
                return key
        except Exception:
            pass
        # 文字列からキーを生成（32バイトになるようにパディング/トランケート）
        key = key_str.encode("utf-8")
        if len(key) < 32:
            key = key.ljust(32, b"\0")
        else:
            key = key[:32]
        return key

    # 開発用デフォルトキー（本番環境では必ず環境変数を設定すること）
    return b"dev-encryption-key-32-bytes!!"[:32].ljust(32, b"\0")


def encrypt_value(plaintext: str, key: bytes | None = None) -> str:
    """文字列をAES-256-GCMで暗号化する.

    Args:
        plaintext: 暗号化する平文
        key: 暗号化キー（Noneの場合は環境変数から取得）

    Returns:
        Base64エンコードされた暗号文（nonce + tag + ciphertext）

    """
    if not plaintext:
        return ""

    if key is None:
        key = get_encryption_key()

    # 12バイトのnonceを生成
    nonce = secrets.token_bytes(12)

    # AES-256-GCM暗号化
    cipher = Cipher(algorithms.AES(key), modes.GCM(nonce), backend=default_backend())
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(plaintext.encode("utf-8")) + encryptor.finalize()

    # nonce(12) + tag(16) + ciphertext を結合してBase64エンコード
    encrypted_data = nonce + encryptor.tag + ciphertext
    return base64.b64encode(encrypted_data).decode("utf-8")


def decrypt_value(encrypted: str, key: bytes | None = None) -> str:
    """AES-256-GCMで暗号化された文字列を復号化する.

    Args:
        encrypted: Base64エンコードされた暗号文
        key: 暗号化キー（Noneの場合は環境変数から取得）

    Returns:
        復号化された平文

    Raises:
        ValueError: 復号化に失敗した場合

    """
    if not encrypted:
        return ""

    if key is None:
        key = get_encryption_key()

    try:
        # Base64デコード
        encrypted_data = base64.b64decode(encrypted)

        # nonce(12) + tag(16) + ciphertext を分離
        nonce = encrypted_data[:12]
        tag = encrypted_data[12:28]
        ciphertext = encrypted_data[28:]

        # AES-256-GCM復号化
        cipher = Cipher(
            algorithms.AES(key), modes.GCM(nonce, tag), backend=default_backend(),
        )
        decryptor = cipher.decryptor()
        plaintext = decryptor.update(ciphertext) + decryptor.finalize()

        return plaintext.decode("utf-8")
    except Exception as e:
        raise ValueError(f"復号化に失敗しました: {e}") from e


def generate_encryption_key() -> str:
    """新しい暗号化キーを生成する.

    Returns:
        Base64エンコードされた32バイトのキー

    """
    key = secrets.token_bytes(32)
    return base64.b64encode(key).decode("utf-8")
