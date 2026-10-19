"""Configuración desde variables de entorno o ``.env``."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    contact_email: str
    scopus_api_key: SecretStr | None = None
    scopus_insttoken: SecretStr | None = None
    scopus_view: Literal["COMPLETE", "STANDARD"] = "COMPLETE"
    ncbi_api_key: SecretStr | None = None

    http_timeout: float = 30.0
    http_max_attempts: int = Field(default=4, ge=1)
    max_results_per_source: int = Field(default=1000, ge=1)
    crossref_max_scan: int = Field(default=2000, ge=1)

    log_dir: str = "logs"
    log_level: str = "INFO"

    @field_validator("contact_email")
    @classmethod
    def _email(cls, value: str) -> str:
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value):
            raise ValueError(f"CONTACT_EMAIL no parece un email válido: {value!r}")
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
