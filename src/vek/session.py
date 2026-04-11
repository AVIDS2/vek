"""Auto-recording execution session.

Usage::

    with vek.session() as s:
        s.store(tool="search", input=query, output=result)
        s.store(tool="summarise", input=text, output=summary)
        # each call is automatically chained to the previous one
"""

from __future__ import annotations

from pathlib import Path

from vek.api import _open, store as _store
from vek.db import DB
from vek.repo import read_head


class Session:
    """Context manager that chains tool calls into a linear DAG segment."""

    def __init__(self, *, path: Path | None = None):
        self._start_path = path
        self._vd: Path | None = None
        self._db: DB | None = None
        self._tip: str | None = None

    # -------------------------------------------------------------- lifecycle

    def __enter__(self) -> Session:
        self._vd, self._db = _open(self._start_path)
        branch = read_head(self._vd)
        self._tip = self._db.get_ref(branch)
        return self

    def __exit__(self, *exc: object) -> bool:
        if self._db is not None:
            self._db.close()
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
        return h

    @property
    def tip(self) -> str | None:
        """Hash of the most recent node in this session."""
        return self._tip
