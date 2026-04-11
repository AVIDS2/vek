"""Auto-recording execution session.

Usage::

    with vek.session() as s:
        s.store(tool="search", input=query, output=result)
        s.store(tool="summarise", input=text, output=summary)
        # each call is automatically chained to the previous one
        # all writes are batched in a single transaction
"""

from __future__ import annotations

from pathlib import Path

from vek.api import _open, store as _store
from vek.db import DB
from vek.repo import HeadLock, read_head


class Session:
    """Context manager that chains tool calls into a linear DAG segment.

    All writes within a session are batched in a single SQLite
    transaction and committed atomically on ``__exit__``.
    """

    def __init__(self, *, path: Path | None = None):
        self._start_path = path
        self._vd: Path | None = None
        self._db: DB | None = None
        self._tip: str | None = None
        self._lock: HeadLock | None = None
        self._count: int = 0

    # -------------------------------------------------------------- lifecycle

    def __enter__(self) -> Session:
        self._vd, self._db = _open(self._start_path)
        self._lock = HeadLock(self._vd)
        self._lock.__enter__()
        branch = read_head(self._vd)
        self._tip = self._db.get_ref(branch)
        # Disable per-call commits — we batch the whole session
        self._db._autocommit = False
        return self

    def __exit__(self, exc_type: type | None, *exc: object) -> bool:
        if self._db is not None:
            if exc_type is None:
                self._db._conn.commit()
            else:
                self._db._conn.rollback()
            self._db._autocommit = True
            self._db.close()
        if self._lock is not None:
            self._lock.__exit__(exc_type, *exc)
        return False

    # --------------------------------------------------------------- recording

    def store(self, tool: str, input: object, output: object) -> str:
        """Record a tool call, chained to the previous one in this session."""
        h = _store(
            tool,
            input,
            output,
            parent=self._tip,
            _vd=self._vd,
            _db=self._db,
        )
        self._tip = h
        self._count += 1
        return h

    @property
    def tip(self) -> str | None:
        """Hash of the most recent node in this session."""
        return self._tip

    @property
    def count(self) -> int:
        """Number of tool calls recorded in this session."""
        return self._count
