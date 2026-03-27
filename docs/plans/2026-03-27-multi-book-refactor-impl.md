# Multi-Book Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor book-expert from single-book hardcoded architecture to multi-book config-driven architecture with shared `lib/` package, commentary layer (tier_3), and preferences system.

**Architecture:** All book-agnostic code moves into an installable `lib/` package. Each book lives in `books/<slug>/` with its own `book.yaml`, knowledge tiers, data, and generated `CLAUDE.md`. Preferences (global + per-book) control response style. Commentary layer (tier_3) adds critical/secondary sources with routing metadata in `_index.md`.

**Tech Stack:** Python 3.11+, PyYAML, pytest, Anthropic SDK

**Design doc:** `docs/plans/2026-03-27-multi-book-refactor-design.md`

---

## Task 1: Package Infrastructure + Test Scaffold

**Files:**
- Modify: `pyproject.toml`
- Create: `lib/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

**Step 1: Update pyproject.toml**

```toml
[project]
name = "book-expert"
version = "0.2.0"
description = "Multi-book literary expert system"
readme = "README.md"
requires-python = ">=3.11"
dependencies = ["pyyaml"]

[project.optional-dependencies]
dev = ["pytest"]

[tool.setuptools.packages.find]
include = ["lib*"]
```

**Step 2: Create lib/__init__.py**

```python
"""book-expert: shared library for multi-book literary expert agents."""
```

**Step 3: Create tests/__init__.py**

Empty file.

**Step 4: Create tests/conftest.py**

This fixture creates a minimal book directory structure for all tests.

```python
import pytest
from pathlib import Path


@pytest.fixture
def book_dir(tmp_path):
    """Create a minimal repo structure with a test book."""
    # Global preferences at repo root (tmp_path is the "repo root")
    (tmp_path / "preferences.yaml").write_text(
        "language: italiano\n"
        "tone: academic_formal\n"
        "citation_density: always\n"
        "interpretation_stance: null\n"
        "answer_length: detailed\n"
    )

    # Book directory: tmp_path/books/test_book/
    bd = tmp_path / "books" / "test_book"
    bd.mkdir(parents=True)

    # book.yaml
    (bd / "book.yaml").write_text(
        "title: Test Book\n"
        "author: Test Author\n"
        "year: 2000\n"
        "language: fr\n"
        "\n"
        "source_text:\n"
        "  file: data/test.csv\n"
        "  format: csv\n"
        "  line_prefix: FR\n"
        "  line_column: line_id\n"
        "  text_column: text\n"
        "  filter_column: chunk_type\n"
        "  filter_value: main_text\n"
        "\n"
        "arcs:\n"
        "  02_01_test_arc:\n"
        "    keywords: [test, beginning, hero]\n"
        "    lines: [1, 3]\n"
        "  02_02_test_arc_two:\n"
        "    keywords: [second, ending]\n"
        "    lines: [4, 5]\n"
        "\n"
        "characters:\n"
        "  hero:\n"
        "    arcs: [02_01_test_arc, 02_02_test_arc_two]\n"
        "  sidekick:\n"
        "    arcs: [02_02_test_arc_two]\n"
    )

    # Per-book preferences override
    (bd / "preferences.yaml").write_text("citation_density: heavy_with_commentary\n")

    # data/test.csv
    data_dir = bd / "data"
    data_dir.mkdir()
    (data_dir / "test.csv").write_text(
        "chunk_id,edition_id,line_id,page,line_no,box,text,text_hash,chunk_type\n"
        "1,1,FR1,1,1,1,First line of the test book.,hash1,main_text\n"
        "2,1,FR2,1,2,1,Second line continues here.,hash2,main_text\n"
        "3,1,FR3,1,3,1,Third line wraps up.,hash3,main_text\n"
        "4,1,FR4,2,1,1,Fourth line starts section two.,hash4,main_text\n"
        "5,1,FR5,2,2,1,Fifth and final line.,hash5,main_text\n"
        "6,1,FR6,2,3,1,A header line.,hash6,page_header\n"
    )

    # knowledge/tier_1
    t1 = bd / "knowledge" / "tier_1"
    t1.mkdir(parents=True)
    (t1 / "00_index.md").write_text("# Index\nTest book index.\n")
    (t1 / "08_qa_cache.md").write_text("# Q&A Cache\n\n---\n")

    # knowledge/tier_2
    t2 = bd / "knowledge" / "tier_2"
    t2.mkdir()
    (t2 / "02_01_test_arc.md").write_text("# Arc 1\nTest arc content.\n")
    (t2 / "02_02_test_arc_two.md").write_text("# Arc 2\nSecond arc content.\n")

    # knowledge/tier_3
    t3 = bd / "knowledge" / "tier_3"
    t3.mkdir()
    (t3 / "_index.md").write_text(
        "# Commentaries — Index\n\n"
        "## test_commentary\n"
        "- **Author**: Test Critic\n"
        "- **Work**: Test Study (2000)\n"
        "- **Covers**: style, themes\n"
        "- **Arcs**: 02_01_test_arc\n"
        "- **Themes**: test theme, darkness\n"
        "- **Stance**: structuralist\n"
    )
    (t3 / "test_commentary.md").write_text("# Test Commentary\n\nSome critical analysis.\n")

    # knowledge/answers
    (bd / "knowledge" / "answers").mkdir()

    return bd
```

**Step 5: Install and verify**

Run: `uv pip install -e ".[dev]"`
Run: `python -c "import lib; print('OK')"`
Expected: prints `OK`

**Step 6: Commit**

```bash
git add pyproject.toml lib/__init__.py tests/__init__.py tests/conftest.py
git commit -m "feat: add lib package infrastructure and test fixtures"
```

---

## Task 2: Config Files (book.yaml + preferences.yaml)

**Files:**
- Create: `preferences.yaml` (repo root — global defaults)
- Create: `books/voyage/book.yaml`
- Create: `books/voyage/preferences.yaml`

**Step 1: Create global preferences.yaml at repo root**

```yaml
language: italiano
tone: academic_formal
citation_density: always
interpretation_stance: null
answer_length: detailed
```

**Step 2: Create books/voyage/book.yaml**

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
    keywords: [incipit, place clichy, ganate, arruolamento, galera, roi misère, preghiera]
    lines: [77, 230]
  02_02_guerra_fronte:
    keywords: [fronte, colonnello, obus, pallottole, fiandre, trincea]
    lines: [230, 1050]
  02_03_guerra_notte:
    keywords: [erranza, notte fiandre, noirceur]
    lines: [1050, 1510]
  02_04_guerra_robinson:
    keywords: [robinson guerra, diserzione, primo robinson, capitano morente]
    lines: [1510, 1770]
  02_05_lola_paris:
    keywords: [lola, beignet, opéra-comique, stand des nations, duval, convalescenza]
    lines: [1770, 2500]
  02_06_musyne_retrovie:
    keywords: [musyne, olympia, princhard, retrovie]
    lines: [2500, 3300]
  02_07_bestombes_teatro:
    keywords: [bestombes, elettroterapia, branledore, teatro, poeta]
    lines: [3300, 4500]
  02_08_nave_africa:
    keywords: [africa, nave, amiral bragueton, colonia, pordurière, foresta, tropici, bambo, piroga]
    lines: [4500, 7400]
  02_09_america_newyork:
    keywords: [new york, america, quarantina, manhattan, grattacieli, ellis island]
    lines: [7400, 8500]
  02_10_detroit_molly:
    keywords: [detroit, ford, fabbrica, molly, catena di montaggio]
    lines: [8500, 9600]
  02_11_rancy_medicina:
    keywords: [rancy, medicina, bébert, pazient, ambulatorio, medico dei poveri]
    lines: [9600, 11500]
  02_12_henrouille:
    keywords: [henrouille, bomba, robinson cieco, protiste, vecchia, nuora]
    lines: [11500, 14600]
  02_13_toulouse:
    keywords: [toulouse, cripta, mummie, morte della vecchia]
    lines: [14600, 15500]
  02_14_vigny_baryton:
    keywords: [vigny, baryton, parapine, manicomio, asilo]
    lines: [15500, 18800]
  02_15_sophie_finale:
    keywords: [sophie, madelon, finale, morte robinson, rimorchiatore, senna, taxi, batignolles]
    lines: [18800, 20500]

characters:
  ganate:
    arcs: [02_01_incipit]
  colonnello:
    arcs: [02_02_guerra_fronte]
  robinson:
    arcs: [02_04_guerra_robinson, 02_11_rancy_medicina, 02_12_henrouille, 02_15_sophie_finale]
  lola:
    arcs: [02_05_lola_paris, 02_09_america_newyork]
  musyne:
    arcs: [02_06_musyne_retrovie]
  molly:
    arcs: [02_10_detroit_molly]
  bébert:
    arcs: [02_11_rancy_medicina]
  baryton:
    arcs: [02_14_vigny_baryton]
  sophie:
    arcs: [02_15_sophie_finale]
  madelon:
    arcs: [02_13_toulouse, 02_14_vigny_baryton, 02_15_sophie_finale]
```

**Step 3: Create books/voyage/preferences.yaml (empty — inherits all global defaults)**

```yaml
# Per-book overrides (sparse — absent keys inherit from global preferences.yaml)
# Uncomment to override:
# citation_density: heavy_with_commentary
```

**Step 4: Verify YAML parses correctly**

Run: `python -c "import yaml; print(yaml.safe_load(open('books/voyage/book.yaml'))['title'])"`
Expected: `Voyage au bout de la nuit`

**Step 5: Commit**

```bash
git add preferences.yaml books/voyage/book.yaml books/voyage/preferences.yaml
git commit -m "feat: add book.yaml and preferences configs for Voyage"
```

---

## Task 3: lib/loader.py — load_book_config (TDD)

**Files:**
- Create: `tests/test_loader.py`
- Create: `lib/loader.py`

**Step 1: Write the failing test**

```python
# tests/test_loader.py
from lib.loader import load_book_config


def test_load_book_config_basic(book_dir):
    config = load_book_config(book_dir)
    assert config["title"] == "Test Book"
    assert config["author"] == "Test Author"
    assert config["year"] == 2000
    assert len(config["arcs"]) == 2
    assert "02_01_test_arc" in config["arcs"]
    assert len(config["characters"]) == 2


def test_load_book_config_merges_preferences(book_dir):
    """Per-book preferences override global defaults."""
    config = load_book_config(book_dir)
    prefs = config["preferences"]
    # Global default
    assert prefs["language"] == "italiano"
    assert prefs["tone"] == "academic_formal"
    # Per-book override
    assert prefs["citation_density"] == "heavy_with_commentary"


def test_load_book_config_source_text(book_dir):
    config = load_book_config(book_dir)
    src = config["source_text"]
    assert src["file"] == "data/test.csv"
    assert src["line_prefix"] == "FR"
    assert src["text_column"] == "text"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_loader.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lib.loader'`

**Step 3: Write minimal implementation**

```python
# lib/loader.py
"""
Knowledge loader for multi-book literary expert system.

All functions take book_dir (Path) as first argument.
Config-driven via book.yaml — no hardcoded routing.
"""

import yaml
from pathlib import Path


def load_book_config(book_dir: Path) -> dict:
    """Parse book.yaml and merge global + per-book preferences."""
    config = yaml.safe_load((book_dir / "book.yaml").read_text(encoding="utf-8"))

    # Global preferences: repo root is book_dir/../../
    root_dir = book_dir.parent.parent
    global_prefs = {}
    global_path = root_dir / "preferences.yaml"
    if global_path.exists():
        global_prefs = yaml.safe_load(global_path.read_text(encoding="utf-8")) or {}

    # Per-book preferences override globals
    book_prefs = {}
    book_path = book_dir / "preferences.yaml"
    if book_path.exists():
        book_prefs = yaml.safe_load(book_path.read_text(encoding="utf-8")) or {}

    config["preferences"] = {**global_prefs, **book_prefs}
    return config
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_loader.py -v`
Expected: 3 passed

**Step 5: Commit**

```bash
git add lib/loader.py tests/test_loader.py
git commit -m "feat: add load_book_config with preference merging"
```

---

## Task 4: lib/loader.py — route_query (TDD)

**Files:**
- Modify: `tests/test_loader.py`
- Modify: `lib/loader.py`

**Step 1: Write the failing tests**

Append to `tests/test_loader.py`:

```python
from lib.loader import load_book_config, route_query


def test_route_query_keyword(book_dir):
    config = load_book_config(book_dir)
    arcs = route_query("tell me about the beginning", config)
    assert "02_01_test_arc" in arcs


def test_route_query_character(book_dir):
    config = load_book_config(book_dir)
    arcs = route_query("what happens to hero?", config)
    assert "02_01_test_arc" in arcs
    assert "02_02_test_arc_two" in arcs


def test_route_query_line_ref(book_dir):
    config = load_book_config(book_dir)
    arcs = route_query("explain L2", config)
    assert "02_01_test_arc" in arcs


def test_route_query_sc_ref(book_dir):
    config = load_book_config(book_dir)
    arcs = route_query("what is SC_00002?", config)
    assert "02_01_test_arc" in arcs


def test_route_query_no_match(book_dir):
    config = load_book_config(book_dir)
    arcs = route_query("completely unrelated query", config)
    assert arcs == []


def test_route_query_cap_at_four(book_dir):
    config = load_book_config(book_dir)
    arcs = route_query("test beginning second ending hero sidekick", config)
    assert len(arcs) <= 4
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_loader.py::test_route_query_keyword -v`
Expected: FAIL — `ImportError: cannot import name 'route_query'`

**Step 3: Write implementation**

Add to `lib/loader.py`:

```python
import re


def route_query(query: str, config: dict) -> list[str]:
    """Route a query to relevant tier_2 arc files using config from book.yaml."""
    query_lower = query.lower()
    matched_arcs = []

    # Keyword matching against arc keywords
    for arc_id, arc_config in config["arcs"].items():
        for kw in arc_config["keywords"]:
            if kw in query_lower:
                if arc_id not in matched_arcs:
                    matched_arcs.append(arc_id)
                break

    # SC_xxxxx references — approximate: SC number maps to line range
    for sc_num_str in re.findall(r"SC_?(\d{3,5})", query, re.IGNORECASE):
        sc_line = int(sc_num_str)
        for arc_id, arc_config in config["arcs"].items():
            lo, hi = arc_config["lines"]
            if lo <= sc_line <= hi and arc_id not in matched_arcs:
                matched_arcs.append(arc_id)

    # Line references (L1234)
    for line_str in re.findall(r"L(\d{1,5})", query):
        line_num = int(line_str)
        for arc_id, arc_config in config["arcs"].items():
            lo, hi = arc_config["lines"]
            if lo <= line_num <= hi and arc_id not in matched_arcs:
                matched_arcs.append(arc_id)

    # Character routing
    for char_name, char_config in config.get("characters", {}).items():
        if char_name in query_lower:
            for arc_id in char_config["arcs"]:
                if arc_id not in matched_arcs:
                    matched_arcs.append(arc_id)

    return matched_arcs[:4]
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_loader.py -v`
Expected: all passed

**Step 5: Commit**

```bash
git add lib/loader.py tests/test_loader.py
git commit -m "feat: add config-driven route_query"
```

---

## Task 5: lib/loader.py — Tier Loading (TDD)

**Files:**
- Modify: `tests/test_loader.py`
- Modify: `lib/loader.py`

**Step 1: Write the failing tests**

Append to `tests/test_loader.py`:

```python
from lib.loader import load_tier1, load_tier2_file, load_tier3


def test_load_tier1(book_dir):
    content = load_tier1(book_dir)
    assert "Index" in content
    assert "Q&A Cache" in content
    assert "00_index.md" in content


def test_load_tier2_file(book_dir):
    content = load_tier2_file(book_dir, "02_01_test_arc")
    assert "Arc 1" in content
    assert "Test arc content" in content


def test_load_tier2_file_missing(book_dir):
    content = load_tier2_file(book_dir, "02_99_nonexistent")
    assert content == ""


def test_load_tier3_arc_match(book_dir):
    result = load_tier3(book_dir, ["02_01_test_arc"])
    assert "Test Commentary" in result
    assert "critical analysis" in result


def test_load_tier3_no_match(book_dir):
    result = load_tier3(book_dir, ["02_99_nonexistent"])
    assert result == ""


def test_load_tier3_theme_match(book_dir):
    result = load_tier3(book_dir, [], query="darkness in the novel")
    assert "Test Commentary" in result


def test_load_tier3_missing_index(book_dir):
    """Gracefully handle missing tier_3."""
    import shutil
    shutil.rmtree(book_dir / "knowledge" / "tier_3")
    result = load_tier3(book_dir, ["02_01_test_arc"])
    assert result == ""
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_loader.py::test_load_tier1 -v`
Expected: FAIL — `ImportError: cannot import name 'load_tier1'`

**Step 3: Write implementation**

Add to `lib/loader.py`:

```python
def load_tier1(book_dir: Path) -> str:
    """Load all tier_1 files concatenated. Goes in cached system prompt."""
    tier1_dir = book_dir / "knowledge" / "tier_1"
    parts = []
    for filepath in sorted(tier1_dir.glob("*.md")):
        text = filepath.read_text(encoding="utf-8")
        parts.append(f"<!-- FILE: {filepath.name} -->\n{text}")
    return "\n\n---\n\n".join(parts)


def load_tier2_file(book_dir: Path, arc_id: str) -> str:
    """Load a specific tier_2 arc file."""
    filepath = book_dir / "knowledge" / "tier_2" / f"{arc_id}.md"
    if filepath.exists():
        return filepath.read_text(encoding="utf-8")
    return ""


def _parse_tier3_index(index_text: str) -> list[dict]:
    """Parse tier_3/_index.md into list of {slug, arcs, themes}."""
    entries = []
    current = None
    for line in index_text.split("\n"):
        if line.startswith("## "):
            if current:
                entries.append(current)
            current = {"slug": line[3:].strip(), "arcs": [], "themes": []}
        elif current:
            if line.startswith("- **Arcs**:"):
                val = line.split(":", 1)[1].strip()
                if val.lower().startswith("all"):
                    current["arcs"] = ["__all__"]
                else:
                    current["arcs"] = [a.strip() for a in val.split(",")]
            elif line.startswith("- **Themes**:"):
                val = line.split(":", 1)[1].strip()
                current["themes"] = [t.strip().lower() for t in val.split(",")]
    if current:
        entries.append(current)
    return entries


def load_tier3(book_dir: Path, arc_ids: list[str], query: str = "") -> str:
    """Load commentaries matching arc_ids or query theme keywords."""
    index_path = book_dir / "knowledge" / "tier_3" / "_index.md"
    if not index_path.exists():
        return ""

    entries = _parse_tier3_index(index_path.read_text(encoding="utf-8"))
    tier3_dir = index_path.parent
    query_lower = query.lower()
    matched = []

    for entry in entries:
        # Arc match: entry covers one of the requested arcs, or covers "all"
        arc_match = "__all__" in entry["arcs"] or bool(
            set(entry["arcs"]) & set(arc_ids)
        )
        # Theme match: any entry theme keyword appears in query
        theme_match = any(t in query_lower for t in entry["themes"]) if query_lower else False

        if arc_match or theme_match:
            filepath = tier3_dir / f"{entry['slug']}.md"
            if filepath.exists():
                matched.append(filepath.read_text(encoding="utf-8"))

    return "\n\n---\n\n".join(matched)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_loader.py -v`
Expected: all passed

**Step 5: Commit**

```bash
git add lib/loader.py tests/test_loader.py
git commit -m "feat: add tier loading (tier_1, tier_2, tier_3 with commentary routing)"
```

---

## Task 6: lib/loader.py — build_context + QA Cache (TDD)

**Files:**
- Modify: `tests/test_loader.py`
- Modify: `lib/loader.py`

**Step 1: Write the failing tests**

Append to `tests/test_loader.py`:

```python
from lib.loader import build_context, append_to_qa_cache


def test_build_context_with_match(book_dir):
    system, dynamic = build_context("tell me about the beginning", book_dir)
    assert "Index" in system  # tier_1 loaded
    assert "Arc 1" in dynamic  # matched tier_2 loaded


def test_build_context_no_match(book_dir):
    system, dynamic = build_context("completely unrelated", book_dir)
    assert "Index" in system
    assert dynamic == ""


def test_build_context_with_commentary(book_dir):
    """When citation_density is heavy_with_commentary, tier_3 is included."""
    # The fixture's per-book prefs set citation_density: heavy_with_commentary
    system, dynamic = build_context("tell me about the beginning", book_dir)
    assert "Test Commentary" in dynamic


def test_append_to_qa_cache(book_dir):
    append_to_qa_cache(book_dir, "Test Q?", "Test summary.", "SC_00001", "Full answer.")
    cache = (book_dir / "knowledge" / "tier_1" / "08_qa_cache.md").read_text()
    assert "## Q: Test Q?" in cache
    assert "Test summary." in cache
    assert "SC_00001" in cache
    # Full answer file created
    answers = list((book_dir / "knowledge" / "answers").glob("*.md"))
    assert len(answers) == 1
    content = answers[0].read_text()
    assert "Full answer." in content


def test_append_to_qa_cache_links_answer(book_dir):
    append_to_qa_cache(book_dir, "Q2?", "Summary2.", full_answer="Answer2.")
    cache = (book_dir / "knowledge" / "tier_1" / "08_qa_cache.md").read_text()
    assert "**Risposta completa**:" in cache
    assert "answers/" in cache
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_loader.py::test_build_context_with_match -v`
Expected: FAIL — `ImportError: cannot import name 'build_context'`

**Step 3: Write implementation**

Add to `lib/loader.py`:

```python
from datetime import date


def build_context(query: str, book_dir: Path) -> tuple[str, str]:
    """
    Build full context for a query.
    Returns: (system_prompt_cached, dynamic_context)
    """
    config = load_book_config(book_dir)
    system_prompt = load_tier1(book_dir)

    arc_ids = route_query(query, config)
    dynamic_parts = []

    # Load matched tier_2 arcs
    for arc_id in arc_ids:
        content = load_tier2_file(book_dir, arc_id)
        if content:
            dynamic_parts.append(f"<!-- ARC: {arc_id} -->\n{content}")

    # Load tier_3 commentaries if citation_density requires it
    prefs = config.get("preferences", {})
    if prefs.get("citation_density") == "heavy_with_commentary":
        commentary = load_tier3(book_dir, arc_ids, query=query)
        if commentary:
            dynamic_parts.append(f"<!-- COMMENTARY -->\n{commentary}")

    dynamic_context = "\n\n---\n\n".join(dynamic_parts) if dynamic_parts else ""
    return system_prompt, dynamic_context


def append_to_qa_cache(book_dir: Path, question: str, summary: str,
                       scene_refs: str = "", full_answer: str = ""):
    """Append a Q&A pair to cache and optionally save the full answer."""
    knowledge_dir = book_dir / "knowledge"
    cache_path = knowledge_dir / "tier_1" / "08_qa_cache.md"
    answers_dir = knowledge_dir / "answers"
    today = date.today().isoformat()

    # Save full answer as .md file
    answer_file = None
    if full_answer:
        answers_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "-", question.lower().strip())[:60].strip("-")
        answer_file = answers_dir / f"{today}_{slug}.md"
        content = f"# {question}\n\n**Data**: {today}\n**SC di riferimento**: {scene_refs}\n\n{full_answer}\n"
        answer_file.write_text(content, encoding="utf-8")

    # Append summary to cache
    entry = f"\n\n## Q: {question}\n"
    if scene_refs:
        entry += f"**SC di riferimento**: {scene_refs}\n"
    entry += f"**Risposta**: {summary}\n"
    if answer_file:
        rel = answer_file.relative_to(knowledge_dir)
        entry += f"**Risposta completa**: {rel}\n"
    entry += f"**Data**: {today}\n"

    with open(cache_path, "a", encoding="utf-8") as f:
        f.write(entry)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_loader.py -v`
Expected: all passed

**Step 5: Commit**

```bash
git add lib/loader.py tests/test_loader.py
git commit -m "feat: add build_context and append_to_qa_cache"
```

---

## Task 7: lib/cite.py (TDD)

**Files:**
- Create: `tests/test_cite.py`
- Create: `lib/cite.py`

**Step 1: Write the failing tests**

```python
# tests/test_cite.py
from lib.cite import load_lines, format_citation


def test_load_lines(book_dir):
    lines = load_lines(book_dir, 1, 3)
    assert len(lines) == 3
    assert lines[0] == ("FR1", "First line of the test book.")
    assert lines[2] == ("FR3", "Third line wraps up.")


def test_load_lines_filters_non_main_text(book_dir):
    """FR6 is page_header — should be filtered out."""
    lines = load_lines(book_dir, 1, 6)
    assert len(lines) == 5
    assert all(lid != "FR6" for lid, _ in lines)


def test_load_lines_empty_range(book_dir):
    lines = load_lines(book_dir, 100, 200)
    assert lines == []


def test_format_citation_multiple():
    lines = [("FR1", "Hello."), ("FR2", "World.")]
    result = format_citation(lines)
    assert result == "> «Hello. World.» (FR1–FR2)"


def test_format_citation_single():
    lines = [("FR1", "Hello.")]
    result = format_citation(lines)
    assert result == "> «Hello.» (FR1)"


def test_format_citation_empty():
    result = format_citation([])
    assert "no main_text" in result
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cite.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lib.cite'`

**Step 3: Write implementation**

```python
# lib/cite.py
"""
Extract and format original text citations from a book's source CSV.

CLI: python -m lib.cite <book_dir> <start_line> <end_line>
"""

import csv
import sys
from pathlib import Path

from lib.loader import load_book_config


def load_lines(book_dir: Path, start: int, end: int) -> list[tuple[str, str]]:
    """Return [(line_id, text), ...] for main_text lines in [start, end]."""
    config = load_book_config(book_dir)
    src = config["source_text"]
    csv_path = book_dir / src["file"]
    prefix = src["line_prefix"]
    line_col = src["line_column"]
    text_col = src["text_column"]
    filter_col = src["filter_column"]
    filter_val = src["filter_value"]

    target_ids = {f"{prefix}{n}" for n in range(start, end + 1)}
    results = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row[line_col] in target_ids and row[filter_col] == filter_val:
                results.append((row[line_col], row[text_col]))
    return results


def format_citation(lines: list[tuple[str, str]]) -> str:
    """Join lines into a blockquote with line range reference."""
    if not lines:
        return "(no main_text lines found in this range)"
    first_id = lines[0][0]
    last_id = lines[-1][0]
    text = " ".join(t for _, t in lines)
    ref = first_id if first_id == last_id else f"{first_id}–{last_id}"
    return f"> «{text}» ({ref})"


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(f"Usage: python -m lib.cite <book_dir> <start_line> <end_line>")
        print(f"Example: python -m lib.cite . 77 80")
        sys.exit(1)
    book_dir = Path(sys.argv[1])
    start, end = int(sys.argv[2]), int(sys.argv[3])
    lines = load_lines(book_dir, start, end)
    print(format_citation(lines))
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cite.py -v`
Expected: all passed

**Step 5: Commit**

```bash
git add lib/cite.py tests/test_cite.py
git commit -m "feat: add config-driven cite.py with CLI"
```

---

## Task 8: lib/save_qa.py (TDD)

**Files:**
- Create: `tests/test_save_qa.py`
- Create: `lib/save_qa.py`

**Step 1: Write the failing tests**

```python
# tests/test_save_qa.py
from lib.save_qa import save


def test_save_basic(book_dir):
    save(book_dir, "Test question?", "Test summary.", "SC_00001", "Full answer text.")
    cache = (book_dir / "knowledge" / "tier_1" / "08_qa_cache.md").read_text()
    assert "## Q: Test question?" in cache
    assert "Test summary." in cache
    assert "SC_00001" in cache


def test_save_creates_answer_file(book_dir):
    save(book_dir, "Q?", "S.", "SC_00001", "Full answer.")
    answers = list((book_dir / "knowledge" / "answers").glob("*.md"))
    assert len(answers) == 1
    assert "Full answer." in answers[0].read_text()


def test_save_without_full_answer(book_dir):
    save(book_dir, "Q?", "S.", "SC_00001")
    cache = (book_dir / "knowledge" / "tier_1" / "08_qa_cache.md").read_text()
    assert "## Q: Q?" in cache
    # No answer file created
    answers = list((book_dir / "knowledge" / "answers").glob("*.md"))
    assert len(answers) == 0
    # No "Risposta completa" link
    assert "Risposta completa" not in cache
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_save_qa.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lib.save_qa'`

**Step 3: Write implementation**

```python
# lib/save_qa.py
"""
Save validated Q&A pairs to the book's cache.

Importable: from lib.save_qa import save
CLI: python -m lib.save_qa <book_dir> "question" "summary" "sc_refs" [--link path]
"""

import sys
from pathlib import Path

from lib.loader import append_to_qa_cache


def save(book_dir: Path, question: str, summary: str,
         scene_refs: str = "", full_answer: str = ""):
    """Save a Q&A pair. Delegates to loader.append_to_qa_cache."""
    append_to_qa_cache(book_dir, question, summary, scene_refs, full_answer)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python -m lib.save_qa <book_dir> <question> <summary> [sc_refs] [--link path]")
        sys.exit(1)

    book_dir = Path(sys.argv[1])
    question = sys.argv[2]
    summary = sys.argv[3]

    # Parse sc_refs (4th positional arg, if not a flag)
    sc_refs = ""
    remaining = sys.argv[4:]
    if remaining and not remaining[0].startswith("--"):
        sc_refs = remaining.pop(0)

    # Handle --link: link to an existing answer file
    full_answer = ""
    if "--link" in remaining:
        idx = remaining.index("--link")
        if idx + 1 < len(remaining):
            linked = Path(remaining[idx + 1])
            knowledge_dir = book_dir / "knowledge"
            if not linked.is_absolute():
                linked = knowledge_dir / linked
            if not linked.exists():
                print(f"Error: --link target does not exist: {linked}")
                sys.exit(1)
            # For --link, we skip full_answer (file already exists).
            # Just write cache entry with the link.
            from lib.loader import load_book_config
            from datetime import date
            import re
            today = date.today().isoformat()
            cache_path = knowledge_dir / "tier_1" / "08_qa_cache.md"
            entry = f"\n\n## Q: {question}\n"
            if sc_refs:
                entry += f"**SC di riferimento**: {sc_refs}\n"
            entry += f"**Risposta**: {summary}\n"
            entry += f"**Risposta completa**: {linked.relative_to(knowledge_dir)}\n"
            entry += f"**Data**: {today}\n"
            with open(cache_path, "a", encoding="utf-8") as f:
                f.write(entry)
            print(f"Linked to {linked.relative_to(knowledge_dir)}")
            sys.exit(0)

    save(book_dir, question, summary, sc_refs, full_answer)
    print(f"Saved to cache.")
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_save_qa.py -v`
Expected: all passed

**Step 5: Commit**

```bash
git add lib/save_qa.py tests/test_save_qa.py
git commit -m "feat: add save_qa.py (importable + CLI)"
```

---

## Task 9: lib/generate_claude_md.py (TDD)

**Files:**
- Create: `tests/test_generate.py`
- Create: `lib/generate_claude_md.py`

**Step 1: Write the failing tests**

```python
# tests/test_generate.py
from lib.generate_claude_md import generate


def test_generate_contains_identity(book_dir):
    result = generate(book_dir)
    assert "Test Book" in result
    assert "Test Author" in result
    assert "2000" in result


def test_generate_contains_tools(book_dir):
    result = generate(book_dir)
    assert "python -m lib.cite" in result
    assert "python -m lib.save_qa" in result


def test_generate_contains_dynamic_routing(book_dir):
    result = generate(book_dir)
    assert "book.yaml" in result
    assert "tier_3/_index.md" in result


def test_generate_contains_preferences(book_dir):
    result = generate(book_dir)
    # Per-book override: heavy_with_commentary
    assert "commentary" in result.lower() or "commentar" in result.lower()


def test_generate_contains_workflow(book_dir):
    result = generate(book_dir)
    assert "cache" in result.lower()
    assert "tier_1" in result
    assert "tier_2" in result
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_generate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lib.generate_claude_md'`

**Step 3: Write implementation**

```python
# lib/generate_claude_md.py
"""
Generate CLAUDE.md for a book from book.yaml + merged preferences.

CLI: python -m lib.generate_claude_md <book_dir>
"""

import sys
from pathlib import Path

from lib.loader import load_book_config


TONE_TEXT = {
    "academic_formal": "Use a formal academic tone with precise literary terminology.",
    "conversational": "Use a conversational, accessible tone while maintaining accuracy.",
    "inspired_professor": "Channel an inspired professor: passionate, erudite, with vivid examples and personal asides.",
}

CITATION_TEXT = {
    "always": "Every substantive answer MUST include at least one original passage from the text.",
    "on_request": "Include original text passages when the user explicitly asks or when directly relevant to the analysis.",
    "heavy_with_commentary": "Include extensive original passages AND relevant critical commentary from tier_3 sources.",
}

STANCE_TEXT = {
    "null": "Present balanced interpretations without favoring any single critical school.",
    "psychoanalytic": "Favor psychoanalytic readings (Freud, Lacan, Kristeva) while acknowledging alternatives.",
    "marxist": "Favor materialist/Marxist readings while acknowledging alternatives.",
    "structuralist": "Favor structuralist/linguistic readings while acknowledging alternatives.",
    "historical": "Favor historical/biographical readings while acknowledging alternatives.",
}

LENGTH_TEXT = {
    "concise": "Keep answers concise: 2-4 paragraphs maximum.",
    "moderate": "Provide moderate-length answers: 4-6 paragraphs.",
    "detailed": "Provide detailed, thorough answers with full analysis and multiple examples.",
}


def _render_preferences(prefs: dict) -> str:
    """Render preferences as natural-language instructions."""
    lines = []
    lang = prefs.get("language", "italiano")
    lines.append(f"- **Language**: Answer in {lang} unless the user writes in another language, in which case match theirs.")
    tone = prefs.get("tone", "academic_formal")
    lines.append(f"- **Tone**: {TONE_TEXT.get(tone, tone)}")
    cite = prefs.get("citation_density", "always")
    lines.append(f"- **Citation density**: {CITATION_TEXT.get(cite, cite)}")
    stance = str(prefs.get("interpretation_stance", "null"))
    lines.append(f"- **Interpretation stance**: {STANCE_TEXT.get(stance, stance)}")
    length = prefs.get("answer_length", "detailed")
    lines.append(f"- **Answer length**: {LENGTH_TEXT.get(length, length)}")
    return "\n".join(lines)


def generate(book_dir: Path) -> str:
    """Generate CLAUDE.md content for a book."""
    config = load_book_config(book_dir)
    prefs = config.get("preferences", {})
    src = config.get("source_text", {})
    prefs_section = _render_preferences(prefs)
    cite_density = prefs.get("citation_density", "always")

    # Commentary instruction varies by citation_density
    commentary_instruction = ""
    if cite_density == "heavy_with_commentary":
        commentary_instruction = (
            "5. **Check commentaries**: read `knowledge/tier_3/_index.md` and load matching critical sources\n"
        )
    else:
        commentary_instruction = (
            "5. **Check commentaries** (if user asks about criticism): read `knowledge/tier_3/_index.md`\n"
        )

    return f"""# {config['title']} — Expert Agent

## Identity
You are a literary expert on {config['author']}'s *{config['title']}* ({config['year']}).
You have access to a structured knowledge base covering the entire novel: scenes,
narrative arcs, detailed character profiles, thematic analysis, and style notes.

## Workflow — follow these steps for EVERY query

1. **Check cache first**: read `knowledge/tier_1/08_qa_cache.md` — if the answer is there, use it directly
2. **Read tier_1 files**: always read the relevant files from `knowledge/tier_1/` for context
3. **Route to tier_2 if needed**: read `book.yaml` for arc keywords and line ranges, then load the matching `knowledge/tier_2/02_*.md` file
4. **Cite the original text**: use cite tool to find and quote relevant passages (see "Tools" below)
{commentary_instruction}6. **Answer the question** using the knowledge files, original text, and any commentaries
7. **Save to cache**: after answering, ALWAYS do two steps:

   **Step A** — Use the **Write** tool to save your COMPLETE answer to:
   `knowledge/answers/YYYY-MM-DD_<slug>.md`

   **Step B** — Run save_qa tool to add the cache entry:
   `python -m lib.save_qa . "the question" "compact 2-4 sentence summary" "SC_xxxxx, SC_yyyyy" --link answers/YYYY-MM-DD_<slug>.md`

## Knowledge architecture

### Tier 1 — Always loaded (cached in system prompt)
Located in `knowledge/tier_1/`:
- `00_index.md` — Master index with file map
- `01_synopsis.md` — Complete plot summary
- `03_characters.md` — All characters with arcs, traits, relations
- `04_themes.md` — Themes with descriptions and distributions
- `05_style.md` — Narrative techniques, language, metaphors
- `06_context.md` — Author biography, publication history, reception
- `08_qa_cache.md` — Previously validated Q&A pairs

### Tier 2 — Loaded on demand
Located in `knowledge/tier_2/`. Arc files containing scene summaries.
Route queries using arc keywords and line ranges defined in `book.yaml`.

### Tier 3 — Critical commentaries
Located in `knowledge/tier_3/`. Secondary/critical sources.
Read `knowledge/tier_3/_index.md` for routing metadata (which arcs/themes each commentary covers).
Load a commentary when its arcs or themes match the query.

### Original text — `{src.get('file', 'data/source.csv')}`
The complete original text in CSV format.
- Line IDs use prefix `{src.get('line_prefix', 'FR')}` (e.g., `{src.get('line_prefix', 'FR')}77`).
  Scene files use `L` references: `L77` = `{src.get('line_prefix', 'FR')}77`.
- Do NOT read the CSV directly — always use the cite tool.

### Full answers — `knowledge/answers/`
Complete answers with citations, saved as individual `.md` files.
Referenced from `08_qa_cache.md` via `**Risposta completa**:` field.

## Tools

- **Cite original text**: `python -m lib.cite . <start_line> <end_line>`
  Example: `python -m lib.cite . 77 80`
- **Save Q&A to cache**: `python -m lib.save_qa . "question" "summary" "SC_refs" --link answers/YYYY-MM-DD_<slug>.md`

## Response preferences

{prefs_section}

## Behavior rules

### Original text citation — MANDATORY
- Use the cite tool to retrieve passages by line range
- When a scene spans many lines, cite the most significant 2-5 lines
- After the original quote, provide your analysis

### Citation precision
- Always reference specific scenes: "In SC_00367 (L1880–1888), ..."
- Cross-reference characters and themes to their dedicated tier_1 files

### Interpretation
- Distinguish literal (what the text says), figurative (what it suggests), and ideological (worldview)
- Present interpretations as readings: "This can be read as..." not "This means..."
- When the knowledge base doesn't cover something, say so explicitly

### Q&A cache — IMPORTANT
- **Before answering**: check `knowledge/tier_1/08_qa_cache.md`
- **After every substantive answer**: save to cache (see workflow step 7)
- Keep cached summaries compact (2-4 sentences)

## Dynamic routing

Read `book.yaml` at query time for:
- **Arc routing**: `arcs` section maps arc IDs to keywords and line ranges
- **Character routing**: `characters` section maps names to their arcs

Read `knowledge/tier_3/_index.md` for:
- **Commentary routing**: which arcs/themes each commentary covers

## Commands

- `/ask <question>` — Answer a question about the novel
- `/scene <SC_ID>` — Show details of a specific scene
- `/arc <name>` — Summarize a narrative arc
- `/character <name>` — Character profile
- `/theme <name>` — Theme analysis
- `/compare <A> vs <B>` — Compare characters, arcs, or themes
- `/cache` — Show current Q&A cache contents
"""


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m lib.generate_claude_md <book_dir>")
        sys.exit(1)
    book_dir = Path(sys.argv[1])
    result = generate(book_dir)
    output = book_dir / "CLAUDE.md"
    output.write_text(result, encoding="utf-8")
    print(f"Generated {output}")
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_generate.py -v`
Expected: all passed

**Step 5: Commit**

```bash
git add lib/generate_claude_md.py tests/test_generate.py
git commit -m "feat: add CLAUDE.md generator with preferences rendering"
```

---

## Task 10: File Migration

Move existing data and knowledge into the `books/voyage/` directory.

**Files:**
- Move: `data/` → `books/voyage/data/`
- Move: `knowledge/` → `books/voyage/knowledge/`
- Create: `books/voyage/knowledge/tier_3/_index.md`

**Step 1: Create books/voyage/ directory structure**

Run: `mkdir -p books/voyage`

**Step 2: Move data/**

Run: `git mv data books/voyage/data`

**Step 3: Move knowledge/**

Run: `git mv knowledge books/voyage/knowledge`

**Step 4: Create tier_3 directory and index**

Run: `mkdir -p books/voyage/knowledge/tier_3`

Create `books/voyage/knowledge/tier_3/_index.md`:

```markdown
# Commentaries — Index

<!-- Add commentary entries below. Format:
## slug_name
- **Author**: Name
- **Work**: Title (Year)
- **Covers**: what aspects
- **Arcs**: arc_ids or "all"
- **Themes**: theme keywords (lowercase, comma-separated)
- **Stance**: critical school

Then create a matching slug_name.md file in this directory.
-->
```

**Step 5: Verify structure**

Run: `ls books/voyage/data/voyage-fr.csv && ls books/voyage/knowledge/tier_1/00_index.md && ls books/voyage/knowledge/tier_3/_index.md`
Expected: all three files listed

**Step 6: Commit**

```bash
git add books/voyage/knowledge/tier_3/_index.md
git commit -m "refactor: move data and knowledge into books/voyage/"
```

---

## Task 11: books/voyage/agent.py

Adapt the existing agent to use the new `lib/` package with `book_dir` parameter.

**Files:**
- Create: `books/voyage/agent.py` (adapted from `src/agent.py`)

**Step 1: Create the adapted agent**

```python
# books/voyage/agent.py
"""
Voyage au bout de la nuit — Expert Agent

Uses Anthropic API with prompt caching:
- Tier 1 knowledge is cached in the system prompt (refreshed every 5 min)
- Tier 2 arc files are loaded dynamically per query
- Q&A cache grows over time to avoid re-derivation
"""

import re
import anthropic
from pathlib import Path

from lib.loader import build_context, route_query, load_book_config, append_to_qa_cache
from lib.cite import load_lines, format_citation

# ── Configuration ─────────────────────────────────────────
BOOK_DIR = Path(".")
MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 4096

AGENT_IDENTITY = """You are a literary expert on Céline's Voyage au bout de la nuit.
You answer questions using the structured knowledge base provided.

Rules:
- Answer in the user's language
- Cite specific scenes: "In SC_00367 (L1880), Bardamu..."
- Distinguish literal / figurative / ideological readings
- Say explicitly when the knowledge base doesn't cover something
- After answering, suggest which scenes the user might want to explore next
"""


# ── Citation post-processing ─────────────────────────────
_CITE_RE = re.compile(r"\(L(\d+)\s*[–\-]\s*L?(\d+)\)")


def append_citations(answer: str) -> str:
    """Parse L-range references and append French text as citations."""
    matches = _CITE_RE.findall(answer)
    if not matches:
        return answer

    seen = set()
    unique_ranges = []
    for start_s, end_s in matches:
        key = (int(start_s), int(end_s))
        if key not in seen:
            seen.add(key)
            unique_ranges.append(key)

    citations = []
    for start, end in unique_ranges:
        lines = load_lines(BOOK_DIR, start, end)
        if lines:
            citations.append(format_citation(lines))

    if not citations:
        return answer

    return answer + "\n\n---\n### Citazioni\n\n" + "\n\n".join(citations)


def create_client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


def ask(client: anthropic.Anthropic, query: str, conversation: list = None) -> str:
    """Send a query to the expert agent with prompt caching."""
    config = load_book_config(BOOK_DIR)
    system_cached, dynamic_context = build_context(query, BOOK_DIR)

    system_blocks = [
        {"type": "text", "text": AGENT_IDENTITY},
        {
            "type": "text",
            "text": f"<knowledge_base_core>\n{system_cached}\n</knowledge_base_core>",
            "cache_control": {"type": "ephemeral"},
        },
    ]

    messages = conversation or []

    user_content = ""
    if dynamic_context:
        arc_ids = route_query(query, config)
        user_content += f'<knowledge_base_detail arcs="{", ".join(arc_ids)}">\n'
        user_content += dynamic_context
        user_content += "\n</knowledge_base_detail>\n\n"

    user_content += query
    messages.append({"role": "user", "content": user_content})

    response = client.messages.create(
        model=MODEL, max_tokens=MAX_TOKENS, system=system_blocks, messages=messages
    )

    usage = response.usage
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_create = getattr(usage, "cache_creation_input_tokens", 0) or 0

    print(f"\n  [tokens] input={usage.input_tokens} cache_read={cache_read} "
          f"cache_create={cache_create} output={usage.output_tokens}")

    if cache_read > 0:
        print(f"  [cache]  HIT — {cache_read} tokens read from cache")
    elif cache_create > 0:
        print(f"  [cache]  MISS — {cache_create} tokens written to cache")

    answer = ""
    for block in response.content:
        if block.type == "text":
            answer += block.text

    return append_citations(answer)


def interactive_session():
    """Run an interactive Q&A session."""
    client = create_client()
    conversation = []

    print("=" * 60)
    print("  VOYAGE AU BOUT DE LA NUIT — Expert Agent")
    print("=" * 60)
    print("  Commands:")
    print("    /quit          — Exit")
    print("    /cache         — Show Q&A cache stats")
    print("    /save Q|||A    — Save a Q&A pair to cache")
    print("    /clear         — Clear conversation history")
    print("    (anything else) — Ask a question")
    print("=" * 60)

    while True:
        try:
            query = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nArrivederci.")
            break

        if not query:
            continue

        if query == "/quit":
            print("Arrivederci.")
            break

        if query == "/clear":
            conversation = []
            print("  [conversation cleared]")
            continue

        if query == "/cache":
            cache_path = BOOK_DIR / "knowledge" / "tier_1" / "08_qa_cache.md"
            content = cache_path.read_text(encoding="utf-8")
            q_count = content.count("## Q:")
            print(f"  [cache] {q_count} validated Q&A pairs")
            print(content[-500:] if len(content) > 500 else content)
            continue

        if query.startswith("/save "):
            parts = query[6:].split("|||")
            if len(parts) == 2:
                append_to_qa_cache(BOOK_DIR, parts[0].strip(), parts[1].strip())
                print("  [cache] Q&A pair saved")
            else:
                print("  Usage: /save question text ||| answer text")
            continue

        # Route and answer
        config = load_book_config(BOOK_DIR)
        arc_ids = route_query(query, config)
        if arc_ids:
            print(f"  [routing] Loading: {', '.join(arc_ids)}")
        else:
            print("  [routing] Tier 1 only (no specific arc matched)")

        answer = ask(client, query, conversation)
        print(f"\n{answer}")

        # Auto-save
        sentences = answer.split(". ")
        summary = ". ".join(sentences[:3])
        if len(summary) > 500:
            summary = summary[:497] + "..."
        if not summary.endswith("."):
            summary += "."
        append_to_qa_cache(BOOK_DIR, query, summary, full_answer=answer)
        print("  [saved] Answer cached")

        conversation.append({"role": "user", "content": query})
        conversation.append({"role": "assistant", "content": answer})
        if len(conversation) > 20:
            conversation = conversation[-20:]


if __name__ == "__main__":
    interactive_session()
```

**Step 2: Verify imports resolve**

Run: `cd books/voyage && python -c "from lib.loader import build_context; print('OK')" && cd ../..`
Expected: `OK`

**Step 3: Commit**

```bash
git add books/voyage/agent.py
git commit -m "feat: add books/voyage/agent.py using lib/ package"
```

---

## Task 12: Generate CLAUDE.md + End-to-End Verification

**Files:**
- Generate: `books/voyage/CLAUDE.md`

**Step 1: Generate CLAUDE.md**

Run: `python -m lib.generate_claude_md books/voyage`
Expected: `Generated books/voyage/CLAUDE.md`

**Step 2: Verify generated CLAUDE.md**

Run: `head -5 books/voyage/CLAUDE.md`
Expected: Should show `# Voyage au bout de la nuit — Expert Agent`

**Step 3: Test cite.py CLI from book directory**

Run: `cd books/voyage && python -m lib.cite . 77 80 && cd ../..`
Expected: A blockquote with French text from lines 77-80

**Step 4: Test save_qa.py CLI from book directory**

Run: `cd books/voyage && python -m lib.save_qa . "Test question" "Test summary" "SC_00019" && cd ../..`
Expected: `Saved to cache.`

**Step 5: Run all tests**

Run: `pytest tests/ -v`
Expected: all passed

**Step 6: Commit**

```bash
git add books/voyage/CLAUDE.md
git commit -m "feat: generate books/voyage/CLAUDE.md from config"
```

---

## Task 13: Cleanup + Root CLAUDE.md

Remove old files that have been migrated to `lib/` and `books/voyage/`.

**Files:**
- Delete: `src/loader.py`, `src/agent.py`, `src/__init__.py` (if exists)
- Delete: `cite.py` (root)
- Delete: `save_qa.py` (root)
- Move: `extract_fields.py` → `lib/extract_fields.py`
- Rewrite: `CLAUDE.md` (root — becomes a pointer)

**Step 1: Remove old source files**

Run: `git rm src/loader.py src/agent.py cite.py save_qa.py`
Run: `rmdir src 2>/dev/null; true`

Note: if `src/` has `__init__.py`, remove it too: `git rm src/__init__.py`

**Step 2: Move extract_fields.py**

Run: `git mv extract_fields.py lib/extract_fields.py`

**Step 3: Rewrite root CLAUDE.md**

Replace the root `CLAUDE.md` with a pointer:

```markdown
# Book Expert

Multi-book literary expert system. Each book is a self-contained workspace.

## Setup

```bash
uv pip install -e .
```

## Usage

To work with a specific book, `cd` into its directory:

```bash
cd books/voyage/
```

Claude Code will read the book's `CLAUDE.md` from that directory.

## Adding a new book

1. Create `books/<slug>/` with `book.yaml`, `data/`, `knowledge/`
2. Run `python -m lib.generate_claude_md books/<slug>/`
3. `cd books/<slug>/` and start a Claude Code session
```

**Step 4: Run all tests to confirm nothing is broken**

Run: `pytest tests/ -v`
Expected: all passed

**Step 5: Commit**

```bash
git add -A
git commit -m "refactor: remove old files, update root CLAUDE.md as pointer"
```

---

## Final Directory Structure

```
book-expert/
├── pyproject.toml
├── preferences.yaml
├── CLAUDE.md                    # pointer to book directories
├── lib/
│   ├── __init__.py
│   ├── loader.py
│   ├── cite.py
│   ├── save_qa.py
│   ├── generate_claude_md.py
│   └── extract_fields.py
├── books/
│   └── voyage/
│       ├── CLAUDE.md            # generated
│       ├── book.yaml
│       ├── preferences.yaml
│       ├── agent.py
│       ├── data/
│       │   └── voyage-fr.csv
│       └── knowledge/
│           ├── tier_1/
│           ├── tier_2/
│           ├── tier_3/
│           │   └── _index.md
│           └── answers/
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_loader.py
│   ├── test_cite.py
│   ├── test_save_qa.py
│   └── test_generate.py
└── docs/
    └── plans/
```