#!/usr/bin/env python3
"""Expand hand-authored seed contexts into a larger deterministic golden set.

Does NOT run the engines — only multiplies context combinations so conformance
can prove parity over ≥100 vectors. Output: test-vectors/contexts.json
"""
from __future__ import annotations

import json
import os
from copy import deepcopy
from itertools import product

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "test-vectors", "contexts.json")

SECRET_HEX = "a3f1c09b5e7d42118826aa0134bf90cd"

# Hand seeds kept first (stable historical fixtures).
HAND = [
    {
        "user_id": "usr_alpha", "spawn_window_id": "spw_01", "slot_index": 0, "spawn_generation": 1,
        "ruleset_version": "2026.09.0", "garden_level": 2, "biome": "meadow",
        "placements": ["fern", "pond"],
        "world": {"precipitation": "rain", "daylight": "dusk", "season": "autumn", "moon": "full"},
        "activity": {"streak_days": 7}, "pity": {"common": 0, "uncommon": 3, "rare": 5, "legendary": 9},
        "occupied_slots": [1], "discovered": ["cat:tabby:v1"], "fully_evolved": [],
        "recent_cats": ["cat:sol:v1"], "cooldown_cats": [],
    },
    {
        "user_id": "usr_alpha", "spawn_window_id": "spw_02", "slot_index": 0, "spawn_generation": 1,
        "ruleset_version": "2026.09.0", "garden_level": 2, "biome": "meadow",
        "placements": ["sunny_rock", "flower"],
        "world": {"precipitation": "none", "daylight": "day", "season": "summer", "moon": "new"},
        "activity": {"streak_days": 0}, "pity": {"common": 0, "uncommon": 0, "rare": 0, "legendary": 0},
        "occupied_slots": [], "discovered": ["cat:tabby:v1", "cat:sol:v1"], "fully_evolved": [],
        "recent_cats": [], "cooldown_cats": [],
    },
    {
        "user_id": "usr_beta", "spawn_window_id": "spw_03", "slot_index": 2, "spawn_generation": 1,
        "ruleset_version": "2026.09.0", "garden_level": 3, "biome": "meadow",
        "placements": ["pond", "fern"],
        "world": {"precipitation": "none", "daylight": "night", "season": "winter", "moon": "full"},
        "activity": {"streak_days": 14}, "pity": {"common": 0, "uncommon": 1, "rare": 12, "legendary": 2},
        "occupied_slots": [], "discovered": [], "fully_evolved": [], "recent_cats": [], "cooldown_cats": [],
    },
    {
        "user_id": "usr_gamma", "spawn_window_id": "spw_04", "slot_index": 0, "spawn_generation": 1,
        "ruleset_version": "2026.09.0", "garden_level": 0, "biome": "meadow",
        "placements": [],
        "world": {"precipitation": "storm", "daylight": "dawn", "season": "spring", "moon": "waxing_crescent"},
        "activity": {"streak_days": 3}, "pity": {"common": 0, "uncommon": 0, "rare": 0, "legendary": 0},
        "occupied_slots": [], "discovered": [], "fully_evolved": [], "recent_cats": [], "cooldown_cats": [],
    },
    {
        "user_id": "usr_delta", "spawn_window_id": "spw_05", "slot_index": 3, "spawn_generation": 2,
        "ruleset_version": "2026.09.0", "garden_level": 5, "biome": "meadow",
        "placements": ["fern", "pond", "sunny_rock", "flower"],
        "world": {"precipitation": "rain", "daylight": "dusk", "season": "autumn", "moon": "waning_gibbous"},
        "activity": {"streak_days": 30}, "pity": {"common": 0, "uncommon": 0, "rare": 0, "legendary": 0},
        "occupied_slots": [0, 1, 2, 3], "discovered": ["cat:tabby:v1"], "fully_evolved": [],
        "recent_cats": [], "cooldown_cats": [],
    },
    {
        "user_id": "usr_delta", "spawn_window_id": "spw_06", "slot_index": 1, "spawn_generation": 1,
        "ruleset_version": "2026.09.0", "garden_level": 4, "biome": "meadow",
        "placements": ["fern"],
        "world": {"precipitation": "drizzle", "daylight": "dusk", "season": "autumn", "moon": "first_quarter"},
        "activity": {"streak_days": 10}, "pity": {"common": 0, "uncommon": 0, "rare": 3, "legendary": 0},
        "occupied_slots": [0], "discovered": ["cat:tabby:v1", "cat:mizzle:v1"],
        "fully_evolved": ["cat:mizzle:v1"], "recent_cats": [], "cooldown_cats": [],
    },
    {
        "user_id": "usr_epsilon", "spawn_window_id": "spw_07", "slot_index": 0, "spawn_generation": 1,
        "ruleset_version": "2026.09.0", "garden_level": 3, "biome": "meadow",
        "placements": ["pond"],
        "world": {"precipitation": "rain", "daylight": "night", "season": "winter", "moon": "full"},
        "activity": {"streak_days": 5}, "pity": {"common": 0, "uncommon": 0, "rare": 0, "legendary": 0},
        "occupied_slots": [], "discovered": [], "fully_evolved": [], "recent_cats": [],
        "cooldown_cats": ["cat:mizzle:v1"],
    },
    {
        "user_id": "usr_zeta", "spawn_window_id": "spw_08", "slot_index": 0, "spawn_generation": 1,
        "ruleset_version": "2026.09.0", "garden_level": 2, "biome": "meadow",
        "placements": ["sunny_rock"],
        "world": {"precipitation": "none", "daylight": "day", "season": "summer", "moon": "new"},
        "activity": {"streak_days": 2}, "pity": {"common": 0, "uncommon": 8, "rare": 0, "legendary": 0},
        "occupied_slots": [2],
        "discovered": ["cat:tabby:v1", "cat:sol:v1", "cat:mizzle:v1", "cat:luna:v1"],
        "fully_evolved": [], "recent_cats": ["cat:tabby:v1"], "cooldown_cats": [],
    },
]

PRECIP = ["none", "drizzle", "rain", "storm"]
DAYLIGHT = ["dawn", "day", "dusk", "night"]
SEASON = ["spring", "summer", "autumn", "winter"]
MOON = ["new", "first_quarter", "full", "last_quarter"]
PLANTS = [
    [],
    ["fern"],
    ["pond"],
    ["sunny_rock"],
    ["flower"],
    ["fern", "pond"],
    ["sunny_rock", "flower"],
    ["fern", "pond", "sunny_rock"],
]
STREAKS = [0, 1, 3, 7, 14, 30]
LEVELS = [0, 1, 2, 3, 5]
PITY_RARE = [0, 2, 5, 12]


def main() -> None:
    contexts = [deepcopy(c) for c in HAND]
    n = 0
    for precip, daylight, season, moon, plants, streak, level, pity_r in product(
        PRECIP, DAYLIGHT, SEASON, MOON, PLANTS[:4], STREAKS[:3], LEVELS[:3], PITY_RARE[:3]
    ):
        # Thin the full cartesian product deterministically.
        key = (
            PRECIP.index(precip)
            + 3 * DAYLIGHT.index(daylight)
            + 5 * SEASON.index(season)
            + 7 * MOON.index(moon)
            + 11 * STREAKS.index(streak)
            + 13 * LEVELS.index(level)
            + 17 * PITY_RARE.index(pity_r)
            + 19 * PLANTS.index(plants)
        )
        if key % 17 != 0:
            continue
        n += 1
        contexts.append({
            "user_id": f"usr_gen_{n:03d}",
            "spawn_window_id": f"spw_gen_{n:03d}",
            "slot_index": n % 4,
            "spawn_generation": 1 + (n % 3),
            "ruleset_version": "2026.09.0",
            "garden_level": level,
            "biome": "meadow",
            "placements": list(plants),
            "world": {
                "precipitation": precip,
                "daylight": daylight,
                "season": season,
                "moon": moon,
            },
            "activity": {"streak_days": streak},
            "pity": {
                "common": 0,
                "uncommon": n % 5,
                "rare": pity_r,
                "legendary": n % 4,
            },
            "occupied_slots": [0] if n % 11 == 0 else [],
            "discovered": ["cat:tabby:v1"] if n % 2 == 0 else [],
            "fully_evolved": ["cat:sol:v1"] if n % 9 == 0 else [],
            "recent_cats": ["cat:mizzle:v1"] if n % 7 == 0 else [],
            "cooldown_cats": ["cat:luna:v1"] if n % 13 == 0 else [],
        })
        if len(contexts) >= 120:
            break

    # Edge: fully occupied garden
    contexts.append({
        "user_id": "usr_full",
        "spawn_window_id": "spw_full_slots",
        "slot_index": 0,
        "spawn_generation": 1,
        "ruleset_version": "2026.09.0",
        "garden_level": 5,
        "biome": "meadow",
        "placements": ["fern", "pond"],
        "world": {"precipitation": "rain", "daylight": "dusk", "season": "autumn", "moon": "full"},
        "activity": {"streak_days": 10},
        "pity": {"common": 0, "uncommon": 0, "rare": 0, "legendary": 0},
        "occupied_slots": [0, 1, 2, 3],
        "discovered": [],
        "fully_evolved": [],
        "recent_cats": [],
        "cooldown_cats": [],
    })

    payload = {
        "_note": (
            "Shared Phase-0 golden contexts. Both JS and Python engines must produce identical "
            "results under the same secret. Generated by tools/gen_contexts.py; re-run to refresh."
        ),
        "secret_hex": SECRET_HEX,
        "contexts": contexts,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    print(f"Wrote {len(contexts)} contexts → {OUT}")


if __name__ == "__main__":
    main()
