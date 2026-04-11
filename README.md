# vek

> Content-addressed execution store for AI agents — git semantics for agent tool calls.

Vek is a minimal execution history layer for AI agents. Every tool call's input and output is stored as an immutable, content-addressed blob, forming a traceable, forkable, replayable execution DAG. Framework-agnostic — plug in with a single function call.

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

# initialise a .vek repository in the current directory
vek.init()

# record a single tool call
h = vek.store(tool="search", input={"q": "climate change"}, output={"results": [...]})

# session — auto-chained recording
with vek.session() as s:
    s.store(tool="search", input=query, output=results)
    s.store(tool="summarise", input=text, output=summary)
```

## CLI

```
vek init                  # create .vek/ repository
vek log                   # show execution history
vek branch [name]         # list or create branches
vek fork <hash>           # fork at a node
vek diff <hash1> <hash2>  # compare two nodes
vek replay <hash>         # replay execution chain
```

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
objects:  hash | content                                         (content-addressed blobs)
nodes:    hash | tool | input_hash | output_hash | parent_hash | timestamp  (execution DAG)
refs:     name | hash                                            (branch pointers)
```

### Object Hashing (git-style)

```
object_id = SHA-256( "blob" + " " + size + "\0" + content )   # for input/output blobs
object_id = SHA-256( "node" + " " + size + "\0" + content )   # for execution nodes
```

Same content is stored exactly once. Different object types with identical content produce different hashes.

## Design Principles

- **Content-addressed** — identical content stored once, forever
- **Immutable** — history cannot be tampered with
- **Framework-agnostic** — no adapters, no shims
- **Local-first** — `.vek/` directory, zero external dependencies
- **Minimal API** — one function call to integrate

## License

[AGPL-3.0](LICENSE)
