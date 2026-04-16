"""Tests for v0.5 reexec/checkpoint features."""

import os
import tempfile

import pytest
import vek
from vek.api import VekError


class TestReexec:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._orig = os.getcwd()
        os.chdir(self._tmp)
        vek.init()

    def teardown_method(self):
        os.chdir(self._orig)

    def test_reexec_creates_new_chain(self):
        h1 = vek.store(tool="add", input={"a": 1, "b": 2}, output={"sum": 3})
        h2 = vek.store(tool="mul", input={"a": 2, "b": 3}, output={"prod": 6})

        def executor(tool, inp):
            if tool == "add":
                return {"sum": inp["a"] + inp["b"]}
            if tool == "mul":
                return {"prod": inp["a"] * inp["b"]}

        result = vek.reexec(h2, executor)
        assert result["nodes"] == 2
        assert result["ref"] == f"reexec-{h2[:8]}"
        assert result["tip"] is not None
        # New chain tip should differ from original (different timestamps)
        assert result["tip"] != h2

    def test_reexec_does_not_advance_current_branch(self):
        h1 = vek.store(tool="echo", input="a", output="a")
        tip_before = vek.status()["tip"]

        vek.reexec(h1, lambda t, i: i)
        tip_after = vek.status()["tip"]
        assert tip_before == tip_after

    def test_reexec_custom_ref(self):
        h = vek.store(tool="echo", input="x", output="x")
        result = vek.reexec(h, lambda t, i: i, ref="my-replay")
        assert result["ref"] == "my-replay"

    def test_reexec_ref_already_exists_raises(self):
        h = vek.store(tool="echo", input="x", output="x")
        vek.reexec(h, lambda t, i: i, ref="taken")
        with pytest.raises(VekError, match="ref already exists"):
            vek.reexec(h, lambda t, i: i, ref="taken")

    def test_reexec_with_different_output(self):
        h = vek.store(tool="echo", input="hello", output="hello")
        result = vek.reexec(h, lambda t, i: "MODIFIED", ref="modified")
        # Verify the new chain has different output
        chain = vek.replay(result["tip"])
        assert chain[0]["output"] == "MODIFIED"

    def test_reexec_chain_is_replayable(self):
        vek.store(tool="a", input="1", output="r1")
        h2 = vek.store(tool="b", input="2", output="r2")
        result = vek.reexec(h2, lambda t, i: f"new_{i}", ref="re1")
        chain = vek.replay(result["tip"])
        assert len(chain) == 2
        assert chain[0]["tool"] == "a"
        assert chain[1]["tool"] == "b"

    def test_reexec_fsck_clean(self):
        h = vek.store(tool="echo", input="x", output="x")
        vek.reexec(h, lambda t, i: i, ref="check")
        errors = vek.fsck()
        assert errors == []

    def test_reexec_blocks_store_in_executor(self):
        """Executor that calls vek.store() must not advance current branch."""
        h = vek.store(tool="echo", input="hello", output="hello")
        node_count_before = len(vek.log(n=100))

        def bad_executor(tool, inp):
            vek.store(tool="side_effect", input="x", output="y")
            return inp

        with pytest.raises(Exception):
            vek.reexec(h, bad_executor, ref="bad")
        # No side-effect nodes on current branch
        assert len(vek.log(n=100)) == node_count_before

    def test_reexec_failed_executor_rolls_back(self):
        """Failed executor must not leave unreachable garbage."""
        h1 = vek.store(tool="a", input="1", output="r1")
        h2 = vek.store(tool="b", input="2", output="r2")
        status_before = vek.status()

        def failing_executor(tool, inp):
            if tool == "b":
                raise RuntimeError("boom")
            return inp

        with pytest.raises(RuntimeError, match="boom"):
            vek.reexec(h2, failing_executor, ref="fail")
        status_after = vek.status()
        # Node and object counts must not increase
        assert status_after["nodes"] == status_before["nodes"]

    def test_reexec_rejects_tag_namespace(self):
        h = vek.store(tool="echo", input="x", output="x")
        with pytest.raises(VekError, match="reserved namespace"):
            vek.reexec(h, lambda t, i: i, ref="tag/fake")

    def test_reexec_rejects_checkpoint_namespace(self):
        h = vek.store(tool="echo", input="x", output="x")
        with pytest.raises(VekError, match="reserved namespace"):
            vek.reexec(h, lambda t, i: i, ref="checkpoint/fake")

    def test_reexec_store_works_after_failed(self):
        """_verify_active must be reset even if reexec() fails."""
        h = vek.store(tool="echo", input="x", output="x")
        try:
            vek.reexec(h, lambda t, i: (_ for _ in ()).throw(RuntimeError("boom")), ref="err")
        except RuntimeError:
            pass
        # store() must work again
        vek.store(tool="after", input="a", output="b")


class TestCheckpoint:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._orig = os.getcwd()
        os.chdir(self._tmp)
        vek.init()

    def teardown_method(self):
        os.chdir(self._orig)

    def test_checkpoint_create(self):
        h = vek.store(tool="echo", input="x", output="x")
        ref = vek.checkpoint(h, "v1-verified")
        assert ref == "checkpoint/v1-verified"

    def test_checkpoint_list(self):
        h = vek.store(tool="echo", input="x", output="x")
        vek.checkpoint(h, "cp1")
        cps = vek.list_checkpoints()
        assert len(cps) == 1
        assert cps[0] == ("cp1", h)

    def test_checkpoint_duplicate_raises(self):
        h = vek.store(tool="echo", input="x", output="x")
        vek.checkpoint(h, "dup")
        with pytest.raises(VekError, match="checkpoint already exists"):
            vek.checkpoint(h, "dup")

    def test_checkpoint_short_hash(self):
        h = vek.store(tool="echo", input="x", output="x")
        ref = vek.checkpoint(h[:8], "short")
        cps = vek.list_checkpoints()
        assert cps[0] == ("short", h)

    def test_checkpoint_does_not_appear_in_branches(self):
        h = vek.store(tool="echo", input="x", output="x")
        vek.checkpoint(h, "mycp")
        branches = vek.branch()
        branch_names = [name for name, _ in branches]
        assert "checkpoint/mycp" not in branch_names

    def test_checkpoint_does_not_appear_in_tags(self):
        h = vek.store(tool="echo", input="x", output="x")
        vek.checkpoint(h, "mycp")
        tags = vek.tag()
        tag_names = [name for name, _ in tags]
        assert "mycp" not in tag_names

    def test_multiple_checkpoints(self):
        h1 = vek.store(tool="a", input="1", output="r1")
        h2 = vek.store(tool="b", input="2", output="r2")
        vek.checkpoint(h1, "step1")
        vek.checkpoint(h2, "step2")
        cps = vek.list_checkpoints()
        assert len(cps) == 2
        labels = [c[0] for c in cps]
        assert "step1" in labels
        assert "step2" in labels
