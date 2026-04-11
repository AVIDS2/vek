"""vek — 30-second demo.

Run:
    pip install -e .
    python examples/demo.py
"""

import tempfile, os, vek

# --- setup (use a temp dir so it's self-contained) ---
os.chdir(tempfile.mkdtemp())
vek.init()


# --- 1. @vek.wrap: one decorator, every call recorded ---

@vek.wrap
def search(query: str) -> dict:
    """Simulate a web search tool."""
    return {"results": [f"Result for '{query}'"]}

@vek.wrap
def summarise(text: str) -> str:
    """Simulate an LLM summariser."""
    return f"Summary: {text[:50]}..."

@vek.wrap
def decide(options: list) -> str:
    """Simulate an agent decision."""
    return options[0]  # always pick first


# --- 2. Run an "agent" ---

results = search("climate change effects")
summary = summarise(str(results))
action  = decide(["publish report", "gather more data"])


# --- 3. Inspect what happened ---

print("=== Execution Log ===")
for node in vek.log():
    print(f"  {node['hash'][:10]}  {node['tool']}")

print()
print("=== Status ===")
s = vek.status()
print(f"  Branch: {s['branch']}, Nodes: {s['nodes']}, Objects: {s['objects']}")

print()
print("=== Replay (full chain) ===")
tip = vek.log()[0]["hash"]
for i, step in enumerate(vek.replay(tip)):
    print(f"  [{i}] {step['tool']}")
    print(f"      in:  {step['input']}")
    print(f"      out: {step['output']}")

print(f"\n=== Integrity Check ===")
errors = vek.fsck()
print(f"  {'OK - clean' if not errors else f'{len(errors)} error(s)'}")

print(f"\n=== Export (portable JSON) ===")
data = vek.export()
print(f"  {len(data['nodes'])} nodes, {len(data['objects'])} objects — ready to share")
