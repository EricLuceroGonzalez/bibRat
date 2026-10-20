"""Registro bibliográfico normalizado, común a todas las fuentes."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Record:
    source: str  # scopus | pubmed | crossref | arxiv
    source_id: str  # EID, PMID, DOI o arXiv id
    title: str
    authors: list[str] = field(default_factory=list)  # "Apellido, Nombre"
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    abstract: str | None = None
    url: str | None = None
    doc_type: str | None = None
    sources: list[str] = field(default_factory=list)  # tras deduplicar
    # Cribado (se conservan al fusionar búsquedas con ``merge``)
    decision: str = ""
    notes: str = ""
    searches: list[str] = field(default_factory=list)  # carpetas de búsqueda de origen

    def __post_init__(self) -> None:
        if self.doi:
            self.doi = self.doi.strip().lower().removeprefix("https://doi.org/")
        if not self.sources:
            self.sources = [self.source]
