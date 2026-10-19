"""Scopus Search API (Elsevier). Requiere API key y acceso institucional (VPN)."""

from __future__ import annotations

import logging
from typing import Any

from biblio_search.query.model import Node
from biblio_search.query.translate import to_scopus
from biblio_search.records import Record
from biblio_search.sources.base import HttpSource, SearchResult, SourceError

logger = logging.getLogger(__name__)

URL = "https://api.elsevier.com/content/search/scopus"
PAGE_SIZE = 25  # máximo de la vista COMPLETE


def _year(cover_date: str | None) -> int | None:
    return int(cover_date[:4]) if cover_date and cover_date[:4].isdigit() else None


def parse_entry(entry: dict[str, Any]) -> Record:
    authors = [
        f"{a.get('surname', '')}, {a.get('given-name', '')}".strip(", ")
        if a.get("surname")
        else a.get("authname", "")
        for a in entry.get("author") or []
    ]
    if not authors and entry.get("dc:creator"):
        authors = [entry["dc:creator"]]  # vista STANDARD: solo el primer autor
    link = next(
        (lk.get("@href") for lk in entry.get("link", []) if lk.get("@ref") == "scopus"),
        None,
    )
    return Record(
        source="scopus",
        source_id=entry.get("eid") or entry.get("dc:identifier", ""),
        title=entry.get("dc:title", ""),
        authors=authors,
        year=_year(entry.get("prism:coverDate")),
        venue=entry.get("prism:publicationName"),
        doi=entry.get("prism:doi"),
        abstract=entry.get("dc:description"),
        url=link,
        doc_type=entry.get("subtypeDescription"),
    )


class ScopusSource(HttpSource):
    name = "scopus"
    min_interval = 0.15

    def _headers(self) -> dict[str, str]:
        if not self.s.scopus_api_key:
            raise SourceError("scopus: falta SCOPUS_API_KEY")
        headers = {
            "X-ELS-APIKey": self.s.scopus_api_key.get_secret_value(),
            "Accept": "application/json",
        }
        if self.s.scopus_insttoken:
            headers["X-ELS-Insttoken"] = self.s.scopus_insttoken.get_secret_value()
        return headers

    def _page(self, query: str, start: int, view: str) -> dict[str, Any]:
        params = {"query": query, "start": start, "count": PAGE_SIZE, "view": view}
        data: dict[str, Any] = self._get(URL, params, self._headers()).json()
        return data["search-results"]

    def search(
        self, node: Node, years: tuple[int | None, int | None], limit: int
    ) -> SearchResult:
        translation = to_scopus(node, years)
        view = self.s.scopus_view
        result = SearchResult(
            self.name,
            translation.query,
            {"view": view, "count": PAGE_SIZE},
            warnings=list(translation.warnings),
        )
        start = 0
        while True:
            try:
                page = self._page(translation.query, start, view)
            except SourceError as exc:
                if (
                    view == "COMPLETE"
                    and start == 0
                    and ("401" in str(exc) or "403" in str(exc))
                ):
                    view = "STANDARD"
                    result.params["view"] = view
                    result.warnings.append(
                        "Scopus no autorizó la vista COMPLETE: se usó STANDARD "
                        "(sin abstracts y solo con el primer autor)."
                    )
                    continue
                raise
            result.raw.append(page)
            result.total_reported = int(page.get("opensearch:totalResults", 0))
            entries = [e for e in page.get("entry", []) if "error" not in e]
            result.records.extend(parse_entry(e) for e in entries)
            start += PAGE_SIZE
            if not entries or start >= min(result.total_reported, limit):
                break
        result.records = result.records[:limit]
        return result

    def check(self) -> str:
        page = self._page("TITLE(systematic review)", 0, "STANDARD")
        total = page.get("opensearch:totalResults", "?")
        return f"Scopus OK ({total} resultados de prueba)"
