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

import vek
from vek import api


def _short(h: str | None, length: int = 10) -> str:
    return h[:length] if h else "(root)"


# ------------------------------------------------------------------- commands


def cmd_init(_args: argparse.Namespace) -> None:
    vd = api.init()
    print(f"Initialized vek repository in {vd}")


def cmd_log(args: argparse.Namespace) -> None:
    if args.graph:
        lines = api.log_graph(limit=args.n)
        for line in lines:
            print(line)
        return
    nodes = api.log(n=args.n)
    if not nodes:
        print("(empty history)")
        return
    for nd in nodes:
        merge = " (merge)" if nd.get("merge_parent") else ""
        print(f"\033[33m{_short(nd['hash'])}\033[0m {nd['tool']}{merge}  {nd['timestamp']}")
        if nd["parent_hash"]:
            print(f"  parent {_short(nd['parent_hash'])}")
        if nd.get("merge_parent"):
            print(f"  merge  {_short(nd['merge_parent'])}")


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


def cmd_show(args: argparse.Namespace) -> None:
    node = api.show(args.hash)
    print(f"\033[33mnode {node['hash']}\033[0m")
    print(f"tool:   {node['tool']}")
    print(f"time:   {node['timestamp']}")
    print(f"parent: {node['parent_hash'] or '(root)'}")
    print(f"\n--- input ({node['input_hash'][:10]}) ---")
    print(json.dumps(node["input"], indent=2, ensure_ascii=False))
    print(f"\n--- output ({node['output_hash'][:10]}) ---")
    print(json.dumps(node["output"], indent=2, ensure_ascii=False))


def cmd_cat_file(args: argparse.Namespace) -> None:
    blob = api.cat_file(args.hash)
    if args.raw:
        sys.stdout.buffer.write(blob)
    else:
        try:
            print(json.dumps(json.loads(blob), indent=2, ensure_ascii=False))
        except (json.JSONDecodeError, UnicodeDecodeError):
            sys.stdout.buffer.write(blob)


def cmd_status(_args: argparse.Namespace) -> None:
    s = api.status()
    print(f"On branch \033[32m{s['branch']}\033[0m")
    if s["tip"]:
        print(f"Tip:     {_short(s['tip'])}")
    else:
        print("Tip:     (no commits yet)")
    print(f"Nodes:   {s['nodes']}")
    print(f"Objects: {s['objects']}")
    print(f"Refs:    {s['refs']}")


def cmd_tag(args: argparse.Namespace) -> None:
    if args.name:
        api.tag(args.name, args.node)
        print(f"Tagged '{args.name}'")
    else:
        tags = api.tag()
        if not tags:
            print("(no tags)")
            return
        for name, h in tags:  # type: ignore[misc]
            print(f"  {name}\t{_short(h)}")


def cmd_fsck(_args: argparse.Namespace) -> None:
    errors = api.fsck()
    if not errors:
        print("\033[32mno errors\033[0m")
        return
    for e in errors:
        print(f"\033[31m{_short(e['hash'])}\033[0m {e['error']}")
    print(f"\n{len(errors)} error(s) found")
    sys.exit(1)


def cmd_merge(args: argparse.Namespace) -> None:
    h = api.merge(args.branch)
    print(f"Merged '{args.branch}' -> {_short(h)}")


def cmd_gc(args: argparse.Namespace) -> None:
    result = api.gc(dry_run=args.dry_run)
    nn = len(result["unreachable_nodes"])
    no = len(result["orphan_objects"])
    if nn == 0 and no == 0:
        print("nothing to clean")
        return
    label = "(dry run) " if args.dry_run else ""
    print(f"{label}{nn} unreachable node(s), {no} orphan object(s)")
    if result["deleted"]:
        print("cleaned.")


def cmd_query(args: argparse.Namespace) -> None:
    nodes = api.query(
        tool=args.tool,
        since=args.since,
        until=args.until,
        branch=args.branch,
        limit=args.limit,
    )
    if not nodes:
        print("(no matches)")
        return
    for nd in nodes:
        print(f"\033[33m{_short(nd['hash'])}\033[0m {nd['tool']}  {nd['timestamp']}")


def cmd_search(args: argparse.Namespace) -> None:
    nodes = api.search(args.pattern, in_field=args.field, limit=args.limit)
    if not nodes:
        print("(no matches)")
        return
    for nd in nodes:
        print(f"\033[33m{_short(nd['hash'])}\033[0m {nd['tool']}  {nd['timestamp']}")


def cmd_annotate(args: argparse.Namespace) -> None:
    chain = api.annotate(args.hash)
    for i, step in enumerate(chain):
        print(f"[{i}] \033[33m{_short(step['hash'])}\033[0m {step['tool']}  {step['timestamp']}")
        print(f"    in:  {json.dumps(step['input'], ensure_ascii=False)}")
        print(f"    out: {json.dumps(step['output'], ensure_ascii=False)}")


def cmd_verify(args: argparse.Namespace) -> None:
    # Build a simple executor from --exec-module or --exec-function
    if args.exec_function:
        mod_name, func_name = args.exec_function.rsplit(":", 1)
        import importlib
        mod = importlib.import_module(mod_name)
        executor = getattr(mod, func_name)
    else:
        # Default: no-op executor that always returns None
        executor = lambda tool, inp: None
    results = api.verify(args.hash, executor)
    mismatches = 0
    for r in results:
        status = "\033[32mOK\033[0m" if r["match"] else "\033[31mMISMATCH\033[0m"
        if not r["match"]:
            mismatches += 1
        print(f"[{r['tool']}] {_short(r['hash'])} {status}")
        if not r["match"] and "error" not in r:
            print(f"  stored:  {json.dumps(r['stored_output'], ensure_ascii=False)}")
            print(f"  reexec:  {json.dumps(r['reexec_output'], ensure_ascii=False)}")
        elif "error" in r:
            print(f"  error: {r['error']}")
    if mismatches:
        print(f"\n{mismatches} mismatch(es) out of {len(results)} node(s)")
        sys.exit(1)
    else:
        print(f"\nAll {len(results)} node(s) verified OK")


def cmd_diff_chains(args: argparse.Namespace) -> None:
    results = api.diff_chains(args.hash1, args.hash2)
    for r in results:
        a = _short(r["node_a"]["hash"]) if r["node_a"] else "(none)"
        b = _short(r["node_b"]["hash"]) if r["node_b"] else "(none)"
        in_s = "\033[32m=\033[0m" if r["input_match"] else "\033[31m!=\033[0m"
        out_s = "\033[32m=\033[0m" if r["output_match"] else "\033[31m!=\033[0m"
        print(f"[{r['position']}] {a} vs {b}  in:{in_s} out:{out_s}")


def cmd_export(args: argparse.Namespace) -> None:
    result = api.export(branch=args.branch, format=args.format)
    if args.format == "json":
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(result, end="")


def cmd_import(args: argparse.Namespace) -> None:
    import pathlib
    text = pathlib.Path(args.file).read_text(encoding="utf-8")
    fmt = args.format
    if fmt == "auto":
        fmt = "jsonl" if args.file.endswith(".jsonl") else "json"
    if fmt == "json":
        data = json.loads(text)
    else:
        data = text
    stats = api.import_data(data, format=fmt)
    print(f"Imported: {stats['nodes_imported']} node(s), "
          f"{stats['objects_imported']} object(s), "
          f"{stats['refs_imported']} ref(s)")


# --------------------------------------------------------------------- parser


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        prog="vek",
        description="Content-addressed execution store for AI agents",
    )
    p.add_argument(
        "--version", action="version", version=f"%(prog)s {vek.__version__}"
    )
    sub = p.add_subparsers(dest="command")

    sub.add_parser("init", help="Initialise a .vek repository")

    lg = sub.add_parser("log", help="Show execution history")
    lg.add_argument("-n", type=int, default=20, help="Max entries to show")
    lg.add_argument("--graph", action="store_true", help="ASCII DAG visualisation")

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

    sh = sub.add_parser("show", help="Inspect a node")
    sh.add_argument("hash", help="Node hash (prefix OK)")

    cf = sub.add_parser("cat-file", help="Dump raw object content")
    cf.add_argument("hash", help="Object hash (prefix OK)")
    cf.add_argument("--raw", action="store_true", help="Output raw bytes")

    sub.add_parser("status", help="Show repository status")

    tg = sub.add_parser("tag", help="List or create tags")
    tg.add_argument("name", nargs="?", help="Tag name")
    tg.add_argument("node", nargs="?", help="Node hash (default: current tip)")

    sub.add_parser("fsck", help="Verify repository integrity")

    mg = sub.add_parser("merge", help="Merge a branch into current")
    mg.add_argument("branch", help="Branch to merge")

    gcmd = sub.add_parser("gc", help="Remove unreachable objects")
    gcmd.add_argument("--dry-run", action="store_true", help="Preview only")

    qy = sub.add_parser("query", help="Query nodes by tool/time/branch")
    qy.add_argument("--tool", help="Filter by tool name")
    qy.add_argument("--since", help="ISO timestamp lower bound")
    qy.add_argument("--until", help="ISO timestamp upper bound")
    qy.add_argument("--branch", help="Restrict to branch")
    qy.add_argument("--limit", type=int, default=50, help="Max results")

    fd = sub.add_parser("search", help="Search node content")
    fd.add_argument("pattern", help="Search pattern")
    fd.add_argument("--field", choices=["input", "output", "both"], default="both")
    fd.add_argument("--limit", type=int, default=50, help="Max results")

    an = sub.add_parser("annotate", help="Annotate first-parent chain")
    an.add_argument("hash", help="Tip node hash")

    vr = sub.add_parser("verify", help="Verify chain by re-execution")
    vr.add_argument("hash", help="Tip node hash")
    vr.add_argument("--exec-function", help="module:function executor")

    dc = sub.add_parser("diff-chains", help="Compare two chains node-by-node")
    dc.add_argument("hash1", help="Tip of chain A")
    dc.add_argument("hash2", help="Tip of chain B")

    exp = sub.add_parser("export", help="Export execution chains")
    exp.add_argument("--branch", help="Export only this branch")
    exp.add_argument("--format", choices=["json", "jsonl"], default="json")

    imp = sub.add_parser("import", help="Import execution chains")
    imp.add_argument("file", help="Path to JSON or JSONL export file")
    imp.add_argument("--format", choices=["json", "jsonl", "auto"], default="auto")

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
        "show": cmd_show,
        "cat-file": cmd_cat_file,
        "status": cmd_status,
        "tag": cmd_tag,
        "merge": cmd_merge,
        "fsck": cmd_fsck,
        "gc": cmd_gc,
        "query": cmd_query,
        "search": cmd_search,
        "annotate": cmd_annotate,
        "verify": cmd_verify,
        "diff-chains": cmd_diff_chains,
        "export": cmd_export,
        "import": cmd_import,
    }

    try:
        dispatch[args.command](args)
    except api.VekError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
