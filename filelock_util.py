"""
ファイルロックユーティリティ.

このモジュールは、複数プロセス間での排他制御を実現するための
ファイルロック機能を提供します。同一ファイルに対する同時アクセスを
防止するために使用されます。
"""

import os
import sys
from typing import Any, Optional, TextIO

import portalocker


class FileLock:
    """
    ファイルベースの排他制御ロック.
    
    ファイルシステムを使用してプロセス間の排他制御を実現します。
    コンテキストマネージャーとして使用することで、自動的にロックの
    取得と解放を行います。
    """

    def __init__(self, lockfile: str) -> None:
        """
        ファイルロックを初期化する.
        
        Args:
            lockfile: ロックファイルのパス
        """
        self.lockfile = lockfile
        self.fp: Optional[TextIO] = None

    def acquire(self) -> None:
        """
        ロックを取得する.
        
        指定されたロックファイルに対して排他ロックを取得します。
        既に他のプロセスがロックを保持している場合は、プログラムを終了します。
        
        Raises:
            SystemExit: 他のプロセスがロックを保持している場合
        """
        # ロックファイルを書き込みモードで開く
        self.fp = open(self.lockfile, "w")
        
        try:
            # 排他ロック + ノンブロッキングでロックを取得
            portalocker.lock(self.fp, portalocker.LOCK_EX | portalocker.LOCK_NB)
        except portalocker.LockException:
            # ロックの取得に失敗した場合（他のプロセスが保持中）
            print(f"他のプロセスがロック中です: {self.lockfile}")
            sys.exit(1)

    def release(self) -> None:
        """
        ロックを解放する.
        
        取得したロックを解放し、ファイルハンドルを閉じます。
        エラーが発生してもプログラムの実行は継続されます。
        """
        if self.fp:
            try:
                # ロックを解放
                portalocker.unlock(self.fp)
            except Exception:
                # エラーが発生してもプログラムを継続
                # （プロセス終了時に自動的にロックは解放される）
                pass
            
            # ファイルハンドルを閉じる
            self.fp.close()
            self.fp = None

    def __enter__(self) -> "FileLock":
        """
        コンテキストマネージャーの開始処理.
        
        with文で使用した際にロックを自動的に取得します。
        
        Returns:
            自分自身のインスタンス
        """
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[Exception],
        exc_tb: Optional[Any],
    ) -> None:
        """
        コンテキストマネージャーの終了処理.
        
        with文のブロックを抜ける際にロックを自動的に解放します。
        
        Args:
            exc_type: 例外の型
            exc_val: 例外の値
            exc_tb: トレースバック情報
        """
        self.release()
