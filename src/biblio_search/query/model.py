"""Árbol de la consulta booleana, independiente de cualquier fuente."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SearchField(StrEnum):
    """Dónde se busca un término."""

    TITLE = "title"
    TITLE_ABSTRACT = "title_abstract"
    ALL = "all"


@dataclass(frozen=True)
class Term:
    """Palabra o frase. Un ``*`` final indica truncamiento (``network*``)."""

    text: str
    field: SearchField = SearchField.TITLE_ABSTRACT

    @property
    def is_phrase(self) -> bool:
        return " " in self.text.strip()

    @property
    def has_wildcard(self) -> bool:
        return "*" in self.text


@dataclass(frozen=True)
class Or:
    children: tuple[Node, ...]


@dataclass(frozen=True)
class And:
    """Conjunción. ``exclude`` contiene lo que se resta con NOT."""

    children: tuple[Node, ...]
    exclude: tuple[Node, ...] = ()


Node = Term | Or | And


def iter_terms(node: Node) -> list[Term]:
    """Todos los términos del árbol, en orden (incluidos los excluidos)."""
    if isinstance(node, Term):
        return [node]
    terms: list[Term] = []
    children = node.children + (node.exclude if isinstance(node, And) else ())
    for child in children:
        terms.extend(iter_terms(child))
    return terms


def positive_terms(node: Node) -> list[Term]:
    """Términos que suman (sin los de las exclusiones NOT)."""
    if isinstance(node, Term):
        return [node]
    terms: list[Term] = []
    for child in node.children:
        terms.extend(positive_terms(child))
    return terms
