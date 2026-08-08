# Phase 1 — Offline vertical slice

## Goal

Play the core loop entirely in the browser with **zero backend**:

```text
open offline
→ start/complete focus (persisted timestamps)
→ gain growth energy + spawn window
→ plant in a slot
→ set fake weather/time
→ advance spawn → visitor arrives (deterministic engine)
→ feed / bond / collect
→ reload / second tab → no lost progress, no duplicate rewards
```

## Stack in `apps/web`

| Layer | Choice |
|---|---|
| Build | Vite + TypeScript |
| PWA | `vite-plugin-pwa` (shell/assets only; never saves) |
| Save | Dexie / IndexedDB — one txn per command |
| Garden render | PixiJS (nearest / pixel placeholders) |
| Timer / menus | Accessible HTML |
| Spawn | Shared `packages/spawn-engine-js` + pure JS HMAC |
| Focus | Shared `packages/domain-ts/focus-session.mjs` |

## Save contract

Every player action:

1. validate intent  
2. append `pending_commands`  
3. update projection  
4. bump `deviceSequence` / `saveVersion`  
5. commit IndexedDB transaction  
6. paint UI  

Multi-tab:

- `navigator.locks` on `purrden:save` for every command
- nested `purrden:focus:<id>` for complete/cancel
- rehydrate projection + focus from IndexedDB **before** apply
- `focus.complete` is idempotent (`rewarded` flag → no second energy/spawn)
- timer auto-completes at zero (single-tab guard + locks)
- `BroadcastChannel` refreshes other tabs

## Content IDs

Plants use `plant:fern:v1` etc. Cats remain `cat:mizzle:v1` … Saves never store sprite paths.

## Not in this phase

Keycloak, Postgres, RabbitMQ, Open-Meteo, real art atlases, cloud sync.
