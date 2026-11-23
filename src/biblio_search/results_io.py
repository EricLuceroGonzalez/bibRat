"""Lectura de los ``results.csv`` generados por ``search`` (o por ``merge``).

Los CSV pueden haber pasado por Excel para cribarlos (columnas ``decision`` y
``notes``). Excel en español los guarda separados por ``;``, a veces en
Windows-1252 y con filas vacías al final. Aquí se detecta todo eso. Si el archivo
no tiene la columna ``title``, se detiene con un error claro en lugar de
producir filas en blanco.
"""

from __future__ import annotations

import csv
import io
import logging
from pathlib import Path

from biblio_search.records import Record

logger = logging.getLogger(__name__)

# Variantes de cabecera aceptadas (sin distinguir mayúsculas) → nombre interno
_ALIASES = {
    "title": "title",
    "título": "title",
    "titulo": "title",
    "authors": "authors",
    "autores": "authors",
    "year": "year",
    "año": "year",
    "venue": "venue",
    "doi": "doi",
    "url": "url",
    "link": "url",
    "doc_type": "doc_type",
    "sources": "sources",
    "fuentes": "sources",
    "searches": "searches",
    "abstract": "abstract",
    "resumen": "abstract",
    "decision": "decision",
    "decisión": "decision",
    "notes": "notes",
    "notas": "notes",
}


class ResultsFormatError(ValueError):
    """El archivo no tiene el formato de un ``results.csv``."""


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


def _read_text(path: Path) -> str:
    """UTF-8 (con o sin BOM); si falla, Windows-1252 (CSV guardado por Excel)."""
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252")


def _delimiter(header: str) -> str:
    """Separador de la cabecera: el que más aparece entre ``,`` ``;`` y tabulador."""
    return max(",;\t", key=header.count)


def read_results(path: Path, label: str | None = None) -> list[Record]:
    """Lee un ``results.csv``. ``label`` identifica la búsqueda de origen.

    Raises:
        ResultsFormatError: si falta la columna ``title``.
    """
    label = label or path.parent.name
    text = _read_text(path)
    header = text.split("\n", 1)[0]
    sep = _delimiter(header)
    if sep != ",":
        logger.warning(
            "%s: separado por %r (¿guardado desde Excel?); se lee igualmente",
            path,
            sep,
        )
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=sep)
    try:
        names = next(reader)
    except StopIteration:
        return []
    columns = {
        _ALIASES[n.strip().casefold()]: i
        for i, n in enumerate(names)
        if n.strip().casefold() in _ALIASES
    }
    if "title" not in columns:
        raise ResultsFormatError(
            f"{path} no parece un results.csv: no tiene columna 'title'. "
            f"Columnas encontradas: {names[:12]}"
        )

    records, skipped = [], 0
    for row in reader:
        if not any(cell.strip() for cell in row):
            skipped += 1  # filas vacías (p. ej. ;;;;; al final, típico de Excel)
            continue

        def get(name: str, row: list[str] = row) -> str:
            i = columns.get(name)
            return row[i].strip() if i is not None and i < len(row) else ""

        sources = _split(get("sources")) or ["desconocida"]
        year = get("year")
        if year.endswith(".0"):  # Excel convierte 2024 en 2024.0 a veces
            year = year[:-2]
        records.append(
            Record(
                source=sources[0],
                source_id=get("doi") or get("url") or "",
                title=get("title"),
                authors=_split(get("authors")),
                year=int(year) if year.isdigit() else None,
                venue=get("venue") or None,
                doi=get("doi") or None,
                abstract=get("abstract") or None,
                url=get("url") or None,
                doc_type=get("doc_type") or None,
                sources=sources,
                decision=get("decision"),
                notes=get("notes"),
                searches=_split(get("searches")) or [label],
            )
        )
    if skipped:
        logger.warning("%s: %d filas vacías ignoradas", path, skipped)
    untitled = sum(not r.title for r in records)
    if untitled:
        logger.warning("%s: %d registros sin título", path, untitled)
    return records
