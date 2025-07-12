import os
import sys

import portalocker


class FileLock:
    def __init__(self, lockfile):
        self.lockfile = lockfile
        self.fp = None

    def acquire(self):
        self.fp = open(self.lockfile, "w")
        try:
            portalocker.lock(self.fp, portalocker.LOCK_EX | portalocker.LOCK_NB)
        except portalocker.LockException:
            print(f"他のプロセスがロック中です: {self.lockfile}")
            sys.exit(1)

    def release(self):
        if self.fp:
            try:
                portalocker.unlock(self.fp)
            except Exception:
                pass
            self.fp.close()
            self.fp = None

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
