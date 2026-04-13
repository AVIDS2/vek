"""Tests for v0.3 query/find/annotate features."""

import os
import tempfile

import vek


class TestQuery:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._orig = os.getcwd()
        os.chdir(self._tmp)
        vek.init()

    def teardown_method(self):
        os.chdir(self._orig)

    def _populate(self):
        """Create a few nodes with different tools and timestamps."""
        vek.store(tool="search", input={"q": "hello"}, output={"results": [1]})
        vek.store(tool="summarise", input={"text": "abc"}, output={"summary": "x"})
        vek.store(tool="search", input={"q": "world"}, output={"results": [2]})

    def test_query_no_filter(self):
        self._populate()
        nodes = vek.query()
        assert len(nodes) == 3

    def test_query_by_tool(self):
        self._populate()
        nodes = vek.query(tool="search")
        assert len(nodes) == 2
        assert all(n["tool"] == "search" for n in nodes)

    def test_query_by_branch(self):
        self._populate()
        nodes = vek.query(branch="main")
        assert len(nodes) == 3

    def test_query_by_branch_nonexistent(self):
        self._populate()
        nodes = vek.query(branch="nope")
        assert nodes == []

    def test_query_limit(self):
        self._populate()
        nodes = vek.query(limit=1)
        assert len(nodes) == 1

    def test_query_since_until(self):
        self._populate()
        # since far past should return all
        nodes = vek.query(since="2000-01-01")
        assert len(nodes) == 3
        # until far future should return all
        nodes = vek.query(until="2099-01-01")
        assert len(nodes) == 3
        # since far future should return none
        nodes = vek.query(since="2099-01-01")
        assert len(nodes) == 0

    def test_query_combo(self):
        self._populate()
        nodes = vek.query(tool="search", limit=1)
        assert len(nodes) == 1
        assert nodes[0]["tool"] == "search"


class TestSearch:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._orig = os.getcwd()
        os.chdir(self._tmp)
        vek.init()

    def teardown_method(self):
        os.chdir(self._orig)

    def test_find_in_output(self):
        vek.store(tool="search", input={"q": "hello"}, output={"results": [1]})
        vek.store(tool="search", input={"q": "world"}, output={"results": [2]})
        vek.store(tool="summarise", input={"text": "abc"}, output={"summary": "x"})
        nodes = vek.search("results", in_field="output")
        assert len(nodes) == 2

    def test_find_in_input(self):
        vek.store(tool="search", input={"q": "hello"}, output={"results": [1]})
        vek.store(tool="summarise", input={"text": "abc"}, output={"summary": "x"})
        nodes = vek.search("hello", in_field="input")
        assert len(nodes) == 1
        assert nodes[0]["tool"] == "search"

    def test_find_no_match(self):
        vek.store(tool="search", input={"q": "hello"}, output={"results": [1]})
        nodes = vek.search("nonexistent_pattern")
        assert nodes == []

    def test_find_limit(self):
        vek.store(tool="a", input="x", output="match")
        vek.store(tool="b", input="y", output="match")
        vek.store(tool="c", input="z", output="match")
        nodes = vek.search("match", limit=2)
        assert len(nodes) == 2


class TestAnnotate:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._orig = os.getcwd()
        os.chdir(self._tmp)
        vek.init()

    def teardown_method(self):
        os.chdir(self._orig)

    def test_annotate_chain(self):
        h1 = vek.store(tool="search", input={"q": "a"}, output={"r": 1})
        h2 = vek.store(tool="summarise", input={"t": "b"}, output={"r": 2})
        chain = vek.annotate(h2)
        assert len(chain) == 2
        # root-first order
        assert chain[0]["hash"] == h1
        assert chain[1]["hash"] == h2
        # materialised content
        assert chain[0]["input"] == {"q": "a"}
        assert chain[0]["output"] == {"r": 1}
        assert chain[1]["input"] == {"t": "b"}
        assert chain[1]["output"] == {"r": 2}

    def test_annotate_single_node(self):
        h = vek.store(tool="search", input={"q": "x"}, output={"r": 0})
        chain = vek.annotate(h)
        assert len(chain) == 1
        assert chain[0]["input"] == {"q": "x"}

    def test_annotate_short_hash(self):
        h = vek.store(tool="search", input="q", output="r")
        chain = vek.annotate(h[:8])
        assert len(chain) == 1
