"""Tests for Phase 5: wrap decorator, hook, async session."""

import asyncio
import os
import tempfile

import vek
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
