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

from pathlib import Path

DIR = ".vek"
DB_NAME = "vek.db"
HEAD = "HEAD"
CONFIG = "config"
DEFAULT_BRANCH = "main"


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
