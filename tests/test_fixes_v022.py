"""Tests for v0.2.2 fixes: concurrent store, fsck refs, import validation, branch/tag separation."""

import os
import sqlite3
import tempfile
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest

import vek
from vek import api
from vek.db import DB
from vek.repo import find, DB_NAME


class TestAtomicStore:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._orig = os.getcwd()
        os.chdir(self._tmp)
        vek.init()

    def teardown_method(self):
        os.chdir(self._orig)

    def test_store_chains_correctly(self):
        """Sequential stores should form a clean chain with no orphans."""
        h1 = vek.store(tool="a", input="1", output="r1")
        h2 = vek.store(tool="b", input="2", output="r2")
        h3 = vek.store(tool="c", input="3", output="r3")
        entries = vek.log()
        assert len(entries) == 3
        assert entries[0]["hash"] == h3
        assert entries[0]["parent_hash"] == h2
        assert entries[1]["parent_hash"] == h1

    def test_concurrent_stores_no_lost_history(self):
        """Two threads storing concurrently must both appear in the chain."""
        os.chdir(self._tmp)
        N = 10

        def do_store(i):
            return vek.store(tool=f"t{i}", input=str(i), output=f"r{i}")

        with ThreadPoolExecutor(max_workers=4) as pool:
            hashes = list(pool.map(do_store, range(N)))

        # All N hashes should be distinct and reachable
        assert len(set(hashes)) == N
        entries = vek.log(n=N + 5)
        entry_hashes = {e["hash"] for e in entries}
        for h in hashes:
            assert h in entry_hashes, f"hash {h[:10]} lost from history"

        # No unreachable garbage
        result = vek.gc(dry_run=True)
        assert result["unreachable_nodes"] == []

    def test_store_rollback_on_failure(self):
        """If put_node raises, ref and objects should not be corrupted."""
        h1 = vek.store(tool="a", input="1", output="r1")
        tip_before = vek.status()["tip"]
        assert tip_before == h1

        # Patch put_node to raise after blobs are written
        original_put_node = DB.put_node

        def exploding_put_node(self, *args, **kwargs):
            raise RuntimeError("simulated failure")

        with patch.object(DB, "put_node", exploding_put_node):
            with pytest.raises(RuntimeError, match="simulated failure"):
                vek.store(tool="b", input="2", output="r2")

        # Ref should still point to h1 — not corrupted
        tip_after = vek.status()["tip"]
        assert tip_after == h1
        # Log should still have exactly 1 entry
        assert len(vek.log()) == 1


class TestFsckRefs:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._orig = os.getcwd()
        os.chdir(self._tmp)
        vek.init()

    def teardown_method(self):
        os.chdir(self._orig)

    def test_fsck_detects_bad_ref(self):
        """fsck should report refs pointing to non-existent nodes."""
        vek.store(tool="a", input="1", output="r1")
        # Inject a bad ref directly into the database
        vd = find()
        db = DB(vd / DB_NAME)
        db.set_ref("broken", "f" * 64)
        db.close()
        errors = vek.fsck()
        assert len(errors) == 1
        assert "broken" in errors[0]["error"]

    def test_fsck_clean_with_valid_refs(self):
        """fsck should pass with valid refs."""
        vek.store(tool="a", input="1", output="r1")
        assert vek.fsck() == []


class TestImportValidation:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._orig = os.getcwd()
        os.chdir(self._tmp)
        vek.init()

    def teardown_method(self):
        os.chdir(self._orig)

    def test_import_rejects_bad_ref(self):
        """Import should skip refs pointing to non-existent nodes."""
        bad_data = {
            "version": 1,
            "objects": [],
            "nodes": [],
            "refs": [{"name": "bad_branch", "hash": "f" * 64}],
        }
        stats = vek.import_data(bad_data)
        assert stats["refs_imported"] == 0
        assert stats.get("refs_skipped_invalid", 0) == 1
        # Verify the bad ref was not written
        branches = dict(vek.branch())
        assert "bad_branch" not in branches

    def test_import_accepts_valid_ref(self):
        """Import should accept refs pointing to existing nodes."""
        vek.store(tool="a", input="1", output="r1")
        data = vek.export()
        # Import into fresh repo
        tmp2 = tempfile.mkdtemp()
        os.chdir(tmp2)
        vek.init()
        stats = vek.import_data(data)
        assert stats["refs_imported"] == 1


class TestBranchTagSeparation:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._orig = os.getcwd()
        os.chdir(self._tmp)
        vek.init()

    def teardown_method(self):
        os.chdir(self._orig)

    def test_branch_does_not_list_tags(self):
        """branch() in list mode should not include tag/ refs."""
        vek.store(tool="a", input="1", output="r1")
        vek.tag("v1")
        branches = vek.branch()
        names = [name for name, _ in branches]
        assert "main" in names
        assert "tag/v1" not in names

    def test_tag_still_works(self):
        """Tags should still be created and listed via tag()."""
        vek.store(tool="a", input="1", output="r1")
        vek.tag("v1")
        tags = vek.tag()
        assert len(tags) == 1
        assert tags[0][0] == "v1"
