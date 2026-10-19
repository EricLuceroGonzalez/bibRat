"""Crossref REST API. Sin booleanos: texto libre + filtro booleano local."""

from __future__ import annotations

import html
import re
from typing import Any

from biblio_search.query.matcher import matches
from biblio_search.query.model import Node
from biblio_search.query.translate import to_crossref
from biblio_search.records import Record
from biblio_search.sources.base import HttpSource, SearchResult

URL = "https://api.crossref.org/works"
PAGE_SIZE = 200
SELECT = "DOI,title,author,issued,container-title,abstract,type,URL"


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    return (
        re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text))).strip()
        or None
    )


def parse_item(item: dict[str, Any]) -> Record:
    authors = [
        f"{a['family']}, {a.get('given', '')}".strip(", ")
        if a.get("family")
        else a.get("name", "")
        for a in item.get("author", [])
    ]
    parts = (item.get("issued") or {}).get("date-parts") or [[None]]
    year = parts[0][0] if parts and parts[0] else None
    titles = item.get("title") or [""]
    venues = item.get("container-title") or [None]
    return Record(
        source="crossref",
        source_id=item.get("DOI", ""),
        title=_clean(titles[0]) or "",
        authors=authors,
        year=int(year) if year else None,
        venue=venues[0],
        doi=item.get("DOI"),
        abstract=_clean(item.get("abstract")),
        url=item.get("URL"),
        doc_type=item.get("type"),
    )


class CrossrefSource(HttpSource):
    name = "crossref"
    min_interval = 0.1

    def search(
        self, node: Node, years: tuple[int | None, int | None], limit: int
    ) -> SearchResult:
        translation = to_crossref(node)
        filters = []
        start, end = years
        if start:
            filters.append(f"from-pub-date:{start}")
        if end:
            filters.append(f"until-pub-date:{end}")
        params: dict[str, Any] = {
            "query.bibliographic": translation.query,
            "rows": PAGE_SIZE,
            "select": SELECT,
            "mailto": self.s.contact_email,
        }
        if filters:
            params["filter"] = ",".join(filters)
        result = SearchResult(
            self.name,
            translation.query,
            {
                k: v
                for k, v in params.items()
                if k not in {"query.bibliographic", "mailto"}
            }
            | {"max_scan": self.s.crossref_max_scan},
            warnings=list(translation.warnings),
        )
        cursor, scanned, api_total = "*", 0, 0
        while scanned < self.s.crossref_max_scan and len(result.records) < limit:
            message = self._get(URL, params | {"cursor": cursor}).json()["message"]
            items = message.get("items", [])
            api_total = message.get("total-results", 0)
            result.raw.append(
                {"next-cursor": message.get("next-cursor"), "count": len(items)}
            )
            if not items:
                break
            scanned += len(items)
            for item in items:
                record = parse_item(item)
                if matches(node, record.title, record.abstract or ""):
                    result.records.append(record)
            cursor = message.get("next-cursor", "")
            if not cursor:
                break
        result.records = result.records[:limit]
        result.total_reported = len(result.records)
        result.warnings.append(
            f"Crossref: {api_total} coincidencias por relevancia; se revisaron las "
            f"primeras {scanned} y {len(result.records)} cumplen la expresión booleana."
        )
        return result

    def check(self) -> str:
        message = self._get(
            URL,
            {
                "query.bibliographic": "systematic review",
                "rows": 0,
                "mailto": self.s.contact_email,
            },
        ).json()["message"]
        return f"Crossref OK ({message.get('total-results')} resultados de prueba)"
