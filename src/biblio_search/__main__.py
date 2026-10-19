"""CLI: ``uv run biblio-search <comando>``.

Comandos:
    translate TABLA             Muestra la consulta que se enviará a cada fuente.
    search TABLA [--out DIR]    Ejecuta la búsqueda y guarda CSV, BibTeX e informe.
    check-config                Comprueba credenciales y acceso a cada fuente.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from pydantic import ValidationError

from biblio_search import __version__
from biblio_search.config import get_settings
from biblio_search.logging_setup import setup_logging
from biblio_search.query.table import TableError, load_table
from biblio_search.query.translate import translate_all
from biblio_search.search import SOURCES, build_sources, default_out_dir, run_search
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
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

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
