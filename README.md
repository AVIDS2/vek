<div align="center">
  <img src="docs/vek.png" alt="vek" width="180" />
  <h1>vek</h1>
  <p><strong>Git semantics for AI agent tool calls</strong></p>
  <p>
    <a href="https://pypi.org/project/vek/"><img src="https://img.shields.io/pypi/v/vek.svg" alt="PyPI" /></a>
    <a href="https://github.com/AVIDS2/vek/actions/workflows/ci.yml"><img src="https://github.com/AVIDS2/vek/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
    <img src="https://img.shields.io/pypi/pyversions/vek.svg" alt="Python 3.10+" />
    <img src="https://img.shields.io/pypi/l/vek.svg" alt="MIT" />
  </p>
</div>

---

Every tool call an agent makes — its input, output, parent, timestamp — is stored as an **immutable, content-addressed blob** in a local SQLite database. The result is a **traceable, forkable, branchable execution DAG** you can query, verify, and replay. Zero external dependencies. Framework-agnostic. One function call to integrate.

### Why vek?

- **You can't debug what you can't see.** Agents make thousands of tool calls. Without a record, you're flying blind.
- **Git proved the model.** Content-addressed, immutable, branchable — the same primitives that make code reviewable make agent execution reviewable.
- **Local-first, zero config.** `.vek/` in your project directory. No server, no API key, no setup.

## Install

```bash
pip install vek
```

## Quick Start

```python
import vek

# 1. Initialise (once per project)
vek.init()

# 2. Record tool calls
h = vek.store(tool="search", input={"q": "climate"}, output={"results": [...]})

# 3. Inspect
node = vek.show(h)          # full node details
vek.log()                   # execution history
vek.status()                # branch, tip, stats

# 4. Branch & fork (like git)
vek.branch("experiment")    # create/switch branch
vek.fork(h, "alt-path")     # fork at a node

# 5. Verify & re-execute
results = vek.verify(h, executor=my_executor)   # dry-run comparison
new = vek.reexec(h, executor=my_executor)       # re-execute into new ref
vek.checkpoint(h, "v1-verified")                # mark verified position
```

### Auto-recording

```python
# Decorator — wraps any function
@vek.wrap
def search(query: str) -> dict:
    return call_api(query)

# Session — batch recording, atomic
with vek.session() as s:
    s.store(tool="search", input=query, output=results)
    s.store(tool="summarise", input=text, output=summary)

# Hook — intercept a dispatch function
dispatch = vek.hook(original_dispatch)
```

## The Three Pillars

| Pillar | What | API |
|--------|------|-----|
| **Store** | Record every tool call immutably | `store`, `session`, `wrap`, `hook` |
| **Query** | Search, inspect, verify history | `query`, `search`, `annotate`, `verify`, `diff_chains` |
| **Re-execute** | Replay & checkpoint verified chains | `reexec`, `checkpoint`, `list_checkpoints` |

## CLI Reference

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
├── objects/     # content-addressed hash objects
├── refs/        # branch pointer files
├── HEAD         # current branch
├── config       # repository configuration
└── vek.db       # SQLite — objects + nodes + refs
```

## Data Model

```
objects:  hash | content
nodes:    hash | tool | input_hash | output_hash | parent_hash | timestamp | merge_parent
refs:     name | hash   (branches, tags with "tag/" prefix, checkpoints with "checkpoint/" prefix)
```

### Object Hashing (git-style)

```
SHA-256( "blob" + " " + size + "\0" + content )   # input/output blobs
SHA-256( "node" + " " + size + "\0" + content )   # execution nodes
```

Same content stored exactly once. Different types with identical content produce different hashes.

### Merge Nodes

Merge creates a node with two parents: `parent_hash` (current branch) and `merge_parent` (target branch). Tool is `__merge__`.

## Concurrency & Safety

- SQLite WAL mode with 5s busy timeout
- `store()` uses `BEGIN IMMEDIATE` to serialise concurrent ref updates
- Advisory file lock (`HEAD.lock`) prevents concurrent branch pointer writes
- Sessions batch all writes in a single transaction (atomic commit/rollback)
- `verify()` and `reexec()` suppress executor side-effects via `ContextVar` — executor cannot mutate the repository
- `reexec()` wraps writes in a transaction — failed re-execution rolls back cleanly, no garbage left behind

## Design Principles

- **Content-addressed** — identical content stored once, forever
- **Immutable** — history cannot be tampered with
- **Framework-agnostic** — no adapters, no shims
- **Local-first** — `.vek/` directory, zero external dependencies
- **Minimal API** — one function call to integrate
- **Atomic sessions** — all-or-nothing batch writes
- **Portable** — export/import execution chains as JSON/JSONL
- **Safe re-execution** — verify without side-effects, re-execute with rollback

## License

[MIT](LICENSE)
