#!/usr/bin/env python3
"""Phase-0 demo: print a spawn winner + explanation for a hand context."""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "packages", "spawn-engine-py"))
sys.path.insert(0, os.path.join(ROOT, "packages", "domain-python"))

from purrden_domain import (  # noqa: E402
    complete_focus,
    create_focus_session,
    growth_energy_for,
    start_focus,
)
from purrden_spawn import load_content, resolve_spawn  # noqa: E402


def main() -> int:
    with open(os.path.join(ROOT, "test-vectors", "contexts.json"), encoding="utf-8") as f:
        spec = json.load(f)
    content = load_content(ROOT)
    secret = bytes.fromhex(spec["secret_hex"])
    ctx = next(c for c in spec["contexts"] if c["spawn_window_id"] == "spw_01")

    # Focus session awards growth energy (display only in Phase 0).
    t0 = 1_700_000_000_000
    focus = create_focus_session(id="demo-focus", target_seconds=25 * 60, now=t0)
    focus = start_focus(focus, now=t0)
    focus = complete_focus(focus, now=t0 + 25 * 60 * 1000)
    energy = growth_energy_for(focus)

    result = resolve_spawn(ctx, content, secret)

    print("=== Purrden Phase 0 demo ===")
    print(f"focus: state={focus['state']} growth_energy={energy}")
    print(f"garden: level={ctx['garden_level']} placements={ctx['placements']}")
    print(f"world:  {ctx['world']}")
    print(f"window: {ctx['spawn_window_id']} slot={ctx['slot_index']}")
    if result["selected"] is None:
        print(f"spawn:  no visitor ({result['no_spawn_reason']})")
        return 0
    print(f"visitor: {result['selected']}  (draw={result['draw']} / {result['total_weight']})")
    print(f"pity→:  {result['pity_after']}")
    print("why:")
    for factor in result["explanation"]["top_factors"]:
        print(f"  - {factor}")
    print("eligible:")
    for e in result["eligible"]:
        mark = "←" if e["id"] == result["selected"] else " "
        print(f"  {mark} {e['id']:16s} tier={e['tier']:9s} score={e['score']:5d} "
              f"w={e['weight']:12d} ppm={e['ppm']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
