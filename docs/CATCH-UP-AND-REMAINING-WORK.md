# Purrden engineering catch-up and remaining work

Canonical engineering handoff as of **2026-08-15**, branch
`agent/purrden-production-milestone`, commit `df50b0d`.

This document answers two questions:

1. Where should a developer read to understand the working system?
2. What remains before Purrden is a complete, secure public game?

The original roadmaps explain intent. This file describes the current code. When they disagree,
the repository, tests, ADRs, and this handoff take precedence until the older document is updated.

## Current product in one paragraph

Purrden is an offline-capable browser cat-garden and focus game. The TypeScript PWA persists actions
in IndexedDB, derives timers from timestamps, prevents multi-tab duplicate rewards, renders a wide
PixiJS garden, and can sync a command ledger to FastAPI/Postgres. Keycloak supplies named accounts
through a same-origin BFF cookie flow. Open-Meteo-derived world context feeds scheduled visits; a
Postgres `SKIP LOCKED` scheduler writes a transactional outbox, RabbitMQ/Celery processes it, and
players read idempotent visits from an inbox. ComfyUI is a build-time art tool only.

## Honest milestone status

| Area | Status | Evidence |
|---|---|---|
| Deterministic spawn engine | Complete | JS/Python engines, 121 golden vectors, property tests |
| Offline focus/garden loop | Complete vertical slice | Dexie store, commands, smoke test, Pixi renderer |
| Durable/multi-tab saves | Complete for current schema | Web Locks, BroadcastChannel, export/import |
| Cloud ledger and reconciliation | Complete alpha | FastAPI sync, claim/join/devices, Alembic, tests |
| Named accounts | Complete alpha | Keycloak OIDC PKCE, BFF cookies, CSRF, claim/logout E2E |
| World context | Functional foundation | rounded cells, Open-Meteo, local daylight/season, fallback |
| Async visits | Functional vertical slice | schedule, `SKIP LOCKED`, outbox, Celery, RabbitMQ, inbox |
| Art Factory | Functional | constrained Comfy client, repair, QA, provenance, promotion |
| Shipped art | One real idle cat | Mizzle idle v2; placeholders cover the rest |
| Side-scroller | Foundation only | 1920px world, camera, parallax, accessible pan controls |
| Accessibility automation | Strong automated baseline | axe WCAG A/AA, keyboard, forced-colors, reduced-motion |
| Production deployment | Local reference stack only | production Compose exists; no real hosted environment |
| Public release | Not ready | manual, operational, content, movement, and hosting gates remain |

## Catch-up path

Read these in order. This is the shortest route from product intent to working code.

1. `README.md` — product pitch, repository layout, basic commands. Its phase label is stale.
2. `docs/CATCH-UP-AND-REMAINING-WORK.md` — current status and remaining work.
3. `docs/DESIGN-NOTES.md` — locked product and architecture decisions.
4. `docs/adr/0001-browser-first-source-of-truth.md` — why the PWA came first.
5. `docs/adr/0002-deterministic-dual-runtime.md` — cross-runtime spawn contract.
6. `docs/adr/0003-modular-monolith-first.md` — why API/workers share one domain.
7. `docs/adr/0004-phase2-guest-session-before-keycloak.md` — account migration history.
8. The feature-specific code map below.
9. `docs/operations/production.md` — current operational commands and limitations.

## Functional code map

### Browser shell and side-scroller

| Concern | Start here | Then read |
|---|---|---|
| App boot and menus | `apps/web/src/ui/app.ts` | `main.ts`, `style.css` |
| Pixi world/camera/parallax | `apps/web/src/ui/garden-pixi.ts` | `assets/atlas.ts`, `assets/palette.ts` |
| Projection rendered by UI | `apps/web/src/game/projection.ts` | `game/types.ts`, `game/content.ts` |
| Player actions | `apps/web/src/game/commands.ts` | shared focus state machine in `packages/domain-ts` |
| Real atlas loading | `apps/web/src/assets/atlas.ts` | `public/assets/cats/mizzle-idle-right-v2.png` |
| Browser release tests | `apps/web/e2e/game.spec.ts` | `playwright.config.ts` |

The current camera moves in four 320px steps across a 1920px world. It is an exploration proof,
not character movement: Mizzle remains centered and the buttons move the camera directly.

### Offline persistence and focus safety

| Concern | Start here |
|---|---|
| IndexedDB schema | `apps/web/src/save/db.ts` |
| Atomic command/save flow | `apps/web/src/save/store.ts` |
| Focus and save locks | `apps/web/src/lib/locks.ts` |
| Offline loop regression | `apps/web/src/game/loop-smoke.ts` |
| Save/cloud DOM smoke | `apps/web/src/ui/dom.test.ts` |

Every action updates the projection and pending command ledger in one Dexie transaction. Focus
completion is timestamp-derived and idempotent. Web Locks serialize mutation, while
BroadcastChannel refreshes sibling tabs. The service worker caches app assets, never save data.

### Cloud save and identity

| Concern | Start here | Then read |
|---|---|---|
| Browser API client | `apps/web/src/cloud/client.ts` | `cloud/outbox.ts`, `cloud/session-store.ts` |
| FastAPI composition | `apps/api/purrden_api/main.py` | `config.py`, `db.py` |
| Guest/claim/join/devices | `apps/api/purrden_api/routes/guest.py` | `services/claim.py` |
| Bootstrap/sync | `apps/api/purrden_api/routes/sync.py` | `services/sync.py`, `projection.py` |
| Keycloak BFF | `apps/api/purrden_api/routes/auth.py` | `auth.py`, Keycloak realm JSON |
| Database contract | `apps/api/purrden_api/models.py` | `alembic/versions/` |
| Named-account E2E | `apps/web/e2e/auth.spec.ts` | CI `phase1-web-build` job |

Browser sessions use an opaque HttpOnly cookie plus a readable CSRF cookie/header pair. Provider
tokens remain server-side. Named-account claim preserves the player ID and revokes guest/share
sessions. The legacy session header exists for non-browser tooling and should not become a browser
authentication shortcut.

### World context and asynchronous visits

| Concern | Start here | Then read |
|---|---|---|
| World route | `apps/api/purrden_api/routes/world.py` | `services/world.py` |
| Visit API | `apps/api/purrden_api/routes/visits.py` | `services/visits.py` |
| Due-row scheduler | `apps/scheduler/scheduler.py` | `apps/scheduler/dispatch.py` |
| Celery worker | `apps/worker/worker.py` | visit/outbox models |
| Runtime services | `deploy/compose/docker-compose.yml` | production override |
| Integration tests | `apps/api/tests/test_world.py` | `test_visits.py` |

Coordinates are rounded to a 0.25-degree cell before provider use and are not returned. Successful
weather is cached per cell/hour in process; recent data or neutral dry context keeps the game
working during provider failure. Scheduling and outbox creation are transactional. Inbox uniqueness
by `schedule_id` makes at-least-once worker delivery safe.

### Spawn engine

| Concern | Location |
|---|---|
| JS reference implementation | `packages/spawn-engine-js/` |
| Python authoritative implementation | `packages/spawn-engine-py/` |
| Rules/content | `content/` |
| Golden contexts | `test-vectors/contexts.json` |
| Cross-runtime verifier | `tools/conformance.py` |

The deterministic boundary is integer milli-logits, a committed exponent lookup table, HMAC-SHA256,
and unbiased rejection sampling over stable content-ID order. Do not replace it with runtime floats.

### Art production

| Concern | Start here |
|---|---|
| Pipeline/state machine | `tools/art-factory/purrden_art/pipeline.py` |
| Restricted Comfy client | `tools/art-factory/purrden_art/comfy_client.py` |
| Background removal/pixel repair | `tools/art-factory/purrden_art/repair.py` |
| Hard QA | `tools/art-factory/purrden_art/qa.py` |
| Specs/style | `art/specs/`, `art/style-bible.yaml` |
| Model approval/provenance | `art/provenance/` |
| Runtime asset map | `apps/web/src/assets/atlas.ts` |

ComfyUI may be called through `http://127.0.0.1:8188`; Purrden must not install, upgrade, reconfigure,
or alter ComfyUI/models without explicit permission. Raw generations and weights remain local and
ignored. Only reviewed, QA-passing PNGs plus provenance enter the shipping tree. Version filenames
when replacing a PWA-cached asset.

### Security, deployment, and operations

| Concern | Location |
|---|---|
| Request/host/session controls | `apps/api/purrden_api/main.py`, `auth.py`, `config.py` |
| Reverse-proxy security headers | `deploy/containers/web.nginx.conf` |
| Locked Python dependencies | `apps/api/requirements.lock` |
| Containers | `deploy/containers/` |
| Local/production services | `deploy/compose/` |
| Backups | `deploy/backup.ps1`, `deploy/restore.ps1` |
| Load smoke | `tools/load_test.py` |
| CI security/build gates | `.github/workflows/ci.yml` |

Production configuration fails closed on missing secrets and HTTPS/host values. Internal service
ports are removed by the production override. This is a secure reference configuration, not proof
of a secure Internet deployment; the edge, secret store, external database, monitoring, and drills
do not exist yet.

## Verification commands

Run from `Z:\Claude app\purrden` in PowerShell unless a command changes directory.

```powershell
# Domain and deterministic parity
python tools/conformance.py
python tools/test_property_spawn.py
python tools/test_focus.py

# Art Factory, no Comfy generation
python -m unittest discover -s tools/art-factory/tests -p 'test_*.py'
python tools/art-factory/cli/art.py comfy validate

# Browser build and smoke
npm --prefix apps/web ci
npm --prefix apps/web run smoke
npm --prefix apps/web run smoke:dom
npm --prefix apps/web run build

# API
python -m pytest apps/api/tests -q

# Production-web browser gate
docker compose -f deploy/compose/docker-compose.yml --profile web up -d --build web
npm --prefix apps/web run e2e
docker compose -f deploy/compose/docker-compose.yml --profile web down
```

The named-account E2E needs the API, Postgres, and Keycloak profile and
`PURRDEN_AUTH_E2E=1`. The complete CI workflow is the canonical automated release gate. At
`df50b0d`, all three GitHub CI jobs pass.

## Everything remaining

The list below is deduplicated from all three roadmaps, the hardened acceptance gates, code state,
and the latest visual/security reviews. “Required” means required for the stated milestone, not that
every item must be built before the next small commit.

### A. Playable side-scroller MVP

- [ ] Replace direct camera buttons with a player movement model: position, velocity, bounds, facing,
      ground collision, and camera follow.
- [ ] Add keyboard controls with remapping-safe defaults; prevent page scrolling only while gameplay
      keys are active.
- [ ] Add touch controls that preserve the large game view and 44px targets.
- [ ] Add gamepad support only after keyboard/touch movement is stable.
- [ ] Persist the player’s world position or deliberately reset it on entry; document the choice.
- [ ] Animate movement with Pixi `AnimatedSprite` or the smallest equivalent already in Pixi.
- [ ] Define interaction range and an accessible HTML alternative for selecting garden slots/cats.
- [ ] Establish 2–3 production parallax layers, ground detail, occlusion rules, and level boundaries.
- [ ] Add a small first garden route with a clear start, exploration purpose, and return point.
- [ ] Keep focus, world, dex, cloud, and save UI in minimalist overlays/sheets without replacing the
      main game surface.
- [ ] Reduce remaining developer telemetry in the player HUD; move diagnostics into Save/Cloud.
- [ ] Add pause/resume and deterministic state behavior when the tab is hidden.
- [ ] Add movement E2E coverage for keyboard, touch-sized controls, bounds, and focus handling.

Exit gate: a player can traverse the garden on desktop and mobile, interact with a slot without a
mouse, open/close menus without losing context, reload safely, and never duplicate an action.

### B. Art and content

- [ ] Generate a true right-facing Mizzle walk cycle with readable paw/body motion; reject the current
      local standing candidate as a walk frame.
- [ ] Repair, hard-QA, visually review, human-promote, hash, and record provenance for every frame.
- [ ] Mirror right-facing frames in Pixi for left movement unless asymmetric clothing requires unique art.
- [ ] Add idle/blink or tail-flick only after walk readability is proven.
- [ ] Generate and promote real sprites for Tabby, Sol, and Luna; placeholders remain fallback-only.
- [ ] Add required growth-stage or outfit variants referenced by content.
- [ ] Create production ground, plant, prop, and parallax tiles under the same pixel/style contract.
- [ ] Build or extend a versioned atlas manifest for animation frame arrays and timings.
- [ ] Add atlas build validation: missing frames, duplicate IDs, dimensions, alpha, palette, baseline,
      provenance hash, and licence approval.
- [ ] Retain exact downloaded model/version licence evidence and hashes outside git where appropriate;
      do not rely only on a generic SDXL family statement.
- [ ] Run a full accepted-assets provenance audit before release.
- [ ] Confirm and publish the final asset licence/attribution file for CC BY-SA/CC0 outputs.

Exit gate: every visible release asset is promoted, traceable, licence-cleared, QA-passing, correctly
loaded after a PWA update, and has a placeholder fallback that does not crash the game.

### C. Core game depth and content

- [ ] Replace developer “advance spawn” shortcuts with real spawn-window timing in normal play.
- [ ] Connect focus completion to server visit scheduling when cloud-connected while preserving the
      fully offline local loop.
- [ ] Define food earning/spending, feeding, bonding, collection, and evolution balance.
- [ ] Finish cat-stage progression and visible dex states.
- [ ] Add garden upgrade/plant progression and meaningful effects on spawn scoring.
- [ ] Add tutorial/onboarding that explains focus, planting, later visits, offline saves, and cloud opt-in.
- [ ] Add non-punitive missed-day/grace behavior; no streak-loss pressure.
- [ ] Add content/ruleset migrations and compatibility tests for existing saves.
- [ ] Add save-schema migration fixtures covering at least the earliest shipped save through current.
- [ ] Decide release content target: minimum cats, plants, route length, and progression duration.
- [ ] Balance with deterministic simulation/replay data before expanding rare content.

Exit gate: the release loop is understandable, rewarding, durable across upgrades, and does not depend
on developer toggles.

### D. World context and visit pipeline

- [ ] Replace approximate daylight calculation with Astral and test polar/day-boundary cases.
- [ ] Add bounded retry with `Retry-After`, exponential backoff, timeout budgets, and circuit breaker
      behavior to the Open-Meteo adapter.
- [ ] Persist last-known-good world context; the current cache is process-local.
- [ ] Move shared weather cache to Valkey only when multiple API replicas require it.
- [ ] Define provider attribution, commercial-use plan, quota monitoring, and self-host/swap path.
- [ ] Store only the rounded geo cell and required consent metadata; never raw precise location.
- [ ] Schedule visits from authoritative server context and rules, not client-supplied weather.
- [ ] Add schedule cancellation/expiry and stale-window behavior.
- [ ] Add scheduler recovery tests for crashes between claim, outbox write, publish, and status update.
- [ ] Add Celery retry/dead-letter policy and operational visibility for poison events.
- [ ] Verify RabbitMQ quorum queue declaration in the production environment.
- [ ] Add inbox acknowledgement/read state and retention cleanup.
- [ ] Add end-to-end tests proving worker retry cannot duplicate a visit.
- [ ] Add optional Web Push only after inbox reliability: VAPID secret handling, explicit opt-in,
      unsubscribe, expiry cleanup, permission-denied UX, and privacy copy.

Exit gate: provider failure never blocks play; scheduling survives restarts; duplicate delivery never
duplicates visits; privacy promises match stored data.

### E. Accounts, sync, and cloud UX

- [ ] Add player-facing account/session state, cloud failure, offline, conflict, and retry UX.
- [ ] Make guest-to-named claim recovery safe if the browser closes mid-flow.
- [ ] Add explicit device/session revocation UI and “sign out all devices.”
- [ ] Define named-account deletion and data export flows.
- [ ] Add email verification/password-reset behavior or explicitly document Keycloak defaults.
- [ ] Add session rotation and concurrent-session tests across multiple browsers/devices.
- [ ] Add reconciliation tests for long offline histories, out-of-order devices, rejected commands,
      schema/ruleset upgrades, and server-ahead/client-ahead cases.
- [ ] Define command-ledger retention/compaction without breaking replay/audit requirements.
- [ ] Make server-authoritative spawning the named-account policy; keep any client spawn explicitly
      limited to offline/guest play.
- [ ] Tighten genesis/import caps whenever new inventory, progression, or content fields are added.
- [ ] Add account abuse controls: registration/login throttling, enumeration-resistant errors, and
      recovery-path testing at the Keycloak/edge layer.

Exit gate: two real browsers can play offline, reconnect, claim, reconcile, revoke, recover, export,
and delete without lost or duplicated progress.

### F. Accessibility and inclusive design

- [ ] Complete manual NVDA testing on Windows for boot, focus timer, movement alternatives, every menu,
      cloud claim, errors, visit inbox, and dex.
- [ ] Test keyboard-only play in Chrome, Edge, and Firefox, including Escape and focus return.
- [ ] Test Windows High Contrast manually, not only Playwright forced-colors emulation.
- [ ] Test at 200% and 400% zoom/reflow and with large text settings.
- [ ] Test screen magnifier usability and ensure camera motion does not disorient.
- [ ] Add a reduced-motion gameplay mode for camera/parallax and any sprite effects.
- [ ] Provide semantic/live text alternatives for important canvas state and interactions.
- [ ] Verify status announcements are useful and not noisy during movement/timer updates.
- [ ] Verify contrast for all final art-backed overlays and weather/daylight palettes.
- [ ] Test touch targets, orientation changes, safe-area insets, and virtual-keyboard behavior.
- [ ] Document known limitations and an accessibility contact/process for the public release.

Exit gate: automated WCAG 2.2 A/AA remains clean and the manual assistive-technology checklist has
documented results and resolved critical/high findings.

### G. Security and privacy release gate

- [ ] Commission or perform a fresh threat-model review after movement, push, account deletion, and
      production hosting are final.
- [ ] Run secret scanning on repository history and container/image layers, not only staged files.
- [ ] Add SAST for TypeScript/Python and container/IaC scanning to CI.
- [ ] Produce SBOMs and signed/provenanced release images; CI currently tests/builds but does not publish.
- [ ] Pin container images by digest and define dependency update policy.
- [ ] Terminate TLS at the real edge; verify HSTS, cookie flags, proxy headers, trusted hosts, redirects,
      CSP, COOP, nosniff, frame denial, and cache rules over HTTPS.
- [ ] Put production secrets in a managed secret store; never `.env`, Compose defaults, images, logs,
      browser storage, or the repository.
- [ ] Rotate all production credentials and document rotation/revocation procedures.
- [ ] Restrict database, RabbitMQ, Keycloak admin, metrics, and debug endpoints to private networks.
- [ ] Disable public API docs/debug tracebacks in production unless intentionally protected.
- [ ] Validate CORS/Origin/CSRF behavior behind the exact production proxy/CDN.
- [ ] Add endpoint-specific request size, rate, and abuse limits at both edge and application layers.
- [ ] Add authentication, sync, import, world-coordinate, scheduler, and inbox fuzz/property tests.
- [ ] Verify logs redact cookies, authorization codes/tokens, CSRF values, precise coordinates, emails,
      and database URLs.
- [ ] Define audit events for login, claim, logout, device revocation, deletion, admin changes, and restores.
- [ ] Publish privacy policy, data inventory, retention periods, subprocessors, location explanation,
      cookie explanation, export/deletion instructions, and age/audience decision.
- [ ] Run dependency audits immediately before release and resolve all high/critical findings.
- [ ] Run an independent penetration test or focused external review before Internet exposure.

Exit gate: the deployed environment, not just source code, passes the security checklist with no known
critical/high finding and no secret or sensitive value exposure.

### H. Deployment and infrastructure

- [ ] Choose the first hosting environment and document DNS, region, cost ceiling, and ownership.
- [ ] Implement OpenTofu for network, compute/container service, managed Postgres, secret store, TLS/DNS,
      object storage backups, monitoring, and least-privilege identities.
- [ ] Keep K3s deferred until measured need: more than two app hosts or orchestration constraints.
- [ ] Build and publish versioned OCI images from CI after tests; scan, sign, and retain provenance.
- [ ] Add a migration job/runbook with forward and rollback/roll-forward decisions.
- [ ] Add zero/low-downtime deployment and a tested rollback procedure.
- [ ] Separate dev/staging/production data, Keycloak realms/clients, secrets, and domains.
- [ ] Configure external production Postgres with encrypted connections, restricted roles, maintenance,
      connection limits/pooling, and high-availability policy.
- [ ] Run Keycloak against its external database with backups and production hostname/proxy settings.
- [ ] Configure RabbitMQ durable storage, quorum queues, resource alarms, monitoring, and recovery policy.
- [ ] Decide whether Valkey is needed from measured replica/cache behavior; do not add it preemptively.
- [ ] Add CDN/static asset caching with versioned immutable assets and safe service-worker rollout.
- [ ] Add staging smoke tests after deployment and production synthetic health checks.

Exit gate: a tagged release can be deployed and reverted from documented automation without direct
database edits or workstation-only steps.

### I. Backups, reliability, observability, and load

- [ ] Store encrypted Postgres/Keycloak backups outside the deployment failure domain.
- [ ] Define backup frequency, retention, RPO, RTO, ownership, and alerting.
- [ ] Automate backup jobs and integrity checks; the current PowerShell scripts are manual references.
- [ ] Perform and document repeated restore drills into isolated infrastructure, including Keycloak and
      application consistency, not only a single local database restore.
- [ ] Add OpenTelemetry instrumentation across API, scheduler, outbox dispatch, Celery tasks, and provider calls.
- [ ] Export metrics to Prometheus and dashboards/alerts to Grafana or the chosen equivalent.
- [ ] Track request latency/error rate, database saturation, scheduler lag, oldest outbox age, queue depth,
      queue age, worker failures/retries, inbox latency, world-provider health, auth failures, and backup age.
- [ ] Add structured correlation IDs from browser request through schedule/outbox/worker/inbox.
- [ ] Define SLOs and alert thresholds; scale workers from queue age, not CPU alone.
- [ ] Run sustained mixed load, not only the current 200-request smoke.
- [ ] Test concurrent sync conflicts, account claims, world lookups, due schedules, and inbox reads.
- [ ] Run failure tests: provider timeout, Postgres restart, RabbitMQ restart, worker crash, duplicate event,
      scheduler overlap, Keycloak outage, full disk, backup failure, and bad deployment rollback.
- [ ] Measure browser performance, bundle loading, memory, canvas FPS, battery impact, and IndexedDB growth
      on representative desktop and mobile hardware.
- [ ] Set capacity limits and an explicit scale gate before replicas/HA/K3s.

Exit gate: measured SLOs hold under target load, alerts fire usefully, and a restore/failure drill meets
the documented RPO/RTO.

### J. Browser, PWA, compatibility, and release quality

- [ ] Test current Chrome, Edge, Firefox, and Safari/WebKit where supported.
- [ ] Test install/update/offline behavior, first load, stale service worker, asset revision, and recovery
      from a partially cached release.
- [ ] Add a user-visible update/reload prompt for incompatible PWA revisions.
- [ ] Verify IndexedDB quota/persistence denial, eviction messaging, export, and restore.
- [ ] Test multi-tab behavior without Web Locks support and document the fallback ceiling.
- [ ] Add real-device mobile testing for viewport height, orientation, touch, safe areas, performance,
      and menu sheets.
- [ ] Profile and reduce the current >500KB main bundle if measurements show load/performance harm;
      do not split it only to silence the warning.
- [ ] Add visual regression coverage for the main view, every menu, mobile sheet, forced colors, and
      representative day/night/weather states.
- [ ] Resolve all critical/high browser console errors and failed asset/network requests.
- [ ] Run save migration, privacy, licence, and security release checklists against the exact candidate.

Exit gate: supported browsers install, update, play offline/online, and recover without blank screens,
stale assets, lost progress, inaccessible controls, or unhandled errors.

### K. Documentation, community, and public launch

- [ ] Update `README.md` milestone table so it no longer labels completed Phase 3/production foundations
      as future work.
- [ ] Keep this handoff synchronized at milestone boundaries; do not turn it into a daily changelog.
- [ ] Add contributor setup, architecture diagram, coding/test conventions, and art contribution rules.
- [ ] Add API/open-source deployment documentation and a supported-version policy.
- [ ] Publish licence notices and generated-asset attribution/provenance summary.
- [ ] Add production runbooks: deploy, rollback, migration failure, auth outage, provider outage,
      queue backlog, database restore, secret rotation, incident response, and data deletion.
- [ ] Define release versioning, changelog, signed tags, and support/security-reporting channels.
- [ ] Prepare a public demo environment with non-sensitive seed data and no development credentials.
- [ ] Complete final product copy, onboarding, privacy/terms/accessibility pages, screenshots, and demo.

Exit gate: a new developer can build/test from documentation, an operator can recover the service,
and a player can understand the game and its data use without private design notes.

## Recommended execution order

1. **Finish the playable side-scroller:** movement, camera follow, keyboard/touch, interaction, one route.
2. **Finish visible art:** Mizzle walk cycle, animation manifest, remaining release sprites/tiles.
3. **Connect the real loop:** focus completion → authoritative scheduled visit → inbox → collection.
4. **Harden player cloud UX:** account/session recovery, conflicts, deletion/export, device revocation.
5. **Close manual quality gates:** NVDA, real browsers/devices, migrations, PWA update recovery.
6. **Provision staging with OpenTofu:** TLS, secret store, external Postgres/Keycloak/RabbitMQ.
7. **Add observability/backups:** telemetry, alerts, off-host backups, repeated restore drills.
8. **Run security/failure/load gates:** independent review, sustained workloads, outage/rollback drills.
9. **Ship a release candidate:** full provenance/privacy/licence review, docs, demo, signed images/tag.

Do not add Valkey, HA replicas, Web Push, or K3s ahead of the boundary that needs them. The current
modular monolith, Postgres scheduler, RabbitMQ/Celery worker, and static PWA are sufficient to finish
the game and prove the public MVP first.

## Definition of public-ready

Purrden is public-ready only when all of the following are true:

- The side-scroller is genuinely playable with keyboard and touch, with accessible alternatives.
- The complete release loop works offline and through named-account cloud sync without duplication.
- World-provider and queue failures degrade safely and recover automatically.
- All visible assets are promoted, licence-cleared, provenance-verified, and PWA-cache-safe.
- Manual accessibility, cross-browser, migration, privacy, and security reviews pass.
- The real HTTPS environment uses managed secrets and private internal services.
- Sustained load/failure tests meet written SLOs.
- Off-host backups and isolated restore drills meet written RPO/RTO.
- Monitoring, alerts, deployment, rollback, incident, and deletion runbooks are proven.
- CI builds, audits, scans, signs, and publishes the exact release artifacts.

Until then, describe the project as a **production-oriented local alpha with complete architectural
vertical slices**, not a production-hosted game.
