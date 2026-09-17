from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3


@contextmanager
def db_connection(path: str | Path):
    """
    Yield an open sqlite3 connection with FK enforcement and Row factory.
    Commits on clean exit; rolls back on exception.
    """
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
