from functools import lru_cache

from fastapi import APIRouter, Query

from ..config import get_settings
from ..services.world import OpenMeteoWeather, WorldContextService

router = APIRouter(prefix="/v1/world", tags=["world"])


@lru_cache
def service() -> WorldContextService:
    return WorldContextService(OpenMeteoWeather(get_settings().weather_base_url))


@router.get("")
def world_context(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
) -> dict[str, object]:
    return service().get(latitude, longitude)
