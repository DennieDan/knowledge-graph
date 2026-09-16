from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


API_ROOT = Path(__file__).resolve().parents[1]
if API_ROOT.name == "dist":
    API_ROOT = API_ROOT.parent


class Settings(BaseSettings):
    # Resolve from this module, including when running the built dist/app package.
    model_config = SettingsConfigDict(
        env_file=API_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    database_url: SecretStr
    google_client_id: SecretStr
    google_client_secret: SecretStr
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"
    session_secret: SecretStr
    web_origin: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
