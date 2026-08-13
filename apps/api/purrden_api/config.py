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
    weather_base_url: str = "https://api.open-meteo.com/v1/forecast"
    public_url: str = "http://127.0.0.1:8000"
    keycloak_url: str = "http://127.0.0.1:8081"
    keycloak_realm: str = "purrden"
    keycloak_client_id: str = "purrden-web"
    keycloak_client_secret: str = ""
    cookie_secure: bool = False
    broker_url: str = "amqp://guest:guest@rabbitmq:5672//"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
