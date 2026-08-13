# Phase 2 — Cloud-save alpha

## Goal

Local commands become trustworthy cross-device state **without** async visits yet.

```text
POST /v1/guest          → player + opaque session + empty projection
GET  /v1/bootstrap      → load cloud projection
POST /v1/sync           → append commands, server re-validates, bump save_version
```

## Auth (this chunk)

Guest and named accounts use opaque, server-side sessions. Browsers receive an HttpOnly BFF
cookie plus a readable CSRF cookie; unsafe requests require the matching CSRF header and an
allowed same-origin request. Keycloak authorization-code callbacks claim guest state into the
named account without exposing provider tokens to the browser. The legacy session header remains
available for non-browser clients.

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

## Browser wire-up

1. **Claim local garden** → `POST /v1/guest/claim` (sanitized genesis)  
2. **Empty guest** → `POST /v1/guest`  
3. **Join session** → `POST /v1/session/join` with shared session id (second browser)  
4. **Outbox flush / Reconcile** → `POST /v1/sync` then optional bootstrap pull if server ahead  
5. **Devices** → `GET /v1/devices`  
6. Vite proxy: `/api/*` → `http://127.0.0.1:8000`

Genesis claim clamps energy/inventory, drops `installationSecretHex`, and only allows known plant/cat ids.

```bash
cd apps/api && uvicorn purrden_api.main:app --reload --port 8000
cd apps/web && npm run dev
# Browser A: Claim local → Copy share session
# Browser B: Join session… → paste id → Reconcile after play
```

## Next

Production restore drills, external TLS/proxy verification, and sustained load testing.
