from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.models import EMBEDDING_MODEL


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
    migration_database_url: SecretStr | None = None
    google_client_id: SecretStr
    google_client_secret: SecretStr
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"
    google_drive_redirect_uri: str = "http://localhost:8000/drive/callback"
    session_secret: SecretStr
    session_https_only: bool = False
    session_same_site: Literal["lax", "strict", "none"] = "lax"
    web_origin: str = "http://localhost:3000"
    waha_base_url: str = "http://localhost:3100"
    waha_api_key: SecretStr | None = None
    # Public URL WAHA POSTs events to (e.g. https://api.example.com/whatsapp/webhooks).
    # Unset disables webhook registration on new sessions — poll-only mode.
    waha_webhook_url: str | None = None
    # Shared secret sent by WAHA as X-Webhook-Token and verified on receipt.
    waha_webhook_secret: SecretStr | None = None
    # Self-hosted encoder; must emit EMBEDDING_DIMENSIONS-wide vectors.
    embedding_model: str = EMBEDDING_MODEL
    embedding_device: str | None = None
    embedding_batch_size: int = 32
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-5-mini"
    openai_timeout_seconds: float = 60.0
    analysis_config_version: str = "core-v1"
    analysis_max_documents: int = 500
    analysis_max_chunks_per_document: int = 60
    analysis_max_candidates_per_document: int = 30
    analysis_max_candidates_per_run: int = 200
    retrieval_limit_per_query: int = 8
    retrieval_max_chunks: int = 40
    retrieval_max_context_chars: int = 50000

    @staticmethod
    def _psycopg_url(value: SecretStr) -> str:
        url = value.get_secret_value()
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+psycopg://", 1)
        return url

    def runtime_url(self) -> str:
        return self._psycopg_url(self.database_url)

    def migration_url(self) -> str:
        return self._psycopg_url(self.migration_database_url or self.database_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
