"""Traducción del árbol de consulta a la sintaxis de cada fuente.

Cada traductor devuelve la cadena de consulta y una lista de avisos sobre lo que
no se pudo expresar fielmente (que se incluyen en el informe de la búsqueda).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from biblio_search.query.model import Node, Or, SearchField, Term, positive_terms


@dataclass
class Translation:
    query: str
    warnings: list[str] = field(default_factory=list)


def _quote(term: Term) -> str:
    text = term.text.strip()
    return f'"{text}"' if term.is_phrase else text


def _join(parts: list[str], op: str) -> str:
    return parts[0] if len(parts) == 1 else "(" + f" {op} ".join(parts) + ")"


# ------------------------------------------------------------------- Scopus
_SCOPUS_FIELDS = {
    SearchField.TITLE: "TITLE",
    SearchField.TITLE_ABSTRACT: "TITLE-ABS-KEY",
    SearchField.ALL: "ALL",
}


def _scopus(node: Node) -> str:
    if isinstance(node, Term):
        return f"{_SCOPUS_FIELDS[node.field]}({_quote(node)})"
    if isinstance(node, Or):
        return _join([_scopus(c) for c in node.children], "OR")
    query = _join([_scopus(c) for c in node.children], "AND")
    if node.exclude:
        # En Scopus AND NOT se evalúa al final: hay que agrupar para que lo que
        # venga después (p. ej. PUBYEAR) no quede dentro de la exclusión.
        excluded = _join([_scopus(e) for e in node.exclude], "OR")
        query = f"({query} AND NOT {excluded})"
    return query


def to_scopus(node: Node, years: tuple[int | None, int | None]) -> Translation:
    query = _scopus(node)
    start, end = years
    if start:
        query += f" AND PUBYEAR > {start - 1}"
    if end:
        query += f" AND PUBYEAR < {end + 1}"
    return Translation(query)


# ------------------------------------------------------------------- PubMed
_PUBMED_FIELDS = {
    SearchField.TITLE: "[ti]",
    SearchField.TITLE_ABSTRACT: "[tiab]",
    SearchField.ALL: "[all]",
}


def _pubmed(node: Node) -> str:
    if isinstance(node, Term):
        return f"{_quote(node)}{_PUBMED_FIELDS[node.field]}"
    if isinstance(node, Or):
        return _join([_pubmed(c) for c in node.children], "OR")
    query = _join([_pubmed(c) for c in node.children], "AND")
    if node.exclude:
        excluded = _join([_pubmed(e) for e in node.exclude], "OR")
        query = f"({query} NOT {excluded})"
    return query


def to_pubmed(node: Node) -> Translation:
    """El rango de años va como parámetros (mindate/maxdate), no en la consulta."""
    return Translation(_pubmed(node))


# -------------------------------------------------------------------- arXiv
def _arxiv_term(term: Term, warnings: list[str]) -> str:
    text = term.text.strip()
    if term.has_wildcard:
        warnings.append(
            f"arXiv no admite truncamiento: '{text}' se busca sin '*' "
            "(solo coincide la palabra exacta)"
        )
        text = text.replace("*", "")
    value = f'"{text}"' if " " in text else text
    if term.field is SearchField.TITLE:
        return f"ti:{value}"
    if term.field is SearchField.ALL:
        return f"all:{value}"
    return f"(ti:{value} OR abs:{value})"


def _arxiv(node: Node, warnings: list[str]) -> str:
    if isinstance(node, Term):
        return _arxiv_term(node, warnings)
    if isinstance(node, Or):
        return _join([_arxiv(c, warnings) for c in node.children], "OR")
    query = _join([_arxiv(c, warnings) for c in node.children], "AND")
    if node.exclude:
        excluded = _join([_arxiv(e, warnings) for e in node.exclude], "OR")
        query = f"({query} ANDNOT {excluded})"
    return query


def to_arxiv(node: Node, years: tuple[int | None, int | None]) -> Translation:
    warnings: list[str] = []
    query = _arxiv(node, warnings)
    start, end = years
    if start or end:
        lo = f"{start or 1991}01010000"
        hi = f"{end or 2100}12312359"
        query = f"({query}) AND submittedDate:[{lo} TO {hi}]"
    return Translation(query, sorted(set(warnings)))


# ------------------------------------------------------------------ Crossref
def to_crossref(node: Node) -> Translation:
    """Crossref no admite booleanos: texto libre + filtro booleano local."""
    words = [t.text.replace("*", "").strip() for t in positive_terms(node)]
    return Translation(
        " ".join(dict.fromkeys(words)),
        [
            "Crossref no admite operadores booleanos: se envían los términos como "
            "texto libre y la expresión booleana se aplica localmente sobre título "
            "y abstract (muchos registros de Crossref no tienen abstract)."
        ],
    )


def _with_years_note(
    translation: Translation, years: tuple[int | None, int | None]
) -> Translation:
    if years[0] or years[1]:
        translation.warnings.append(
            f"Años {years[0] or '…'}–{years[1] or '…'}: se envían como parámetros "
            "datetype=pdat, mindate y maxdate (no aparecen en la consulta)."
        )
    return translation


def translate_all(
    node: Node, years: tuple[int | None, int | None] = (None, None)
) -> dict[str, Translation]:
    """Traducciones para todas las fuentes (útil para revisarlas antes de buscar)."""
    return {
        "scopus": to_scopus(node, years),
        "pubmed": _with_years_note(to_pubmed(node), years),
        "crossref": to_crossref(node),
        "arxiv": to_arxiv(node, years),
    }
