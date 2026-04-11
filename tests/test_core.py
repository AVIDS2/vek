"""Tests for vek core hashing primitives."""

from vek.core import canonical, hash_blob, hash_node


def test_canonical_deterministic():
    """Same object always produces identical bytes."""
    a = canonical({"b": 2, "a": 1})
    b = canonical({"a": 1, "b": 2})
    assert a == b


def test_canonical_nested():
    obj = {"x": [3, 1, 2], "y": {"z": True}}
    assert canonical(obj) == canonical(obj)


def test_hash_blob_stable():
    data = b'{"key":"value"}'
    h1 = hash_blob(data)
    h2 = hash_blob(data)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex


def test_hash_blob_vs_node_differ():
    """Same content hashed as blob vs node must produce different IDs."""
    data = b"same content"
    assert hash_blob(data) != hash_node(data)


def test_different_content_different_hash():
    assert hash_blob(b"aaa") != hash_blob(b"bbb")
