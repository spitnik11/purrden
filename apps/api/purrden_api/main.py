from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from . import __version__
from .config import get_settings
from .db import init_db
from .routes import auth, guest, health, sync, visits, world


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Dev/test convenience. Production should run Alembic migrations.
    init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Purrden API",
        version=__version__,
        description="Phase 2 cloud-save BFF — command ledger + projection",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(self), camera=(), microphone=()"
        return response
    app.include_router(health.router)
    app.include_router(guest.router)
    app.include_router(sync.router)
    app.include_router(world.router)
    app.include_router(auth.router)
    app.include_router(visits.router)
    return app


app = create_app()
