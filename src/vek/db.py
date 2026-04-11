"""SQLite storage backend.

Schema mirrors git's layered model:
    objects  -  content-addressed blob store  (like .git/objects/)
    nodes    -  execution DAG vertices        (like git commits)
    refs     -  named pointers to nodes       (like git branches)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS objects (
    hash    TEXT PRIMARY KEY,
    content BLOB NOT NULL
);

CREATE TABLE IF NOT EXISTS nodes (
    hash        TEXT PRIMARY KEY,
    tool        TEXT NOT NULL,
    input_hash  TEXT NOT NULL,
    output_hash TEXT NOT NULL,
    parent_hash TEXT,
    timestamp   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS refs (
    name TEXT PRIMARY KEY,
    hash TEXT NOT NULL
);
"""


class DB:
    """Thin wrapper around a per-repository SQLite database."""

    def __init__(self, path: Path):
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)

    # ------------------------------------------------------------------ objects

    def put_object(self, h: str, blob: bytes) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO objects(hash, content) VALUES(?, ?)",
            (h, blob),
        )
        self._conn.commit()

    def get_object(self, h: str) -> bytes | None:
        row = self._conn.execute(
            "SELECT content FROM objects WHERE hash = ?", (h,)
        ).fetchone()
        return row[0] if row else None

    # ------------------------------------------------------------------- nodes

    def put_node(
        self,
        h: str,
        tool: str,
        input_hash: str,
        output_hash: str,
        parent_hash: str | None,
        ts: str,
    ) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO nodes VALUES(?, ?, ?, ?, ?, ?)",
            (h, tool, input_hash, output_hash, parent_hash, ts),
        )
        self._conn.commit()

    def get_node(self, h: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM nodes WHERE hash = ?", (h,)
        ).fetchone()
        if not row:
            return None
        return dict(
            hash=row[0],
            tool=row[1],
            input_hash=row[2],
            output_hash=row[3],
            parent_hash=row[4],
            timestamp=row[5],
        )

    def walk(self, start: str) -> list[dict]:
        """Traverse parent chain from *start* back to root."""
        chain: list[dict] = []
        cur: str | None = start
        while cur:
            node = self.get_node(cur)
            if node is None:
                break
            chain.append(node)
            cur = node["parent_hash"]
        return chain

    # -------------------------------------------------------------------- refs

    def get_ref(self, name: str) -> str | None:
        row = self._conn.execute(
            "SELECT hash FROM refs WHERE name = ?", (name,)
        ).fetchone()
        return row[0] if row else None

    def set_ref(self, name: str, h: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO refs(name, hash) VALUES(?, ?)",
            (name, h),
        )
        self._conn.commit()

    def list_refs(self) -> list[tuple[str, str]]:
        return self._conn.execute(
            "SELECT name, hash FROM refs ORDER BY name"
        ).fetchall()

    # ------------------------------------------------------------------- misc

    def close(self) -> None:
        self._conn.close()
