"""Lectura de la tabla CSV de términos → árbol de consulta.

Formato (una fila por concepto; los nombres de columna admiten español o inglés)::

    concepto,terminos,campo,operador
    tecnica,machine learning; deep learning; neural network*,title_abstract,AND
    dominio,radiology; medical imaging,title_abstract,AND
    exclusion,review; editorial,title,NOT

- Los términos de una fila (separados por ``;`` o ``|``) se unen con OR.
- Las filas AND se unen entre sí con AND.
- Las filas NOT se excluyen del resultado.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from biblio_search.query.model import And, Node, Or, SearchField, Term

_ALIASES = {
    "concept": "concept",
    "concepto": "concept",
    "terms": "terms",
    "terminos": "terms",
    "términos": "terms",
    "field": "field",
    "campo": "field",
    "operator": "operator",
    "operador": "operator",
}
_FIELDS = {
    "title": SearchField.TITLE,
    "titulo": SearchField.TITLE,
    "título": SearchField.TITLE,
    "title_abstract": SearchField.TITLE_ABSTRACT,
    "titulo_resumen": SearchField.TITLE_ABSTRACT,
    "título_resumen": SearchField.TITLE_ABSTRACT,
    "all": SearchField.ALL,
    "todo": SearchField.ALL,
}


class TableError(ValueError):
    """La tabla de términos no es válida."""


def parse_rows(rows: list[dict[str, str]]) -> Node:
    """Convierte filas (ya leídas) en un árbol de consulta."""
    include: list[Node] = []
    exclude: list[Node] = []
    for line, raw in enumerate(rows, start=2):  # línea 1 = cabecera
        row = {
            _ALIASES.get(k.strip().lower(), k): (v or "").strip()
            for k, v in raw.items()
        }
        terms_txt = row.get("terms", "")
        if not terms_txt:
            continue  # fila vacía
        field_txt = (row.get("field") or "title_abstract").lower()
        if field_txt not in _FIELDS:
            raise TableError(
                f"línea {line}: campo '{field_txt}' no válido "
                f"(usa: title, title_abstract, all)"
            )
        operator = (row.get("operator") or "AND").upper()
        if operator not in {"AND", "NOT"}:
            raise TableError(
                f"línea {line}: operador '{operator}' no válido (AND o NOT)"
            )
        terms = [t.strip() for t in re.split(r"[;|]", terms_txt) if t.strip()]
        group = Or(tuple(Term(t, _FIELDS[field_txt]) for t in terms))
        node: Node = group.children[0] if len(terms) == 1 else group
        (exclude if operator == "NOT" else include).append(node)
    if not include:
        raise TableError("la tabla no tiene ninguna fila AND con términos")
    if len(include) == 1 and not exclude:
        return include[0]
    return And(tuple(include), tuple(exclude))


def load_table(path: Path) -> Node:
    """Lee un CSV (separado por comas o punto y coma) y devuelve el árbol."""
    text = path.read_text(encoding="utf-8-sig")
    try:
        dialect = csv.Sniffer().sniff(text.splitlines()[0], delimiters=",;\t")
    except (csv.Error, IndexError) as exc:
        raise TableError(f"{path.name}: no se reconoce el formato CSV") from exc
    rows = list(csv.DictReader(text.splitlines(), dialect=dialect))
    missing = (
        {"terms"} - {_ALIASES.get(k.strip().lower(), k) for k in rows[0]}
        if rows
        else {"terms"}
    )
    if missing:
        raise TableError(f"{path.name}: falta la columna 'terminos' (o 'terms')")
    return parse_rows(rows)
