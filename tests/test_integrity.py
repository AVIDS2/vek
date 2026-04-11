"""Tests for Phase 2: fsck, gc, tags."""

import os
import tempfile

import pytest

import vek
from vek import api


class TestFsck:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._orig = os.getcwd()
        os.chdir(self._tmp)
        vek.init()

    def teardown_method(self):
        os.chdir(self._orig)

    def test_fsck_clean_repo(self):
        vek.store(tool="a", input="i", output="o")
        errors = vek.fsck()
        assert errors == []

    def test_fsck_clean_after_session(self):
        with vek.session() as s:
            s.store(tool="a", input="1", output="r1")
            s.store(tool="b", input="2", output="r2")
        errors = vek.fsck()
        assert errors == []


class TestGC:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._orig = os.getcwd()
        os.chdir(self._tmp)
        vek.init()

    def teardown_method(self):
        os.chdir(self._orig)

    def test_gc_nothing_to_clean(self):
        vek.store(tool="a", input="i", output="o")
        result = vek.gc(dry_run=True)
        assert result["unreachable_nodes"] == []
        assert result["orphan_objects"] == []

    def test_gc_dry_run_no_delete(self):
        vek.store(tool="a", input="i", output="o")
        result = vek.gc(dry_run=True)
        assert result["deleted"] is False


class TestTags:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._orig = os.getcwd()
        os.chdir(self._tmp)
        vek.init()

    def teardown_method(self):
        os.chdir(self._orig)

    def test_tag_list_empty(self):
        tags = vek.tag()
        assert tags == []

    def test_tag_create_and_list(self):
        h = vek.store(tool="a", input="i", output="o")
        vek.tag("v1")
        tags = vek.tag()
        assert len(tags) == 1
        assert tags[0][0] == "v1"
        assert tags[0][1] == h

    def test_tag_specific_hash(self):
        h1 = vek.store(tool="a", input="1", output="1")
        vek.store(tool="b", input="2", output="2")
        vek.tag("checkpoint", h1)
        tags = vek.tag()
        assert tags[0][1] == h1

    def test_tag_duplicate_raises(self):
        vek.store(tool="a", input="i", output="o")
        vek.tag("v1")
        with pytest.raises(api.VekError, match="already exists"):
            vek.tag("v1")

    def test_tag_empty_branch_raises(self):
        with pytest.raises(api.VekError, match="nothing to tag"):
            vek.tag("v1")
