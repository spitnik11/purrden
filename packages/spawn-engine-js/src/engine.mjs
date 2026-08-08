// Purrden spawn engine — JS reference implementation (pure, zero-build ESM).
//
// Determinism contract (must stay byte-identical to the Python port):
//   - all scoring is signed INTEGER milli-logits (no floats)
//   - weights come from the committed integer exp LUT (content/exp_lut.json), never exp() at runtime
//   - the RNG draw is HMAC-SHA256 -> uint64 stream -> rejection sampling (no modulo bias)
//   - candidates are walked in stable content-id order
//
// `hmac(secretBytes, messageString) -> Uint8Array(32)` is injected so this file stays runtime-neutral
// (Node passes a node:crypto impl; the browser will pass a Web Crypto impl in Phase 1).

const TIERS = ["common", "uncommon", "rare", "legendary"];
const AFFINITY_KINDS = ["precipitation", "daylight", "season", "moon"];

function aff(cat, kind, value) {
  if (value == null) return 0;
  const table = cat.affinities?.[kind];
  return (table && Object.prototype.hasOwnProperty.call(table, value)) ? table[value] : 0;
}

function clampCap(value, cap) {
  return value > cap ? cap : value;
}

// Returns { score, factors:[{label,value}], pityApplied }
function scoreCat(cat, ctx, ruleset) {
  const factors = [];
  let score = cat.base_score;

  for (const kind of AFFINITY_KINDS) {
    const v = aff(cat, kind, ctx.world?.[kind]);
    if (v !== 0) factors.push({ label: `${kind}:${ctx.world[kind]}`, value: v });
    score += v;
  }
  for (const plant of ctx.placements ?? []) {
    const v = (cat.affinities?.placements && Object.prototype.hasOwnProperty.call(cat.affinities.placements, plant))
      ? cat.affinities.placements[plant] : 0;
    if (v !== 0) factors.push({ label: `plant:${plant}`, value: v });
    score += v;
  }

  // Streak raises luck for non-common cats only (a constant added to every cat cancels after max-subtract).
  if (cat.rarity !== "common") {
    const streak = clampCap((ctx.activity?.streak_days ?? 0) * ruleset.streak_bonus_per_day, ruleset.streak_bonus_cap);
    if (streak > 0) factors.push({ label: `streak:${ctx.activity.streak_days}d`, value: streak });
    score += streak;
  }

  const p = ruleset.pity[cat.rarity] ?? { per_miss: 0, cap: 0 };
  const pityBonus = clampCap((ctx.pity?.[cat.rarity] ?? 0) * p.per_miss, p.cap);
  if (pityBonus > 0) factors.push({ label: `pity:${cat.rarity}`, value: pityBonus });
  score += pityBonus;

  if (!(ctx.discovered ?? []).includes(cat.id)) {
    factors.push({ label: "discovery", value: ruleset.discovery_bonus });
    score += ruleset.discovery_bonus;
  }
  if ((ctx.recent_cats ?? []).includes(cat.id)) score -= ruleset.recent_visit_penalty;
  if ((ctx.fully_evolved ?? []).includes(cat.id)) score -= ruleset.fully_evolved_penalty;

  return { score, factors, pityApplied: pityBonus > 0 };
}

function biomeMatches(cat, ctx) {
  return cat.biome == null || cat.biome === ctx.biome;
}

// Hard gates. Fallback cats bypass level/biome so the pool is never empty.
function passesGates(cat, ctx) {
  if (!cat.enabled) return false;
  if ((ctx.cooldown_cats ?? []).includes(cat.id)) return false;
  if (cat.fallback) return true;
  return ctx.garden_level >= cat.min_garden_level && biomeMatches(cat, ctx);
}

function weightForDiff(diffMilli, lut) {
  // diffMilli <= 0. index = round(-diff / step), clamped to the table.
  const negDiff = -diffMilli;
  let idx = Math.floor((negDiff + Math.floor(lut.step_millilogits / 2)) / lut.step_millilogits);
  if (idx > lut.max_index) idx = lut.max_index;
  return lut.weights[idx];
}

function canonicalSeed(ctx, ruleset) {
  // Manual canonical serialization (sorted keys, no whitespace). Ids are simple slugs — a full
  // JCS/RFC-8785 escaper comes with real content in Phase 1. ponytail: slug-only for now.
  return '{"algorithmVersion":"' + ruleset.algorithm_version +
    '","rulesetVersion":"' + ctx.ruleset_version +
    '","slotIndex":' + ctx.slot_index +
    ',"spawnGeneration":' + ctx.spawn_generation +
    ',"spawnWindowId":"' + ctx.spawn_window_id +
    '","userId":"' + ctx.user_id + '"}';
}

function readUint64BE(bytes) {
  let v = 0n;
  for (let i = 0; i < 8; i++) v = (v << 8n) | BigInt(bytes[i]);
  return v;
}

function unbiasedDraw(hmac, secretBytes, canonical, total) {
  const T = BigInt(total);
  const TWO64 = 1n << 64n;
  const limit = (TWO64 / T) * T; // largest multiple of T that fits in 64 bits
  for (let c = 0; c < 1000; c++) {
    const digest = hmac(secretBytes, canonical + "|" + c);
    const v = readUint64BE(digest);
    if (v < limit) return Number(v % T);
  }
  throw new Error("rejection sampling failed to converge"); // astronomically unreachable
}

export function resolveSpawn(ctx, content, hmac, secretBytes) {
  const { cats, ruleset, lut } = content;

  const pityAfterInit = () => {
    const o = {};
    for (const t of TIERS) o[t] = ctx.pity?.[t] ?? 0;
    return o;
  };

  if ((ctx.occupied_slots ?? []).length >= ruleset.garden_slot_count) {
    return {
      selected: null, no_spawn_reason: "no_free_slot", fallback_used: false,
      total_weight: 0, draw: 0, eligible: [], pity_after: pityAfterInit(),
      explanation: { selected: null, tier: null, pity_applied: false, top_factors: [] },
    };
  }

  const gated = cats.filter((c) => passesGates(c, ctx));
  const fallbackUsed = !gated.some((c) => !c.fallback);

  // Score, then quantize relative to the top score.
  const scored = gated.map((c) => ({ cat: c, ...scoreCat(c, ctx, ruleset) }));
  const maxScore = Math.max(...scored.map((s) => s.score));
  const eligible = scored
    .map((s) => {
      const weight = weightForDiff(s.score - maxScore, lut);
      return { id: s.cat.id, tier: s.cat.rarity, score: s.score, weight, factors: s.factors, pityApplied: s.pityApplied };
    })
    .sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));

  const total = eligible.reduce((acc, e) => acc + e.weight, 0);
  for (const e of eligible) e.ppm = Math.floor((e.weight * 1_000_000) / total); // weight<=1e9 -> <2^53, exact

  const draw = unbiasedDraw(hmac, secretBytes, canonicalSeed(ctx, ruleset), total);

  let cumulative = 0;
  let selected = eligible[eligible.length - 1];
  for (const e of eligible) {
    cumulative += e.weight;
    if (draw < cumulative) { selected = e; break; }
  }

  const pityAfter = pityAfterInit();
  for (const t of TIERS) pityAfter[t] = t === selected.tier ? 0 : pityAfter[t] + 1;

  const topFactors = [...selected.factors]
    .filter((f) => f.value > 0)
    .sort((a, b) => (b.value - a.value) || (a.label < b.label ? -1 : 1))
    .slice(0, 3)
    .map((f) => `${f.label}(+${f.value})`);

  return {
    selected: selected.id,
    no_spawn_reason: null,
    fallback_used: fallbackUsed,
    total_weight: total,
    draw,
    eligible: eligible.map(({ id, tier, score, weight, ppm }) => ({ id, tier, score, weight, ppm })),
    pity_after: pityAfter,
    explanation: { selected: selected.id, tier: selected.tier, pity_applied: selected.pityApplied, top_factors: topFactors },
  };
}
