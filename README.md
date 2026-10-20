# biblio-search

Búsqueda bibliográfica **reproducible** en **Scopus, PubMed, Crossref y arXiv** a partir de una tabla CSV de términos y operadores booleanos. Pensado para revisiones sistemáticas: guarda la consulta exacta enviada a cada fuente, las respuestas originales y los conteos de la fase de identificación de PRISMA.

## Inicio rápido

```bash
make setup
cp -n .env.example .env          # solo la primera vez; rellena CONTACT_EMAIL y las keys
uv run biblio-search check-config                       # ¿hay acceso a cada fuente?
uv run biblio-search translate examples/terminos.csv    # revisa las consultas antes de buscar
uv run biblio-search search examples/terminos.csv --from-year 2020 --to-year 2024
```

| Comando | Qué hace |
|---|---|
| `translate TABLA [--from-year A] [--to-year B]` | Muestra la consulta que se enviará a cada fuente, con avisos sobre lo que no se puede traducir. No hace peticiones. |
| `search TABLA [--out DIR] [--sources ...] [--max N]` | Busca en las fuentes y guarda resultados e informe. Si una fuente falla, las demás continúan y el error queda en el informe. |
| `check-config [--sources ...]` | Comprueba las credenciales y el acceso a cada fuente. |
| `merge [BÚSQUEDAS...] [--out DIR]` | Une varias búsquedas en un solo CSV y BibTeX sin duplicados. Sin argumentos usa todas las de `searches/`. |
| `check-seeds SEMILLAS [BÚSQUEDAS...]` | Indica qué artículos semilla encontró la búsqueda y cuáles faltan. |

## La tabla de términos

CSV con una fila por **concepto** (las cabeceras pueden ir en español o en inglés):

```csv
concepto,terminos,campo,operador
tecnica,machine learning; deep learning; neural network*,title_abstract,AND
dominio,radiology; medical imaging,title_abstract,AND
exclusion,review; editorial,title,NOT
```

- **terminos:** separados por `;` (o `|`), y se unen con **OR**. Las frases con espacios se buscan como frase. `*` al final de una palabra trunca: `network*` encuentra network, networks…
- **operador:** `AND` (por defecto) une los conceptos entre sí; `NOT` excluye. Todas las filas NOT forman una única exclusión.
- **campo:** `title`, `title_abstract` (por defecto; en Scopus incluye las keywords) o `all`.
- Se aceptan CSV separados por coma o por punto y coma, como los que exporta Excel en español.

El ejemplo anterior equivale a *(machine learning OR deep learning OR neural network\*) AND (radiology OR medical imaging) NOT (review OR editorial en el título)*.

## Cómo se traduce a cada fuente

| Fuente | Booleanos | Campos | Truncamiento `*` | Años |
|---|---|---|---|---|
| Scopus | Nativos (`AND`, `OR`, `AND NOT`) | `TITLE`, `TITLE-ABS-KEY`, `ALL` | Sí | `PUBYEAR` en la consulta |
| PubMed | Nativos (`AND`, `OR`, `NOT`) | `[ti]`, `[tiab]`, `[all]` | Sí | Parámetros `mindate` y `maxdate` (`pdat`) |
| arXiv | Nativos (`AND`, `OR`, `ANDNOT`) | `ti:`, `ti: OR abs:`, `all:` | **No**: se quita el `*` y queda un aviso | `submittedDate` |
| Crossref | **No los admite** | — | Se aplica en el filtro local | Filtros `from-pub-date` y `until-pub-date` |

**Crossref:** se envían los términos como texto libre. De los `CROSSREF_MAX_SCAN` primeros resultados por relevancia se conservan solo los que cumplen la expresión booleana sobre título y abstract. Muchos registros de Crossref no tienen abstract, así que en ellos solo se evalúa el título. Por eso Crossref es la fuente menos exhaustiva: úsala como complemento.

Revisa siempre `translate` antes de buscar. En PubMed, el informe guarda además la `querytranslation`, es decir, cómo interpretó PubMed tu consulta (expansión a términos MeSH incluida).

## Resultados

Cada búsqueda crea una carpeta, por defecto `searches/AAAA-MM-DD_HHMM_<tabla>/`:

```
results.csv     registros únicos, con columnas "decision" y "notes" (vacías) para cribar
results.bib     BibTeX (importable en Zotero; clave tipo he2021deep)
report.md       informe legible: fecha, consultas exactas, conteos PRISMA, avisos
report.json     lo mismo en formato máquina (incluye el SHA-256 de la tabla)
raw/            respuestas originales de cada API, para auditoría
```

**Deduplicado.** Dos registros son el mismo artículo si comparten DOI, o si coinciden el título normalizado y el año. Se conserva el de la fuente con más prioridad (Scopus > PubMed > Crossref > arXiv) y se completan sus campos vacíos, como el abstract, con los de las demás. La columna `sources` indica en qué fuentes apareció cada artículo.

**Reproducibilidad.** Las bases de datos cambian con el tiempo, así que repetir la búsqueda otro día puede dar otros números. Por eso el informe guarda la fecha, la versión de la herramienta, el hash de la tabla, las consultas y los parámetros exactos, y `raw/` guarda las respuestas tal como llegaron. Incluye `report.md` en el material suplementario de la revisión.

## Unir búsquedas: `merge`

Después de varias búsquedas (iteraciones de la tabla, fuentes consultadas en días distintos…):

```bash
uv run biblio-search merge                                   # todas las de searches/
uv run biblio-search merge searches/2026-10-20_* --out merged/final
```

Genera `merged.csv`, `merged.bib` y `merge_report.md`, que indica cuántos registros aportó cada búsqueda y cuántos duplicados se eliminaron. Los duplicados se detectan igual que en `search`: por DOI, o por título normalizado y año.

- **El cribado se conserva.** Si ya rellenaste `decision` o `notes` en algún CSV, esos valores pasan al resultado.
- **Los conflictos no se resuelven solos.** Si un mismo artículo tiene decisiones distintas en dos búsquedas, `decision` queda como `CONFLICTO: excluir | incluir` para que lo resuelvas a mano. El informe dice cuántos hay.
- La columna `searches` indica de qué búsquedas procede cada artículo, y `sources`, de qué fuentes.

## Validar con artículos semilla: `check-seeds`

Crea un archivo de texto con los artículos que tu búsqueda **debe** encontrar, uno por línea, ya sea un DOI (con o sin `https://doi.org/`) o un título. Las líneas que empiezan por `#` son comentarios:

```text
# semillas.txt
10.1148/radiol.2017162326
https://doi.org/10.1038/s41591-019-0447-x
End-to-end lung cancer screening with three-dimensional deep learning
```

```bash
uv run biblio-search check-seeds semillas.txt searches/2026-10-20_1530_terminos   # una búsqueda
uv run biblio-search check-seeds semillas.txt merged/final/merged.csv            # el conjunto fusionado
uv run biblio-search check-seeds semillas.txt                                    # todo searches/
```

Muestra cada semilla encontrada (con las fuentes donde apareció), las que faltan y el porcentaje encontrado. Termina con código 1 si falta alguna, así que puedes usarlo en scripts. Cuando falte una, abre ese artículo y busca qué términos usa que tu tabla no tiene.

## Acceso a las APIs

| Fuente | Credencial | Notas |
|---|---|---|
| Scopus | `SCOPUS_API_KEY` en <https://dev.elsevier.com> | **Conéctate a la VPN de tu institución** antes de buscar, o pide un `SCOPUS_INSTTOKEN` a la biblioteca. Con `SCOPUS_VIEW=COMPLETE` se obtienen abstracts y todos los autores; si tu licencia no lo permite, el programa usa `STANDARD` y lo anota en el informe. |
| PubMed | `NCBI_API_KEY` (opcional): cuenta NCBI → *Account settings* | Sin key: 3 peticiones/s; con key: 10/s. |
| Crossref | — | Usa `CONTACT_EMAIL` para el *polite pool*. |
| arXiv | — | Una petición cada 3 s: las búsquedas grandes tardan. |

## Estructura

```
src/biblio_search/
├── __main__.py        CLI (translate / search / check-config)
├── config.py          configuración (.env)
├── query/
│   ├── model.py       árbol de la consulta: Term, Or, And (+exclusiones)
│   ├── table.py       CSV → árbol
│   ├── translate.py   árbol → Scopus / PubMed / arXiv / Crossref
│   └── matcher.py     evaluación local del booleano (Crossref)
├── sources/           un cliente por API (+ base con reintentos y límites)
├── records.py         registro normalizado
├── dedupe.py          fusión entre fuentes
├── export.py          CSV y BibTeX
├── report.py          informe PRISMA (md + json)
├── search.py          orquestación
├── results_io.py      lectura de results.csv
├── merge.py           fusión de búsquedas
└── seeds.py           comprobación de artículos semilla
```

## Desarrollo

```bash
make test     # tests con respuestas simuladas (no requieren red ni keys)
make check    # lint + tests
```
