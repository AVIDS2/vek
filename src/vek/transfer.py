"""Export and import execution chains in portable formats.

Supports JSON (full dump) and JSON Lines (streaming) formats.
"""

from __future__ import annotations

import base64
import json
from typing import IO

from vek.db import DB


# ------------------------------------------------------------------- export


def export_json(db: DB, *, branch: str | None = None) -> dict:
    """Export chains reachable from refs as a JSON-serialisable dict.

    The format is::

        {
            "version": 1,
            "refs": [{"name": "main", "hash": "abc..."}],
            "nodes": [{...}],
            "objects": [{"hash": "...", "content_b64": "..."}],
        }
    """
    # Collect reachable nodes
    reachable_nodes: dict[str, dict] = {}
    reachable_objects: set[str] = set()

    refs = db.list_refs()
    if branch:
        refs = [(n, h) for n, h in refs if n == branch]

    for _name, tip in refs:
        for node in db.walk(tip):
            if node["hash"] not in reachable_nodes:
                reachable_nodes[node["hash"]] = node
                reachable_objects.add(node["input_hash"])
                reachable_objects.add(node["output_hash"])

    # Collect objects
    objects = []
    for obj_hash in sorted(reachable_objects):
        blob = db.get_object(obj_hash)
        if blob is not None:
            objects.append({
                "hash": obj_hash,
                "content_b64": base64.b64encode(blob).decode("ascii"),
            })

    return {
        "version": 1,
        "refs": [{"name": n, "hash": h} for n, h in refs],
        "nodes": list(reachable_nodes.values()),
        "objects": objects,
    }


def export_jsonl(db: DB, fp: IO[str], *, branch: str | None = None) -> int:
    """Export chains as JSON Lines to a file-like object.

    Each line is a JSON object with a ``type`` field:
    ``ref``, ``node``, or ``object``.

    Returns the number of lines written.
    """
    count = 0
    refs = db.list_refs()
    if branch:
        refs = [(n, h) for n, h in refs if n == branch]

    for name, h in refs:
        fp.write(json.dumps({"type": "ref", "name": name, "hash": h}) + "\n")
        count += 1

    seen_nodes: set[str] = set()
    seen_objects: set[str] = set()

    for _name, tip in refs:
        for node in db.walk(tip):
            if node["hash"] in seen_nodes:
                continue
            seen_nodes.add(node["hash"])
            fp.write(json.dumps({"type": "node", **node}) + "\n")
            count += 1

            for obj_hash in (node["input_hash"], node["output_hash"]):
                if obj_hash not in seen_objects:
                    seen_objects.add(obj_hash)
                    blob = db.get_object(obj_hash)
                    if blob is not None:
                        fp.write(json.dumps({
                            "type": "object",
                            "hash": obj_hash,
                            "content_b64": base64.b64encode(blob).decode("ascii"),
                        }) + "\n")
                        count += 1

    return count


# ------------------------------------------------------------------- import


def import_json(db: DB, data: dict) -> dict:
    """Import from a JSON export dict.  Skips duplicates.

    Returns ``{"nodes_imported": int, "objects_imported": int, "refs_imported": int}``.
    """
    stats = {"nodes_imported": 0, "objects_imported": 0, "refs_imported": 0}

    # Import objects first (nodes reference them)
    for obj in data.get("objects", []):
        blob = base64.b64decode(obj["content_b64"])
        existing = db.get_object(obj["hash"])
        if existing is None:
            db.put_object(obj["hash"], blob)
            stats["objects_imported"] += 1

    # Import nodes
    for node in data.get("nodes", []):
        existing = db.get_node(node["hash"])
        if existing is None:
            db.put_node(
                node["hash"],
                node["tool"],
                node["input_hash"],
                node["output_hash"],
                node.get("parent_hash"),
                node["timestamp"],
                merge_parent=node.get("merge_parent"),
            )
            stats["nodes_imported"] += 1

    # Import refs (skip existing to avoid overwriting local state)
    for ref in data.get("refs", []):
        existing = db.get_ref(ref["name"])
        if existing is None:
            db.set_ref(ref["name"], ref["hash"])
            stats["refs_imported"] += 1

    return stats


def import_jsonl(db: DB, fp: IO[str]) -> dict:
    """Import from a JSON Lines stream.  Skips duplicates.

    Returns ``{"nodes_imported": int, "objects_imported": int, "refs_imported": int}``.
    """
    stats = {"nodes_imported": 0, "objects_imported": 0, "refs_imported": 0}

    # Two-pass: buffer everything, import objects first
    objects = []
    nodes = []
    refs = []

    for line in fp:
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        rtype = record.get("type")
        if rtype == "object":
            objects.append(record)
        elif rtype == "node":
            nodes.append(record)
        elif rtype == "ref":
            refs.append(record)

    for obj in objects:
        blob = base64.b64decode(obj["content_b64"])
        if db.get_object(obj["hash"]) is None:
            db.put_object(obj["hash"], blob)
            stats["objects_imported"] += 1

    for node in nodes:
        if db.get_node(node["hash"]) is None:
            db.put_node(
                node["hash"],
                node["tool"],
                node["input_hash"],
                node["output_hash"],
                node.get("parent_hash"),
                node["timestamp"],
                merge_parent=node.get("merge_parent"),
            )
            stats["nodes_imported"] += 1

    for ref in refs:
        if db.get_ref(ref["name"]) is None:
            db.set_ref(ref["name"], ref["hash"])
            stats["refs_imported"] += 1

    return stats
