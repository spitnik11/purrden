# Phase 3 world context

The first Phase 3 slice is `GET /v1/world?latitude=...&longitude=...`.
It rounds coordinates to a 0.25-degree cell before calling Open-Meteo, returns no
coordinates, caches successful results per cell/hour, and falls back to recent
weather or a neutral dry context when the provider is unavailable. Daylight and
meteorological season are computed locally without another API.

This is intentionally process-local. Move the cache to Valkey only when multiple
API replicas need to share it. Scheduling, workers, RabbitMQ, inbox, and push remain
separate later Phase 3 slices.
