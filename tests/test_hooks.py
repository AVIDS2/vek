"""Tests for Phase 5: wrap decorator, hook, async session."""

import asyncio
import os
import tempfile
from unittest.mock import patch

import pytest

import vek
from vek.db import DB
from vek import api
from vek.hooks import wrap, hook


class TestWrap:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._orig = os.getcwd()
        os.chdir(self._tmp)
        vek.init()

    def teardown_method(self):
        os.chdir(self._orig)

    def test_wrap_records_call(self):
        @wrap
        def search(query: str) -> dict:
            return {"results": [query]}

        result = search("hello")
        assert result == {"results": ["hello"]}
        entries = vek.log()
        assert len(entries) == 1
        assert "search" in entries[0]["tool"]

    def test_wrap_preserves_return_value(self):
        @wrap
        def add(a: int, b: int) -> int:
            return a + b

        assert add(2, 3) == 5

    def test_wrap_records_args_as_input(self):
        @wrap
        def greet(name: str, greeting: str = "hello") -> str:
            return f"{greeting} {name}"

        greet("world")
        entries = vek.log()
        node = vek.show(entries[0]["hash"])
        assert node["input"]["name"] == "world"
        assert node["input"]["greeting"] == "hello"


class TestHook:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._orig = os.getcwd()
        os.chdir(self._tmp)
        vek.init()

    def teardown_method(self):
        os.chdir(self._orig)

    def test_hook_records_dispatch(self):
        def my_dispatch(tool_name, input_data):
            return {"ok": True, "tool": tool_name}

        hooked = hook(my_dispatch)
        result = hooked("search", {"q": "test"})
        assert result["ok"] is True
        entries = vek.log()
        assert len(entries) == 1
        assert entries[0]["tool"] == "search"


class TestAsyncSession:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._orig = os.getcwd()
        os.chdir(self._tmp)
        vek.init()

    def teardown_method(self):
        os.chdir(self._orig)

    def test_async_session_basic(self):
        async def run():
            async with vek.async_session() as s:
                h1 = s.store(tool="a", input="1", output="r1")
                h2 = s.store(tool="b", input="2", output="r2")
            return h1, h2

        h1, h2 = asyncio.run(run())
        entries = vek.log()
        assert len(entries) == 2
        assert entries[0]["parent_hash"] == h1

    def test_async_session_count(self):
        async def run():
            async with vek.async_session() as s:
                s.store(tool="a", input="1", output="r1")
                s.store(tool="b", input="2", output="r2")
                return s.count

        count = asyncio.run(run())
        assert count == 2

    def test_concurrent_async_sessions(self):
        """Two concurrent async sessions must not raise database is locked."""
        async def worker(name, n):
            async with vek.async_session() as s:
                for i in range(n):
                    s.store(tool=f"{name}_{i}", input=str(i), output=f"r{i}")
                return s.count

        async def run():
            t1 = asyncio.create_task(worker("a", 3))
            t2 = asyncio.create_task(worker("b", 3))
            c1, c2 = await asyncio.gather(t1, t2)
            return c1, c2

        c1, c2 = asyncio.run(run())
        assert c1 == 3
        assert c2 == 3
        entries = vek.log(n=10)
        # Both sessions committed — at least 3 entries on current branch
        assert len(entries) >= 3
        # No unreachable garbage
        result = vek.gc(dry_run=True)
        assert result["unreachable_nodes"] == []

    def test_async_session_releases_lock_on_init_failure(self):
        """HEAD.lock must not leak if __aenter__ fails after lock acquisition."""
        from pathlib import Path
        from vek.repo import find

        vd = find()
        lock_path = vd / "HEAD.lock"

        def exploding_begin(*a, **kw):
            raise RuntimeError("simulated init failure")

        async def run():
            with patch.object(DB, "begin_immediate", exploding_begin):
                with pytest.raises(RuntimeError, match="simulated init failure"):
                    async with vek.async_session() as s:
                        pass  # should never reach here

        asyncio.run(run())
        assert not lock_path.exists(), "HEAD.lock leaked after __aenter__ failure"
        # Subsequent session should succeed without stale-lock error
        async def run_ok():
            async with vek.async_session() as s:
                s.store(tool="after_fail", input="x", output="y")
                return s.count
        assert asyncio.run(run_ok()) == 1
