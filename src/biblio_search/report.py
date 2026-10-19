"""Informe reproducible de la búsqueda (PRISMA: fase de identificación)."""

from __future__ import annotations

import hashlib
import json
import platform
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from biblio_search import __version__
from biblio_search.sources.base import SearchResult


@dataclass
class SearchReport:
    table_path: Path
    years: tuple[int | None, int | None]
    results: list[SearchResult] = field(default_factory=list)
    duplicates_removed: int = 0
    unique_records: int = 0
    started_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds")
    )

    def table_sha256(self) -> str:
        return hashlib.sha256(self.table_path.read_bytes()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": f"biblio-search {__version__}",
            "python": platform.python_version(),
            "date_utc": self.started_at,
            "table": {"path": str(self.table_path), "sha256": self.table_sha256()},
            "years": {"from": self.years[0], "to": self.years[1]},
            "sources": [
                {
                    "source": r.source,
                    "query": r.query,
                    "params": r.params,
                    "total_reported": r.total_reported,
                    "retrieved": len(r.records),
                    "warnings": r.warnings,
                    "error": r.error,
                }
                for r in self.results
            ],
            "identified": sum(len(r.records) for r in self.results),
            "duplicates_removed": self.duplicates_removed,
            "unique_records": self.unique_records,
        }

    def write(self, out_dir: Path) -> None:
        data = self.to_dict()
        (out_dir / "report.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (out_dir / "report.md").write_text(self.to_markdown(data), encoding="utf-8")

    @staticmethod
    def to_markdown(d: dict[str, Any]) -> str:
        lines = [
            "# Informe de búsqueda",
            "",
            f"- **Fecha (UTC):** {d['date_utc']}",
            f"- **Herramienta:** {d['tool']} (Python {d['python']})",
            f"- **Tabla de términos:** `{d['table']['path']}`",
            f"- **SHA-256 de la tabla:** `{d['table']['sha256']}`",
            f"- **Años:** {d['years']['from'] or '—'} a {d['years']['to'] or '—'}",
            "",
            "## Resultados por fuente",
            "",
            "| Fuente | Total según la fuente | Recuperados | Estado |",
            "|---|---|---|---|",
        ]
        for s in d["sources"]:
            status = f"❌ {s['error']}" if s["error"] else "✅"
            counts = f"{s['total_reported']} | {s['retrieved']}"
            lines.append(f"| {s['source']} | {counts} | {status} |")
        lines += [
            "",
            "## Diagrama PRISMA (identificación)",
            "",
            f"- Registros identificados: **{d['identified']}**",
            f"- Duplicados eliminados: **{d['duplicates_removed']}**",
            f"- Registros para cribado: **{d['unique_records']}**",
            "",
            "## Consultas exactas",
            "",
        ]
        for s in d["sources"]:
            lines += [f"### {s['source']}", "", "```", s["query"], "```", ""]
            if s["params"]:
                lines.append(
                    f"Parámetros: `{json.dumps(s['params'], ensure_ascii=False)}`"
                )
                lines.append("")
            for w in s["warnings"]:
                lines.append(f"> ⚠️ {w}")
            if s["warnings"]:
                lines.append("")
        return "\n".join(lines)
