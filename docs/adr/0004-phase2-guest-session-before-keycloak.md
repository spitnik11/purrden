# ADR 0004 — Guest BFF session before Keycloak

Status: Accepted (2026-08-08)

## Context
Phase 2 needs a command ledger and authoritative projection. Keycloak is the long-term auth
choice but blocks the persistence vertical if required on day one of cloud-save.

## Decision
- Ship an **opaque guest session** (`bff_sessions` + `X-Purrden-Session` header) for alpha.
- Keep tokens off the client beyond that opaque id (still no access/refresh in JS).
- Add Keycloak Authorization Code + HttpOnly cookie BFF in a follow-up Phase 2 PR without
  changing the command ledger schema.

## Consequences
- Guest cloud saves are first-class; account claim becomes a migration of `player_id` linkage.
- CSRF remains required once cookie auth lands; header-only guest sessions avoid CSRF for now
  when the SPA uses explicit headers (still validate Origin in production later).
