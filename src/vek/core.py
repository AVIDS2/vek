"""Content hashing primitives.

Follows git's object hashing convention:
    object_id = SHA-256( type + " " + size + "\\0" + content )

Two object types:
    blob  -  raw content (tool call input or output)
    node  -  execution graph vertex
"""

from __future__ import annotations

import hashlib
import json


def canonical(obj: object) -> bytes:
    """Deterministic JSON serialization for any Python object."""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def _hash_with_prefix(prefix: str, data: bytes) -> str:
    """SHA-256 hash with git-style type prefix: 'type size\\0content'."""
    header = f"{prefix} {len(data)}\0".encode("ascii")
    return hashlib.sha256(header + data).hexdigest()


def hash_blob(data: bytes) -> str:
    """Hash a content blob (tool call input or output)."""
    return _hash_with_prefix("blob", data)


def hash_node(data: bytes) -> str:
    """Hash a node (execution step)."""
    return _hash_with_prefix("node", data)
