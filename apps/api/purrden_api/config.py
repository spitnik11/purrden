from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "purrden-api"
    env: str = "dev"
    # Override with DATABASE_URL. Compose uses Postgres; tests use sqlite memory.
    database_url: str = "sqlite+pysqlite:///:memory:"
    # Production-ish default for compose:
    # postgresql+psycopg://purrden:purrden@postgres:5432/purrden
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:8080"
    # Guest claim / spawn secrets — rotate in real deploy; never ship real secrets.
    guest_claim_pepper: str = "dev-only-guest-pepper-change-me"
    spawn_hmac_secret_hex: str = "a3f1c09b5e7d42118826aa0134bf90cd"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
