# ADR 0001 — Browser-first PWA with tiered source-of-truth

Status: Accepted (2026-08-06)

## Context
Purrden must be playable in a browser, offline, and installable, while also being a credible
showcase for scalable cloud architecture. Those are two different milestones and must not be
conflated.

## Decision
- The product is an installable PWA. The first release (offline vertical slice) runs entirely in the
  browser with **no backend**.
- Source of truth is tiered: **IndexedDB** owns local/guest state; **PostgreSQL** owns authoritative
  state after sign-in; a cache (Valkey) is disposable and never authoritative; RabbitMQ carries work,
  not truth.
- Guest saves are player-editable and therefore **untrusted**; claiming a guest save into an account
  is a one-time validated import. The server never trusts future client-generated rolls.

## Consequences
- Phase 1 containerizes only the web build + a static server; database/API/broker arrive in later
  phases behind Compose profiles.
- Every browser command is a request the server independently revalidates.

## Reconsider if
Offline play stops being a goal, or a non-browser client becomes primary.
