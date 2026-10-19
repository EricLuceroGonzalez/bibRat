import json

from biblio_search.__main__ import main
from biblio_search.query.model import Term
from biblio_search.records import Record
from biblio_search.search import run_search
from biblio_search.sources.base import SearchResult, SourceError


class Fake:
    def __init__(self, name, records=None, fail=False):
        self.name, self._records, self._fail = name, records or [], fail

    def search(self, node, years, limit):
        if self._fail:
            raise SourceError("HTTP 401: invalid key")
        return SearchResult(
            self.name,
            f"Q-{self.name}",
            {},
            len(self._records),
            list(self._records),
            raw=[{"ok": True}],
        )


def test_run_search_writes_everything(tmp_path) -> None:
    table = tmp_path / "t.csv"
    table.write_text("terminos\nx\n", encoding="utf-8")

    def rec(s: str) -> Record:
        return Record(
            s, f"{s}1", "Same title about something long", doi="10.1/x", year=2020
        )

    sources = [
        Fake("scopus", [rec("scopus")]),
        Fake("pubmed", [rec("pubmed")]),
        Fake("arxiv", fail=True),
    ]
    out = tmp_path / "out"
    report = run_search(Term("x"), table, sources, out, (2020, None), 10)  # type: ignore[arg-type]
    data = json.loads((out / "report.json").read_text())
    assert data["identified"] == 2 and data["duplicates_removed"] == 1
    assert data["unique_records"] == 1
    assert data["sources"][2]["error"].startswith("HTTP 401")
    assert (out / "results.csv").exists() and (out / "results.bib").exists()
    assert (out / "raw" / "scopus.json").exists()
    md = (out / "report.md").read_text()
    assert "Q-scopus" in md and "Duplicados eliminados: **1**" in md
    assert report.unique_records == 1


def test_cli_translate(tmp_path, capsys) -> None:
    table = tmp_path / "t.csv"
    table.write_text("terminos,campo\ndeep learning,title\n", encoding="utf-8")
    assert main(["translate", str(table)]) == 0
    out = capsys.readouterr().out
    assert 'TITLE("deep learning")' in out and '"deep learning"[ti]' in out
