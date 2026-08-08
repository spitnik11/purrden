from fastapi import APIRouter

from .. import __version__
from ..config import get_settings
from ..schemas import HealthOut

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut)
@router.get("/healthz", response_model=HealthOut)
def health() -> HealthOut:
    s = get_settings()
    return HealthOut(status="ok", version=__version__, env=s.env)
