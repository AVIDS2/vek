"""Tests for repository init / discovery."""

import os
import sqlite3
import tempfile
from pathlib import Path

from vek.repo import DB_NAME, find, init, read_head, write_head


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


def test_fresh_repo_has_indexes():
    with tempfile.TemporaryDirectory() as tmp:
        vd = init(Path(tmp))
        # DB is created on first open, not init — trigger it
        import vek as _vek
        _cwd = os.getcwd()
        os.chdir(tmp)
        try:
            _vek.store(tool="ping", input="x", output="y")
        finally:
            os.chdir(_cwd)
        conn = sqlite3.connect(str(vd / DB_NAME))
        indexes = {
            row[1]
            for row in conn.execute("PRAGMA index_list('nodes')").fetchall()
        }
        conn.close()
        assert "idx_nodes_tool" in indexes
        assert "idx_nodes_timestamp" in indexes
        assert "idx_nodes_parent" in indexes
