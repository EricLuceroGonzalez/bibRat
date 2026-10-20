import csv

from biblio_search.__main__ import main
from biblio_search.dedupe import deduplicate
from biblio_search.export import write_csv
from biblio_search.merge import merge_results
from biblio_search.records import Record
from biblio_search.results_io import read_results, resolve_results
from biblio_search.seeds import check_seeds, load_seeds


def _rec(source, doi, title, decision="", notes="", year=2021):
    return Record(
        source,
        doi or title,
        title,
        doi=doi,
        year=year,
        decision=decision,
        notes=notes,
        authors=["Pérez, Ana"],
    )


def _search(root, name, records):
    folder = root / name
    folder.mkdir(parents=True)
    write_csv(records, folder / "results.csv")
    return folder


def test_roundtrip_csv(tmp_path) -> None:
    folder = _search(
        tmp_path,
        "s1",
        [_rec("scopus", "10.1/A", "Deep learning in CT", "incluir", "ok")],
    )
    [r] = read_results(folder / "results.csv")
    assert (r.doi, r.decision, r.notes, r.searches) == (
        "10.1/a",
        "incluir",
        "ok",
        ["s1"],
    )
    assert r.authors == ["Pérez, Ana"] and r.year == 2021


def test_merge_dedupes_and_keeps_screening(tmp_path) -> None:
    root = tmp_path / "searches"
    _search(
        root,
        "2026-10-01_a",
        [
            _rec("scopus", "10.1/a", "Deep learning in CT scans", "incluir"),
            _rec(
                "pubmed",
                "10.1/b",
                "Another relevant article title",
                "excluir",
                "fuera de tema",
            ),
        ],
    )
    _search(
        root,
        "2026-10-05_b",
        [
            _rec("crossref", "10.1/A", "Deep learning in CT scans", ""),  # mismo DOI
            _rec(
                "arxiv", None, "Another relevant article title!", "Incluir"
            ),  # mismo título, otra decisión
            _rec("arxiv", "10.1/c", "Totally new paper on radiology", ""),
        ],
    )
    paths = resolve_results([], default_root=root)
    assert len(paths) == 2
    unique, report = merge_results(paths, tmp_path / "out")
    assert (report.total_in, report.unique, report.duplicates_removed) == (5, 3, 2)
    by_doi = {r.doi: r for r in unique}
    assert by_doi["10.1/a"].decision == "incluir"
    assert set(by_doi["10.1/a"].searches) == {"2026-10-01_a", "2026-10-05_b"}
    assert by_doi["10.1/b"].decision == "CONFLICTO: excluir | Incluir"
    assert by_doi["10.1/b"].notes == "fuera de tema"
    assert report.conflicts == 1
    rows = list(
        csv.DictReader(
            (tmp_path / "out" / "merged.csv")
            .read_text(encoding="utf-8-sig")
            .splitlines()
        )
    )
    assert len(rows) == 3 and "searches" in rows[0]
    assert (tmp_path / "out" / "merged.bib").exists()
    assert (
        "Duplicados eliminados: **2**"
        in (tmp_path / "out" / "merge_report.md").read_text()
    )


def test_decision_conflicts_accumulate() -> None:
    records = [
        _rec("scopus", "10.1/x", "T long enough title here", d)
        for d in ("incluir", "excluir", "dudoso")
    ]
    [merged], _ = deduplicate(records)
    assert merged.decision == "CONFLICTO: dudoso | excluir | incluir"


def test_seeds(tmp_path) -> None:
    seeds_file = tmp_path / "semillas.txt"
    seeds_file.write_text(
        "# mis semillas\nhttps://doi.org/10.1000/A\n\nDeep learning in CT scans\n10.9999/missing\n",
        encoding="utf-8",
    )
    seeds = load_seeds(seeds_file)
    assert [s.doi for s in seeds] == ["10.1000/a", None, "10.9999/missing"]
    report = check_seeds(
        seeds, [_rec("scopus", "10.1000/a", "Deep learning in CT scans")]
    )
    assert len(report.found) == 2 and [s.raw for s in report.missing] == [
        "10.9999/missing"
    ]
    assert round(report.recall, 2) == 0.67


def test_cli_merge_and_seeds(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    _search(
        tmp_path / "searches",
        "s1",
        [_rec("scopus", "10.1000/a", "Deep learning in CT scans")],
    )
    _search(
        tmp_path / "searches",
        "s2",
        [_rec("pubmed", "10.1000/a", "Deep learning in CT scans")],
    )
    assert main(["merge", "--out", "m"]) == 0
    assert "únicos: 1" in capsys.readouterr().out
    (tmp_path / "s.txt").write_text("10.1000/a\n10.2000/zzz\n", encoding="utf-8")
    assert main(["check-seeds", "s.txt", "m/merged.csv"]) == 1  # falta una
    out = capsys.readouterr().out
    assert "Encontradas 1 de 2" in out and "✗ 10.2000/zzz" in out
