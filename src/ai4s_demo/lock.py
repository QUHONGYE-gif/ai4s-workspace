"""Single-process lock for one data directory, implemented per platform.

Linux uses ``fcntl.flock``; Windows has no ``fcntl`` and uses ``msvcrt.locking``.
Both raise ``BlockingIOError`` when another process already holds the lock, which
keeps the single-worker boundary in ``create_app`` identical on either platform.
"""

import os

if os.name == "nt":  # pragma: no cover - exercised only on Windows
    import msvcrt

    def acquire_lock(fileobj):
        # msvcrt.locking locks a byte range starting at the current position; lock
        # one byte beyond the file end so an empty lock file still gets a range.
        # The caller must open with read+write ("a+"), otherwise Windows denies
        # a shared lock on an append-only handle.
        fileobj.seek(0, os.SEEK_END)
        size = max(fileobj.tell(), 1)
        fileobj.seek(0)
        try:
            msvcrt.locking(fileobj.fileno(), msvcrt.LK_NBLCK, size)
        except PermissionError:
            raise BlockingIOError("lock held by another process") from None

    def release_lock(fileobj):
        fileobj.seek(0, os.SEEK_END)
        size = max(fileobj.tell(), 1)
        fileobj.seek(0)
        msvcrt.locking(fileobj.fileno(), msvcrt.LK_UNLCK, size)
else:
    import fcntl

    def acquire_lock(fileobj):
        fcntl.flock(fileobj, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def release_lock(fileobj):
        fcntl.flock(fileobj, fcntl.LOCK_UN)
