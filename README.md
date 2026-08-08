# Purrden

A browser-first, offline-capable **8-bit pixel-art cat-garden** game. Run real focus sessions → earn
garden growth → your garden choices plus live world conditions (weather, time, season) influence
which cats visit **later** → return to collect, bond, and evolve them.

Built deliberately to demonstrate four competencies: **containerization, CI/CD, complex API
integration, and scalable cloud deployment.**

> **Architectural rule:** the shipped game never needs ComfyUI, an LLM, a VLM, or an AI agent.
> AI creates build-time art; accepted PNGs are ordinary static assets.

License: **AGPL-3.0-or-later** (code). Design notes: [`docs/DESIGN-NOTES.md`](docs/DESIGN-NOTES.md).

## Status: Phase 0 — Foundations (in progress)

| Gate | State |
|---|---|
| Dual-runtime spawn engine (JS + Python) | Working |
| Cross-runtime golden vectors | Expanding toward ≥100 |
| Focus-session state machine | Working (TS + Python) |
| Content IDs + style bible + 4 cat specs | Done |
| Model license registry (RAIL++-M approved) | Done |
| `art models scan` + hard QA CLI | Scaffolded |
| Full Phase-0 exit (end-to-end art job + 100 goldens) | In progress |

## Layout

```text
purrden/
├─ apps/                 web · api · worker · scheduler (later phases)
├─ packages/
│  ├─ spawn-engine-js/   JS reference spawn engine (pure ESM)
│  ├─ spawn-engine-py/   Python authoritative spawn engine
│  ├─ domain-ts/         focus state machine (ESM)
│  └─ domain-python/     focus state machine (Python)
├─ content/              cats, ruleset, integer exp LUT (cross-runtime contract)
├─ art/
│  ├─ style-bible.yaml
│  ├─ specs/             durable asset specs (not prompts)
│  ├─ workflows/recipes/
│  ├─ provenance/        model license registry
│  └─ accepted/          human-promoted sprites only
├─ tools/
│  ├─ art-factory/       developer-only art production
│  ├─ conformance.py     JS ↔ Python spawn parity
│  └─ gen_contexts.py    golden vector expander
├─ test-vectors/
├─ tests/
├─ deploy/
└─ docs/
```

## Run (Phase 0)

Requires **Node 18+** and **Python 3.10+**. No build step yet.

```bash
# regenerate integer exp LUT (rarely needed)
python tools/gen_exp_lut.py

# expand golden contexts (≥100)
python tools/gen_contexts.py

# prove JS and Python spawn engines agree (the Phase-0 engine gate)
python tools/conformance.py

# property invariants + focus unit tests
python tools/test_property_spawn.py
python tools/test_focus.py

# art factory: license registry / model scan / hard QA
python tools/art-factory/cli/art.py licenses
python tools/art-factory/cli/art.py models scan
# python tools/art-factory/cli/art.py qa path/to/32x32.png
```

Optional: copy [`.env.example`](.env.example) → `.env` and set `PURRDEN_ART_MODEL_ROOT` to your
local ComfyUI weights directory. **Never commit weights.**

## Determinism contract

All scoring is integer milli-logits; weights come from the committed `content/exp_lut.json` (never
`exp()` at runtime); the RNG draw is `HMAC-SHA256 → uint64 stream → rejection sampling` (no modulo
bias); candidates are walked in stable content-id order. See
[`docs/adr/0002-deterministic-dual-runtime.md`](docs/adr/0002-deterministic-dual-runtime.md).

## Model licensing (art)

`pixelArtDiffusionXL_spriteShaper` and `ArsMJStyleSDXL_-_Pixel_Art` are registered as
**APPROVED_FOR_GENERATED_ASSETS** under CreativeML OpenRAIL++-M (licensor claims no rights in
Output). Provenance still records exact SHA-256 + recipe + seed for every promoted sprite. Registry:
[`art/provenance/model-licenses.yaml`](art/provenance/model-licenses.yaml).

## Phases (acceptance gates)

0. **Contracts & proofs** — spawn parity + art-spec pipeline viable  
1. **Offline vertical slice** — full local loop in a PWA (no cloud)  
2. **Cloud-save alpha** — command ledger, guest claim, multi-device reconcile  
3. **World-powered public MVP** — weather, Astral, RabbitMQ/Celery visits  
4. **Production scaling** — OpenTofu, HA, OTel, restore drills  

## GitHub

Public repository: [spitnik11/purrden](https://github.com/spitnik11/purrden)
