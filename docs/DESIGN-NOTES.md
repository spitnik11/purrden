# Purrden — Design Notes (session digest)

Sources (desktop design docs, 2026-08-07):

1. **Hardened Implementation Roadmap** — browser game, durable saves, local open-source Art Factory
2. **Art Automation & Licensing** — model commercial-use clearance (supersedes earlier YELLOW flags)

Formal Obsidian notes remain at `02 Projects/Purrden/` and curated memory `PROJECT-Purrden.md`.

---

## Product

Browser-playable **8-bit pixel-art cat garden × Pomodoro focus timer** (*Neko Atsume × Forest*).

Loop: focus session → growth energy → tend garden → garden + world (weather/time/season) + pity shape a later **spawn window** → cats visit asynchronously → collect / feed / bond / evolve.

Portfolio pillars: **Docker · CI/CD · complex API integrations · scalable cloud**.

---

## Non-negotiable architectural rule

> **The shipped game never needs ComfyUI, an LLM, a VLM, or an AI agent.**  
> AI creates build-time art; accepted PNGs + metadata are ordinary static assets.

Two cooperating tracks meet only through a **versioned asset manifest**:

| Track | What |
|---|---|
| **Game/product** | TypeScript PWA → IndexedDB (Dexie) → PixiJS garden → FastAPI/Postgres sync → world data → RabbitMQ/Celery async spawning |
| **Art Factory (dev only)** | asset specs → model registry → prompt compiler → ComfyUI → pixel repair → hard QA → optional local VLM → human promotion → atlas |

---

## Locked stack

| Concern | Choice |
|---|---|
| Browser app | TypeScript + Vite PWA |
| Garden renderer | PixiJS (nearest-neighbor); HTML for timer/menus/dex/settings |
| Local saves | Dexie / IndexedDB (not localStorage for game state) |
| Cloud truth | PostgreSQL |
| API | FastAPI BFF + Keycloak (opaque session cookie; tokens server-side) |
| Jobs | RabbitMQ quorum + Celery (Phase 3+; not earlier) |
| Cache | Valkey only (never authoritative) |
| Weather | Open-Meteo adapter (self-hostable later) |
| Astronomy | Astral (local) |
| IaC | OpenTofu |
| Observability | OpenTelemetry → Prometheus/Grafana |
| Code license | AGPL-3.0-or-later |
| Assets | CC BY-SA 4.0 / CC0 |
| Pixel tool | LibreSprite (GPL); Pixelorama optional (MIT) |

---

## Browser / save rules

- **Autosave on every action** in one IndexedDB transaction (command + projection + deviceSequence).
- Focus timer = **persisted timestamps**; `setInterval` is display only. Auth timeout must not kill a running focus session.
- Multi-tab: Web Locks (`purrden:focus:…`, `purrden:sync-leader`, `purrden:migration`) + BroadcastChannel.
- Service worker caches the **game shell/assets**, never saves or authenticated responses.
- Cloud sync = **command ledger + optimistic `save_version`**, not whole-save replacement.
- Guest IDB is **untrusted**; claim = one-time validated genesis import.
- Manual JSON export/import from first vertical slice; `navigator.storage.persist()` is advisory.

Content IDs are stable forever:

```text
cat:puddle:v1   plant:fern:v1   biome:garden:v1   ruleset:2026.09.0
```

Saves never reference sprite filenames.

---

## Spawn engine (Phase 0 core)

- Seed: `HMAC-SHA256(secret, canonical JSON of user·window·slot·generation·ruleset·algorithm)` — never wall-clock.
- Scoring: signed **milli-logits**; weights from committed **`content/exp_lut.json`** (never runtime `exp()`).
- Draw: HMAC → uint64 stream → **rejection sampling** → walk candidates by stable content id.
- Soft affinities + guaranteed **fallback pool**; pity by rarity tier; hard gates sparse.
- **TS/JS is first executable reference**; Python is the Phase-2 cloud authority. Shared golden vectors enforce parity.

Current Phase-0 content cats: `cat:tabby:v1` (fallback), `cat:sol:v1` (sunny), `cat:mizzle:v1` (rain/fern/pond ≈ design “puddle”), `cat:luna:v1` (night).

---

## Model licensing (supersedes hardened-doc YELLOW flags)

Per **Art Automation & Licensing** design doc (user-confirmed for commercial project use):

| Model | Family | Status |
|---|---|---|
| `pixelArtDiffusionXL_spriteShaper` | CreativeML OpenRAIL++-M (SDXL lineage) | **APPROVED_FOR_GENERATED_ASSETS** |
| `ArsMJStyleSDXL_-_Pixel_Art` | CreativeML OpenRAIL++-M | **APPROVED_FOR_GENERATED_ASSETS** |

RAIL++-M: perpetual, worldwide, royalty-free; **licensor claims no rights in generated Output**. Use-restriction list still applies (no defamation / personal-data abuse, etc.). Civitai “contact creator” page notes do **not** override the model license grants.

Still required for every promoted sprite:

- model SHA-256 + tags in provenance
- no weight files in the git repo
- human promotion gate
- Z-Image (Apache-2.0) remains an optional GREEN baseline lane

Model root (read-only, never committed):

```text
PURRDEN_ART_MODEL_ROOT=C:\Users\losth\Desktop\pixel art models
COMFYUI_URL=http://127.0.0.1:8188
```

---

## Phases (acceptance gates, not calendar dates)

| Phase | Exit gate |
|---|---|
| **0 Contracts & proofs** | One deterministic spawn vector + one art-spec → generate/repair/QA/trace; engines agree on ≥100 goldens |
| **1 Offline vertical slice** | Offline: focus → grow → plant → advance time → visit → feed/evolve → reload; multi-tab no dups |
| **2 Cloud-save alpha** | Guest → cloud claim; two browsers offline + reconcile; no duplicate rewards |
| **3 World-powered public MVP** | Real weather/time; provider fail ≠ stop game; worker retry ≠ duplicate visit |
| **4 Production scaling** | Load/queue-age SLOs; restore drill; deploy/revert runbooks |
| **Release hardening** | A11y, privacy, migration, security, full GREEN art audit |

Sequencing discipline: **no Keycloak / RabbitMQ / weather until their phase**. Prove the loop offline first.

---

## Token / agent cost controls (built into architecture)

- Structured asset specs (not free-form prompt thrashing)
- Local prompt planner + hard QA before any VLM
- Fixed candidate/refinement budgets
- Coding agent talks to Art Factory via narrow tools later (MCP optional); never raw Comfy graphs / shell / model download
- Work in phase chunks; commit + push each vertical slice

---

## GitHub

- Public repo: **`spitnik11/purrden`**
- Independent of private `z-image-studio` — port only generic ComfyUI-client concepts
- CI never regenerates AI art; CI validates accepted assets + engine golden vectors + builds
