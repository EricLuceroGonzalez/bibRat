"""Lectura de los ``results.csv`` generados por ``search`` (o por ``merge``)."""

from __future__ import annotations

import csv
from pathlib import Path

from biblio_search.records import Record


def resolve_results(
    paths: list[Path], default_root: Path = Path("searches")
) -> list[Path]:
    """Convierte carpetas de búsqueda y archivos en una lista de ``results.csv``.

    Sin rutas, usa todas las ``searches/*/results.csv``.
    """
    if not paths:
        return sorted(default_root.glob("*/results.csv"))
    found: list[Path] = []
    for path in paths:
        if path.is_dir():
            candidate = path / "results.csv"
            if candidate.exists():
                found.append(candidate)
            else:
                found.extend(sorted(path.glob("*/results.csv")))
        elif path.suffix.lower() == ".csv":
            found.append(path)
    return found


def _split(value: str) -> list[str]:
    return [v.strip() for v in value.split(";") if v.strip()]


def read_results(path: Path, label: str | None = None) -> list[Record]:
    """Lee un ``results.csv``. ``label`` identifica la búsqueda de origen."""
    label = label or path.parent.name
    records = []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            sources = _split(row.get("sources", "")) or ["desconocida"]
            year = (row.get("year") or "").strip()
            records.append(
                Record(
                    source=sources[0],
                    source_id=row.get("doi") or row.get("url") or "",
                    title=row.get("title", ""),
                    authors=_split(row.get("authors", "")),
                    year=int(year) if year.isdigit() else None,
                    venue=row.get("venue") or None,
                    doi=row.get("doi") or None,
                    abstract=row.get("abstract") or None,
                    url=row.get("url") or None,
                    doc_type=row.get("doc_type") or None,
                    sources=sources,
                    decision=row.get("decision", "").strip(),
                    notes=row.get("notes", "").strip(),
                    searches=_split(row.get("searches", "")) or [label],
                )
            )
    return records
