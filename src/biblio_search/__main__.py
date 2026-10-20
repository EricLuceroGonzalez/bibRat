"""CLI: ``uv run biblio-search <comando>``.

Comandos:
    translate TABLA             Muestra la consulta que se enviará a cada fuente.
    search TABLA [--out DIR]    Ejecuta la búsqueda y guarda CSV, BibTeX e informe.
    check-config                Comprueba credenciales y acceso a cada fuente.
    merge [BÚSQUEDAS...]        Une varias búsquedas en un CSV/BibTeX sin duplicados.
    check-seeds SEMILLAS [RUTA] Indica qué artículos semilla se encontraron.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from biblio_search import __version__
from biblio_search.config import get_settings
from biblio_search.dedupe import deduplicate
from biblio_search.logging_setup import setup_logging
from biblio_search.merge import merge_results
from biblio_search.query.table import TableError, load_table
from biblio_search.query.translate import translate_all
from biblio_search.records import Record
from biblio_search.results_io import read_results, resolve_results
from biblio_search.search import SOURCES, build_sources, default_out_dir, run_search
from biblio_search.seeds import check_seeds, load_seeds
from biblio_search.sources.base import SourceError, TransientError

logger = logging.getLogger(__name__)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="biblio-search",
        description="Búsqueda reproducible en Scopus, PubMed, Crossref y arXiv.",
    )
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("table", type=Path, help="CSV con los términos")
    common.add_argument("--from-year", type=int, help="año inicial (incluido)")
    common.add_argument("--to-year", type=int, help="año final (incluido)")

    sub.add_parser("translate", parents=[common], help="ver las consultas por fuente")
    s = sub.add_parser("search", parents=[common], help="ejecutar la búsqueda")
    s.add_argument(
        "--out", type=Path, help="carpeta de salida (por defecto searches/…)"
    )
    s.add_argument(
        "--sources",
        default=",".join(SOURCES),
        help=f"fuentes separadas por comas (por defecto: {','.join(SOURCES)})",
    )
    s.add_argument("--max", type=int, help="máximo de resultados por fuente")
    c = sub.add_parser("check-config", help="comprobar acceso a las fuentes")
    c.add_argument("--sources", default=",".join(SOURCES))

    m = sub.add_parser("merge", help="unir búsquedas eliminando duplicados")
    m.add_argument(
        "inputs",
        nargs="*",
        type=Path,
        help="carpetas de búsqueda o results.csv (por defecto: searches/*)",
    )
    m.add_argument("--out", type=Path, help="carpeta de salida (por defecto merged/…)")

    k = sub.add_parser("check-seeds", help="¿se encontraron los artículos semilla?")
    k.add_argument("seeds", type=Path, help="archivo con un DOI o título por línea")
    k.add_argument(
        "inputs",
        nargs="*",
        type=Path,
        help="búsqueda(s), results.csv o merged.csv (por defecto: searches/*)",
    )
    return p


def _load_records(inputs: list[Path]) -> list[Record]:
    """Registros únicos de las búsquedas indicadas (o de todas en searches/)."""
    records: list[Record] = []
    for path in resolve_results(inputs):
        label = path.parent.name if path.name == "results.csv" else path.stem
        records.extend(read_results(path, label))
    return deduplicate(records)[0]


def _cmd_merge(args: argparse.Namespace) -> int:
    csv_paths = resolve_results(args.inputs)
    if not csv_paths:
        print(
            "No se encontró ningún results.csv (¿existe la carpeta searches/?)",
            file=sys.stderr,
        )
        return 2
    out_dir = args.out or Path("merged") / datetime.now().strftime("%Y-%m-%d_%H%M")
    _, report = merge_results(csv_paths, out_dir)
    for name, n in report.inputs:
        print(f"  {n:>5}  {name}")
    print(
        f"\nEntrada: {report.total_in} · duplicados: {report.duplicates_removed} "
        f"· únicos: {report.unique}"
    )
    if report.conflicts:
        print(
            f"⚠ {report.conflicts} artículos con decisiones de cribado distintas "
            "(columna decision = CONFLICTO)"
        )
    print(f"Resultado en {out_dir}/ (merged.csv, merged.bib, merge_report.md)")
    return 0


def _cmd_check_seeds(args: argparse.Namespace) -> int:
    seeds = load_seeds(args.seeds)
    records = _load_records(args.inputs)
    if not records:
        print("No hay resultados que revisar.", file=sys.stderr)
        return 2
    report = check_seeds(seeds, records)
    for seed, record in report.found:
        print(f"✓ {seed.raw}\n    → {record.title[:90]}  [{', '.join(record.sources)}]")
    for seed in report.missing:
        print(f"✗ {seed.raw}")
    total = len(seeds)
    print(
        f"\nEncontradas {len(report.found)} de {total} semillas "
        f"({report.recall:.0%}) entre {len(records)} registros únicos."
    )
    if report.missing:
        print(
            "Revisa los artículos que faltan: ¿qué términos usan que tu tabla no tiene?"
        )
    return 0 if not report.missing else 1


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if args.command == "merge":
        return _cmd_merge(args)
    if args.command == "check-seeds":
        return _cmd_check_seeds(args)

    if args.command == "translate":
        try:
            node = load_table(args.table)
        except (TableError, OSError) as exc:
            print(f"Error en la tabla: {exc}", file=sys.stderr)
            return 2
        for name, tr in translate_all(node, (args.from_year, args.to_year)).items():
            print(f"── {name} " + "─" * (60 - len(name)))
            print(tr.query)
            for w in tr.warnings:
                print(f"   ⚠ {w}")
            print()
        return 0

    try:
        settings = get_settings()
    except ValidationError as exc:
        print(f"Configuración inválida:\n{exc}", file=sys.stderr)
        return 2
    setup_logging(
        log_dir=settings.log_dir,
        log_filename="biblio_search.log",
        level=settings.log_level,
    )
    for noisy in ("urllib3", "requests"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    names = [n.strip() for n in args.sources.split(",") if n.strip()]
    try:
        sources = build_sources(names, settings)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2

    if args.command == "check-config":
        ok = True
        for source in sources:
            try:
                print("✓", source.check())
            except (SourceError, TransientError, OSError, KeyError, ValueError) as exc:
                ok = False
                print(f"✗ {source.name}: {exc}")
        return 0 if ok else 1

    try:
        node = load_table(args.table)
    except (TableError, OSError) as exc:
        print(f"Error en la tabla: {exc}", file=sys.stderr)
        return 2
    out_dir = args.out or default_out_dir(args.table)
    report = run_search(
        node,
        args.table,
        sources,
        out_dir,
        (args.from_year, args.to_year),
        args.max or settings.max_results_per_source,
    )
    data = report.to_dict()
    print(
        f"\nIdentificados: {data['identified']} · duplicados: "
        f"{data['duplicates_removed']} · para cribar: {data['unique_records']}"
    )
    for s in data["sources"]:
        estado = (
            f"ERROR: {s['error']}"
            if s["error"]
            else f"{s['retrieved']} de {s['total_reported']}"
        )
        print(f"  {s['source']:<9} {estado}")
    print(f"\nResultados en {out_dir}/ (results.csv, results.bib, report.md)")
    return 1 if any(s["error"] for s in data["sources"]) else 0


if __name__ == "__main__":
    sys.exit(main())
