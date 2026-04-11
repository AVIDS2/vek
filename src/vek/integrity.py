"""Repository integrity verification and garbage collection.

Analogous to ``git fsck`` and ``git gc``.
"""

from __future__ import annotations

from vek.core import canonical, hash_blob, hash_node
from vek.db import DB


# --------------------------------------------------------------------- fsck


def fsck(db: DB) -> list[dict]:
    """Verify the integrity of every reachable node.

    Checks:
    1. Node hash matches recomputed hash from its fields.
    2. input_hash blob exists in objects table.
    3. output_hash blob exists in objects table.
    4. input_hash matches recomputed hash of stored blob content.
    5. output_hash matches recomputed hash of stored blob content.
    6. parent_hash (if set) points to an existing node.

    Returns a list of error dicts ``{"hash", "error"}``.
    """
    errors: list[dict] = []
    rows = db._conn.execute("SELECT * FROM nodes").fetchall()

    for row in rows:
        h, tool, in_h, out_h, parent_h, ts, merge_h = row

        # 1. Recompute node hash — merge nodes include merge_parent
        fields = dict(
            tool=tool,
            input_hash=in_h,
            output_hash=out_h,
            parent_hash=parent_h,
            timestamp=ts,
        )
        if merge_h is not None:
            fields["merge_parent"] = merge_h
        payload = canonical(fields)
        expected = hash_node(payload)
        if expected != h:
            errors.append({"hash": h, "error": f"node hash mismatch: expected {expected[:10]}"})

        # 2-3. Blob existence
        in_blob = db.get_object(in_h)
        if in_blob is None:
            errors.append({"hash": h, "error": f"missing input blob {in_h[:10]}"})
        else:
            # 4. Blob hash verification
            if hash_blob(in_blob) != in_h:
                errors.append({"hash": h, "error": f"input blob hash mismatch {in_h[:10]}"})

        out_blob = db.get_object(out_h)
        if out_blob is None:
            errors.append({"hash": h, "error": f"missing output blob {out_h[:10]}"})
        else:
            # 5. Blob hash verification
            if hash_blob(out_blob) != out_h:
                errors.append({"hash": h, "error": f"output blob hash mismatch {out_h[:10]}"})

        # 6. Parent existence
        if parent_h is not None:
            if db.get_node(parent_h) is None:
                errors.append({"hash": h, "error": f"missing parent node {parent_h[:10]}"})

        # 7. Merge parent existence
        if merge_h is not None:
            if db.get_node(merge_h) is None:
                errors.append({"hash": h, "error": f"missing merge parent {merge_h[:10]}"})

    return errors


# ----------------------------------------------------------------------- gc


def gc(db: DB, *, dry_run: bool = False) -> dict:
    """Remove unreachable nodes and orphaned objects.

    An object/node is *reachable* if it can be reached by walking
    back from any ref tip.  Everything else is garbage.

    Returns ``{"unreachable_nodes": [...], "orphan_objects": [...], "deleted": bool}``.
    """
    # 1. Collect all reachable node hashes by walking every ref
    reachable_nodes: set[str] = set()
    reachable_objects: set[str] = set()

    for _name, tip_hash in db.list_refs():
        for node in db.walk(tip_hash):
            reachable_nodes.add(node["hash"])
            reachable_objects.add(node["input_hash"])
            reachable_objects.add(node["output_hash"])

    # 2. Find all nodes and objects in the database
    all_nodes = {
        r[0]
        for r in db._conn.execute("SELECT hash FROM nodes").fetchall()
    }
    all_objects = {
        r[0]
        for r in db._conn.execute("SELECT hash FROM objects").fetchall()
    }

    unreachable_nodes = sorted(all_nodes - reachable_nodes)
    orphan_objects = sorted(all_objects - reachable_objects)

    # 3. Delete if not dry run
    if not dry_run and (unreachable_nodes or orphan_objects):
        for h in unreachable_nodes:
            db._conn.execute("DELETE FROM nodes WHERE hash = ?", (h,))
        for h in orphan_objects:
            db._conn.execute("DELETE FROM objects WHERE hash = ?", (h,))
        db._conn.commit()

    return {
        "unreachable_nodes": unreachable_nodes,
        "orphan_objects": orphan_objects,
        "deleted": not dry_run and bool(unreachable_nodes or orphan_objects),
    }
