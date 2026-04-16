"""vek - Content-addressed execution store for AI agents."""

from vek.api import (
    init, store, log, branch, fork, diff, replay,
    show, cat_file, status, tag, fsck, gc,
    merge, log_graph, export, import_data,
    query, search, annotate,
    verify, diff_chains,
    reexec, checkpoint, list_checkpoints,
)
from vek.hooks import AsyncSession as _AsyncSession
from vek.hooks import hook, wrap
from vek.session import Session as _Session

__version__ = "0.5.2"
__all__ = [
    "init", "store", "log", "branch", "fork", "diff", "replay",
    "show", "cat_file", "status", "tag", "fsck", "gc",
    "merge", "log_graph", "export", "import_data",
    "query", "search", "annotate",
    "verify", "diff_chains",
    "reexec", "checkpoint", "list_checkpoints",
    "session", "async_session", "wrap", "hook",
]


def session(**kwargs):
    """Open an auto-recording execution session."""
    return _Session(**kwargs)


def async_session(**kwargs):
    """Open an async auto-recording execution session."""
    return _AsyncSession(**kwargs)
