from pathlib import Path

import pytest

from biblio_search.query.matcher import matches
from biblio_search.query.model import And, Or, SearchField, Term
from biblio_search.query.table import TableError, load_table, parse_rows
from biblio_search.query.translate import to_arxiv, to_crossref, to_pubmed, to_scopus

ROWS = [
    {
        "concepto": "t",
        "terminos": "machine learning; neural network*",
        "campo": "title_abstract",
        "operador": "AND",
    },
    {
        "concepto": "d",
        "terminos": "radiology",
        "campo": "title_abstract",
        "operador": "AND",
    },
    {"concepto": "x", "terminos": "review", "campo": "title", "operador": "NOT"},
]


@pytest.fixture
def tree():
    return parse_rows(ROWS)


def test_parse_rows_structure(tree) -> None:
    assert isinstance(tree, And)
    assert tree.children[0] == Or((Term("machine learning"), Term("neural network*")))
    assert tree.children[1] == Term("radiology")
    assert tree.exclude == (Term("review", SearchField.TITLE),)


def test_single_row_is_plain_or() -> None:
    node = parse_rows([{"terms": "a; b"}])
    assert node == Or((Term("a"), Term("b")))


@pytest.mark.parametrize(
    ("row", "msg"),
    [
        ({"terminos": "x", "campo": "abstract"}, "campo"),
        ({"terminos": "x", "operador": "OR"}, "operador"),
        ({"terminos": "x", "operador": "NOT"}, "ninguna fila AND"),
    ],
)
def test_parse_rows_errors(row, msg) -> None:
    with pytest.raises(TableError, match=msg):
        parse_rows([row])


def test_load_table_semicolon_csv_with_pipes(tmp_path: Path) -> None:
    csv_file = tmp_path / "t.csv"
    csv_file.write_text(
        "concepto;terminos;campo;operador\nt;deep learning|cnn;title;AND\n",
        encoding="utf-8-sig",
    )
    assert load_table(csv_file) == Or(
        (Term("deep learning", SearchField.TITLE), Term("cnn", SearchField.TITLE))
    )


def test_scopus(tree) -> None:
    # La exclusión queda agrupada: PUBYEAR no puede caer dentro del AND NOT.
    assert to_scopus(tree, (2020, 2024)).query == (
        '(((TITLE-ABS-KEY("machine learning") OR TITLE-ABS-KEY("neural network*")) '
        "AND TITLE-ABS-KEY(radiology)) AND NOT TITLE(review)) "
        "AND PUBYEAR > 2019 AND PUBYEAR < 2025"
    )


def test_multiple_exclusions_are_one_group() -> None:
    node = parse_rows(
        [
            {"terms": "a"},
            {"terms": "b", "operator": "NOT"},
            {"terms": "c", "operator": "NOT"},
        ]
    )
    assert to_scopus(node, (None, None)).query == (
        "(TITLE-ABS-KEY(a) AND NOT (TITLE-ABS-KEY(b) OR TITLE-ABS-KEY(c)))"
    )


def test_pubmed(tree) -> None:
    assert to_pubmed(tree).query == (
        '((("machine learning"[tiab] OR "neural network*"[tiab]) '
        "AND radiology[tiab]) NOT review[ti])"
    )


def test_arxiv_strips_wildcards_with_warning(tree) -> None:
    tr = to_arxiv(tree, (None, None))
    assert 'ti:"neural network"' in tr.query
    assert "ANDNOT ti:review" in tr.query
    assert tr.warnings and "truncamiento" in tr.warnings[0]


def test_crossref_free_text(tree) -> None:
    tr = to_crossref(tree)
    assert tr.query == "machine learning neural network radiology"
    assert "localmente" in tr.warnings[0]


def test_matcher(tree) -> None:
    assert matches(tree, "Neural networks for radiology", "")
    assert matches(tree, "A study", "Machine-learning in radiology")
    assert not matches(tree, "A review of neural networks in radiology", "")
    assert not matches(tree, "Neural networks", "for cardiology")
    # "review" excluido solo en el título: en el abstract no excluye
    assert matches(tree, "Neural networks in radiology", "we review the field")
