from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine():
    settings = get_settings()
    url = settings.database_url
    connect_args: dict = {}
    kwargs: dict = {"future": True}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        # Keep a single shared in-memory DB across connections (tests + TestClient).
        if ":memory:" in url:
            kwargs["poolclass"] = StaticPool
    kwargs["connect_args"] = connect_args
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_fk(dbapi_conn, _):  # noqa: ANN001
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables (dev/test). Prefer Alembic migrations in real deploys."""
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
