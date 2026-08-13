from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Callable, Protocol

import httpx


class WeatherProvider(Protocol):
    def current(self, latitude: float, longitude: float) -> str: ...


class OpenMeteoWeather:
    def __init__(self, base_url: str, client: httpx.Client | None = None) -> None:
        self.base_url = base_url
        self.client = client or httpx.Client(timeout=3)

    def current(self, latitude: float, longitude: float) -> str:
        response = self.client.get(
            self.base_url,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "current": "weather_code",
                "timezone": "UTC",
            },
        )
        response.raise_for_status()
        code = response.json().get("current", {}).get("weather_code")
        if not isinstance(code, int) or not 0 <= code <= 99:
            raise ValueError("Open-Meteo returned an invalid weather code")
        if code in {95, 96, 99}:
            return "storm"
        if code in {51, 53, 56}:
            return "drizzle"
        if code in {55, 57, 61, 63, 65, 66, 67, 80, 81, 82}:
            return "rain"
        if code in {71, 73, 75, 77, 85, 86}:
            return "snow"
        return "none"


@dataclass(frozen=True)
class CachedWorld:
    value: dict[str, object]
    fetched_at: datetime


class WorldContextService:
    def __init__(
        self,
        provider: WeatherProvider,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        stale_for: timedelta = timedelta(hours=6),
    ) -> None:
        self.provider = provider
        self.now = now
        self.stale_for = stale_for
        self._hourly: dict[tuple[float, float, datetime], CachedWorld] = {}
        self._last_good: dict[tuple[float, float], CachedWorld] = {}
        self._lock = Lock()  # ponytail: process-local; use Valkey when replicas need shared cache

    def get(self, latitude: float, longitude: float) -> dict[str, object]:
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValueError("invalid coordinates")
        now = self.now().astimezone(timezone.utc)
        cell = (round(latitude * 4) / 4, round(longitude * 4) / 4)
        key = (*cell, now.replace(minute=0, second=0, microsecond=0))
        with self._lock:
            cached = self._hourly.get(key)
        if cached:
            return dict(cached.value)

        local = now + timedelta(hours=round(cell[1] / 15))
        daylight = "day" if 7 <= local.hour < 18 else "dawn" if local.hour == 6 else "dusk" if local.hour == 18 else "night"
        month = local.month if cell[0] >= 0 else (local.month + 5) % 12 + 1
        season = ("winter", "spring", "summer", "autumn")[(month % 12) // 3]
        context = {"daylight": daylight, "season": season}

        try:
            precipitation = self.provider.current(*cell)
            value = {**context, "precipitation": precipitation, "source": "open-meteo", "stale": False}
            entry = CachedWorld(value, now)
            with self._lock:
                self._hourly[key] = entry
                self._last_good[cell] = entry
            return dict(value)
        except (httpx.HTTPError, ValueError):
            with self._lock:
                previous = self._last_good.get(cell)
            if previous and now - previous.fetched_at <= self.stale_for:
                return {**previous.value, **context, "stale": True}
            return {**context, "precipitation": "none", "source": "fallback", "stale": True}
