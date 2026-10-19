"""Evaluación local de la consulta sobre un registro (para fuentes sin booleanos)."""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

from biblio_search.query.model import And, Node, Or, SearchField, Term


def normalize(text: str) -> str:
    """Minúsculas, sin acentos ni puntuación, espacios simples."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(re.findall(r"[a-z0-9*]+", ascii_text.lower()))


@lru_cache(maxsize=512)
def _pattern(text: str) -> re.Pattern[str]:
    words = normalize(text).split()
    parts = [
        re.escape(w.rstrip("*")) + (r"\w*" if w.endswith("*") else "") for w in words
    ]
    return re.compile(r"\b" + r"\s+".join(parts) + r"\b")


def matches(node: Node, title: str, abstract: str = "") -> bool:
    """¿Cumple el registro la expresión? Usa título y/o abstract según el campo."""
    title_n, abstract_n = normalize(title), normalize(abstract)

    def ev(n: Node) -> bool:
        if isinstance(n, Term):
            haystack = (
                title_n if n.field is SearchField.TITLE else f"{title_n} {abstract_n}"
            )
            return bool(_pattern(n.text).search(haystack))
        if isinstance(n, Or):
            return any(ev(c) for c in n.children)
        assert isinstance(n, And)
        return all(ev(c) for c in n.children) and not any(ev(e) for e in n.exclude)

    return ev(node)
