# ADR 0002 — Deterministic dual-runtime spawn engine

Status: Accepted (2026-08-06)

## Context
The browser needs an optimistic spawn preview; the server needs the authoritative result. The two
run different languages (TypeScript/JS and Python). Raw floating-point `exp()` and modulo-based
random draws can disagree across runtimes, which would make optimistic UI diverge from the server
and make replay untrustworthy.

## Decision
Enforce determinism at the **integer layer**:
- All score modifiers are signed integers in **milli-logits**.
- Softmax weights come from a **committed versioned integer exp lookup table** (`content/exp_lut.json`),
  never `exp()` at runtime. The table is the cross-runtime compatibility contract.
- Score→weight index uses integer rounding: `idx = min(max_index, (-diff + step/2) // step)`.
- The RNG draw is `HMAC-SHA256(secret, canonical_seed || counter)` → big-endian uint64 stream →
  **rejection sampling** into `[0, total)` (no modulo bias) → walk candidates in stable content-id order.
- Cloud spawns use a server-only HMAC secret; offline guest spawns use a Web-Crypto installation
  secret stored in IndexedDB. Seeds never use wall-clock time (retries must reproduce the same cat).

## Consequences
- A CI conformance suite runs identical golden vectors against both engines; they must match exactly.
- Every visit stores a replay record (rules/content version, eligible pool, weights, draw, winner,
  pity transition, explanation) and is reproducible.
- Phase 0 uses integer-ppm normalization for reporting; a canonical fixed-total (largest-remainder)
  normalization is deferred until a cross-system normalized weight is actually needed.

## Reconsider if
A single shared runtime (e.g. WASM) replaces the dual implementation.
