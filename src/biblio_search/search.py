"""Orquestación: tabla → consultas → fuentes → deduplicado → archivos."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

import requests

from biblio_search.config import Settings
from biblio_search.dedupe import deduplicate
from biblio_search.export import write_bibtex, write_csv
from biblio_search.query.model import Node
from biblio_search.records import Record
from biblio_search.report import SearchReport
from biblio_search.sources.arxiv import ArxivSource
from biblio_search.sources.base import (
    HttpSource,
    SearchResult,
    SourceError,
    TransientError,
)
from biblio_search.sources.crossref import CrossrefSource
from biblio_search.sources.pubmed import PubMedSource
from biblio_search.sources.scopus import ScopusSource

logger = logging.getLogger(__name__)

SOURCES: dict[str, type[HttpSource]] = {
    "scopus": ScopusSource,
    "pubmed": PubMedSource,
    "crossref": CrossrefSource,
    "arxiv": ArxivSource,
}


def build_sources(names: list[str], settings: Settings) -> list[HttpSource]:
    unknown = set(names) - SOURCES.keys()
    if unknown:
        raise ValueError(f"fuentes desconocidas: {', '.join(sorted(unknown))}")
    session = requests.Session()
    return [SOURCES[n](settings, session) for n in names]


def default_out_dir(table: Path) -> Path:
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    return Path("searches") / f"{stamp}_{table.stem}"


def run_search(
    node: Node,
    table: Path,
    sources: list[HttpSource],
    out_dir: Path,
    years: tuple[int | None, int | None],
    limit: int,
) -> SearchReport:
    """Ejecuta la búsqueda en todas las fuentes y escribe los resultados.

    Un fallo en una fuente no detiene las demás: queda registrado en el informe.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "raw").mkdir(exist_ok=True)
    report = SearchReport(table, years)
    all_records: list[Record] = []
    for source in sources:
        logger.info("Buscando en %s…", source.name)
        try:
            result = source.search(node, years, limit)
        except (
            SourceError,
            TransientError,
            requests.RequestException,
            ValueError,
        ) as exc:
            logger.error("%s falló: %s", source.name, exc)
            result = SearchResult(source.name, "", {}, error=str(exc))
        report.results.append(result)
        all_records.extend(result.records)
        _save_raw(out_dir / "raw", result)
        logger.info(
            "%s: %d recuperados (total según la fuente: %d)",
            source.name,
            len(result.records),
            result.total_reported,
        )
    unique, removed = deduplicate(all_records)
    report.duplicates_removed, report.unique_records = removed, len(unique)
    write_csv(unique, out_dir / "results.csv")
    write_bibtex(unique, out_dir / "results.bib")
    report.write(out_dir)
    return report


def _save_raw(raw_dir: Path, result: SearchResult) -> None:
    if not result.raw:
        return
    if all(isinstance(r, str) for r in result.raw):  # arXiv: XML
        for i, page in enumerate(result.raw):
            (raw_dir / f"{result.source}_{i:03d}.xml").write_text(
                page, encoding="utf-8"
            )
    else:
        (raw_dir / f"{result.source}.json").write_text(
            json.dumps(result.raw, ensure_ascii=False, indent=1), encoding="utf-8"
        )
