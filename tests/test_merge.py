"""Tests for Phase 3: merge, graph log, structural diff."""

import os
import tempfile

import pytest

import vek
from vek import api
from vek.graph import json_diff


class TestMerge:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._orig = os.getcwd()
        os.chdir(self._tmp)
        vek.init()

    def teardown_method(self):
        os.chdir(self._orig)

    def test_merge_creates_merge_node(self):
        # Create shared ancestor
        vek.store(tool="base", input="0", output="r0")
        # Create dev branch and add a commit on it
        vek.branch("dev")
        h_dev = vek.store(tool="dev_work", input="d", output="rd")
        # Switch back to main and add a different commit
        vek.branch("main")
        h_main = vek.store(tool="main_work", input="m", output="rm")
        # Now merge dev into main
        merge_hash = vek.merge("dev")
        node = vek.show(merge_hash)
        assert node["tool"] == "__merge__"
        assert node["parent_hash"] == h_main
        assert node["merge_parent"] == h_dev

    def test_merge_same_tip_raises(self):
        vek.store(tool="a", input="1", output="r1")
        vek.branch("dev")
        with pytest.raises(api.VekError, match="already up to date"):
            vek.merge("dev")

    def test_merge_empty_current_raises(self):
        with pytest.raises(api.VekError, match="has no commits"):
            vek.merge("dev")

    def test_merge_empty_target_raises(self):
        vek.store(tool="a", input="1", output="r1")
        with pytest.raises(api.VekError, match="not found or empty"):
            vek.merge("nonexistent")

    def test_fsck_after_merge(self):
        vek.store(tool="base", input="0", output="r0")
        vek.branch("dev")
        vek.store(tool="dev_work", input="d", output="rd")
        vek.branch("main")
        vek.store(tool="main_work", input="m", output="rm")
        vek.merge("dev")
        errors = vek.fsck()
        assert errors == []


class TestGraphLog:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._orig = os.getcwd()
        os.chdir(self._tmp)
        vek.init()

    def teardown_method(self):
        os.chdir(self._orig)

    def test_graph_log_empty(self):
        lines = vek.log_graph()
        assert lines == ["(empty)"]

    def test_graph_log_with_nodes(self):
        vek.store(tool="a", input="1", output="r1")
        vek.store(tool="b", input="2", output="r2")
        lines = vek.log_graph()
        assert len(lines) >= 2


class TestJsonDiff:
    def test_identical(self):
        assert json_diff({"a": 1}, {"a": 1}) == []

    def test_change(self):
        changes = json_diff({"a": 1}, {"a": 2})
        assert len(changes) == 1
        assert changes[0]["op"] == "change"
        assert changes[0]["path"] == "/a"

    def test_add_key(self):
        changes = json_diff({"a": 1}, {"a": 1, "b": 2})
        assert len(changes) == 1
        assert changes[0]["op"] == "add"

    def test_remove_key(self):
        changes = json_diff({"a": 1, "b": 2}, {"a": 1})
        assert len(changes) == 1
        assert changes[0]["op"] == "remove"

    def test_nested_change(self):
        changes = json_diff({"a": {"b": 1}}, {"a": {"b": 2}})
        assert changes[0]["path"] == "/a/b"

    def test_list_add(self):
        changes = json_diff([1, 2], [1, 2, 3])
        assert len(changes) == 1
        assert changes[0]["op"] == "add"
        assert changes[0]["path"] == "[2]"

    def test_type_change(self):
        changes = json_diff({"a": 1}, {"a": "str"})
        assert changes[0]["op"] == "change"

    def test_structural_diff_in_api(self):
        """Verify api.diff returns structural diff format."""
        tmp = tempfile.mkdtemp()
        orig = os.getcwd()
        os.chdir(tmp)
        vek.init()
        h1 = vek.store(tool="t", input={"x": 1}, output={"y": 1})
        h2 = vek.store(tool="t", input={"x": 2}, output={"y": 2})
        d = vek.diff(h1, h2)
        assert isinstance(d["input_diff"], list)
        assert d["input_diff"][0]["op"] == "change"
        os.chdir(orig)
