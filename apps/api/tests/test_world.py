from datetime import datetime, timedelta, timezone

import httpx

from purrden_api.services.world import OpenMeteoWeather, WorldContextService


class Provider:
    def __init__(self) -> None:
        self.calls: list[tuple[float, float]] = []
        self.fail = False

    def current(self, latitude: float, longitude: float) -> str:
        self.calls.append((latitude, longitude))
        if self.fail:
            raise httpx.ConnectError("offline")
        return "rain"


def test_world_context_rounds_location_and_falls_back():
    clock = [datetime(2026, 8, 13, 12, tzinfo=timezone.utc)]
    provider = Provider()
    worlds = WorldContextService(provider, now=lambda: clock[0])

    fresh = worlds.get(40.7128, -74.0060)
    assert fresh == {"daylight": "day", "season": "summer", "precipitation": "rain", "source": "open-meteo", "stale": False}
    assert provider.calls == [(40.75, -74.0)]
    assert "latitude" not in fresh and "longitude" not in fresh

    clock[0] += timedelta(hours=1)
    provider.fail = True
    stale = worlds.get(40.7128, -74.0060)
    assert stale["precipitation"] == "rain" and stale["stale"] is True

    neutral = worlds.get(-33.9, 151.2)
    assert neutral["source"] == "fallback" and neutral["precipitation"] == "none"
    assert neutral["season"] == "winter"


def test_open_meteo_maps_weather_and_rejects_bad_payload():
    rain = httpx.MockTransport(lambda _request: httpx.Response(200, json={"current": {"weather_code": 63}}))
    assert OpenMeteoWeather("https://weather.test", httpx.Client(transport=rain)).current(0, 0) == "rain"

    bad = httpx.MockTransport(lambda _request: httpx.Response(200, json={"current": {}}))
    provider = OpenMeteoWeather("https://weather.test", httpx.Client(transport=bad))
    try:
        provider.current(0, 0)
        assert False, "malformed weather must be rejected"
    except ValueError:
        pass
