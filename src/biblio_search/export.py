"""Exportación a CSV (para cribar) y BibTeX (para Zotero / LaTeX)."""

from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path

from biblio_search.records import Record

CSV_COLUMNS = [
    "id",
    "title",
    "authors",
    "year",
    "venue",
    "doi",
    "url",
    "doc_type",
    "sources",
    "searches",
    "abstract",
    "decision",
    "notes",
]


def write_csv(records: list[Record], path: Path) -> None:
    """CSV con columnas vacías ``decision`` y ``notes`` para el cribado.

    Se escribe en UTF-8 con BOM para que Excel lo abra con acentos correctos.
    """
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for i, r in enumerate(records, start=1):
            writer.writerow(
                {
                    "id": i,
                    "title": r.title,
                    "authors": "; ".join(r.authors),
                    "year": r.year or "",
                    "venue": r.venue or "",
                    "doi": r.doi or "",
                    "url": r.url or "",
                    "doc_type": r.doc_type or "",
                    "sources": "; ".join(r.sources),
                    "searches": "; ".join(r.searches),
                    "abstract": r.abstract or "",
                    "decision": r.decision,
                    "notes": r.notes,
                }
            )


_BIB_ESCAPE = str.maketrans({c: f"\\{c}" for c in "&%$#_{}"})


def _bib(value: str) -> str:
    return value.translate(_BIB_ESCAPE)


def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def citation_key(record: Record, used: set[str]) -> str:
    """``apellidoAAAApalabra``, p. ej. ``he2016deep``; únicas añadiendo a, b, c…"""
    family = record.authors[0].split(",")[0] if record.authors else "anon"
    family = re.sub(r"[^a-z]", "", _ascii(family).lower()) or "anon"
    words = [
        w for w in re.findall(r"[a-z]+", _ascii(record.title).lower()) if len(w) > 3
    ]
    base = f"{family}{record.year or 'nd'}{words[0] if words else ''}"
    key, suffix = base, 0
    while key in used:
        key = base + chr(ord("a") + suffix)
        suffix += 1
    used.add(key)
    return key


def _entry_type(record: Record) -> str:
    kind = (record.doc_type or "").lower()
    if record.source == "arxiv" and record.venue in {None, "arXiv"}:
        return "misc"
    if "conference" in kind or "proceedings" in kind:
        return "inproceedings"
    if "chapter" in kind:
        return "incollection"
    if "book" in kind:
        return "book"
    return "article"


def write_bibtex(records: list[Record], path: Path) -> None:
    used: set[str] = set()
    chunks = []
    for r in records:
        etype = _entry_type(r)
        fields = {
            "title": "{" + _bib(r.title) + "}",  # doble llave: conserva mayúsculas
            "author": " and ".join(_bib(a) for a in r.authors),
            "year": str(r.year) if r.year else "",
            ("booktitle" if etype == "inproceedings" else "journal"): _bib(
                r.venue or ""
            ),
            "doi": r.doi or "",
            "url": r.url or "",
            "abstract": _bib(r.abstract or ""),
            "note": "Fuentes: " + ", ".join(r.sources),
        }
        if etype == "misc" and r.source == "arxiv":
            fields |= {"eprint": r.source_id, "archiveprefix": "arXiv"}
            fields.pop("journal", None)
        body = ",\n".join(f"  {k} = {{{v}}}" for k, v in fields.items() if v)
        chunks.append(f"@{etype}{{{citation_key(r, used)},\n{body}\n}}\n")
    path.write_text("\n".join(chunks), encoding="utf-8")
