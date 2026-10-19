"""Fusión de registros duplicados entre fuentes."""

from __future__ import annotations

from dataclasses import fields

from biblio_search.query.matcher import normalize
from biblio_search.records import Record

# Orden de preferencia cuando dos fuentes tienen el mismo artículo.
SOURCE_PRIORITY = ["scopus", "pubmed", "crossref", "arxiv"]


def _keys(record: Record) -> list[str]:
    keys = []
    if record.doi:
        keys.append(f"doi:{record.doi}")
    title = normalize(record.title).replace("*", "")
    if len(title) > 20:
        keys.append(f"title:{title}:{record.year or ''}")
    return keys


def _merge(base: Record, other: Record) -> None:
    """Completa en ``base`` los campos vacíos con los de ``other``."""
    for f in fields(Record):
        if f.name in {"source", "source_id", "sources"}:
            continue
        if not getattr(base, f.name) and getattr(other, f.name):
            setattr(base, f.name, getattr(other, f.name))
    for src in other.sources:
        if src not in base.sources:
            base.sources.append(src)


def deduplicate(records: list[Record]) -> tuple[list[Record], int]:
    """Devuelve (registros únicos, número de duplicados eliminados).

    Dos registros son el mismo artículo si comparten DOI, o si comparten título
    normalizado y año. Se conserva el de la fuente con más prioridad y se
    completan sus campos vacíos (p. ej. el abstract) con los de las demás.
    """
    ordered = sorted(
        records,
        key=lambda r: (
            SOURCE_PRIORITY.index(r.source) if r.source in SOURCE_PRIORITY else 99
        ),
    )
    unique: list[Record] = []
    index: dict[str, Record] = {}
    for record in ordered:
        match = next((index[k] for k in _keys(record) if k in index), None)
        if match is None:
            unique.append(record)
            match = record
        else:
            _merge(match, record)
        for key in _keys(match):
            index.setdefault(key, match)
    return unique, len(records) - len(unique)
