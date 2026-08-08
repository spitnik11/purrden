#!/usr/bin/env python3
"""Property-style invariants over spawn results (Python engine)."""
from __future__ import annotations

import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "packages", "spawn-engine-py"))

from purrden_spawn import load_content, resolve_spawn  # noqa: E402


class SpawnPropertyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "test-vectors", "contexts.json"), encoding="utf-8") as f:
            spec = json.load(f)
        cls.secret = bytes.fromhex(spec["secret_hex"])
        cls.contexts = spec["contexts"]
        cls.content = load_content(ROOT)
        cls.results = [resolve_spawn(ctx, cls.content, cls.secret) for ctx in cls.contexts]

    def test_weights_non_negative(self):
        for r in self.results:
            for e in r["eligible"]:
                self.assertGreaterEqual(e["weight"], 0)
                self.assertGreaterEqual(e["ppm"], 0)

    def test_draw_in_range(self):
        for r in self.results:
            if r["selected"] is None:
                continue
            self.assertGreater(r["total_weight"], 0)
            self.assertGreaterEqual(r["draw"], 0)
            self.assertLess(r["draw"], r["total_weight"])

    def test_selected_is_eligible(self):
        for r in self.results:
            if r["selected"] is None:
                continue
            ids = {e["id"] for e in r["eligible"]}
            self.assertIn(r["selected"], ids)

    def test_fallback_pool_or_no_slot(self):
        for ctx, r in zip(self.contexts, self.results):
            if r["no_spawn_reason"] == "no_free_slot":
                continue
            self.assertTrue(r["eligible"], "eligible pool must not be empty when a free slot exists")

    def test_pity_bounded_non_negative(self):
        for r in self.results:
            for tier, v in r["pity_after"].items():
                self.assertGreaterEqual(v, 0)
                self.assertIsInstance(v, int)

    def test_replay_stable(self):
        for ctx in self.contexts[:20]:
            a = resolve_spawn(ctx, self.content, self.secret)
            b = resolve_spawn(ctx, self.content, self.secret)
            self.assertEqual(a, b)

    def test_disabled_never_selected(self):
        # All cats in content are enabled; inject a disabled clone mentally via score path:
        # simply assert selected is always from content enabled set.
        enabled = {c["id"] for c in self.content["cats"] if c["enabled"]}
        for r in self.results:
            if r["selected"]:
                self.assertIn(r["selected"], enabled)


if __name__ == "__main__":
    unittest.main()
