"""Auto-recording decorators and hooks for agent tool dispatch.

Usage::

    # 1. Decorator — wraps a single function
    @vek.wrap
    def search(query: str) -> dict:
        return {"results": [...]}

    # 2. Hook — wraps an arbitrary dispatch function
    dispatch = vek.hook(original_dispatch)
    result = dispatch("search", {"q": "hello"})

    # 3. Async support
    async with vek.async_session() as s:
        s.store(tool="search", input=query, output=result)
"""

from __future__ import annotations

import asyncio
import functools
import inspect
from pathlib import Path
from typing import Any, Callable, TypeVar

from vek.api import _open, store as _store
from vek.db import DB
from vek.repo import read_head

F = TypeVar("F", bound=Callable[..., Any])


# -------------------------------------------------------------------- wrap


def wrap(fn: F) -> F:
    """Decorator that auto-records each call as a vek node.

    The function name becomes the ``tool``, the arguments become
    ``input``, and the return value becomes ``output``.

    Works for both sync and async functions.
    """
    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            tool_name = fn.__qualname__
            input_data = _build_input(fn, args, kwargs)
            result = await fn(*args, **kwargs)
            _store(tool=tool_name, input=input_data, output=result)
            return result

        return async_wrapper  # type: ignore[return-value]

    @functools.wraps(fn)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        tool_name = fn.__qualname__
        input_data = _build_input(fn, args, kwargs)
        result = fn(*args, **kwargs)
        _store(tool=tool_name, input=input_data, output=result)
        return result

    return sync_wrapper  # type: ignore[return-value]


def _build_input(fn: Callable[..., Any], args: tuple, kwargs: dict) -> dict:
    """Convert positional + keyword args into a dict for storage."""
    sig = inspect.signature(fn)
    bound = sig.bind(*args, **kwargs)
    bound.apply_defaults()
    return dict(bound.arguments)


# -------------------------------------------------------------------- hook


def hook(dispatch_fn: Callable[[str, Any], Any]) -> Callable[[str, Any], Any]:
    """Wrap a tool dispatch function to auto-record calls.

    ``dispatch_fn(tool_name, input) -> output``

    Returns a new dispatch function that records every call.
    """
    @functools.wraps(dispatch_fn)
    def wrapper(tool_name: str, input_data: Any) -> Any:
        result = dispatch_fn(tool_name, input_data)
        _store(tool=tool_name, input=input_data, output=result)
        return result

    return wrapper


# -------------------------------------------------------------- async session


class AsyncSession:
    """Async context manager for recording tool calls.

    Usage::

        async with AsyncSession() as s:
            s.store(tool="search", input=q, output=r)
    """

    def __init__(self, *, path: Path | None = None):
        self._start_path = path
        self._vd: Path | None = None
        self._db: DB | None = None
        self._tip: str | None = None
        self._count: int = 0

    async def __aenter__(self) -> AsyncSession:
        loop = asyncio.get_running_loop()
        self._vd, self._db = await loop.run_in_executor(
            None, _open, self._start_path
        )
        branch = read_head(self._vd)
        self._tip = self._db.get_ref(branch)
        self._db._autocommit = False
        return self

    async def __aexit__(self, exc_type: type | None, *exc: object) -> bool:
        loop = asyncio.get_running_loop()
        if self._db is not None:
            if exc_type is None:
                await loop.run_in_executor(None, self._db._conn.commit)
            else:
                await loop.run_in_executor(None, self._db._conn.rollback)
            self._db._autocommit = True
            self._db.close()
        return False

    def store(self, tool: str, input: object, output: object) -> str:
        """Record a tool call (sync — safe from async context for SQLite)."""
        h = _store(
            tool, input, output,
            parent=self._tip,
            _vd=self._vd,
            _db=self._db,
        )
        self._tip = h
        self._count += 1
        return h

    @property
    def tip(self) -> str | None:
        return self._tip

    @property
    def count(self) -> int:
        return self._count
