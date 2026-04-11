"""Tests for repository init / discovery."""

import os
import tempfile
from pathlib import Path

from vek.repo import find, init, read_head, write_head


def test_init_creates_structure():
    with tempfile.TemporaryDirectory() as tmp:
        vd = init(Path(tmp))
        assert vd.is_dir()
        assert (vd / "HEAD").exists()
        assert (vd / "config").exists()
        assert (vd / "objects").is_dir()
        assert (vd / "refs").is_dir()


def test_init_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        vd1 = init(Path(tmp))
        vd2 = init(Path(tmp))
        assert vd1 == vd2


def test_find_walks_up():
    with tempfile.TemporaryDirectory() as tmp:
        init(Path(tmp))
        child = Path(tmp) / "a" / "b"
        child.mkdir(parents=True)
        assert find(child) is not None


def test_head_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        vd = init(Path(tmp))
        assert read_head(vd) == "main"
        write_head(vd, "experiment")
        assert read_head(vd) == "experiment"
