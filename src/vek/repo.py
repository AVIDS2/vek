"""Repository discovery and initialisation.

Layout mirrors git:
    .vek/
    |-- objects/     # reserved for future loose-object storage
    |-- refs/        # reserved for future ref files
    |-- HEAD         # current branch  (text: "ref: <branch>")
    |-- config       # repo configuration
    |-- vek.db       # SQLite database (objects + nodes + refs)
"""

from __future__ import annotations

import time
from pathlib import Path

DIR = ".vek"
DB_NAME = "vek.db"
HEAD = "HEAD"
HEAD_LOCK = "HEAD.lock"
CONFIG = "config"
DEFAULT_BRANCH = "main"
LOCK_STALE_SECONDS = 300  # 5 minutes


def find(start: Path | None = None) -> Path | None:
    """Walk up the directory tree until a .vek/ directory is found."""
    p = (start or Path.cwd()).resolve()
    while True:
        candidate = p / DIR
        if candidate.is_dir():
            return candidate
        if p.parent == p:
            return None
        p = p.parent


def init(path: Path | None = None) -> Path:
    """Create a .vek/ repository.  Idempotent."""
    root = (path or Path.cwd()).resolve()
    vd = root / DIR
    vd.mkdir(exist_ok=True)
    (vd / "objects").mkdir(exist_ok=True)
    (vd / "refs").mkdir(exist_ok=True)
    head = vd / HEAD
    if not head.exists():
        head.write_text(f"ref: {DEFAULT_BRANCH}\n")
    cfg = vd / CONFIG
    if not cfg.exists():
        cfg.write_text("[core]\n")
    return vd


def read_head(vd: Path) -> str:
    """Return the current branch name."""
    text = (vd / HEAD).read_text().strip()
    return text.removeprefix("ref: ")


def write_head(vd: Path, ref: str) -> None:
    (vd / HEAD).write_text(f"ref: {ref}\n")


# ------------------------------------------------------------------- locking


class LockError(Exception):
    """Could not acquire HEAD lock."""


class HeadLock:
    """Advisory file lock on HEAD to prevent concurrent branch pointer writes.

    Usage::

        with HeadLock(vek_dir):
            write_head(vek_dir, "main")
    """

    def __init__(self, vd: Path):
        self._path = vd / HEAD_LOCK

    def __enter__(self) -> "HeadLock":
        self._acquire()
        return self

    def __exit__(self, *exc: object) -> bool:
        self._release()
        return False

    def _acquire(self) -> None:
        # Remove stale lock files
        if self._path.exists():
            age = time.time() - self._path.stat().st_mtime
            if age > LOCK_STALE_SECONDS:
                self._path.unlink(missing_ok=True)

        try:
            # Atomic creation — fails if file already exists
            fd = self._path.open("x")
            fd.write(str(time.time()))
            fd.close()
        except FileExistsError:
            raise LockError(
                f"Unable to acquire lock: {self._path} exists. "
                "Another vek process may be running."
            )

    def _release(self) -> None:
        self._path.unlink(missing_ok=True)
