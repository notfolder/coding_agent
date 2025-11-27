"""暗号化ユーティリティのテスト."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# 親ディレクトリをPythonパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.utils.encryption import (
    decrypt_value,
    encrypt_value,
    generate_encryption_key,
    get_encryption_key,
)


class TestEncryption:
    """暗号化テストクラス."""

    def test_encrypt_decrypt_roundtrip(self) -> None:
        """暗号化と復号化のラウンドトリップテスト."""
        plaintext = "test-api-key-12345"
        key = get_encryption_key()

        encrypted = encrypt_value(plaintext, key)
        decrypted = decrypt_value(encrypted, key)

        assert decrypted == plaintext
        assert encrypted != plaintext

    def test_encrypt_empty_string(self) -> None:
        """空文字列の暗号化テスト."""
        result = encrypt_value("")
        assert result == ""

    def test_decrypt_empty_string(self) -> None:
        """空文字列の復号化テスト."""
        result = decrypt_value("")
        assert result == ""

    def test_encrypt_unicode(self) -> None:
        """Unicode文字列の暗号化テスト."""
        plaintext = "日本語テスト文字列🔐"
        key = get_encryption_key()

        encrypted = encrypt_value(plaintext, key)
        decrypted = decrypt_value(encrypted, key)

        assert decrypted == plaintext

    def test_different_encryptions_are_different(self) -> None:
        """同じ平文でも毎回異なる暗号文が生成されることを確認."""
        plaintext = "test-value"
        key = get_encryption_key()

        encrypted1 = encrypt_value(plaintext, key)
        encrypted2 = encrypt_value(plaintext, key)

        # nonceが毎回異なるため、暗号文も異なる
        assert encrypted1 != encrypted2

        # ただし、どちらも同じ平文に復号化される
        assert decrypt_value(encrypted1, key) == plaintext
        assert decrypt_value(encrypted2, key) == plaintext

    def test_decrypt_with_wrong_key_fails(self) -> None:
        """異なるキーでの復号化が失敗することを確認."""
        plaintext = "secret-data"
        key1 = b"key1-32-bytes-here-0000000000001"
        key2 = b"key2-32-bytes-here-0000000000002"

        encrypted = encrypt_value(plaintext, key1)

        with pytest.raises(ValueError, match="復号化に失敗"):
            decrypt_value(encrypted, key2)

    def test_generate_encryption_key(self) -> None:
        """暗号化キー生成テスト."""
        key1 = generate_encryption_key()
        key2 = generate_encryption_key()

        # キーはBase64エンコードされた44文字の文字列
        assert len(key1) == 44
        assert len(key2) == 44

        # 毎回異なるキーが生成される
        assert key1 != key2

    def test_get_encryption_key_from_env(self) -> None:
        """環境変数からの暗号化キー取得テスト."""
        test_key = "test-encryption-key-32-bytes!!"
        os.environ["ENCRYPTION_KEY"] = test_key

        try:
            key = get_encryption_key()
            # キーは32バイトに調整される
            assert len(key) == 32
        finally:
            del os.environ["ENCRYPTION_KEY"]
