"""Tests for v0.4 verify/diff_chains features."""

import os
import tempfile

import vek


class TestVerify:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._orig = os.getcwd()
        os.chdir(self._tmp)
        vek.init()

    def teardown_method(self):
        os.chdir(self._orig)

    def _build_chain(self):
        h1 = vek.store(tool="add", input={"a": 1, "b": 2}, output={"sum": 3})
        h2 = vek.store(tool="mul", input={"a": 2, "b": 3}, output={"prod": 6})
        return h1, h2

    def test_verify_all_match(self):
        h1, h2 = self._build_chain()
        def executor(tool, inp):
            if tool == "add":
                return {"sum": inp["a"] + inp["b"]}
            if tool == "mul":
                return {"prod": inp["a"] * inp["b"]}
            return None

        results = vek.verify(h2, executor)
        assert len(results) == 2
        assert all(r["match"] for r in results)

    def test_verify_mismatch(self):
        h1, h2 = self._build_chain()
        # Executor returns wrong result for "mul"
        def executor(tool, inp):
            if tool == "add":
                return {"sum": inp["a"] + inp["b"]}
            if tool == "mul":
                return {"prod": 999}  # wrong!
            return None

        results = vek.verify(h2, executor)
        assert len(results) == 2
        assert results[0]["match"] is True
        assert results[1]["match"] is False
        assert results[1]["stored_output"] == {"prod": 6}
        assert results[1]["reexec_output"] == {"prod": 999}

    def test_verify_executor_error(self):
        h1, h2 = self._build_chain()
        def executor(tool, inp):
            raise RuntimeError("tool unavailable")

        results = vek.verify(h2, executor)
        assert len(results) == 2
        assert all(not r["match"] for r in results)
        assert "error" in results[0]

    def test_verify_single_node(self):
        h = vek.store(tool="echo", input="hello", output="hello")
        results = vek.verify(h, lambda t, i: i)
        assert len(results) == 1
        assert results[0]["match"] is True

    def test_verify_short_hash(self):
        h = vek.store(tool="echo", input="x", output="x")
        results = vek.verify(h[:8], lambda t, i: i)
        assert len(results) == 1

    def test_verify_blocks_store_in_executor(self):
        """Executor that calls vek.store() must not mutate the repo."""
        h = vek.store(tool="echo", input="hello", output="hello")
        node_count_before = len(vek.log(n=100))

        def bad_executor(tool, inp):
            # This should raise — verify is read-only
            vek.store(tool="side_effect", input="x", output="y")
            return inp

        results = vek.verify(h, bad_executor)
        # The node where executor ran should report error
        assert len(results) == 1
        assert results[0]["match"] is False
        assert "error" in results[0]
        # No new nodes written
        assert len(vek.log(n=100)) == node_count_before

    def test_verify_non_canonicalizable_output(self):
        """Executor returning un-serializable output should not crash verify."""
        h = vek.store(tool="echo", input="hello", output="hello")

        def circular_executor(tool, inp):
            # Return a circular structure that canonical() can't handle
            lst = [1, 2]
            lst.append(lst)
            return lst

        results = vek.verify(h, circular_executor)
        assert len(results) == 1
        assert results[0]["match"] is False
        assert "error" in results[0]

    def test_verify_flag_reset_after_error(self):
        """_verify_active must be reset even if verify() raises."""
        h = vek.store(tool="echo", input="x", output="x")
        from vek import api
        assert api._verify_active is False
        # Verify with an executor that raises on first node
        try:
            vek.verify(h, lambda t, i: (_ for _ in ()).throw(RuntimeError("boom")))
        except Exception:
            pass
        # Flag must be reset
        assert api._verify_active is False
        # store() must work again
        vek.store(tool="after", input="a", output="b")


class TestDiffChains:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._orig = os.getcwd()
        os.chdir(self._tmp)
        vek.init()

    def teardown_method(self):
        os.chdir(self._orig)

    def test_identical_chains(self):
        h1 = vek.store(tool="a", input="1", output="r1")
        h2 = vek.store(tool="b", input="2", output="r2")
        results = vek.diff_chains(h2, h2)
        assert len(results) == 2
        assert all(r["input_match"] for r in results)
        assert all(r["output_match"] for r in results)

    def test_diverged_chains(self):
        h1 = vek.store(tool="a", input="1", output="r1")
        h2 = vek.store(tool="b", input="2", output="r2")
        # Fork from h1 with different output
        vek.fork(h1, branch_name="fork1")
        h3 = vek.store(tool="c", input="3", output="r3_different")
        results = vek.diff_chains(h2, h3)
        # Root node (h1) should match; second node should differ
        assert len(results) == 2
        assert results[0]["input_match"] is True
        assert results[0]["output_match"] is True
        assert results[1]["output_match"] is False

    def test_different_length_chains(self):
        h1 = vek.store(tool="a", input="1", output="r1")
        h2 = vek.store(tool="b", input="2", output="r2")
        # Short chain: just h1
        results = vek.diff_chains(h1, h2)
        assert len(results) == 2
        assert results[0]["input_match"] is True  # both start at h1
        assert results[1]["node_b"] is not None
        assert results[1]["node_a"] is None  # chain A is shorter

    def test_single_node_diff(self):
        h = vek.store(tool="a", input="x", output="y")
        results = vek.diff_chains(h, h)
        assert len(results) == 1
        assert results[0]["input_match"] is True
        assert results[0]["output_match"] is True
