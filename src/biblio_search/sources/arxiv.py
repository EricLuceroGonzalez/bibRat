"""arXiv API (Atom). Límite: 1 petición cada 3 s."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from biblio_search.query.model import Node
from biblio_search.query.translate import to_arxiv
from biblio_search.records import Record
from biblio_search.sources.base import HttpSource, SearchResult

URL = "https://export.arxiv.org/api/query"
PAGE_SIZE = 100
NS = {
    "a": "http://www.w3.org/2005/Atom",
    "os": "http://a9.com/-/spec/opensearch/1.1/",
    "arxiv": "http://arxiv.org/schemas/atom",
}


def _t(el: ET.Element | None) -> str:
    return re.sub(r"\s+", " ", el.text or "").strip() if el is not None else ""


def _last_first(name: str) -> str:
    parts = name.split()
    return f"{parts[-1]}, {' '.join(parts[:-1])}" if len(parts) > 1 else name


def parse_entry(entry: ET.Element) -> Record:
    url = _t(entry.find("a:id", NS))
    arxiv_id = re.sub(r"v\d+$", "", url.rsplit("/abs/", 1)[-1])
    published = _t(entry.find("a:published", NS))
    category = entry.find("arxiv:primary_category", NS)
    return Record(
        source="arxiv",
        source_id=arxiv_id,
        title=_t(entry.find("a:title", NS)),
        authors=[
            _last_first(_t(a.find("a:name", NS))) for a in entry.findall("a:author", NS)
        ],
        year=int(published[:4]) if published[:4].isdigit() else None,
        venue=_t(entry.find("arxiv:journal_ref", NS)) or "arXiv",
        doi=_t(entry.find("arxiv:doi", NS)) or f"10.48550/arXiv.{arxiv_id}",
        abstract=_t(entry.find("a:summary", NS)) or None,
        url=url,
        doc_type=category.get("term") if category is not None else "preprint",
    )


class ArxivSource(HttpSource):
    name = "arxiv"
    min_interval = 3.1

    def search(
        self, node: Node, years: tuple[int | None, int | None], limit: int
    ) -> SearchResult:
        translation = to_arxiv(node, years)
        params = {
            "search_query": translation.query,
            "max_results": PAGE_SIZE,
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
        result = SearchResult(
            self.name,
            translation.query,
            {k: v for k, v in params.items() if k != "search_query"},
            warnings=list(translation.warnings),
        )
        start = 0
        while True:
            xml = self._get(URL, params | {"start": start}).text
            result.raw.append(xml)
            root = ET.fromstring(xml)
            result.total_reported = int(_t(root.find("os:totalResults", NS)) or 0)
            entries = root.findall("a:entry", NS)
            result.records.extend(parse_entry(e) for e in entries)
            start += PAGE_SIZE
            if not entries or start >= min(result.total_reported, limit):
                break
        result.records = result.records[:limit]
        return result

    def check(self) -> str:
        xml = self._get(URL, {"search_query": "ti:review", "max_results": 0}).text
        total = _t(ET.fromstring(xml).find("os:totalResults", NS))
        return f"arXiv OK ({total} resultados de prueba)"
