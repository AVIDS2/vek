"""DAG visualisation and structural diff utilities."""

from __future__ import annotations

from collections import deque

from vek.db import DB


# ----------------------------------------------------------- ASCII graph log


def _collect_dag(db: DB, tips: list[str], limit: int) -> list[dict]:
    """BFS from all ref tips, collecting nodes in topological order."""
    visited: set[str] = set()
    queue: deque[str] = deque(tips)
    nodes: list[dict] = []

    while queue and len(nodes) < limit:
        h = queue.popleft()
        if h in visited:
            continue
        node = db.get_node(h)
        if node is None:
            continue
        visited.add(h)
        nodes.append(node)
        if node["parent_hash"]:
            queue.append(node["parent_hash"])
        if node.get("merge_parent"):
            queue.append(node["merge_parent"])

    # Sort by timestamp descending (newest first)
    nodes.sort(key=lambda n: n["timestamp"], reverse=True)
    return nodes


def graph_log(db: DB, *, branch_name: str | None = None, limit: int = 30) -> list[str]:
    """Build ASCII graph lines like ``git log --graph --oneline``.

    Returns a list of ready-to-print strings.
    """
    if branch_name:
        tip = db.get_ref(branch_name)
        tips = [tip] if tip else []
    else:
        tips = [h for _, h in db.list_refs()]

    if not tips:
        return ["(empty)"]

    nodes = _collect_dag(db, tips, limit)
    if not nodes:
        return ["(empty)"]

    # Build a set of all node hashes for merge detection
    hash_set = {n["hash"] for n in nodes}

    lines: list[str] = []
    for node in nodes:
        h_short = node["hash"][:10]
        is_merge = node.get("merge_parent") is not None

        if is_merge:
            prefix = "*   "  # merge commit
        else:
            prefix = "* "

        line = f"{prefix}\033[33m{h_short}\033[0m {node['tool']}  {node['timestamp']}"
        lines.append(line)

        if is_merge:
            mp = node["merge_parent"][:10] if node.get("merge_parent") else ""
            pp = node["parent_hash"][:10] if node["parent_hash"] else ""
            lines.append(f"|\\  merge {pp} + {mp}")

    return lines


# ---------------------------------------------------------- structural diff


def json_diff(a: object, b: object, path: str = "") -> list[dict]:
    """Recursive structural diff between two JSON-compatible objects.

    Returns a list of change records:
        {"op": "add"|"remove"|"change", "path": str, "old"?: ..., "new"?: ...}
    """
    changes: list[dict] = []

    if type(a) != type(b):
        changes.append({"op": "change", "path": path or "/", "old": a, "new": b})
        return changes

    if isinstance(a, dict) and isinstance(b, dict):
        all_keys = sorted(set(a.keys()) | set(b.keys()))
        for k in all_keys:
            child_path = f"{path}/{k}"
            if k not in a:
                changes.append({"op": "add", "path": child_path, "new": b[k]})
            elif k not in b:
                changes.append({"op": "remove", "path": child_path, "old": a[k]})
            else:
                changes.extend(json_diff(a[k], b[k], child_path))
    elif isinstance(a, list) and isinstance(b, list):
        max_len = max(len(a), len(b))
        for i in range(max_len):
            child_path = f"{path}[{i}]"
            if i >= len(a):
                changes.append({"op": "add", "path": child_path, "new": b[i]})
            elif i >= len(b):
                changes.append({"op": "remove", "path": child_path, "old": a[i]})
            else:
                changes.extend(json_diff(a[i], b[i], child_path))
    else:
        if a != b:
            changes.append({"op": "change", "path": path or "/", "old": a, "new": b})

    return changes
