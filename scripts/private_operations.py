"""Serialize local portfolio and loss-ledger writes across service/CLI processes.

The SQLite lock contains no policy or claim data. It is a local transaction
coordination mechanism, not tenant authorization or encryption.
"""
from contextlib import contextmanager
import os
import pathlib
import sqlite3


@contextmanager
def private_write_lock(folder):
    folder = pathlib.Path(folder).resolve()
    if any(part.lower() in ('public', 'dist') for part in folder.parts):
        raise ValueError('PRIVATE_WRITE_LOCK_REQUIRES_PRIVATE_DIRECTORY')
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / '.workspace-write-lock.sqlite'
    if path.is_symlink():
        raise ValueError('PRIVATE_WRITE_LOCK_MUST_NOT_BE_SYMLINK')
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        pass
    else:
        os.close(fd)
    if not path.is_file() or (os.name == 'posix' and path.stat().st_mode & 0o077):
        raise ValueError('PRIVATE_WRITE_LOCK_PERMISSIONS_REQUIRED')
    db = sqlite3.connect(path, timeout=30)
    try:
        db.execute('BEGIN IMMEDIATE')
        yield
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()
