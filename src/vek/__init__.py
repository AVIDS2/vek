"""vek - Content-addressed execution store for AI agents."""

from vek.api import init, store, log, branch, fork, diff, replay
from vek.session import Session as _Session

__version__ = "0.1.0"
__all__ = ["init", "store", "log", "branch", "fork", "diff", "replay", "session"]


def session(**kwargs):
    """Open an auto-recording execution session."""
    return _Session(**kwargs)
