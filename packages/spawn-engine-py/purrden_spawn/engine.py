"""Purrden spawn engine — Python authoritative implementation.

Must stay byte-identical in results to the JS reference (packages/spawn-engine-js). All scoring is
integer milli-logits; weights come from the committed integer exp LUT; the draw is
HMAC-SHA256 -> uint64 stream -> rejection sampling. See engine.mjs for the shared contract.
"""
from __future__ import annotations

import hashlib
import hmac as _hmac
from typing import Any, Callable

TIERS = ("common", "uncommon", "rare", "legendary")
AFFINITY_KINDS = ("precipitation", "daylight", "season", "moon")

HmacFn = Callable[[bytes, str], bytes]


def _default_hmac(secret: bytes, message: str) -> bytes:
    return _hmac.new(secret, message.encode("utf-8"), hashlib.sha256).digest()


def _aff(cat: dict, kind: str, value: Any) -> int:
    if value is None:
        return 0
    return cat.get("affinities", {}).get(kind, {}).get(value, 0)


def _clamp_cap(value: int, cap: int) -> int:
    return cap if value > cap else value


def _score_cat(cat: dict, ctx: dict, ruleset: dict) -> dict:
    factors: list[dict] = []
    score = cat["base_score"]

    world = ctx.get("world", {})
    for kind in AFFINITY_KINDS:
        v = _aff(cat, kind, world.get(kind))
        if v != 0:
            factors.append({"label": f"{kind}:{world[kind]}", "value": v})
        score += v

    placements = cat.get("affinities", {}).get("placements", {})
    for plant in ctx.get("placements", []):
        v = placements.get(plant, 0)
        if v != 0:
            factors.append({"label": f"plant:{plant}", "value": v})
        score += v

    if cat["rarity"] != "common":
        streak = _clamp_cap(ctx.get("activity", {}).get("streak_days", 0) * ruleset["streak_bonus_per_day"],
                            ruleset["streak_bonus_cap"])
        if streak > 0:
            factors.append({"label": f"streak:{ctx['activity']['streak_days']}d", "value": streak})
        score += streak

    p = ruleset["pity"].get(cat["rarity"], {"per_miss": 0, "cap": 0})
    pity_bonus = _clamp_cap(ctx.get("pity", {}).get(cat["rarity"], 0) * p["per_miss"], p["cap"])
    if pity_bonus > 0:
        factors.append({"label": f"pity:{cat['rarity']}", "value": pity_bonus})
    score += pity_bonus

    if cat["id"] not in ctx.get("discovered", []):
        factors.append({"label": "discovery", "value": ruleset["discovery_bonus"]})
        score += ruleset["discovery_bonus"]
    if cat["id"] in ctx.get("recent_cats", []):
        score -= ruleset["recent_visit_penalty"]
    if cat["id"] in ctx.get("fully_evolved", []):
        score -= ruleset["fully_evolved_penalty"]

    return {"score": score, "factors": factors, "pity_applied": pity_bonus > 0}


def _biome_matches(cat: dict, ctx: dict) -> bool:
    return cat["biome"] is None or cat["biome"] == ctx.get("biome")


def _passes_gates(cat: dict, ctx: dict) -> bool:
    if not cat["enabled"]:
        return False
    if cat["id"] in ctx.get("cooldown_cats", []):
        return False
    if cat["fallback"]:
        return True
    return ctx["garden_level"] >= cat["min_garden_level"] and _biome_matches(cat, ctx)


def _weight_for_diff(diff_milli: int, lut: dict) -> int:
    neg = -diff_milli
    idx = (neg + lut["step_millilogits"] // 2) // lut["step_millilogits"]
    if idx > lut["max_index"]:
        idx = lut["max_index"]
    return lut["weights"][idx]


def _canonical_seed(ctx: dict, ruleset: dict) -> str:
    return (
        '{"algorithmVersion":"' + ruleset["algorithm_version"]
        + '","rulesetVersion":"' + ctx["ruleset_version"]
        + '","slotIndex":' + str(ctx["slot_index"])
        + ',"spawnGeneration":' + str(ctx["spawn_generation"])
        + ',"spawnWindowId":"' + ctx["spawn_window_id"]
        + '","userId":"' + ctx["user_id"] + '"}'
    )


def _unbiased_draw(hmac_fn: HmacFn, secret: bytes, canonical: str, total: int) -> int:
    two64 = 1 << 64
    limit = (two64 // total) * total
    for c in range(1000):
        digest = hmac_fn(secret, canonical + "|" + str(c))
        v = int.from_bytes(digest[:8], "big")
        if v < limit:
            return v % total
    raise RuntimeError("rejection sampling failed to converge")


def resolve_spawn(ctx: dict, content: dict, secret: bytes, hmac_fn: HmacFn | None = None) -> dict:
    hmac_fn = hmac_fn or _default_hmac
    cats, ruleset, lut = content["cats"], content["ruleset"], content["lut"]

    def pity_after_init() -> dict:
        return {t: ctx.get("pity", {}).get(t, 0) for t in TIERS}

    if len(ctx.get("occupied_slots", [])) >= ruleset["garden_slot_count"]:
        return {
            "selected": None, "no_spawn_reason": "no_free_slot", "fallback_used": False,
            "total_weight": 0, "draw": 0, "eligible": [], "pity_after": pity_after_init(),
            "explanation": {"selected": None, "tier": None, "pity_applied": False, "top_factors": []},
        }

    gated = [c for c in cats if _passes_gates(c, ctx)]
    fallback_used = not any(not c["fallback"] for c in gated)

    scored = [{"cat": c, **_score_cat(c, ctx, ruleset)} for c in gated]
    max_score = max(s["score"] for s in scored)
    eligible = sorted(
        (
            {
                "id": s["cat"]["id"], "tier": s["cat"]["rarity"], "score": s["score"],
                "weight": _weight_for_diff(s["score"] - max_score, lut),
                "factors": s["factors"], "pity_applied": s["pity_applied"],
            }
            for s in scored
        ),
        key=lambda e: e["id"],
    )

    total = sum(e["weight"] for e in eligible)
    for e in eligible:
        e["ppm"] = (e["weight"] * 1_000_000) // total

    draw = _unbiased_draw(hmac_fn, secret, _canonical_seed(ctx, ruleset), total)

    cumulative = 0
    selected = eligible[-1]
    for e in eligible:
        cumulative += e["weight"]
        if draw < cumulative:
            selected = e
            break

    pity_after = pity_after_init()
    for t in TIERS:
        pity_after[t] = 0 if t == selected["tier"] else pity_after[t] + 1

    top_factors = [
        f"{f['label']}(+{f['value']})"
        for f in sorted(
            (f for f in selected["factors"] if f["value"] > 0),
            key=lambda f: (-f["value"], f["label"]),
        )[:3]
    ]

    return {
        "selected": selected["id"],
        "no_spawn_reason": None,
        "fallback_used": fallback_used,
        "total_weight": total,
        "draw": draw,
        "eligible": [{k: e[k] for k in ("id", "tier", "score", "weight", "ppm")} for e in eligible],
        "pity_after": pity_after,
        "explanation": {
            "selected": selected["id"], "tier": selected["tier"],
            "pity_applied": selected["pity_applied"], "top_factors": top_factors,
        },
    }
