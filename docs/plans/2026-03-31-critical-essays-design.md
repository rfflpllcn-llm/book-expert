# Critical Essays Integration — Design

## Goal

Integrate 5-15 published critical essays (PDFs) into the book-expert system so they can be cited on-demand when users ask about criticism or scholarly interpretations.

## Core idea

**Every critical essay follows the same preprocessing pipeline as the actual book.** The existing stages (`00__pdf2jsonl` → `01__book_natural_bounds` → `02__semantic_chunking` → `03__generate_knowledge` → `04__generate_book_yaml`) are reused for essays. Each essay is treated like a small book and gets the full treatment: JSONL, sections JSON, semantic chunks, a complete knowledge base (tier_1 + tier_2), and a YAML descriptor.

**No embeddings.** The LLM is the router. `_index.yaml` summaries (extracted from each essay's generated YAML) are always loaded into context. When a query touches criticism, the agent reads the summaries, decides which essay arcs are relevant, and loads their tier_2 files via `cite_essay`. This avoids the embedding infrastructure while getting semantic matching for free — the LLM understands that "narrative voice" relates to "style parlé".

**Hybrid retrieval.** The routing layer uses compact summaries from `_index.yaml` (small, always loaded). The retrieval layer uses the essay's **tier_2 analytical summaries** (scene-by-scene breakdowns with figures, themes, line references) — not raw JSONL text. This gives the agent pre-digested critical analysis, which is far more useful for answering questions about scholarly interpretations than raw text would be.

## Prompt budget

The `_index.yaml` summaries are loaded into the system prompt. The budget depends on what goes into each entry.

**Empirical baseline**: the sample essay (Poétique de Céline, a full-length monograph) produces 14 top-level sections with ~19 essay-specific arcs. At ~70 tokens per chapter summary + ~120 for the essay header, that's ~1,100 tokens for this essay.

**Budget tiers** (for 15 essays):

| What's loaded per essay | Est. tokens/essay | 15 essays |
|---|---|---|
| Header only (author, work, year, stance, essay-level summary) | ~150 | ~2.3k |
| Header + chapter titles (no chapter summaries) | ~300 | ~4.5k |
| Header + chapter titles + chapter summaries | ~1,000 | ~15k |

**Decision**: load **header + chapter-level titles and summaries** into the system prompt (~15k for 15 essays). Sub-part details and arc-level granularity are available on demand via tier_2 files.

The routing unit for LLM-as-router is the **top-level section** (chapter). The agent requests specific arcs within a chapter via `cite_essay`.

### Hard limit: 100k tokens

If the total `_index.yaml` rendered summaries exceed 100k tokens, degrade to header-only (~2.3k for 15 essays) and rely on the agent calling `cite_essay . <slug> --toc` to get the chapter list on demand. This adds one tool call but caps the fixed cost. `load_tier3()` should check the rendered size and fall back automatically.

## Storage

Each essay gets its own directory under `data/essays/<slug>/` with the full pipeline output:

```
data/essays/godard_poetique/
├── godard_poetique.pdf               # source PDF
├── godard_poetique.jsonl              # full line-level extraction (stage 0)
├── godard_poetique-filtered.jsonl     # id + text only (stage 0)
├── godard_poetique_sections.json      # natural bounds (stage 1)
├── godard_poetique_chunks.jsonl       # semantic chunks (stage 2)
├── tier_1/                            # knowledge base (stage 3)
│   ├── 00_index.md
│   ├── 01_synopsis.md
│   ├── 03_characters.md
│   ├── 04_themes.md
│   ├── 05_style.md
│   └── 06_context.md
├── tier_2/                            # arc detail files (stage 3)
│   ├── 02_01_primato_stile.md
│   ├── 02_02_quadro_teorico.md
│   └── ...
└── godard_poetique.yaml               # essay descriptor (stage 4)
```

Additionally:
- **Routing metadata**: `knowledge/tier_3/_index.yaml` — aggregated from all per-essay `.yaml` files. Chapter-level summaries loaded into context.

### Why essays don't live in `knowledge/tier_3/`

The current `load_tier3()` reads `_index.md`, resolves `<slug>.md` files from `knowledge/tier_3/`, and injects their full text into prompt context. With 5-15 essays' worth of tier_1 + tier_2 files that would explode prompt size. Essays live in `data/essays/` and their analytical content is accessed on demand via `cite_essay`.

### Metadata format: `_index.md` → `_index.yaml`

The current `_index.md` is Markdown parsed ad-hoc by `_parse_tier3_index()`, which only extracts `slug`, `arcs`, and `themes`. Switch to `_index.yaml` — a single structured file read with `yaml.safe_load()`.

The `_index.yaml` is **aggregated** from each essay's generated `.yaml` file (stage 4 output). Schema per essay entry:

```yaml
essays:
  godard_poetique:
    author: "Henri Godard"
    work: "Poétique de Céline"
    year: 1985
    summary: >
      Monografia critica che analizza sistematicamente la poetica romanzesca di
      Céline. Godard parte dalla lingua per risalire al plurivocalismo, all'écriture,
      allo stile, alla voce narrante e infine al genere romanzo-autobiografia.
    stance: "stylistic-linguistic"
    arcs:                              # essay-specific arcs (NOT novel arcs)
      - 02_01_primato_stile
      - 02_02_quadro_teorico
      - 02_03_lingua_principi
      # ...
    themes:
      - "Stile e linguaggio"
      - "Oralità e parlato"
      - "Voce narrante"
      # ...
    characters:
      - Céline
      - Bardamu
      - Proust
      - Joyce
      - Bakhtine
      # ...
    sections:
      - id: 0
        title: "AVANT-PROPOS"
        summary: "Godard presenta l'oggetto e il metodo del saggio."
        start_id: "5"
        end_id: "272"
        arcs: []
      - id: 1
        title: "CHAPITRE I – Les français de Céline"
        summary: >
          Capitolo che copre l'intera dimensione linguistica dell'opera celiniana:
          dalla scelta del francese popolare all'oralità trasposta, dall'argot ai
          neologismi.
        start_id: "410"
        end_id: "3547"
        arcs:
          - 02_01_primato_stile
          - 02_03_lingua_principi
          - 02_04_oralita_sintassi
          # ...
      # ...
```

**Key**: the `arcs` are essay-specific (e.g. `02_01_primato_stile`), not novel arcs. They describe the essay's own argumentative structure and map directly to tier_2 file names in `data/essays/<slug>/tier_2/`.

### Why LLM-as-router works here

- **Semantic matching is free**: the LLM understands that "narrative voice" maps to "style parlé" without keyword enumeration
- **Cross-essay reasoning**: the agent sees all essay summaries at once and can decide to pull arcs from multiple essays for comparison
- **Chapter-level precision**: summaries include per-chapter descriptions, so the agent requests specific chapters — not entire essays
- **Rich retrieval**: tier_2 files contain scene-by-scene analytical summaries with figures, themes, and line references — far more useful than raw text for criticism questions

## Prerequisite refactoring

The preprocessing stages are not yet callable as a generic pipeline. The following changes are needed before essays can flow through them:

### Stage 0: `convert.py` needs CLI arguments

Current state: `__main__` hardcodes `poétique_de_céline-001.pdf` (`convert.py:84`). The `extract_lines_to_jsonl()` function itself is generic.

Change: add `argparse` to `__main__` so it accepts `python -m preprocessing.00__pdf2jsonl.convert <pdf_path> [--lang <lang>]`. The function is already parametric — only the entry point needs wiring.

### Stage 1: prompt-only, no runnable tooling

Current state: `preprocessing/01__book_natural_bounds/` contains only `prompt.md` — a prompt template for manual LLM use.

Change: add a `run.py` that takes a PDF + filtered JSONL, sends the prompt to Claude API, and writes `_sections.json`. For essays this is lightweight (short documents).

### Stage 2: `batch_processor.py` hardcodes sandbox paths

Current state: `CONFIG` dict at top of file hardcodes absolute paths to sandbox directories (`batch_processor.py:18-24`).

Change: make `CONFIG` paths configurable via CLI args or a config file, falling back to current defaults. The processing logic itself is generic.

### Stage 3: prompt needs adaptation for essays

Current state: `preprocessing/03__generate_knowledge/` contains `prompt_knowledge_base_builder.md` designed for novels.

Change: add an essay-specific prompt variant. The output structure is the same (tier_1 + tier_2), but the prompt should orient the LLM toward critical analysis: identifying the critic's argument, theoretical framework, figures discussed, and how sections relate to the novel being studied. The existing `book.yaml` arcs/themes of the novel can be provided as context so the LLM can note cross-references.

### Stage 4: YAML generation works as-is

Current state: `preprocessing/04__generate_book_yaml/` generates a YAML descriptor. The Godard essay already has a generated `godard_poetique.yaml` that matches the `_index.yaml` schema.

Change: none to the stage itself. Add a post-step that merges per-essay `.yaml` files into `knowledge/tier_3/_index.yaml`.

## Ingestion pipeline

Each essay goes through stages 0-4, producing the same artifacts as a book.

### Stage 0: PDF → JSONL

CLI: `python -m preprocessing.00__pdf2jsonl.convert data/essays/<slug>/<slug>.pdf`

- Produces `<slug>.jsonl` and `<slug>-filtered.jsonl`

### Stage 1: Natural bounds

CLI: `python -m preprocessing.01__book_natural_bounds.run data/essays/<slug>/<slug>.pdf data/essays/<slug>/<slug>-filtered.jsonl`

- Produces `<slug>_sections.json`
- Same structure as the book: `section`, `title`, `start_id`, `end_id`, `sub_parts`

### Stage 2: Semantic chunking

CLI: `python -m preprocessing.02__semantic_chunking.batch_processor --input data/essays/<slug>/<slug>-filtered.jsonl --sections data/essays/<slug>/<slug>_sections.json --output data/essays/<slug>/<slug>_chunks.jsonl`

- Target chunk size ~300-500 tokens, respecting section boundaries

### Stage 3: Generate knowledge base

CLI: `python -m preprocessing.03__generate_knowledge.run data/essays/<slug>/`

- Reads chunks + sections
- Produces `tier_1/` (index, synopsis, characters, themes, style, context) and `tier_2/` (one file per arc)
- Uses essay-specific prompt variant

### Stage 4: Generate YAML descriptor

CLI: `python -m preprocessing.04__generate_book_yaml.run data/essays/<slug>/`

- Reads tier_1 + tier_2 + sections
- Produces `<slug>.yaml` with the full schema (author, work, summary, arcs, themes, characters, sections with start/end IDs)

### Post-step: Aggregate into `_index.yaml`

CLI: `python -m lib.aggregate_essay_index .`

- Reads all `data/essays/*/*.yaml` files
- Merges into `knowledge/tier_3/_index.yaml`
- Idempotent: re-running regenerates from source YAML files

### Orchestrator: `lib/ingest_essay.py`

CLI: `python -m lib.ingest_essay . <slug>`

Runs stages 0-4 + aggregation in sequence for a single essay. Also supports `--all` to process all PDFs in `data/essays/`.

## Query-time flow

### Always loaded: essay summaries

`_index.yaml` chapter-level summaries are loaded into the system prompt via `load_tier3()`. The agent sees every essay's header + chapter titles and summaries. This is the routing layer — the LLM decides what's relevant.

### On-demand: `cite_essay` tool

CLI: `python -m lib.cite_essay . <slug> <arc_id>`

Resolution contract:
1. Look up `data/essays/<slug>/tier_2/<arc_id>.md`
2. Return the analytical summary (scene-by-scene breakdown with figures, themes, line references)

This returns **pre-digested critical analysis**, not raw text. Each tier_2 file contains:
- Arc synopsis
- Per-scene summaries (SC21, SC22, ...) with line ranges
- Figures and themes per scene

For raw text when needed (e.g., quoting the critic's exact words):
`python -m lib.cite_essay . <slug> <start_line> <end_line> --raw`
- Reads `<slug>-filtered.jsonl` and returns lines in range

Optional: `python -m lib.cite_essay . <slug> --toc` returns tier_1/00_index.md (the arc table) for the agent to browse before requesting a specific arc.

### Example

User: "What do critics say about Céline's narrative voice?"

1. Agent sees in system prompt: Godard's essay has chapters on "Le plurivocalisme célinien" and "De Bardamu à Céline" with arcs about voice and identity
2. Agent calls `python -m lib.cite_essay . godard_poetique 02_13_voce_identita`
3. Gets back analytical summary: 17 scenes covering the evolution from Bardamu to Ferdinand to Céline, with line references and figure mentions
4. Agent calls `python -m lib.cite . 8248 8260 --lang it` to quote the novel passage Godard discusses
5. Agent synthesizes the critic's argument with the novel passage

### Comparison with previous design

| Aspect | Previous (raw JSONL) | Hybrid (tier_2 summaries) |
|---|---|---|
| What `cite_essay` returns | Raw lines from filtered JSONL | Analytical summaries with scenes, figures, themes |
| New code needed | `cite_essay` JSONL reader, `analyze_essay` | `cite_essay` tier_2 reader (trivial), essay-specific prompt for stage 3 |
| Retrieval usefulness | Agent must interpret raw academic French | Agent gets pre-digested analysis in Italian with cross-references |
| Pipeline reuse | Stages 0-2 only, stage 3 is custom | All stages 0-4 reused |
| Artifacts per essay | JSONL + sections + chunks + `_index.yaml` entry | Full knowledge base (tier_1 + tier_2) + YAML |

## Loader changes (`lib/loader.py`)

The current `load_tier3()` + `build_context()` flow **must change**. Here's why and how:

### Current behavior (to be replaced)

1. `_parse_tier3_index()` parses `_index.md` — extracts only `slug`, `arcs`, `themes`
2. `load_tier3()` matches arcs/themes, then reads `knowledge/tier_3/<slug>.md` files and returns their full text
3. `build_context()` injects that text into dynamic context when `citation_density == "heavy_with_commentary"`
4. Tests `test_load_tier3_arc_match` and `test_build_context_with_commentary` cover this flow

### New behavior

1. `_parse_tier3_index()` → replace with `_load_tier3_index()` that reads `_index.yaml` via `yaml.safe_load()`. Returns the full structured data.
2. `load_tier3()` → formats and returns chapter-level summaries for all essays (header + chapter titles/summaries). No arc/theme filtering — the LLM sees everything and decides. Checks rendered token count against 100k limit; falls back to header-only if exceeded.
3. `build_context()` → **always** includes the tier_3 summary in the system prompt (not gated by `citation_density`). The `citation_density` preference instead controls the CLAUDE.md instructions (whether the agent proactively consults essays or only when asked).
4. Update existing tests to match new behavior. Add tests for YAML parsing, summary loading, and fallback.

### Migration path

- Remove per-commentary `knowledge/tier_3/<slug>.md` files (currently small hand-written notes)
- Migrate their content into `_index.yaml` summary fields
- Delete `_index.md`, replace with `_index.yaml`
- `heavy_with_commentary` now means "agent proactively consults essays for every query" vs. "agent consults essays only when user asks about criticism"

### Files that reference old behavior (must update)

**Tests:**
- `tests/conftest.py:109` — fixture creates `_index.md` + `<slug>.md` files → update to create `_index.yaml`
- `tests/test_loader.py:93` — `test_load_tier3_arc_match` expects full commentary text → expects formatted summaries
- `tests/test_loader.py:129` — `test_build_context_with_commentary` expects commentary in dynamic context → expects summaries in system prompt
- `tests/test_generate.py:21` — asserts `tier_3/_index.md` in output → assert `_index.yaml`

**Docs:**
- `docs/adding-a-new-book.md:161-190` — tier_3 setup instructions reference `_index.md` format and `<slug>.md` files
- `docs/knowledge-base-guide.md:13-176` — tier_3 section describes `_index.md` format, per-commentary `.md` files, `heavy_with_commentary` semantics

**Code:**
- `lib/loader.py:84-132` — `_parse_tier3_index()` and `load_tier3()`
- `lib/loader.py:152-157` — `build_context()` tier_3 gating
- `lib/generate_claude_md.py:89-98` — commentary instruction generation

## CLAUDE.md generator changes

### When `_index.yaml` exists and has entries

- Add `cite_essay` to the Tools section:
  ```
  - **Cite essay**: `python -m lib.cite_essay . <slug> <arc_id>`
    Loads the analytical summary for a specific arc of a critical essay.
    Use `--toc` to see all arcs: `python -m lib.cite_essay . <slug> --toc`
    Use `--raw <start> <end>` for exact quotes: `python -m lib.cite_essay . <slug> 3550 3618 --raw`
  ```
- List available essays (with authors and chapter titles) in the tier_3 knowledge architecture section, read from `_index.yaml`
- Workflow step 5:
  - For `heavy_with_commentary`: "**Consult critical essays**: review essay summaries in tier_3, call `cite_essay` for relevant arcs"
  - Otherwise: "**Check commentaries** (if user asks about criticism): review essay summaries in tier_3, call `cite_essay` for relevant arcs"

### When essay PDFs exist but no `_index.yaml`

- Do not advertise `cite_essay`
- Note in tier_3 section that essays are present but not yet ingested

## Dependencies

- `pymupdf` (fitz) — PDF text extraction (already used for book)
- Claude API — natural bounds (stage 1), knowledge generation (stage 3), YAML generation (stage 4)
- `pyyaml` — already a dependency

## What's NOT in scope

- Embeddings / vector search — the LLM routes from summaries
- Backward compatibility with `_index.md` format — clean migration to YAML
