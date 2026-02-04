from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

_DB_LOCK = threading.RLock()


@contextmanager
def db_lock() -> Iterator[None]:
    _DB_LOCK.acquire()
    try:
        yield
    finally:
        _DB_LOCK.release()


def _connect(path: Path, timeout: float | None) -> sqlite3.Connection:
    if timeout is None:
        return sqlite3.connect(path)
    return sqlite3.connect(path, timeout=timeout)


@contextmanager
def db_connection(
    path: Path,
    *,
    timeout: float | None = None,
    row_factory: Callable | None = None,
    foreign_keys: bool = True,
) -> Iterator[sqlite3.Connection]:
    with db_lock():
        with _connect(path, timeout) as conn:
            if row_factory is not None:
                conn.row_factory = row_factory
            if foreign_keys:
                conn.execute("PRAGMA foreign_keys = ON")
            yield conn
