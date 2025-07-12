"""ファイルロックユーティリティ.

このモジュールは、複数プロセス間での排他制御を実現するための
ファイルロック機能を提供します。同一ファイルに対する同時アクセスを
防止するために使用されます。
"""
from __future__ import annotations

import contextlib
import sys
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

if TYPE_CHECKING:
    import types

import portalocker
from typing_extensions import Self


class FileLock:
    """ファイルベースの排他制御ロック.

    ファイルシステムを使用してプロセス間の排他制御を実現します。
    コンテキストマネージャーとして使用することで、自動的にロックの
    取得と解放を行います。
    """

    def __init__(self, lockfile: str) -> None:
        """ファイルロックを初期化する.

        Args:
            lockfile: ロックファイルのパス

        """
        self.lockfile = lockfile
        self.fp: TextIO | None = None

    def acquire(self) -> None:
        """ロックを取得する.

        指定されたロックファイルに対して排他ロックを取得します。
        既に他のプロセスがロックを保持している場合は、プログラムを終了します。

        Raises:
            SystemExit: 他のプロセスがロックを保持している場合

        """
        lockfile_path = Path(self.lockfile)
        self.fp = lockfile_path.open("w")

        try:
            portalocker.lock(self.fp, portalocker.LOCK_EX | portalocker.LOCK_NB)
        except portalocker.LockException:
            sys.exit(1)

    def release(self) -> None:
        """ロックを解放する.

        取得したロックを解放し、ファイルハンドルを閉じます。
        エラーが発生してもプログラムの実行は継続されます。
        """
        if self.fp:
            with contextlib.suppress(portalocker.LockException):
                portalocker.unlock(self.fp)

            self.fp.close()
            self.fp = None

    def __enter__(self) -> Self:
        """コンテキストマネージャーの開始処理.

        with文で使用した際にロックを自動的に取得します。

        Returns:
            自分自身のインスタンス

        """
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        """コンテキストマネージャーの終了処理.

        with文のブロックを抜ける際にロックを自動的に解放します。

        Args:
            exc_type: 例外の型
            exc_val: 例外の値
            exc_tb: トレースバック情報

        """
        self.release()
