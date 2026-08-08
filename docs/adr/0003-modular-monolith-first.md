# ADR 0003 — Modular monolith first; K3s only after measured need

Status: Accepted (2026-08-07)

## Context
Purrden needs credible cloud architecture for a portfolio (API, workers, queues, observability) without
paying the coordination tax of microservices or Kubernetes on day one.

## Decision
- Ship as a **modular monolith + separate worker/scheduler processes** in one repository.
- Deployable units: `apps/web`, `apps/api`, `apps/worker`, `apps/scheduler` (scheduler appears with
  async visits in Phase 3).
- Shared packages: domain (TS + Python), contracts, persistence.
- **Art Factory** lives under `tools/art-factory` and is **developer workstation only** — never part of
  the shipped runtime Compose profile.
- Compose profiles: `core` (web/api/postgres), `async` (rabbitmq/worker/scheduler), `cache` (valkey),
  `auth` (keycloak), `observability` (otel/prometheus/grafana).
- OCI images from early phases; **OpenTofu** for infra; **K3s deferred** until >2 app hosts or a
  measured failover/rolling-placement need.

## Consequences
- Horizontal scale of API and workers is possible without rewriting domain code.
- No microservice boundaries until a real ownership or scale pressure appears.

## Reconsider if
Multiple teams need independent deploy cadences, or measured ops pain forces an orchestrator.
