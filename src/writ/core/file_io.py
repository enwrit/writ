"""Cross-platform file locking and atomic append for conversation files.

Conversation files are append-only markdown. Two agents on the same machine
could both append simultaneously, so we use advisory file locks to prevent
corruption.  Lock scope is per-file (conversations are independent).
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_LOCK_TIMEOUT_S = 5.0
_LOCK_RETRIES = 3
_LOCK_RETRY_DELAY_S = 0.5


@contextmanager
def file_lock(path: Path) -> Iterator[None]:
    """Acquire an advisory lock on *path*, yielding while held.

    Uses ``fcntl.flock`` on Unix and ``msvcrt.locking`` on Windows.
    Retries up to ``_LOCK_RETRIES`` times with backoff.
    """
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd: int | None = None
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
        _acquire(fd, lock_path)
        yield
    finally:
        if fd is not None:
            _release(fd)
            os.close(fd)


def _acquire(fd: int, lock_path: Path) -> None:
    delay = _LOCK_RETRY_DELAY_S
    for attempt in range(_LOCK_RETRIES):
        try:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError:
            if attempt == _LOCK_RETRIES - 1:
                raise OSError(
                    f"Could not acquire lock on {lock_path} after "
                    f"{_LOCK_RETRIES} retries ({_LOCK_TIMEOUT_S}s timeout)."
                ) from None
            time.sleep(delay)
            delay *= 2


def _release(fd: int) -> None:
    try:
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass


def atomic_append(path: Path, content: str) -> None:
    """Append *content* to *path* under an advisory file lock.

    The write is "atomic-ish": we acquire a lock, seek to the end, write,
    flush, then release.  A crash mid-write could leave a partial message,
    but the lock ensures no interleaving from concurrent writers.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(path):
        with open(path, "a", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
