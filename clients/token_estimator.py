"""トークン数推定ユーティリティ.

文字数からトークン数を推定します。
"""

from __future__ import annotations


def estimate_tokens(text: str) -> int:
    """テキストからトークン数を推定する.
    
    推定方法:
    - 英語: 約4文字で1トークン
    - 日本語: 約1文字で1トークン
    - 混在テキスト: 文字種を判定して計算
    
    Args:
        text: トークン数を推定するテキスト
        
    Returns:
        推定トークン数
        
    """
    if not text:
        return 0
    
    # 簡易的な推定: 日本語文字数 + (英数字・記号文字数 / 4)
    japanese_chars = 0
    other_chars = 0
    
    for char in text:
        # 日本語文字（ひらがな、カタカナ、漢字）の判定
        code = ord(char)
        if (0x3040 <= code <= 0x309F or  # ひらがな
            0x30A0 <= code <= 0x30FF or  # カタカナ
            0x4E00 <= code <= 0x9FFF or  # 漢字
            0x3400 <= code <= 0x4DBF):   # 漢字拡張
            japanese_chars += 1
        else:
            other_chars += 1
    
    # 推定トークン数 = 日本語文字数 + (その他文字数 / 4)
    estimated_tokens = japanese_chars + (other_chars / 4)
    
    return int(estimated_tokens)


def estimate_messages_tokens(messages: list[dict[str, str]]) -> int:
    """メッセージリストからトークン数を推定する.
    
    Args:
        messages: メッセージの辞書リスト（role, contentを含む）
        
    Returns:
        推定トークン数
        
    """
    total_tokens = 0
    
    for message in messages:
        # roleのトークン数（固定）
        total_tokens += 4  # role, content等のキーとフォーマット
        
        # contentのトークン数
        content = message.get("content", "")
        if content:
            total_tokens += estimate_tokens(content)
        
        # function_call等の追加データ
        if "function_call" in message:
            func_call = message["function_call"]
            total_tokens += estimate_tokens(str(func_call))
    
    return total_tokens
