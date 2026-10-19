import csv

from biblio_search.dedupe import deduplicate
from biblio_search.export import citation_key, write_bibtex, write_csv
from biblio_search.records import Record


def _r(source, doi=None, title="Deep Learning for Radiology Images", year=2021, **kw):
    return Record(
        source=source, source_id=f"{source}-id", title=title, doi=doi, year=year, **kw
    )


def test_dedupe_by_doi_and_title() -> None:
    records = [
        _r("crossref", doi="10.1/A", abstract="from crossref"),
        _r("scopus", doi="10.1/a"),
        _r("arxiv", doi=None, title="Deep learning for radiology images!"),
        _r("pubmed", doi="10.9/other", title="Something else entirely here"),
    ]
    unique, removed = deduplicate(records)
    assert removed == 2
    first = unique[0]
    assert first.source == "scopus"  # mayor prioridad
    assert first.abstract == "from crossref"  # completado desde otra fuente
    assert set(first.sources) == {"scopus", "crossref", "arxiv"}


def test_csv_has_screening_columns(tmp_path) -> None:
    path = tmp_path / "r.csv"
    write_csv([_r("scopus", doi="10.1/a", authors=["Núñez, José"])], path)
    rows = list(csv.DictReader(path.read_text(encoding="utf-8-sig").splitlines()))
    assert rows[0]["authors"] == "Núñez, José"
    assert rows[0]["decision"] == "" and rows[0]["notes"] == ""


def test_bibtex(tmp_path) -> None:
    path = tmp_path / "r.bib"
    recs = [
        _r(
            "scopus",
            doi="10.1/a",
            authors=["Núñez, José"],
            venue="J & Co",
            doc_type="Conference Paper",
        ),
        _r(
            "arxiv",
            title="Deep learning for radiology images",
            year=2021,
            authors=["Núñez, José"],
            venue="arXiv",
        ),
    ]
    write_bibtex(recs, path)
    text = path.read_text(encoding="utf-8")
    assert "@inproceedings{nunez2021deep," in text
    assert "@misc{nunez2021deepa," in text
    assert "booktitle = {J \\& Co}" in text
    assert "archiveprefix = {arXiv}" in text


def test_citation_key_unique() -> None:
    used: set[str] = set()
    r = _r("scopus", authors=["He, Kaiming"])
    assert [citation_key(r, used) for _ in range(3)] == [
        "he2021deep",
        "he2021deepa",
        "he2021deepb",
    ]
