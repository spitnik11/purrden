# Purrden

A browser-first, offline-capable **8-bit pixel-art cat-garden** game. Run real focus sessions → earn
garden growth → your garden choices plus live world conditions (weather, time, season) influence
which cats visit **later** → return to collect, bond, and evolve them.

Built deliberately to demonstrate four competencies: **containerization, CI/CD, complex API
integration, and scalable cloud deployment.**

> **Architectural rule:** the shipped game never needs ComfyUI, an LLM, a VLM, or an AI agent.
> AI creates build-time art; accepted PNGs are ordinary static assets.

License: **AGPL-3.0-or-later** (code). Design notes: [`docs/DESIGN-NOTES.md`](docs/DESIGN-NOTES.md).

## Status: Phase 2 — Cloud-save alpha (started)

| Gate | State |
|---|---|
| Phase 0 spawn + art factory | Done |
| Phase 1 offline PWA | Playable (`apps/web`) |
| Multi-tab focus locks + smoke | Done |
| Docker web profile | Done |
| FastAPI command ledger + guest session | Done |
| Postgres models + Alembic | Done |
| **Browser outbox → /v1/sync** | **Done** |
| Keycloak BFF cookies | Deferred (ADR 0004) |

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

## Run

Requires **Node 20+** and **Python 3.10+**.

### Phase 1 — playable offline PWA

```bash
cd apps/web
npm install
npm run dev
# open http://127.0.0.1:5173
# loop: Start focus (3s dev) → auto-completes → plant → set rain → Advance spawn → feed/collect
npm run smoke   # pure offline-loop regression (no browser)
npm run build   # production + service worker
```

Docker:

```bash
# static web only
docker compose -f deploy/compose/docker-compose.yml --profile web up --build
# open http://127.0.0.1:8080

# web + API + Postgres (Phase 2)
docker compose -f deploy/compose/docker-compose.yml --profile core up --build
# API docs http://127.0.0.1:8000/docs
```

Desktop shortcuts (Windows): `Purrden-Local-Dev.bat` on your Desktop starts Vite + browser.

### Phase 2 — API + cloud from the PWA

```bash
# terminal A — API
cd apps/api
pip install -r requirements.txt
uvicorn purrden_api.main:app --reload --port 8000

# terminal B — web (proxies /api → :8000)
cd apps/web
npm run dev
# Cloud save panel → Connect guest → play → Sync now
npm run smoke:cloud   # optional; skips if API down
```

Desktop: run **`Purrden-API-Dev.bat`** then **`Purrden-Local-Dev.bat`**.

### Phase 0 — domain / art factory

```bash
python tools/conformance.py
python tools/test_property_spawn.py
python tools/test_focus.py
pip install -r tools/art-factory/requirements.txt
python tools/art-factory/tests/test_art_factory.py
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
