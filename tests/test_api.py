"""Integration tests for the public API."""

import os
import tempfile

import vek
from vek import api


class TestStore:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._orig = os.getcwd()
        os.chdir(self._tmp)
        vek.init()

    def teardown_method(self):
        os.chdir(self._orig)

    def test_store_returns_64char_hash(self):
        h = vek.store(tool="search", input={"q": "hello"}, output={"r": "world"})
        assert isinstance(h, str)
        assert len(h) == 64

    def test_log_after_store(self):
        vek.store(tool="search", input="q", output="r")
        entries = vek.log()
        assert len(entries) == 1
        assert entries[0]["tool"] == "search"

    def test_chain_builds_parent_links(self):
        h1 = vek.store(tool="a", input="1", output="1")
        h2 = vek.store(tool="b", input="2", output="2")
        entries = vek.log()
        assert len(entries) == 2
        assert entries[0]["hash"] == h2
        assert entries[0]["parent_hash"] == h1

    def test_content_dedup(self):
        vek.store(tool="a", input="same", output="same")
        vek.store(tool="a", input="same", output="same")
        entries = vek.log()
        assert entries[0]["input_hash"] == entries[1]["input_hash"]
        assert entries[0]["output_hash"] == entries[1]["output_hash"]
        # Different timestamps -> different node hashes
        assert entries[0]["hash"] != entries[1]["hash"]


class TestSession:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._orig = os.getcwd()
        os.chdir(self._tmp)
        vek.init()

    def teardown_method(self):
        os.chdir(self._orig)

    def test_session_chains(self):
        with vek.session() as s:
            h1 = s.store(tool="a", input="1", output="1")
            h2 = s.store(tool="b", input="2", output="2")
        entries = vek.log()
        assert len(entries) == 2
        assert entries[0]["parent_hash"] == h1

    def test_session_tip(self):
        with vek.session() as s:
            s.store(tool="x", input="i", output="o")
            assert s.tip is not None
            assert len(s.tip) == 64


class TestBranchFork:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._orig = os.getcwd()
        os.chdir(self._tmp)
        vek.init()

    def teardown_method(self):
        os.chdir(self._orig)

    def test_branch_list_empty(self):
        refs = vek.branch()
        assert refs == []

    def test_branch_create(self):
        vek.store(tool="x", input="i", output="o")
        vek.branch("dev")
        refs = vek.branch()
        names = [r[0] for r in refs]
        assert "main" in names
        assert "dev" in names

    def test_fork_creates_branch(self):
        h = vek.store(tool="x", input="i", output="o")
        bname = vek.fork(h, "alt")
        assert bname == "alt"


class TestReplayDiff:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._orig = os.getcwd()
        os.chdir(self._tmp)
        vek.init()

    def teardown_method(self):
        os.chdir(self._orig)

    def test_replay_root_to_tip(self):
        with vek.session() as s:
            s.store(tool="a", input="1", output="r1")
            h2 = s.store(tool="b", input="2", output="r2")
        chain = vek.replay(h2)
        assert len(chain) == 2
        assert chain[0]["tool"] == "a"
        assert chain[1]["tool"] == "b"
        assert "input" in chain[0]
        assert "output" in chain[0]

    def test_diff_same_input(self):
        h1 = vek.store(tool="t", input="same", output="out1")
        h2 = vek.store(tool="t", input="same", output="out2")
        d = vek.diff(h1, h2)
        assert d["input_match"] is True
        assert d["output_match"] is False
        assert "output_diff" in d
