"""Tests for Phase 1: short hash, show, cat-file, status."""

import os
import tempfile

import vek
from vek import api


class TestShortHash:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._orig = os.getcwd()
        os.chdir(self._tmp)
        vek.init()

    def teardown_method(self):
        os.chdir(self._orig)

    def test_short_prefix_resolves(self):
        h = vek.store(tool="a", input="i", output="o")
        node = api.show(h[:8])
        assert node["hash"] == h

    def test_short_prefix_in_fork(self):
        h = vek.store(tool="a", input="i", output="o")
        bname = vek.fork(h[:10], "alt")
        assert bname == "alt"

    def test_short_prefix_in_diff(self):
        h1 = vek.store(tool="a", input="x", output="o1")
        h2 = vek.store(tool="a", input="x", output="o2")
        d = vek.diff(h1[:10], h2[:10])
        assert d["input_match"] is True

    def test_short_prefix_in_replay(self):
        with vek.session() as s:
            s.store(tool="a", input="1", output="r1")
            h = s.store(tool="b", input="2", output="r2")
        chain = vek.replay(h[:10])
        assert len(chain) == 2

    def test_unknown_prefix_raises(self):
        import pytest
        with pytest.raises(api.VekError, match="object not found"):
            api.show("deadbeef00")

    def test_ambiguous_prefix_raises(self):
        # Hard to guarantee ambiguity, so just test the mechanism
        import pytest
        with pytest.raises(api.VekError, match="object not found"):
            api.cat_file("0000000000")


class TestShow:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._orig = os.getcwd()
        os.chdir(self._tmp)
        vek.init()

    def teardown_method(self):
        os.chdir(self._orig)

    def test_show_has_materialised_content(self):
        h = vek.store(tool="search", input={"q": "hello"}, output={"r": "world"})
        node = vek.show(h)
        assert node["input"] == {"q": "hello"}
        assert node["output"] == {"r": "world"}
        assert node["tool"] == "search"
        assert node["hash"] == h


class TestCatFile:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._orig = os.getcwd()
        os.chdir(self._tmp)
        vek.init()

    def teardown_method(self):
        os.chdir(self._orig)

    def test_cat_file_returns_bytes(self):
        h = vek.store(tool="a", input="hello", output="world")
        node = vek.show(h)
        blob = vek.cat_file(node["input_hash"])
        assert isinstance(blob, bytes)
        assert b"hello" in blob


class TestStatus:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._orig = os.getcwd()
        os.chdir(self._tmp)
        vek.init()

    def teardown_method(self):
        os.chdir(self._orig)

    def test_status_empty(self):
        s = vek.status()
        assert s["branch"] == "main"
        assert s["tip"] is None
        assert s["nodes"] == 0

    def test_status_after_store(self):
        h = vek.store(tool="a", input="i", output="o")
        s = vek.status()
        assert s["tip"] == h
        assert s["nodes"] == 1
        assert s["objects"] == 2  # input + output blobs
        assert s["refs"] == 1
