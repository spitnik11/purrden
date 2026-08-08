#!/usr/bin/env python3
"""Unit tests for the focus-session state machine (Python)."""
from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "packages", "domain-python"))

from purrden_domain import (  # noqa: E402
    FocusState,
    cancel_focus,
    complete_focus,
    create_focus_session,
    elapsed_seconds,
    growth_energy_for,
    pause_focus,
    start_focus,
)


class FocusTests(unittest.TestCase):
    def test_happy_path_complete(self):
        t0 = 1_000_000
        s = create_focus_session(id="f1", target_seconds=60, now=t0)
        s = start_focus(s, now=t0)
        self.assertEqual(s["state"], FocusState.RUNNING)
        # 60s later
        s = complete_focus(s, now=t0 + 60_000)
        self.assertEqual(s["state"], FocusState.COMPLETED)
        self.assertEqual(growth_energy_for(s), 1)

    def test_pause_resume_accumulates(self):
        t0 = 2_000_000
        s = create_focus_session(id="f2", target_seconds=120, now=t0)
        s = start_focus(s, now=t0)
        s = pause_focus(s, now=t0 + 50_000)
        self.assertEqual(elapsed_seconds(s, now=t0 + 50_000), 50)
        s = start_focus(s, now=t0 + 80_000)
        s = complete_focus(s, now=t0 + 80_000 + 70_000)
        self.assertEqual(s["state"], FocusState.COMPLETED)
        self.assertEqual(s["accumulatedMs"], 120_000)
        self.assertEqual(growth_energy_for(s), 2)

    def test_incomplete_complete_is_noop_while_running(self):
        t0 = 3_000_000
        s = create_focus_session(id="f3", target_seconds=300, now=t0)
        s = start_focus(s, now=t0)
        s2 = complete_focus(s, now=t0 + 10_000)
        self.assertEqual(s2["state"], FocusState.RUNNING)
        self.assertIsNone(s2["completedAt"])

    def test_cancel(self):
        t0 = 4_000_000
        s = create_focus_session(id="f4", target_seconds=60, now=t0)
        s = start_focus(s, now=t0)
        s = cancel_focus(s, now=t0 + 20_000)
        self.assertEqual(s["state"], FocusState.CANCELLED)
        self.assertEqual(growth_energy_for(s), 0)

    def test_cannot_start_from_completed(self):
        t0 = 5_000_000
        s = create_focus_session(id="f5", target_seconds=60, now=t0)
        s = start_focus(s, now=t0)
        s = complete_focus(s, now=t0 + 60_000)
        with self.assertRaises(ValueError):
            start_focus(s, now=t0 + 70_000)


if __name__ == "__main__":
    unittest.main()
