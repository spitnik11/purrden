from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .config import get_settings
from .db import init_db
from .routes import guest, health, sync


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
    app.include_router(health.router)
    app.include_router(guest.router)
    app.include_router(sync.router)
    return app


app = create_app()
