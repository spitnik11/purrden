"""Phase-0 conformance gate: prove the JS and Python spawn engines agree exactly.

Runs the Python engine and the JS CLI over the same shared contexts under the same secret, then
deep-compares every result. Exit 0 = engines conform; exit 1 = a divergence was found.

Run:  python tools/conformance.py
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "packages", "spawn-engine-py"))

from purrden_spawn import load_content, resolve_spawn  # noqa: E402


def run_js(contexts_path: str, secret_hex: str) -> list:
    cli = os.path.join(ROOT, "packages", "spawn-engine-js", "src", "cli.mjs")
    out = subprocess.run(["node", cli, contexts_path, secret_hex],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def diff(a, b, path=""):
    """Yield human-readable difference paths between two JSON-able values."""
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                yield f"{path}.{k}: missing in Python"
            elif k not in b:
                yield f"{path}.{k}: missing in JS"
            else:
                yield from diff(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            yield f"{path}: length {len(a)} (py) != {len(b)} (js)"
        else:
            for i, (x, y) in enumerate(zip(a, b)):
                yield from diff(x, y, f"{path}[{i}]")
    elif a != b:
        yield f"{path}: {a!r} (py) != {b!r} (js)"


def main() -> int:
    contexts_path = os.path.join(ROOT, "test-vectors", "contexts.json")
    with open(contexts_path, encoding="utf-8") as f:
        spec = json.load(f)
    secret_hex = spec["secret_hex"]
    contexts = spec["contexts"]

    content = load_content(ROOT)
    secret = bytes.fromhex(secret_hex)

    py_results = [resolve_spawn(ctx, content, secret) for ctx in contexts]
    # round-trip through JSON so the comparison sees the same types the JS side produces
    py_results = json.loads(json.dumps(py_results))
    js_results = run_js(contexts_path, secret_hex)

    diffs = list(diff(py_results, js_results, "results"))
    n = len(contexts)
    if diffs:
        print(f"CONFORMANCE FAILED across {n} contexts. {len(diffs)} divergence(s):")
        for d in diffs[:40]:
            print("  " + d)
        return 1

    print(f"CONFORMANCE OK: {n} contexts, JS and Python results identical.")
    print("\nSample results:")
    for ctx, r in list(zip(contexts, py_results))[:n]:
        sel = r["selected"] or f"(no spawn: {r['no_spawn_reason']})"
        factors = ", ".join(r["explanation"]["top_factors"]) or "—"
        print(f"  {ctx['spawn_window_id']}: {sel:16s} draw={r['draw']:<12} "
              f"total_w={r['total_weight']:<12} why=[{factors}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
