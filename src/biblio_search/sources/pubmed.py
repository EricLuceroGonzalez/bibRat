"""PubMed vía NCBI E-utilities (esearch + efetch)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from biblio_search.query.model import Node
from biblio_search.query.translate import to_pubmed
from biblio_search.records import Record
from biblio_search.sources.base import HttpSource, SearchResult

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
FETCH_BATCH = 200


def _text(el: ET.Element | None) -> str:
    return "".join(el.itertext()).strip() if el is not None else ""


def parse_article(article: ET.Element) -> Record:
    citation = article.find("MedlineCitation")
    assert citation is not None
    art = citation.find("Article")
    pmid = _text(citation.find("PMID"))
    authors: list[str] = []
    for au in art.findall("AuthorList/Author") if art is not None else []:
        if au.find("LastName") is not None:
            name = _text(au.find("LastName"))
            fore = _text(au.find("ForeName"))
            authors.append(f"{name}, {fore}" if fore else name)
        elif au.find("CollectiveName") is not None:
            authors.append(_text(au.find("CollectiveName")))
    abstract_parts = []
    for part in art.findall("Abstract/AbstractText") if art is not None else []:
        label = part.get("Label")
        text = _text(part)
        abstract_parts.append(f"{label}: {text}" if label else text)
    year_txt = (
        _text(art.find("Journal/JournalIssue/PubDate/Year")) if art is not None else ""
    )
    if not year_txt and art is not None:
        year_txt = _text(art.find("Journal/JournalIssue/PubDate/MedlineDate"))[:4]
    doi = next(
        (
            _text(i)
            for i in article.findall("PubmedData/ArticleIdList/ArticleId")
            if i.get("IdType") == "doi"
        ),
        None,
    )
    types = (
        [_text(t) for t in art.findall("PublicationTypeList/PublicationType")]
        if art is not None
        else []
    )
    return Record(
        source="pubmed",
        source_id=pmid,
        title=_text(art.find("ArticleTitle")) if art is not None else "",
        authors=authors,
        year=int(year_txt) if year_txt.isdigit() else None,
        venue=_text(art.find("Journal/Title")) if art is not None else None,
        doi=doi,
        abstract="\n".join(abstract_parts) or None,
        url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        doc_type=types[0] if types else None,
    )


class PubMedSource(HttpSource):
    name = "pubmed"

    @property
    def min_interval(self) -> float:  # type: ignore[override]
        return 0.11 if self.s.ncbi_api_key else 0.34

    def _common(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "tool": "biblio-search",
            "email": self.s.contact_email,
        }
        if self.s.ncbi_api_key:
            params["api_key"] = self.s.ncbi_api_key.get_secret_value()
        return params

    def search(
        self, node: Node, years: tuple[int | None, int | None], limit: int
    ) -> SearchResult:
        translation = to_pubmed(node)
        params: dict[str, Any] = {
            "db": "pubmed",
            "term": translation.query,
            "retmax": min(limit, 9999),
            "retmode": "json",
            "sort": "relevance",
        }
        start, end = years
        if start or end:
            params |= {
                "datetype": "pdat",
                "mindate": start or 1800,
                "maxdate": end or 3000,
            }
        result = SearchResult(
            self.name,
            translation.query,
            {k: v for k, v in params.items() if k != "term"},
            warnings=list(translation.warnings),
        )
        data = self._get(BASE + "esearch.fcgi", params | self._common()).json()
        result.raw.append(data)
        es = data["esearchresult"]
        result.total_reported = int(es.get("count", 0))
        if es.get("querytranslation"):
            result.params["querytranslation"] = es["querytranslation"]
        ids: list[str] = es.get("idlist", [])
        for i in range(0, len(ids), FETCH_BATCH):
            batch = ids[i : i + FETCH_BATCH]
            xml = self._get(
                BASE + "efetch.fcgi",
                {"db": "pubmed", "id": ",".join(batch), "retmode": "xml"}
                | self._common(),
                method="POST",
            ).text
            root = ET.fromstring(xml)
            result.records.extend(
                parse_article(a) for a in root.findall("PubmedArticle")
            )
        return result

    def check(self) -> str:
        data = self._get(
            BASE + "esearch.fcgi",
            {
                "db": "pubmed",
                "term": "systematic review[ti]",
                "retmax": 0,
                "retmode": "json",
            }
            | self._common(),
        ).json()
        key = "con API key" if self.s.ncbi_api_key else "sin API key (3 req/s)"
        return (
            f"PubMed OK, {key} ({data['esearchresult']['count']} resultados de prueba)"
        )
