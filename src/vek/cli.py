"""Command-line interface.

Usage:
    vek init
    vek log [-n N]
    vek branch [name]
    vek fork <hash> [--name NAME]
    vek diff <hash1> <hash2>
    vek replay <hash>
"""

from __future__ import annotations

import argparse
import json
import sys

from vek import api


def _short(h: str | None, length: int = 10) -> str:
    return h[:length] if h else "(root)"


# ------------------------------------------------------------------- commands


def cmd_init(_args: argparse.Namespace) -> None:
    vd = api.init()
    print(f"Initialized vek repository in {vd}")


def cmd_log(args: argparse.Namespace) -> None:
    nodes = api.log(n=args.n)
    if not nodes:
        print("(empty history)")
        return
    for nd in nodes:
        print(f"\033[33m{_short(nd['hash'])}\033[0m {nd['tool']}  {nd['timestamp']}")
        if nd["parent_hash"]:
            print(f"  parent {_short(nd['parent_hash'])}")


def cmd_branch(args: argparse.Namespace) -> None:
    if args.name:
        api.branch(args.name)
        print(f"Switched to branch '{args.name}'")
    else:
        from vek.repo import find, read_head

        vd = find()
        current = read_head(vd) if vd else ""
        refs = api.branch()
        if not refs:
            print("(no branches)")
            return
        for name, h in refs:  # type: ignore[misc]
            marker = "* " if name == current else "  "
            print(f"{marker}{name}\t{_short(h)}")


def cmd_fork(args: argparse.Namespace) -> None:
    bname = api.fork(args.hash, args.name)
    print(f"Forked to branch '{bname}' at {_short(args.hash)}")


def cmd_diff(args: argparse.Namespace) -> None:
    d = api.diff(args.hash1, args.hash2)
    print(json.dumps(d, indent=2, default=str))


def cmd_replay(args: argparse.Namespace) -> None:
    chain = api.replay(args.hash)
    for i, step in enumerate(chain):
        print(f"[{i}] \033[33m{_short(step['hash'])}\033[0m {step['tool']}")
        print(f"    in:  {json.dumps(step['input'], ensure_ascii=False)}")
        print(f"    out: {json.dumps(step['output'], ensure_ascii=False)}")


# --------------------------------------------------------------------- parser


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        prog="vek",
        description="Content-addressed execution store for AI agents",
    )
    sub = p.add_subparsers(dest="command")

    sub.add_parser("init", help="Initialise a .vek repository")

    lg = sub.add_parser("log", help="Show execution history")
    lg.add_argument("-n", type=int, default=20, help="Max entries to show")

    br = sub.add_parser("branch", help="List or create branches")
    br.add_argument("name", nargs="?", help="New branch name")

    fk = sub.add_parser("fork", help="Fork at a node")
    fk.add_argument("hash", help="Node hash to fork from")
    fk.add_argument("--name", help="Branch name (default: fork-<hash[:8]>)")

    df = sub.add_parser("diff", help="Compare two nodes")
    df.add_argument("hash1")
    df.add_argument("hash2")

    rp = sub.add_parser("replay", help="Replay execution chain")
    rp.add_argument("hash", help="Tip node hash")

    args = p.parse_args(argv)

    if args.command is None:
        p.print_help()
        sys.exit(1)

    dispatch = {
        "init": cmd_init,
        "log": cmd_log,
        "branch": cmd_branch,
        "fork": cmd_fork,
        "diff": cmd_diff,
        "replay": cmd_replay,
    }

    try:
        dispatch[args.command](args)
    except api.VekError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
