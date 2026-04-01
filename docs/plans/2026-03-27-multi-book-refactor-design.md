# Multi-Book Refactor Design

**Date**: 2026-03-27
**Status**: Approved (revised after review)

## Goals

1. Support multiple books, each as a self-contained workspace
2. Add a commentary layer (tier_3) for critical/secondary material per book
3. User-configurable preferences: language, tone, citation density, interpretation stance, answer length

## Directory Structure

```
book-expert/
├── pyproject.toml                # declares lib as installable package + pyyaml dep
├── preferences.yaml              # global defaults
├── lib/
│   ├── __init__.py
│   ├── cite.py                   # generic citation tool (book-agnostic)
│   ├── loader.py                 # generic tier loader (read + write)
│   ├── save_qa.py                # cache writer (importable + CLI)
│   └── generate_claude_md.py     # renders CLAUDE.md from book config + preferences
├── books/
│   └── voyage/
│       ├── CLAUDE.md             # generated from preferences, reads book.yaml live
│       ├── preferences.yaml     # per-book overrides (optional, sparse)
│       ├── book.yaml             # book metadata: title, author, arcs, citation config
│       ├── data/
│       │   └── voyage-fr.csv
│       └── knowledge/
│           ├── tier_1/           # synopsis, characters, themes, style, context, cache
│           ├── tier_2/           # arc/scene files
│           ├── tier_3/           # commentaries
│           │   ├── _index.md     # single source of truth for routing metadata
│           │   ├── godard_poetique.md
│           │   └── kristeva_abjection.md
│           └── answers/          # full answers (inside knowledge/ for cache link compat)
│               └── 2026-03-22_chi-e-robinson.md
```

### Key decisions

- **answers/ stays inside knowledge/**: the Q&A cache (`tier_1/08_qa_cache.md`) stores links like `answers/...` relative to `knowledge/`. Moving answers outside would break these links. Keeping `knowledge/answers/` preserves the current format unchanged.
- **lib/ is an installable Python package**: `pyproject.toml` declares `lib` as a package with `pyyaml` as a dependency. Install with `uv pip install -e .` from repo root. This means `from lib.loader import ...` works from any working directory — no `sys.path` hacks needed.
- **You `cd books/voyage/` for Claude Code** (so the right CLAUDE.md loads), but **all Python CLI invocations use paths relative to the book directory**, resolved by the lib functions. Since lib is installed as a package, imports work regardless of cwd.

## Package Setup

`pyproject.toml` at repo root:

```toml
[project]
name = "book-expert"
version = "0.2.0"
requires-python = ">=3.11"
dependencies = ["pyyaml"]

[tool.setuptools.packages.find]
include = ["lib*"]
```

After cloning: `uv pip install -e .` makes `lib` importable everywhere.

## Preferences System

### Global defaults (`preferences.yaml` at root)

```yaml
language: italiano
tone: academic_formal       # academic_formal | conversational | inspired_professor
citation_density: always    # always | on_request | heavy_with_commentary
interpretation_stance: null # null (balanced) | psychoanalytic | marxist | structuralist | historical
answer_length: detailed     # concise | moderate | detailed
```

### Per-book overrides (`books/<slug>/preferences.yaml`)

Sparse — only specify what differs from global. Absent keys inherit from root.

```yaml
citation_density: heavy_with_commentary
```

### How preferences reach Claude

`generate_claude_md.py` merges global + per-book preferences and renders them as natural-language instructions in a `## Response preferences` section of CLAUDE.md. Regenerate only when preferences change.

## Commentary Layer (tier_3)

### `tier_3/_index.md` — single source of truth for routing

```markdown
# Commentaries — Index

## godard_poetique
- **Author**: Henri Godard
- **Work**: Poétique de Céline (1985)
- **Covers**: style, language, narrative technique
- **Arcs**: all (general study)
- **Themes**: oralità, argot, three dots, register mixing
- **Stance**: structuralist / linguistic

## kristeva_abjection
- **Author**: Julia Kristeva
- **Work**: Pouvoirs de l'horreur (1980)
- **Covers**: body, disgust, abjection, maternal
- **Arcs**: 02_08_nave_africa, 02_11_rancy_medicina, 02_12_henrouille
- **Themes**: corpo e malattia, notte e oscurità
- **Stance**: psychoanalytic
```

### Commentary file format

Plain markdown, no frontmatter. All routing metadata lives in `_index.md` only — one source of truth, no drift.

```markdown
# Poétique de Céline — Henri Godard (1985)

## On the "trois points"

Godard argues that Céline's ellipsis points...
```

### Routing

When a query matches an arc or theme that a commentary covers, the agent loads both the tier_2 arc file and the relevant tier_3 commentary — but only if `citation_density` is `heavy_with_commentary` or the user explicitly asks about critical interpretations.

Adding a new commentary: drop a `.md` file in `tier_3/`, add an entry to `_index.md`. No code changes.

## book.yaml — Book-Specific Metadata

Replaces hardcoded routing in loader.py and citation config in cite.py.

```yaml
title: Voyage au bout de la nuit
author: Louis-Ferdinand Céline
year: 1932
language: fr

source_text:
  file: data/voyage-fr.csv
  format: csv
  line_prefix: FR
  line_column: line_id
  text_column: text
  filter_column: chunk_type
  filter_value: main_text

arcs:
  02_01_incipit:
    keywords: [incipit, place clichy, ganate, arruolamento, galera]
    lines: [77, 230]
  02_02_guerra_fronte:
    keywords: [fronte, colonnello, obus, pallottole, fiandre, trincea]
    lines: [230, 1050]
  # ... all 15 arcs

characters:
  robinson:
    arcs: [02_04_guerra_robinson, 02_11_rancy_medicina, 02_12_henrouille, 02_15_sophie_finale]
  lola:
    arcs: [02_05_lola_paris, 02_09_america_newyork]
  # ... all characters
```

## Shared Library (lib/)

All book-agnostic. Installed as a Python package. Each function takes `book_dir` (Path) as argument.

### lib/loader.py
- `load_book_config(book_dir)` — parses book.yaml, merges preferences (global + per-book)
- `load_tier1(book_dir)` — reads knowledge/tier_1/*.md
- `load_tier2_file(book_dir, arc_id)` — reads a specific arc file
- `load_tier3(book_dir, arc_ids, themes)` — reads _index.md, loads matching commentaries
- `route_query(query, config)` — keyword routing driven by book.yaml
- `build_context(query, book_dir)` — orchestrates everything, returns (system_cached, dynamic_context)
- `append_to_qa_cache(book_dir, question, summary, scene_refs, full_answer)` — writes to cache and saves full answer to knowledge/answers/

### lib/cite.py
- `load_lines(book_dir, start, end)` — reads source_text config from book.yaml
- `format_citation(lines)` — same format as today
- CLI entry point: `python -m lib.cite <book_dir> <start> <end>`

### lib/save_qa.py
- `save(book_dir, question, summary, scene_refs, full_answer)` — importable function used by agent.py
- CLI entry point: `python -m lib.save_qa <book_dir> "question" "summary" "refs"`
- Both paths call the same underlying `append_to_qa_cache` in loader.py

### lib/generate_claude_md.py
- Reads book.yaml (title, author, year)
- Merges global + per-book preferences.yaml
- Renders CLAUDE.md with static sections (identity, workflow, behavior rules, preferences)
- Dynamic sections tell Claude to read book.yaml and tier_3/_index.md at runtime
- CLI: `python -m lib.generate_claude_md books/voyage/`

## CLAUDE.md Template

**Static sections (baked in by generator):**
- Identity (from book.yaml title/author/year)
- Response preferences (from merged preferences)
- Workflow steps (with paths relative to book dir)
- Behavior rules (citation precision, interpretation rules, cache rules)
- Commands

**Dynamic sections (read live by Claude):**
- Arc routing → reads book.yaml
- Character routing → reads book.yaml
- Available commentaries → reads knowledge/tier_3/_index.md

This means CLAUDE.md only needs regeneration when preferences or workflow rules change. Knowledge changes (new arcs, new commentaries) are picked up automatically.

## CLAUDE.md Workflow — cite.py and save_qa.py Invocation

Since Claude Code runs from `books/<slug>/` but lib is an installed package, CLAUDE.md instructs:

```markdown
## Tools
- Cite original text: `python -m lib.cite . <start> <end>`
- Save Q&A to cache: `python -m lib.save_qa . "question" "summary" "refs"`
```

The `.` means "current directory" = the book directory. The lib functions resolve all paths from there.

## Migration Plan

```
CURRENT                          →  NEW
──────────────────────────────────────────────
CLAUDE.md                        →  books/voyage/CLAUDE.md (regenerated)
src/agent.py                     →  books/voyage/agent.py (imports from lib)
src/loader.py                    →  lib/loader.py (generic via book.yaml)
cite.py                          →  lib/cite.py (reads source_text config)
save_qa.py                       →  lib/save_qa.py (importable + CLI)
extract_fields.py                →  lib/extract_fields.py
data/voyage-fr.csv               →  books/voyage/data/voyage-fr.csv
data/*.json, *.jsonl             →  books/voyage/data/
knowledge/tier_1/*               →  books/voyage/knowledge/tier_1/
knowledge/tier_2/*               →  books/voyage/knowledge/tier_2/
knowledge/answers/*              →  books/voyage/knowledge/answers/ (stays inside knowledge/)
(new)                            →  books/voyage/knowledge/tier_3/_index.md
(new)                            →  books/voyage/book.yaml
(new)                            →  books/voyage/preferences.yaml
(new)                            →  preferences.yaml (root global)
(new)                            →  lib/__init__.py
(new)                            →  lib/generate_claude_md.py
```

### Code changes
- `pyproject.toml`: add pyyaml dependency, declare lib as package
- `loader.py`: replace ARC_ROUTES dict with book.yaml parser, add load_tier3(), add append_to_qa_cache(book_dir, ...)
- `cite.py`: read CSV path and column config from book.yaml, add `__main__` entry point
- `save_qa.py`: export save() function + `__main__` CLI, both delegate to loader.append_to_qa_cache
- `agent.py`: stays per-book, uses `from lib.loader import ...` and `from lib.cite import ...`

### Unchanged
- Knowledge file formats (tier_1, tier_2 markdown)
- Q&A cache format (links to answers/ relative to knowledge/)
- Answer file format

## Review Log

### 2026-03-27 — Post-review revision
Fixes applied:
- **answers/ stays inside knowledge/**: preserves cache link format (`answers/...` relative to knowledge/)
- **lib/ is an installable package**: eliminates sys.path hacks, works from any cwd
- **pyyaml added as dependency**: explicitly declared in pyproject.toml
- **Commentary metadata single source**: _index.md is canonical, individual files have no frontmatter
- **Write API exported from lib/**: append_to_qa_cache in loader.py, save() in save_qa.py — both importable for agent.py's auto-save and /save command
