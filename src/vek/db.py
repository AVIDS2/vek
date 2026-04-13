"""SQLite storage backend.

Schema mirrors git's layered model:
    objects  -  content-addressed blob store  (like .git/objects/)
    nodes    -  execution DAG vertices        (like git commits)
    refs     -  named pointers to nodes       (like git branches)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

_SCHEMA_V1 = """\
CREATE TABLE IF NOT EXISTS objects (
    hash    TEXT PRIMARY KEY,
    content BLOB NOT NULL
);

CREATE TABLE IF NOT EXISTS nodes (
    hash         TEXT PRIMARY KEY,
    tool         TEXT NOT NULL,
    input_hash   TEXT NOT NULL,
    output_hash  TEXT NOT NULL,
    parent_hash  TEXT,
    timestamp    TEXT NOT NULL,
    merge_parent TEXT
);

CREATE TABLE IF NOT EXISTS refs (
    name TEXT PRIMARY KEY,
    hash TEXT NOT NULL
);
"""

_CURRENT_VERSION = 3


class DB:
    """Thin wrapper around a per-repository SQLite database."""

    def __init__(self, path: Path):
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._autocommit = True
        self._migrate()

    def _commit(self) -> None:
        """Commit only if autocommit is enabled (not inside a batch)."""
        if self._autocommit:
            self._conn.commit()

    def begin_immediate(self) -> None:
        """Start an IMMEDIATE transaction (grabs a write lock)."""
        self._conn.execute("BEGIN IMMEDIATE")

    def commit(self) -> None:
        """Commit the current transaction."""
        self._conn.commit()

    def rollback(self) -> None:
        """Roll back the current transaction."""
        self._conn.rollback()

    def _migrate(self) -> None:
        ver = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if ver == 0:
            self._conn.executescript(_SCHEMA_V1)
            self._conn.execute(f"PRAGMA user_version = {_CURRENT_VERSION}")
            self._conn.commit()
        elif ver < _CURRENT_VERSION:
            # v1 -> v2: add merge_parent column
            if ver < 2:
                try:
                    self._conn.execute(
                        "ALTER TABLE nodes ADD COLUMN merge_parent TEXT"
                    )
                except sqlite3.OperationalError:
                    pass  # column already exists
            # v2 -> v3: add indexes for query performance
            if ver < 3:
                self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_nodes_tool ON nodes(tool)"
                )
                self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_nodes_timestamp ON nodes(timestamp)"
                )
                self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_nodes_parent ON nodes(parent_hash)"
                )
            self._conn.execute(f"PRAGMA user_version = {_CURRENT_VERSION}")
            self._conn.commit()

    # ------------------------------------------------------------------ objects

    def put_object(self, h: str, blob: bytes) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO objects(hash, content) VALUES(?, ?)",
            (h, blob),
        )
        self._commit()

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
        merge_parent: str | None = None,
    ) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO nodes VALUES(?, ?, ?, ?, ?, ?, ?)",
            (h, tool, input_hash, output_hash, parent_hash, ts, merge_parent),
        )
        self._commit()

    def get_node(self, h: str) -> dict | None:
        row = self._conn.execute(
            "SELECT hash, tool, input_hash, output_hash, parent_hash,"
            "       timestamp, merge_parent FROM nodes WHERE hash = ?",
            (h,),
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
            merge_parent=row[6],
        )

    def walk(self, start: str) -> list[dict]:
        """BFS traversal of the DAG from *start*, following both
        ``parent_hash`` and ``merge_parent`` links.

        Returns nodes in topological-ish order (newest first).
        """
        result: list[dict] = []
        seen: set[str] = set()
        queue: list[str] = [start]
        while queue:
            cur = queue.pop(0)
            if cur in seen:
                continue
            node = self.get_node(cur)
            if node is None:
                continue
            seen.add(cur)
            result.append(node)
            if node["parent_hash"]:
                queue.append(node["parent_hash"])
            if node.get("merge_parent"):
                queue.append(node["merge_parent"])
        return result

    def walk_linear(self, start: str) -> list[dict]:
        """Traverse only the ``parent_hash`` chain (linear history)."""
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
        self._commit()

    def list_refs(self) -> list[tuple[str, str]]:
        return self._conn.execute(
            "SELECT name, hash FROM refs ORDER BY name"
        ).fetchall()

    # ----------------------------------------------------------------- resolve

    def resolve_prefix(self, prefix: str) -> str:
        """Resolve a short hash prefix to a full hash.

        Searches nodes first, then objects.  Raises *KeyError* on
        zero matches and *ValueError* on ambiguous (multiple) matches.
        """
        if len(prefix) == 64:
            return prefix
        like = prefix + "%"
        rows = self._conn.execute(
            "SELECT hash FROM nodes WHERE hash LIKE ?", (like,)
        ).fetchall()
        if not rows:
            rows = self._conn.execute(
                "SELECT hash FROM objects WHERE hash LIKE ?", (like,)
            ).fetchall()
        hashes = list({r[0] for r in rows})
        if len(hashes) == 0:
            raise KeyError(prefix)
        if len(hashes) > 1:
            raise ValueError(
                f"ambiguous prefix {prefix!r} matches {len(hashes)} objects"
            )
        return hashes[0]

    # ------------------------------------------------------------------- query

    def query_nodes(
        self,
        *,
        tool: str | None = None,
        since: str | None = None,
        until: str | None = None,
        branch: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Query nodes with optional filters.

        If *branch* is given, only returns nodes reachable from that
        branch tip.  Otherwise searches all nodes in the repository.
        """
        if branch is not None:
            tip = self.get_ref(branch)
            if tip is None:
                return []
            candidates = {n["hash"]: n for n in self.walk(tip)}
        else:
            rows = self._conn.execute(
                "SELECT hash, tool, input_hash, output_hash, parent_hash,"
                "       timestamp, merge_parent FROM nodes"
            ).fetchall()
            candidates = {
                r[0]: dict(
                    hash=r[0], tool=r[1], input_hash=r[2], output_hash=r[3],
                    parent_hash=r[4], timestamp=r[5], merge_parent=r[6],
                )
                for r in rows
            }

        results: list[dict] = []
        for n in sorted(
            candidates.values(),
            key=lambda x: x["timestamp"],
            reverse=True,
        ):
            if tool is not None and n["tool"] != tool:
                continue
            if since is not None and n["timestamp"] < since:
                continue
            if until is not None and n["timestamp"] > until:
                continue
            results.append(n)
            if len(results) >= limit:
                break
        return results

    def search_content(
        self,
        pattern: str,
        *,
        in_field: str = "both",  # "input", "output", or "both"
        limit: int = 50,
    ) -> list[dict]:
        """Search nodes whose input/output JSON contains *pattern*.

        Uses SQLite LIKE on the raw object content for a lightweight
        full-text search.  Returns matching nodes (newest first).
        """
        like = f"%{pattern}%"
        if in_field == "input":
            fields = ["input_hash"]
        elif in_field == "output":
            fields = ["output_hash"]
        else:
            fields = ["input_hash", "output_hash"]

        node_hashes: set[str] = set()
        for field in fields:
            rows = self._conn.execute(
                f"SELECT hash FROM objects WHERE content LIKE ?", (like,)
            ).fetchall()
            obj_hashes = {r[0] for r in rows}
            if not obj_hashes:
                continue
            placeholders = ",".join("?" for _ in obj_hashes)
            node_rows = self._conn.execute(
                f"SELECT hash FROM nodes WHERE {field} IN ({placeholders})",
                list(obj_hashes),
            ).fetchall()
            node_hashes.update(r[0] for r in node_rows)

        results: list[dict] = []
        for h in node_hashes:
            n = self.get_node(h)
            if n is not None:
                results.append(n)
        results.sort(key=lambda x: x["timestamp"], reverse=True)
        return results[:limit]

    # ------------------------------------------------------------------- stats

    def count_nodes(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]

    def count_objects(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM objects").fetchone()[0]

    def count_refs(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM refs").fetchone()[0]

    # ------------------------------------------------------------------- misc

    def close(self) -> None:
        self._conn.close()
