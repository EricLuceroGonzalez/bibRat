"""Fixtures compartidas."""

from __future__ import annotations

import pytest

from biblio_search.config import Settings


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        contact_email="test@example.org",
        scopus_api_key="KEY",  # type: ignore[arg-type]
        http_max_attempts=2,
        log_dir=str(tmp_path / "logs"),
    )


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Sin esperas reales entre peticiones ni en los reintentos."""
    monkeypatch.setattr("biblio_search.sources.base.time.sleep", lambda s: None)
    monkeypatch.setattr("biblio_search.sources.base._wait", lambda st: 0)
