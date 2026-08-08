# Phase 2 — Cloud-save alpha

## Goal

Local commands become trustworthy cross-device state **without** async visits yet.

```text
POST /v1/guest          → player + opaque session + empty projection
GET  /v1/bootstrap      → load cloud projection
POST /v1/sync           → append commands, server re-validates, bump save_version
```

## Auth (this chunk)

Guest **opaque BFF session** via header `X-Purrden-Session`.  
Keycloak + cookie sessions remain Phase 2 follow-up (not blocking the ledger).

## Idempotency

| Constraint | Prevents |
|---|---|
| `(player_id, command_id)` unique | Retry double-apply |
| `(player_id, device_id, device_sequence)` unique | Sequence replay |

Rejected commands are recorded with `status=rejected` and do not bump `save_version`.

## Run

```bash
# API tests (SQLite, no Docker)
cd apps/api
pip install -r requirements.txt
pytest tests/ -q

# Local API with memory DB
uvicorn purrden_api.main:app --reload --app-dir apps/api

# Compose core profile (when Docker Desktop is up)
docker compose -f deploy/compose/docker-compose.yml --profile core up --build
```

## Browser wire-up (this chunk)

PWA (`apps/web`):

1. **Connect guest** → `POST /v1/guest` → store `sessionId` in Dexie preferences  
2. **Outbox flush** → pending `pending_commands` → `POST /v1/sync` with `X-Purrden-Session`  
3. Auto-flush after each local `dispatch` when connected  
4. **Pull bootstrap** → replace local projection from `GET /v1/bootstrap` (confirm first)  
5. Vite dev proxy: `/api/*` → `http://127.0.0.1:8000`

Spawn commands embed `visitor` + `pity` in the payload so the server ledger can replay without server RNG (Phase 3 will own spawn).

```bash
# terminal A
cd apps/api && uvicorn purrden_api.main:app --reload --port 8000
# terminal B
cd apps/web && npm run dev
# UI: Cloud save → Connect guest → play → Sync now
npm run smoke:cloud   # optional API integration smoke
```

## Not yet

Keycloak, RabbitMQ, Open-Meteo, Celery, multi-device claim UX polish.
