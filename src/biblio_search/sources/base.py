"""Base común: sesión HTTP, límite de peticiones y reintentos."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import requests
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from biblio_search import __version__
from biblio_search.config import Settings
from biblio_search.query.model import Node
from biblio_search.records import Record

logger = logging.getLogger(__name__)


class SourceError(Exception):
    """Error no recuperable de una fuente (credenciales, consulta inválida…)."""


class TransientError(Exception):
    """429 / 5xx: se reintenta."""

    def __init__(self, status: int, retry_after: float | None = None) -> None:
        super().__init__(f"HTTP {status}")
        self.retry_after = retry_after


@dataclass
class SearchResult:
    """Resultado de buscar en una fuente, con todo lo necesario para el informe."""

    source: str
    query: str
    params: dict[str, Any]
    total_reported: int = 0
    records: list[Record] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    raw: list[Any] = field(default_factory=list)  # respuestas tal cual (auditoría)


def _wait(state: RetryCallState) -> float:
    exc = state.outcome.exception() if state.outcome else None
    if isinstance(exc, TransientError) and exc.retry_after:
        return min(exc.retry_after, 60.0)
    return wait_exponential_jitter(initial=2, max=30)(state)


class HttpSource:
    """Cliente base. Las subclases definen ``name``, ``min_interval`` y ``search``."""

    name = "base"
    min_interval = 0.0  # segundos mínimos entre peticiones

    def __init__(self, settings: Settings, session: requests.Session | None = None):
        self.s = settings
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = (
            f"BiblioSearch/{__version__} (mailto:{settings.contact_email})"
        )
        self._last = 0.0
        self._lock = threading.Lock()
        self._get = retry(
            retry=retry_if_exception_type(
                (TransientError, requests.ConnectionError, requests.Timeout)
            ),
            stop=stop_after_attempt(settings.http_max_attempts),
            wait=_wait,
            before_sleep=lambda st: logger.warning(
                "%s: reintento %d (%s)",
                self.name,
                st.attempt_number,
                st.outcome.exception() if st.outcome else "",
            ),
            reraise=True,
        )(self._get_once)

    def _throttle(self) -> None:
        with self._lock:
            delay = self.min_interval - (time.monotonic() - self._last)
            if delay > 0:
                time.sleep(delay)
            self._last = time.monotonic()

    def _get_once(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        method: str = "GET",
    ) -> requests.Response:
        self._throttle()
        if method == "POST":
            response = self.session.post(
                url, data=params, headers=headers, timeout=self.s.http_timeout
            )
        else:
            response = self.session.get(
                url, params=params, headers=headers, timeout=self.s.http_timeout
            )
        if response.status_code == 429 or response.status_code >= 500:
            retry_after = response.headers.get("Retry-After")
            raise TransientError(
                response.status_code,
                float(retry_after) if retry_after and retry_after.isdigit() else None,
            )
        if response.status_code >= 400:
            raise SourceError(
                f"{self.name}: HTTP {response.status_code}: {response.text[:300]}"
            )
        return response

    def search(
        self, node: Node, years: tuple[int | None, int | None], limit: int
    ) -> SearchResult:
        raise NotImplementedError

    def check(self) -> str:
        """Comprobación rápida de acceso; devuelve un texto para mostrar."""
        raise NotImplementedError
