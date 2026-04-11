"""High-level public operations.

Every function either opens its own DB connection (top-level calls)
or accepts an injected one (for use inside a Session).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from vek.core import canonical, hash_blob, hash_node
from vek.db import DB
from vek.repo import (
    DB_NAME,
    find,
    init as _repo_init,
    read_head,
    write_head,
)


class VekError(Exception):
    """Any vek-specific runtime error."""


# ---------------------------------------------------------------------- helpers


def _open(start: Path | None = None) -> tuple[Path, DB]:
    """Locate .vek/ and return (vek_dir, db)."""
    vd = find(start)
    if vd is None:
        raise VekError("not a vek repository (run `vek init`)")
    return vd, DB(vd / DB_NAME)


# ------------------------------------------------------------------- public API


def init(path: str | Path | None = None) -> Path:
    """Initialise a .vek repository.  Idempotent."""
    vd = _repo_init(Path(path) if path else None)
    # Ensure the SQLite schema exists.
    DB(vd / DB_NAME).close()
    return vd


def store(
    tool: str,
    input: object,
    output: object,
    *,
    parent: str | None = ...,  # type: ignore[assignment]
    _vd: Path | None = None,
    _db: DB | None = None,
) -> str:
    """Record one tool call.  Returns the node hash.

    When called outside a session, the new node is automatically
    chained to the tip of the current branch (like ``git commit``).
    """
    own_db = _db is None
    if own_db:
        vd, db = _open()
    else:
        vd, db = _vd, _db  # type: ignore[assignment]

    # --- store input / output blobs (content-addressed, deduped) ---
    in_blob = canonical(input)
    out_blob = canonical(output)
    in_hash = hash_blob(in_blob)
    out_hash = hash_blob(out_blob)
    db.put_object(in_hash, in_blob)
    db.put_object(out_hash, out_blob)

    # --- resolve parent ---
    branch_name = read_head(vd)
    if parent is ...:
        parent = db.get_ref(branch_name)

    # --- build node ---
    ts = datetime.now(timezone.utc).isoformat()
    node_payload = canonical(
        dict(
            tool=tool,
            input_hash=in_hash,
            output_hash=out_hash,
            parent_hash=parent,
            timestamp=ts,
        )
    )
    node_hash = hash_node(node_payload)

    db.put_node(node_hash, tool, in_hash, out_hash, parent, ts)

    # --- advance branch pointer ---
    db.set_ref(branch_name, node_hash)

    if own_db:
        db.close()
    return node_hash


def log(n: int = 20, *, branch_name: str | None = None) -> list[dict]:
    """Return the last *n* nodes on the current (or given) branch."""
    vd, db = _open()
    ref = branch_name or read_head(vd)
    tip = db.get_ref(ref)
    if tip is None:
        db.close()
        return []
    chain = db.walk(tip)[:n]
    db.close()
    return chain


def branch(name: str | None = None) -> str | list[tuple[str, str]]:
    """List branches (*name*=None) or create a new branch at HEAD tip."""
    vd, db = _open()
    if name is None:
        refs = db.list_refs()
        db.close()
        return refs
    current = read_head(vd)
    tip = db.get_ref(current)
    if tip:
        db.set_ref(name, tip)
    write_head(vd, name)
    db.close()
    return name


def fork(node_hash: str, branch_name: str | None = None) -> str:
    """Create a new branch rooted at *node_hash* and switch to it."""
    vd, db = _open()
    node = db.get_node(node_hash)
    if node is None:
        db.close()
        raise VekError(f"node not found: {node_hash}")
    bname = branch_name or f"fork-{node_hash[:8]}"
    db.set_ref(bname, node_hash)
    write_head(vd, bname)
    db.close()
    return bname


def diff(hash1: str, hash2: str) -> dict:
    """Compare two nodes and their input/output blobs."""
    vd, db = _open()
    n1 = db.get_node(hash1)
    n2 = db.get_node(hash2)
    if n1 is None or n2 is None:
        db.close()
        raise VekError("one or both nodes not found")

    result: dict = {
        "node1": n1,
        "node2": n2,
        "input_match": n1["input_hash"] == n2["input_hash"],
        "output_match": n1["output_hash"] == n2["output_hash"],
    }

    if not result["input_match"]:
        i1 = json.loads(db.get_object(n1["input_hash"]) or b"null")
        i2 = json.loads(db.get_object(n2["input_hash"]) or b"null")
        result["input_diff"] = {"left": i1, "right": i2}

    if not result["output_match"]:
        o1 = json.loads(db.get_object(n1["output_hash"]) or b"null")
        o2 = json.loads(db.get_object(n2["output_hash"]) or b"null")
        result["output_diff"] = {"left": o1, "right": o2}

    db.close()
    return result


def replay(node_hash: str) -> list[dict]:
    """Return the full execution chain from root to *node_hash*,
    with input/output content materialised inline."""
    vd, db = _open()
    chain = db.walk(node_hash)
    if not chain:
        db.close()
        raise VekError(f"node not found: {node_hash}")
    enriched = []
    for node in reversed(chain):  # root-first order
        entry = dict(node)
        entry["input"] = json.loads(db.get_object(node["input_hash"]) or b"null")
        entry["output"] = json.loads(db.get_object(node["output_hash"]) or b"null")
        enriched.append(entry)
    db.close()
    return enriched
