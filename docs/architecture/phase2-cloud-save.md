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

## Not in this chunk

Keycloak, RabbitMQ, Open-Meteo, Celery, browser→API wire-up in the PWA (next).
