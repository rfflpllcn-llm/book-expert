# Adding a New Book

This guide walks through every step needed to add a new book to the system.

## Prerequisites

- Python 3.11+ with the project installed (`uv pip install -e ".[dev]"`)
- The book's full text as a CSV file (see [Source Text Format](#source-text-format))
- A knowledge base with scene summaries, character profiles, themes, etc.

## Quick Overview

```
books/<slug>/
├── book.yaml                 # book metadata + routing config
├── preferences.yaml          # per-book response style overrides (optional)
├── agent.py                  # interactive agent (copy from voyage, adjust identity)
├── data/
│   └── <source>.csv          # original text
└── knowledge/
    ├── tier_1/               # always-loaded context (system prompt)
    ├── tier_2/               # on-demand arc files
    ├── tier_3/               # critical commentaries (optional)
    │   └── _index.md         # routing metadata for commentaries
    └── answers/              # cached full answers (auto-populated)
```

## Step-by-Step

### 1. Create the directory structure

Pick a short lowercase slug for the book (e.g., `madame-bovary`, `processo`, `recherche`).

```bash
SLUG=madame-bovary
mkdir -p books/$SLUG/{data,knowledge/{tier_1,tier_2,tier_3,answers}}
```

### 2. Prepare the source text CSV

Place your CSV in `books/<slug>/data/`. The CSV must have at minimum:

| Column | Purpose |
|--------|---------|
| A line ID column | Unique identifier per line (e.g., `FR1`, `EN1`, `IT1`) |
| A text column | The actual text content |
| A type/filter column | Distinguishes main text from headers/footers/notes |

Example header:

```csv
chunk_id,edition_id,line_id,page,line_no,box,text,text_hash,chunk_type
```

The `cite.py` tool uses these columns to extract and format citations. Only rows matching the filter value (e.g., `main_text`) are returned.

### 3. Write `book.yaml`

This is the central config file. Every field is used by `lib/loader.py` for routing and by `lib/generate_claude_md.py` for CLAUDE.md generation.

```yaml
title: Madame Bovary
author: Gustave Flaubert
year: 1857
language: fr

source_text:
  file: data/bovary-fr.csv      # path relative to book directory
  format: csv
  line_prefix: FR                # prefix used in line IDs (FR1, FR2, ...)
  line_column: line_id           # CSV column containing the line ID
  text_column: text              # CSV column containing the text
  filter_column: chunk_type      # CSV column to filter on
  filter_value: main_text        # only rows with this value are cited

arcs:
  02_01_tostes:
    keywords: [tostes, charles, premier mariage, heloise]
    lines: [1, 500]             # [start_line, end_line] — inclusive range
  02_02_vaubyessard:
    keywords: [vaubyessard, bal, marquis]
    lines: [500, 900]
  # ... one entry per narrative arc

characters:
  charles:
    arcs: [02_01_tostes, 02_02_vaubyessard]
  emma:
    arcs: [02_01_tostes, 02_02_vaubyessard]
  # ... one entry per character, listing which arcs they appear in
```

**Key points:**

- `arcs` keys must match the tier_2 filenames exactly (without `.md`)
- `keywords` are matched case-insensitively against user queries for routing
- `lines` ranges are used to route `SC_xxxxx` and `Lnnn` references to the right arc
- `characters` names are matched in queries to pull in all their arcs

### 4. Write `preferences.yaml` (optional)

Per-book overrides for response style. Only include keys you want to change from the global defaults in the root `preferences.yaml`.

```yaml
# Only override what differs from global defaults
citation_density: heavy_with_commentary
interpretation_stance: psychoanalytic
```

Available keys and values:

| Key | Values |
|-----|--------|
| `language` | Any language name (e.g., `italiano`, `français`, `english`) |
| `tone` | `academic_formal`, `conversational`, `inspired_professor` |
| `citation_density` | `always`, `on_request`, `heavy_with_commentary` |
| `interpretation_stance` | `null`, `psychoanalytic`, `marxist`, `structuralist`, `historical` |
| `answer_length` | `concise`, `moderate`, `detailed` |

If the file is absent or empty, all global defaults apply.

### 5. Build the knowledge base

#### Tier 1 — `knowledge/tier_1/`

These files are loaded into every system prompt. Keep them concise (~10K tokens total). Required files:

| File | Content |
|------|---------|
| `00_index.md` | Master index: file map, arc table, scene count |
| `01_synopsis.md` | Complete plot summary across all arcs |
| `03_characters.md` | All characters with arcs, traits, relations |
| `04_themes.md` | Themes with descriptions and key examples |
| `05_style.md` | Narrative techniques, language, metaphors |
| `06_context.md` | Author biography, publication history, reception |
| `08_qa_cache.md` | Empty cache scaffold (see below) |

Initialize the QA cache with:

```markdown
# Risposte validate — Q&A Cache

Questo file raccoglie risposte già validate a domande frequenti.

---
```

#### Tier 2 — `knowledge/tier_2/`

One file per narrative arc, named to match the `arcs` keys in `book.yaml`:

```
02_01_tostes.md
02_02_vaubyessard.md
02_03_yonville.md
...
```

Each file contains detailed scene-by-scene summaries with scene IDs (`SC_xxxxx`) and line references (`L123–L456`).

#### Tier 3 — `knowledge/tier_3/` (critical essays)

Essay routing metadata is stored in `_index.yaml`. This file is generated automatically
by `python -m lib.aggregate_essay_index <book_dir>` from per-essay YAML descriptors
in `data/essays/<slug>/<slug>.yaml`.

Each essay goes through the same preprocessing pipeline as the book (stages 0-4)
and produces its own knowledge base in `data/essays/<slug>/`.

To add a critical essay:
1. Place the PDF in `data/essays/<slug>/<slug>.pdf`
2. Run the preprocessing pipeline (stages 0-4) to generate JSONL, sections, chunks, tier_1, tier_2, and YAML
3. Run `python -m lib.aggregate_essay_index .` to update `_index.yaml`
4. Run `python -m lib.generate_claude_md .` to update CLAUDE.md with `cite_essay` tool

### 6. Generate `CLAUDE.md`

```bash
python -m lib.generate_claude_md books/<slug>
```

This reads `book.yaml` + merged preferences and writes `books/<slug>/CLAUDE.md`. Regenerate whenever you change `book.yaml` or preferences.

### 7. Copy and adapt `agent.py`

Copy `books/voyage/agent.py` as a starting point:

```bash
cp books/voyage/agent.py books/<slug>/agent.py
```

Edit the `AGENT_IDENTITY` string to match the new book. The rest of the agent code is generic — it uses `lib/` functions with `BOOK_DIR = Path(".")`.

### 8. Verify

```bash
# From the repo root:
pytest tests/ -v                                    # all lib tests pass

# From the book directory:
cd books/<slug>
python -m lib.cite . 1 5                            # citations work
python -c "from lib.loader import load_book_config; c = load_book_config('.'); print(c['title'])"
```

### 9. Use it

```bash
cd books/<slug>
# Claude Code reads CLAUDE.md from the working directory
```

## Checklist

- [ ] `books/<slug>/book.yaml` — metadata, source_text, arcs, characters
- [ ] `books/<slug>/data/<source>.csv` — full text with line IDs
- [ ] `books/<slug>/knowledge/tier_1/` — 7 files (index, synopsis, characters, themes, style, context, cache)
- [ ] `books/<slug>/knowledge/tier_2/` — one `.md` per arc, names match `book.yaml` keys
- [ ] `books/<slug>/knowledge/tier_3/_index.md` — commentary routing (can be empty scaffold)
- [ ] `books/<slug>/knowledge/answers/` — empty directory
- [ ] `books/<slug>/preferences.yaml` — per-book overrides (or empty/absent)
- [ ] `books/<slug>/agent.py` — adapted from voyage
- [ ] `books/<slug>/CLAUDE.md` — generated via `python -m lib.generate_claude_md books/<slug>`
- [ ] `pytest tests/ -v` — all passing
- [ ] `python -m lib.cite books/<slug> <start> <end>` — returns text
