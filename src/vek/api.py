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
from vek.graph import graph_log as _graph_log, json_diff
from vek.integrity import fsck as _fsck, gc as _gc
from vek.transfer import (
    export_json as _export_json,
    export_jsonl as _export_jsonl,
    import_json as _import_json,
    import_jsonl as _import_jsonl,
)
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


def _resolve(db: DB, h: str) -> str:
    """Resolve a potentially short hash prefix to its full hash."""
    try:
        return db.resolve_prefix(h)
    except KeyError:
        raise VekError(f"object not found: {h}")
    except ValueError as exc:
        raise VekError(str(exc))


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
    chain = db.walk_linear(tip)[:n]
    db.close()
    return chain


def branch(name: str | None = None) -> str | list[tuple[str, str]]:
    """List branches (*name*=None) or create/switch to a branch.

    - If the branch already exists, just switch HEAD to it.
    - If the branch is new, copy the current tip and switch.
    """
    vd, db = _open()
    if name is None:
        refs = db.list_refs()
        db.close()
        return refs
    existing = db.get_ref(name)
    if existing is None:
        # New branch — copy current tip
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
    node_hash = _resolve(db, node_hash)
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
    hash1 = _resolve(db, hash1)
    hash2 = _resolve(db, hash2)
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
        result["input_diff"] = json_diff(i1, i2)

    if not result["output_match"]:
        o1 = json.loads(db.get_object(n1["output_hash"]) or b"null")
        o2 = json.loads(db.get_object(n2["output_hash"]) or b"null")
        result["output_diff"] = json_diff(o1, o2)

    db.close()
    return result


def replay(node_hash: str) -> list[dict]:
    """Return the linear execution chain from root to *node_hash*,
    with input/output content materialised inline."""
    vd, db = _open()
    node_hash = _resolve(db, node_hash)
    chain = db.walk_linear(node_hash)
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


def show(node_hash: str) -> dict:
    """Return full node details with materialised input/output."""
    vd, db = _open()
    node_hash = _resolve(db, node_hash)
    node = db.get_node(node_hash)
    if node is None:
        db.close()
        raise VekError(f"node not found: {node_hash}")
    result = dict(node)
    result["input"] = json.loads(db.get_object(node["input_hash"]) or b"null")
    result["output"] = json.loads(db.get_object(node["output_hash"]) or b"null")
    db.close()
    return result


def cat_file(obj_hash: str) -> bytes:
    """Return raw content of a content-addressed object."""
    vd, db = _open()
    obj_hash = _resolve(db, obj_hash)
    blob = db.get_object(obj_hash)
    if blob is None:
        db.close()
        raise VekError(f"object not found: {obj_hash}")
    db.close()
    return blob


def status() -> dict:
    """Return repository status summary."""
    vd, db = _open()
    branch_name = read_head(vd)
    tip = db.get_ref(branch_name)
    result = {
        "branch": branch_name,
        "tip": tip,
        "nodes": db.count_nodes(),
        "objects": db.count_objects(),
        "refs": db.count_refs(),
    }
    db.close()
    return result


# ----------------------------------------------------------------- tags

TAG_PREFIX = "tag/"


def tag(name: str | None = None, node_hash: str | None = None) -> str | list[tuple[str, str]]:
    """Create or list lightweight tags.

    - ``tag()`` — list all tags
    - ``tag("v1")`` — tag current tip
    - ``tag("v1", hash)`` — tag a specific node
    """
    vd, db = _open()
    if name is None:
        rows = db._conn.execute(
            "SELECT name, hash FROM refs WHERE name LIKE ? ORDER BY name",
            (TAG_PREFIX + "%",),
        ).fetchall()
        db.close()
        return [(n.removeprefix(TAG_PREFIX), h) for n, h in rows]

    if node_hash is not None:
        node_hash = _resolve(db, node_hash)
    else:
        branch_name = read_head(vd)
        node_hash = db.get_ref(branch_name)
        if node_hash is None:
            db.close()
            raise VekError("nothing to tag (empty branch)")

    ref_name = TAG_PREFIX + name
    existing = db.get_ref(ref_name)
    if existing is not None:
        db.close()
        raise VekError(f"tag '{name}' already exists")

    db.set_ref(ref_name, node_hash)
    db.close()
    return name


# ----------------------------------------------------------------- merge


def merge(target_branch: str) -> str:
    """Merge *target_branch* into the current branch.

    Creates a merge node with two parents: the current tip (parent_hash)
    and the target branch tip (merge_parent).  The merge node records
    the tool as ``__merge__`` with both branch names as input.

    Returns the merge node hash.
    """
    vd, db = _open()
    current = read_head(vd)
    our_tip = db.get_ref(current)
    their_tip = db.get_ref(target_branch)

    if our_tip is None:
        db.close()
        raise VekError(f"current branch '{current}' has no commits")
    if their_tip is None:
        db.close()
        raise VekError(f"branch '{target_branch}' not found or empty")
    if our_tip == their_tip:
        db.close()
        raise VekError("already up to date")

    # Check that target isn't an ancestor of current (already merged)
    ancestor_hashes = {n["hash"] for n in db.walk(our_tip)}
    if their_tip in ancestor_hashes:
        db.close()
        raise VekError(f"'{target_branch}' is already an ancestor of '{current}'")

    merge_input = canonical({"merge": [current, target_branch]})
    merge_output = canonical({"merged_tips": [our_tip, their_tip]})
    in_hash = hash_blob(merge_input)
    out_hash = hash_blob(merge_output)
    db.put_object(in_hash, merge_input)
    db.put_object(out_hash, merge_output)

    ts = datetime.now(timezone.utc).isoformat()
    node_payload = canonical(
        dict(
            tool="__merge__",
            input_hash=in_hash,
            output_hash=out_hash,
            parent_hash=our_tip,
            merge_parent=their_tip,
            timestamp=ts,
        )
    )
    node_hash = hash_node(node_payload)
    db.put_node(node_hash, "__merge__", in_hash, out_hash, our_tip, ts, merge_parent=their_tip)
    db.set_ref(current, node_hash)

    db.close()
    return node_hash


# --------------------------------------------------------------- graph log


def log_graph(*, branch_name: str | None = None, limit: int = 30) -> list[str]:
    """Return ASCII DAG lines (like ``git log --graph --oneline``)."""
    _vd, db = _open()
    lines = _graph_log(db, branch_name=branch_name, limit=limit)
    db.close()
    return lines


# -------------------------------------------------------------- integrity


def fsck() -> list[dict]:
    """Verify repository integrity.  Returns list of errors."""
    _vd, db = _open()
    errors = _fsck(db)
    db.close()
    return errors


def gc(*, dry_run: bool = False) -> dict:
    """Remove unreachable nodes and orphaned objects."""
    _vd, db = _open()
    result = _gc(db, dry_run=dry_run)
    db.close()
    return result


# --------------------------------------------------------------- transfer


def export(*, branch: str | None = None, format: str = "json") -> dict | str:
    """Export execution chains.

    - ``format="json"`` returns a dict.
    - ``format="jsonl"`` returns a newline-delimited JSON string.
    """
    _vd, db = _open()
    if format == "jsonl":
        import io
        buf = io.StringIO()
        _export_jsonl(db, buf, branch=branch)
        db.close()
        return buf.getvalue()
    result = _export_json(db, branch=branch)
    db.close()
    return result


def import_data(data: dict | str, *, format: str = "json") -> dict:
    """Import execution chains.

    - ``format="json"``: *data* is a dict (from ``export``).
    - ``format="jsonl"``: *data* is a JSONL string.
    """
    _vd, db = _open()
    if format == "jsonl":
        import io
        buf = io.StringIO(data)  # type: ignore[arg-type]
        result = _import_jsonl(db, buf)
    else:
        result = _import_json(db, data)  # type: ignore[arg-type]
    db.close()
    return result
