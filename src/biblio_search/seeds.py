"""Comprobación de artículos semilla: ¿encuentra la búsqueda los que debe?"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from biblio_search.query.matcher import normalize
from biblio_search.records import Record

_DOI_RE = re.compile(r"10\.\d{4,9}/\S+", re.IGNORECASE)


@dataclass
class Seed:
    raw: str
    doi: str | None
    title: str | None


@dataclass
class SeedReport:
    found: list[tuple[Seed, Record]] = field(default_factory=list)
    missing: list[Seed] = field(default_factory=list)

    @property
    def recall(self) -> float:
        total = len(self.found) + len(self.missing)
        return len(self.found) / total if total else 0.0


def load_seeds(path: Path) -> list[Seed]:
    """Una semilla por línea: un DOI (con o sin https://doi.org/) o un título.

    Las líneas vacías y las que empiezan por ``#`` se ignoran.
    """
    seeds = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = _DOI_RE.search(line)
        if match:
            seeds.append(Seed(line, match.group(0).rstrip(".,;").lower(), None))
        else:
            seeds.append(Seed(line, None, normalize(line).replace("*", "")))
    return seeds


def check_seeds(seeds: list[Seed], records: list[Record]) -> SeedReport:
    by_doi = {r.doi: r for r in records if r.doi}
    by_title = {normalize(r.title).replace("*", ""): r for r in records}
    report = SeedReport()
    for seed in seeds:
        record = by_doi.get(seed.doi) if seed.doi else by_title.get(seed.title or "")
        if record:
            report.found.append((seed, record))
        else:
            report.missing.append(seed)
    return report
