# vek

> Content-addressed execution store for AI agents — git semantics for agent tool calls.

[![CI](https://github.com/AVIDS2/vek/actions/workflows/ci.yml/badge.svg)](https://github.com/AVIDS2/vek/actions/workflows/ci.yml)

Vek is a minimal execution history layer for AI agents. Every tool call's input and output is stored as an immutable, content-addressed blob, forming a traceable, forkable, branchable execution DAG. Framework-agnostic — plug in with a single function call.

## Philosophy

**Manage agent execution history like git manages code.**
Git doesn't care what language you write in. Vek doesn't care what framework your agent runs on.

## Install

```
pip install vek
```

## Quick Start

```python
import vek

vek.init()

# record a single tool call
h = vek.store(tool="search", input={"q": "climate change"}, output={"results": [...]})

# session — auto-chained, atomic recording
with vek.session() as s:
    s.store(tool="search", input=query, output=results)
    s.store(tool="summarise", input=text, output=summary)

# auto-record with decorator
@vek.wrap
def search(query: str) -> dict:
    return {"results": [...]}

# inspect
node = vek.show(h)
blob = vek.cat_file(node["input_hash"])
```

## CLI

```
vek init                  # create .vek/ repository
vek status                # current branch, tip, stats
vek log [-n 20] [--graph] # execution history / ASCII DAG
vek show <hash>           # inspect a node (short hash OK)
vek cat-file <hash>       # dump raw object content
vek branch [name]         # list or create/switch branches
vek fork <hash>           # fork at a node
vek merge <branch>        # merge branch into current
vek diff <hash1> <hash2>  # structural JSON diff
vek replay <hash>         # replay first-parent chain
vek query [--tool X] [--since T] [--until T] [--branch B] [--limit N]
vek search <pattern> [--field input|output|both] [--limit N]
vek annotate <hash>       # annotate chain with materialised content
vek verify <hash> [--exec-function module:func]  # verify by re-execution
vek diff-chains <h1> <h2> # compare two chains node-by-node
vek reexec <hash> [--exec-function module:func] [--ref name]  # re-execute into new ref
vek checkpoint [label] [hash]  # list or create checkpoints
vek tag [name] [hash]     # list or create tags
vek fsck                  # verify repository integrity
vek gc [--dry-run]        # remove unreachable objects
vek export [--format json|jsonl] [--branch name]
vek import <file> [--format auto|json|jsonl]
vek --version
```

## Python API

| Function | Description |
|----------|-------------|
| `vek.init()` | Initialise `.vek/` repository |
| `vek.store(tool, input, output)` | Record one tool call |
| `vek.session()` | Context manager for atomic batch recording |
| `vek.async_session()` | Async context manager |
| `vek.wrap(fn)` | Decorator for auto-recording |
| `vek.hook(dispatch_fn)` | Wrap a dispatch function |
| `vek.log(n=20)` | Recent execution history |
| `vek.log_graph()` | ASCII DAG visualisation |
| `vek.show(hash)` | Node details with materialised content |
| `vek.cat_file(hash)` | Raw object bytes |
| `vek.status()` | Repository summary |
| `vek.branch(name)` | Create/switch branch |
| `vek.fork(hash, name)` | Fork at a node |
| `vek.merge(branch)` | Merge branch (creates multi-parent node) |
| `vek.diff(h1, h2)` | Structural JSON diff |
| `vek.replay(hash)` | First-parent chain from root to hash |
| `vek.query(tool=, since=, until=, branch=, limit=)` | Filtered node query |
| `vek.search(pattern, in_field=, limit=)` | Search by input/output content |
| `vek.annotate(hash)` | Annotate chain with materialised content |
| `vek.verify(hash, executor)` | Dry-run re-execution with output comparison |
| `vek.diff_chains(h1, h2)` | Compare two chains node-by-node |
| `vek.reexec(hash, executor, ref=)` | Re-execute chain into new ref |
| `vek.checkpoint(hash, label)` | Mark verified checkpoint |
| `vek.list_checkpoints()` | List all checkpoints |
| `vek.tag(name, hash)` | Lightweight tags |
| `vek.fsck()` | Integrity verification |
| `vek.gc()` | Garbage collection |
| `vek.export()` | Export chains (JSON/JSONL) |
| `vek.import_data(data)` | Import chains |

All hash arguments accept short prefixes (e.g. `h[:8]`).

## Storage Layout

```
.vek/
├── objects/     # (reserved) content-addressed hash objects
├── refs/        # (reserved) branch pointer files
├── HEAD         # current branch
├── config       # repository configuration
└── vek.db       # SQLite — objects + nodes + refs
```

## Data Model

```
objects:  hash | content
nodes:    hash | tool | input_hash | output_hash | parent_hash | timestamp | merge_parent
refs:     name | hash                     (branches, tags with "tag/" prefix)
```

### Object Hashing (git-style)

```
SHA-256( "blob" + " " + size + "\0" + content )   # input/output blobs
SHA-256( "node" + " " + size + "\0" + content )   # execution nodes
```

Same content stored exactly once. Different types with identical content produce different hashes.

### Merge Nodes

Merge creates a node with two parents: `parent_hash` (current branch) and `merge_parent` (target branch). Tool is `__merge__`.

## Concurrency

- SQLite WAL mode with 5s busy timeout
- `store()` uses `BEGIN IMMEDIATE` to serialise concurrent ref updates
- Advisory file lock (`HEAD.lock`) prevents concurrent branch pointer writes
- Sessions batch all writes in a single transaction (atomic commit/rollback)

## Design Principles

- **Content-addressed** — identical content stored once, forever
- **Immutable** — history cannot be tampered with
- **Framework-agnostic** — no adapters, no shims
- **Local-first** — `.vek/` directory, zero external dependencies
- **Minimal API** — one function call to integrate
- **Atomic sessions** — all-or-nothing batch writes
- **Portable** — export/import execution chains as JSON/JSONL

## License

[AGPL-3.0](LICENSE)
