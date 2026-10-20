"""Fusión de varias búsquedas en un único conjunto deduplicado."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from biblio_search import __version__
from biblio_search.dedupe import CONFLICT, deduplicate
from biblio_search.export import write_bibtex, write_csv
from biblio_search.records import Record
from biblio_search.results_io import read_results


@dataclass
class MergeReport:
    inputs: list[tuple[str, int]] = field(default_factory=list)  # (búsqueda, registros)
    total_in: int = 0
    unique: int = 0
    conflicts: int = 0
    date_utc: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds")
    )

    @property
    def duplicates_removed(self) -> int:
        return self.total_in - self.unique

    def to_markdown(self) -> str:
        lines = [
            "# Fusión de búsquedas",
            "",
            f"- **Fecha (UTC):** {self.date_utc}",
            f"- **Herramienta:** biblio-search {__version__}",
            "",
            "| Búsqueda | Registros |",
            "|---|---|",
            *[f"| {name} | {n} |" for name, n in self.inputs],
            "",
            f"- Registros de entrada: **{self.total_in}**",
            f"- Duplicados eliminados: **{self.duplicates_removed}**",
            f"- Registros únicos: **{self.unique}**",
        ]
        if self.conflicts:
            lines.append(
                f"- ⚠️ Decisiones de cribado en conflicto: **{self.conflicts}** "
                f"(busca `{CONFLICT}` en la columna `decision`)"
            )
        return "\n".join(lines) + "\n"


def merge_results(
    csv_paths: list[Path], out_dir: Path
) -> tuple[list[Record], MergeReport]:
    """Une los ``results.csv`` indicados, deduplica y escribe CSV, BibTeX e informe."""
    report = MergeReport()
    records: list[Record] = []
    for path in csv_paths:
        batch = read_results(path)
        report.inputs.append((path.parent.name, len(batch)))
        records.extend(batch)
    report.total_in = len(records)
    unique, _ = deduplicate(records)
    unique.sort(key=lambda r: (-(r.year or 0), r.title.casefold()))
    report.unique = len(unique)
    report.conflicts = sum(r.decision.startswith(CONFLICT) for r in unique)

    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(unique, out_dir / "merged.csv")
    write_bibtex(unique, out_dir / "merged.bib")
    (out_dir / "merge_report.md").write_text(report.to_markdown(), encoding="utf-8")
    (out_dir / "merge_report.json").write_text(
        json.dumps(
            {
                "date_utc": report.date_utc,
                "inputs": [{"search": n, "records": c} for n, c in report.inputs],
                "total_in": report.total_in,
                "duplicates_removed": report.duplicates_removed,
                "unique": report.unique,
                "conflicts": report.conflicts,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return unique, report
