# Critical Essays Integration — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Integrate critical essays into the book-expert system using the same preprocessing pipeline as the book, with LLM-as-router for query-time retrieval.

**Architecture:** Each essay goes through stages 0-4 (same as the book), producing a full knowledge base (tier_1 + tier_2) and a YAML descriptor. An aggregated `_index.yaml` provides chapter-level summaries always loaded into the system prompt. The agent routes queries semantically and loads essay tier_2 files on demand via `cite_essay`. No embeddings.

**Tech Stack:** Python, PyYAML, pytest. Existing `lib/` package. No new dependencies.

**Design doc:** `docs/plans/2026-03-31-critical-essays-design.md`

---

## Task 1: Migrate `_index.md` to `_index.yaml` — loader

The foundation: replace the ad-hoc Markdown parser with YAML. This touches `lib/loader.py`, the test fixture, and all loader tests that reference tier_3.

**Files:**
- Modify: `lib/loader.py:84-132` (`_parse_tier3_index`, `load_tier3`)
- Modify: `lib/loader.py:152-157` (`build_context` tier_3 gating)
- Modify: `tests/conftest.py:106-119` (tier_3 fixture)
- Modify: `tests/test_loader.py:93-114` (tier_3 tests)
- Modify: `tests/test_loader.py:129-133` (`build_context_with_commentary` test)

**Step 1: Update the test fixture to create `_index.yaml` instead of `_index.md`**

In `tests/conftest.py`, replace the tier_3 fixture block (lines 106-119):

```python
    # knowledge/tier_3
    t3 = bd / "knowledge" / "tier_3"
    t3.mkdir()
    import yaml as _yaml
    _yaml.safe_dump(
        {"essays": {
            "test_commentary": {
                "author": "Test Critic",
                "work": "Test Study",
                "year": 2000,
                "summary": "A structuralist analysis of style and themes in the test book.",
                "stance": "structuralist",
                "arcs": ["02_01_primato_stile"],
                "themes": ["test theme", "darkness"],
                "characters": ["Céline"],
                "sections": [
                    {
                        "id": 1,
                        "title": "Chapter on Style",
                        "summary": "Analyzes core stylistic techniques.",
                        "start_id": "1",
                        "end_id": "100",
                        "arcs": ["02_01_primato_stile"],
                    },
                ],
            },
        }},
        (t3 / "_index.yaml").open("w"),
        allow_unicode=True,
        sort_keys=False,
    )
```

Remove the line that creates `test_commentary.md` (line 119).

**Step 2: Rewrite `_parse_tier3_index` → `_load_tier3_index` in `lib/loader.py`**

Replace `_parse_tier3_index` (lines 84-105) with:

```python
def _load_tier3_index(book_dir: Path) -> dict:
    """Load tier_3/_index.yaml. Returns the parsed dict or empty."""
    index_path = book_dir / "knowledge" / "tier_3" / "_index.yaml"
    if not index_path.exists():
        return {}
    return yaml.safe_load(index_path.read_text(encoding="utf-8")) or {}
```

**Step 3: Rewrite `load_tier3` to return formatted summaries**

Replace `load_tier3` (lines 108-132) with:

```python
def load_tier3(book_dir: Path, **_kwargs) -> str:
    """Load essay summaries from _index.yaml for system prompt injection.

    Returns formatted chapter-level summaries for all essays.
    Ignores arc_ids/query — the LLM does its own routing.
    """
    data = _load_tier3_index(book_dir)
    essays = data.get("essays", {})
    if not essays:
        return ""

    parts = []
    for slug, info in essays.items():
        lines = [
            f"## {info.get('author', 'Unknown')} — *{info.get('work', slug)}* ({info.get('year', '?')})",
            f"**Stance**: {info.get('stance', 'N/A')}",
            "",
            info.get("summary", ""),
            "",
            "**Sections:**",
        ]
        for sec in info.get("sections", []):
            lines.append(f"- **{sec.get('title', 'Untitled')}**: {sec.get('summary', '')}")
        parts.append("\n".join(lines))

    return "\n\n---\n\n".join(parts)
```

**Step 4: Update `build_context` to always include tier_3 summaries**

Replace lines 152-157 in `build_context`:

```python
    # Load tier_3 essay summaries (always — small fixed cost, LLM routes)
    commentary = load_tier3(book_dir)
    if commentary:
        dynamic_parts.append(f"<!-- ESSAYS -->\n{commentary}")
```

Remove the `citation_density` gate.

**Step 5: Update the tier_3 loader tests**

In `tests/test_loader.py`, replace:

`test_load_tier3_arc_match` (line 93):
```python
def test_load_tier3_arc_match(book_dir):
    result = load_tier3(book_dir)
    assert "Test Critic" in result
    assert "Test Study" in result
    assert "Chapter on Style" in result
```

`test_load_tier3_no_match` (line 99) — remove entirely (no arc filtering anymore).

`test_load_tier3_theme_match` (line 104) — remove entirely (no theme filtering anymore).

`test_load_tier3_missing_index` (line 109):
```python
def test_load_tier3_missing_index(book_dir):
    """Gracefully handle missing tier_3."""
    import shutil
    shutil.rmtree(book_dir / "knowledge" / "tier_3")
    result = load_tier3(book_dir)
    assert result == ""
```

`test_build_context_with_commentary` (line 129):
```python
def test_build_context_with_commentary(book_dir):
    """Essay summaries are always included in dynamic context."""
    system, dynamic = build_context("tell me about the beginning", book_dir)
    assert "Test Critic" in dynamic
    assert "Test Study" in dynamic
```

**Step 6: Update `load_tier3` import in test file**

The import at line 2 of `test_loader.py` already imports `load_tier3` — no change needed.

**Step 7: Run tests**

Run: `cd /home/rp/git/rfflpllcn-llm/book-expert && uv run pytest tests/test_loader.py -v`
Expected: all tests pass (some removed, remaining updated)

**Step 8: Commit**

```bash
git add lib/loader.py tests/conftest.py tests/test_loader.py
git commit -m "refactor: migrate tier_3 from _index.md to _index.yaml with LLM-as-router"
```

---

## Task 2: Migrate `_index.md` to `_index.yaml` — CLAUDE.md generator

Update `generate_claude_md.py` to reference `_index.yaml`, add `cite_essay` tool, and adjust workflow step 5.

**Files:**
- Modify: `lib/generate_claude_md.py:89-98` (commentary instruction)
- Modify: `lib/generate_claude_md.py:140-141` (tier_3 knowledge section)
- Modify: `lib/generate_claude_md.py:151-154` (tools section)
- Modify: `lib/generate_claude_md.py:186-189` (dynamic routing section)
- Modify: `tests/test_generate.py:18-21` (dynamic routing assertion)

**Step 1: Write the failing test**

In `tests/test_generate.py`, update `test_generate_contains_dynamic_routing`:

```python
def test_generate_contains_dynamic_routing(book_dir):
    result = generate(book_dir)
    assert "book.yaml" in result
    assert "_index.yaml" in result
```

**Step 2: Run test to verify it fails**

Run: `cd /home/rp/git/rfflpllcn-llm/book-expert && uv run pytest tests/test_generate.py::test_generate_contains_dynamic_routing -v`
Expected: FAIL — output still contains `_index.md`

**Step 3: Add test for cite_essay tool**

Add to `tests/test_generate.py`:

```python
def test_generate_contains_cite_essay_tool(book_dir):
    """When _index.yaml has entries, cite_essay tool is documented."""
    import yaml as _yaml
    index_path = book_dir / "knowledge" / "tier_3" / "_index.yaml"
    data = _yaml.safe_load(index_path.read_text())
    assert data.get("essays"), "fixture should have essays"
    result = generate(book_dir)
    assert "cite_essay" in result
```

**Step 4: Update `generate_claude_md.py`**

Replace the commentary instruction block (lines 89-98):

```python
    # Commentary / essay instruction varies by citation_density
    # Check if _index.yaml has essay entries
    tier3_index = book_dir / "knowledge" / "tier_3" / "_index.yaml"
    has_essays = False
    if tier3_index.exists():
        import yaml as _y
        _data = _y.safe_load(tier3_index.read_text(encoding="utf-8")) or {}
        has_essays = bool(_data.get("essays"))

    if has_essays:
        cite_essay_doc = (
            "- **Cite essay**: `python -m lib.cite_essay . <slug> <arc_id>`\n"
            "  Loads the analytical summary for a specific arc of a critical essay.\n"
            "  Use `--toc` to see all arcs: `python -m lib.cite_essay . <slug> --toc`\n"
            "  Use `--raw <start> <end>` for exact quotes: `python -m lib.cite_essay . <slug> 100 200 --raw`"
        )
    else:
        cite_essay_doc = ""

    if has_essays and cite_density == "heavy_with_commentary":
        commentary_instruction = (
            "5. **Consult critical essays**: review essay summaries in tier_3, call `cite_essay` for relevant arcs\n"
        )
    elif has_essays:
        commentary_instruction = (
            "5. **Check commentaries** (if user asks about criticism): review essay summaries in tier_3, call `cite_essay` for relevant arcs\n"
        )
    else:
        commentary_instruction = (
            "5. **Check commentaries** (if user asks about criticism): read `knowledge/tier_3/_index.yaml`\n"
        )
```

In the tier_3 knowledge architecture section (around line 140), replace `_index.md` with `_index.yaml`:

```
### Tier 3 — Critical essays
Located in `knowledge/tier_3/`. Routing metadata in `_index.yaml`.
Essay summaries are loaded automatically. Use `cite_essay` to retrieve detailed analysis.
```

In the tools section, add `cite_essay_doc` after the cite tool:

```python
{cite_tool_doc}
{cite_essay_doc}
- **Save Q&A to cache**: ...
```

In the dynamic routing section (around line 186), replace `_index.md` with `_index.yaml`:

```
Read `knowledge/tier_3/_index.yaml` for:
- **Essay routing**: essay summaries with chapter-level descriptions
```

**Step 5: Run tests**

Run: `cd /home/rp/git/rfflpllcn-llm/book-expert && uv run pytest tests/test_generate.py -v`
Expected: all tests pass

**Step 6: Commit**

```bash
git add lib/generate_claude_md.py tests/test_generate.py
git commit -m "feat: update CLAUDE.md generator for _index.yaml and cite_essay tool"
```

---

## Task 3: Implement `cite_essay` tool

The query-time tool that loads essay tier_2 files (analytical summaries) on demand.

**Files:**
- Create: `lib/cite_essay.py`
- Create: `tests/test_cite_essay.py`

**Step 1: Write the failing tests**

Create `tests/test_cite_essay.py`:

```python
# tests/test_cite_essay.py
import pytest
from pathlib import Path

from lib.cite_essay import load_arc, load_toc, load_raw_lines


@pytest.fixture
def essay_dir(tmp_path):
    """Create a minimal essay directory structure."""
    edir = tmp_path / "data" / "essays" / "test_essay"
    edir.mkdir(parents=True)

    # tier_2 arc file
    t2 = edir / "tier_2"
    t2.mkdir()
    (t2 / "02_01_test_arc.md").write_text(
        "# Test Arc\n\n## Synopsis\nArc synopsis.\n\n"
        "### SC1 (L10–L20)\nScene summary.\n\n**Figures**: Author\n**Themes**: Style\n"
    )

    # tier_1 index
    t1 = edir / "tier_1"
    t1.mkdir()
    (t1 / "00_index.md").write_text("# Index\n\n| # | Arc | Lines |\n|---|---|---|\n| 1 | Test Arc | 10–20 |\n")

    # filtered JSONL
    import json
    lines = [{"id": str(i), "t": f"Line {i} text."} for i in range(1, 25)]
    (edir / "test_essay-filtered.jsonl").write_text(
        "\n".join(json.dumps(l, ensure_ascii=False) for l in lines) + "\n"
    )

    return edir


def test_load_arc(essay_dir):
    result = load_arc(essay_dir, "02_01_test_arc")
    assert "Test Arc" in result
    assert "Scene summary" in result


def test_load_arc_missing(essay_dir):
    result = load_arc(essay_dir, "02_99_nonexistent")
    assert result == ""


def test_load_toc(essay_dir):
    result = load_toc(essay_dir)
    assert "Index" in result
    assert "Test Arc" in result


def test_load_raw_lines(essay_dir):
    result = load_raw_lines(essay_dir, 5, 10)
    assert "Line 5 text." in result
    assert "Line 10 text." in result
    assert "Line 11 text." not in result


def test_load_raw_lines_empty_range(essay_dir):
    result = load_raw_lines(essay_dir, 100, 200)
    assert result == ""
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/rp/git/rfflpllcn-llm/book-expert && uv run pytest tests/test_cite_essay.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lib.cite_essay'`

**Step 3: Implement `lib/cite_essay.py`**

```python
"""
Load critical essay content on demand.

CLI:
  python -m lib.cite_essay <book_dir> <slug> <arc_id>
  python -m lib.cite_essay <book_dir> <slug> --toc
  python -m lib.cite_essay <book_dir> <slug> <start> <end> --raw
"""

import json
import sys
from pathlib import Path


def _essay_dir(book_dir: Path, slug: str) -> Path:
    return book_dir / "data" / "essays" / slug


def load_arc(essay_dir: Path, arc_id: str) -> str:
    """Load a tier_2 arc file from an essay's knowledge base."""
    filepath = essay_dir / "tier_2" / f"{arc_id}.md"
    if filepath.exists():
        return filepath.read_text(encoding="utf-8")
    return ""


def load_toc(essay_dir: Path) -> str:
    """Load the essay's tier_1 index (table of contents)."""
    filepath = essay_dir / "tier_1" / "00_index.md"
    if filepath.exists():
        return filepath.read_text(encoding="utf-8")
    return ""


def load_raw_lines(essay_dir: Path, start: int, end: int) -> str:
    """Load raw lines from the essay's filtered JSONL by ID range."""
    jsonl_files = list(essay_dir.glob("*-filtered.jsonl"))
    if not jsonl_files:
        return ""

    lines = []
    with open(jsonl_files[0], encoding="utf-8") as f:
        for raw in f:
            record = json.loads(raw)
            line_id = int(record["id"])
            if start <= line_id <= end:
                lines.append(f"[{record['id']}] {record['t']}")

    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage:")
        print("  python -m lib.cite_essay <book_dir> <slug> <arc_id>")
        print("  python -m lib.cite_essay <book_dir> <slug> --toc")
        print("  python -m lib.cite_essay <book_dir> <slug> <start> <end> --raw")
        sys.exit(1)

    book_dir = Path(sys.argv[1])
    slug = sys.argv[2]
    edir = _essay_dir(book_dir, slug)

    if sys.argv[3] == "--toc":
        print(load_toc(edir))
    elif len(sys.argv) >= 5 and sys.argv[-1] == "--raw":
        start, end = int(sys.argv[3]), int(sys.argv[4])
        print(load_raw_lines(edir, start, end))
    else:
        arc_id = sys.argv[3]
        result = load_arc(edir, arc_id)
        if result:
            print(result)
        else:
            print(f"Arc '{arc_id}' not found in {edir / 'tier_2'}/", file=sys.stderr)
            sys.exit(1)
```

**Step 4: Run tests**

Run: `cd /home/rp/git/rfflpllcn-llm/book-expert && uv run pytest tests/test_cite_essay.py -v`
Expected: all 5 tests pass

**Step 5: Commit**

```bash
git add lib/cite_essay.py tests/test_cite_essay.py
git commit -m "feat: add cite_essay tool for on-demand essay retrieval"
```

---

## Task 4: Implement `aggregate_essay_index`

Merges per-essay `.yaml` descriptors into `knowledge/tier_3/_index.yaml`.

**Files:**
- Create: `lib/aggregate_essay_index.py`
- Create: `tests/test_aggregate_essay_index.py`

**Step 1: Write the failing tests**

Create `tests/test_aggregate_essay_index.py`:

```python
# tests/test_aggregate_essay_index.py
import yaml
from pathlib import Path

from lib.aggregate_essay_index import aggregate


def test_aggregate_single_essay(tmp_path):
    """Single essay YAML produces valid _index.yaml."""
    bd = tmp_path / "book"
    bd.mkdir()
    edir = bd / "data" / "essays" / "test_essay"
    edir.mkdir(parents=True)
    (bd / "knowledge" / "tier_3").mkdir(parents=True)

    essay_yaml = {
        "essays": {
            "test_essay": {
                "author": "Test Author",
                "work": "Test Work",
                "year": 2000,
                "summary": "A test summary.",
                "stance": "stylistic",
                "arcs": ["02_01_test"],
                "themes": ["style"],
                "characters": ["Foo"],
                "sections": [
                    {"id": 1, "title": "Ch 1", "summary": "First chapter.", "start_id": "1", "end_id": "50", "arcs": ["02_01_test"]},
                ],
            }
        }
    }
    with open(edir / "test_essay.yaml", "w") as f:
        yaml.safe_dump(essay_yaml, f, allow_unicode=True, sort_keys=False)

    aggregate(bd)

    index_path = bd / "knowledge" / "tier_3" / "_index.yaml"
    assert index_path.exists()
    data = yaml.safe_load(index_path.read_text())
    assert "test_essay" in data["essays"]
    assert data["essays"]["test_essay"]["author"] == "Test Author"


def test_aggregate_multiple_essays(tmp_path):
    """Multiple essay YAMLs are merged into one _index.yaml."""
    bd = tmp_path / "book"
    bd.mkdir()
    (bd / "knowledge" / "tier_3").mkdir(parents=True)

    for slug in ["essay_a", "essay_b"]:
        edir = bd / "data" / "essays" / slug
        edir.mkdir(parents=True)
        essay_yaml = {"essays": {slug: {"author": f"Author {slug}", "work": f"Work {slug}", "year": 2000, "summary": "Summary.", "stance": "s", "arcs": [], "themes": [], "characters": [], "sections": []}}}
        with open(edir / f"{slug}.yaml", "w") as f:
            yaml.safe_dump(essay_yaml, f, allow_unicode=True, sort_keys=False)

    aggregate(bd)

    data = yaml.safe_load((bd / "knowledge" / "tier_3" / "_index.yaml").read_text())
    assert "essay_a" in data["essays"]
    assert "essay_b" in data["essays"]


def test_aggregate_no_essays(tmp_path):
    """No essay directories → _index.yaml with empty essays dict."""
    bd = tmp_path / "book"
    (bd / "data" / "essays").mkdir(parents=True)
    (bd / "knowledge" / "tier_3").mkdir(parents=True)

    aggregate(bd)

    data = yaml.safe_load((bd / "knowledge" / "tier_3" / "_index.yaml").read_text())
    assert data["essays"] == {}


def test_aggregate_idempotent(tmp_path):
    """Running twice produces same result."""
    bd = tmp_path / "book"
    bd.mkdir()
    (bd / "knowledge" / "tier_3").mkdir(parents=True)
    edir = bd / "data" / "essays" / "test_essay"
    edir.mkdir(parents=True)
    essay_yaml = {"essays": {"test_essay": {"author": "A", "work": "W", "year": 1, "summary": "S.", "stance": "s", "arcs": [], "themes": [], "characters": [], "sections": []}}}
    with open(edir / "test_essay.yaml", "w") as f:
        yaml.safe_dump(essay_yaml, f, allow_unicode=True, sort_keys=False)

    aggregate(bd)
    first = (bd / "knowledge" / "tier_3" / "_index.yaml").read_text()
    aggregate(bd)
    second = (bd / "knowledge" / "tier_3" / "_index.yaml").read_text()
    assert first == second
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/rp/git/rfflpllcn-llm/book-expert && uv run pytest tests/test_aggregate_essay_index.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement `lib/aggregate_essay_index.py`**

```python
"""
Aggregate per-essay YAML descriptors into knowledge/tier_3/_index.yaml.

CLI: python -m lib.aggregate_essay_index <book_dir>
"""

import sys

import yaml
from pathlib import Path


def aggregate(book_dir: Path) -> None:
    """Merge all data/essays/<slug>/<slug>.yaml into _index.yaml."""
    essays_dir = book_dir / "data" / "essays"
    merged = {"essays": {}}

    if essays_dir.exists():
        for essay_subdir in sorted(essays_dir.iterdir()):
            if not essay_subdir.is_dir():
                continue
            yaml_files = list(essay_subdir.glob("*.yaml"))
            for yf in yaml_files:
                data = yaml.safe_load(yf.read_text(encoding="utf-8")) or {}
                for slug, info in data.get("essays", {}).items():
                    merged["essays"][slug] = info

    output = book_dir / "knowledge" / "tier_3" / "_index.yaml"
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        yaml.safe_dump(merged, f, allow_unicode=True, sort_keys=False, width=120)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m lib.aggregate_essay_index <book_dir>")
        sys.exit(1)
    aggregate(Path(sys.argv[1]))
    print("Done: _index.yaml updated")
```

**Step 4: Run tests**

Run: `cd /home/rp/git/rfflpllcn-llm/book-expert && uv run pytest tests/test_aggregate_essay_index.py -v`
Expected: all 4 tests pass

**Step 5: Commit**

```bash
git add lib/aggregate_essay_index.py tests/test_aggregate_essay_index.py
git commit -m "feat: add aggregate_essay_index to merge essay YAMLs into _index.yaml"
```

---

## Task 5: Add CLI to `convert.py` (stage 0 refactor)

The only preprocessing stage that needs code changes. Currently `__main__` hardcodes a filename.

**Files:**
- Modify: `preprocessing/00__pdf2jsonl/convert.py:83-84`

**Step 1: Replace the hardcoded `__main__` block**

In `convert.py`, replace lines 83-84:

```python
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Extract text lines from PDF to JSONL")
    parser.add_argument("pdf_path", help="Path to the PDF file")
    parser.add_argument("--lang", default=None, help="Language code (e.g., fr, en)")
    args = parser.parse_args()
    extract_lines_to_jsonl(args.pdf_path, lang=args.lang)
```

**Step 2: Verify it works**

Run: `cd /home/rp/git/rfflpllcn-llm/book-expert && python -m preprocessing.00__pdf2jsonl.convert --help`
Expected: shows usage with `pdf_path` and `--lang` arguments

**Step 3: Commit**

```bash
git add preprocessing/00__pdf2jsonl/convert.py
git commit -m "refactor: add CLI arguments to convert.py (stage 0)"
```

---

## Task 6: Place Godard essay artifacts into the new directory structure

Move the already-generated Godard essay through the new layout: `data/essays/godard_poetique/` with tier_1, tier_2, and YAML.

**Files:**
- Create: `books/voyage2_plus_it/data/essays/godard_poetique/` (directory)
- Move: existing Godard artifacts from `preprocessing/04__generate_book_yaml/godard_poetique/` and `books/voyage2_plus_it/data/essays/`

**Step 1: Create directory structure and copy artifacts**

```bash
cd /home/rp/git/rfflpllcn-llm/book-expert

# Create target directory
mkdir -p books/voyage2_plus_it/data/essays/godard_poetique/tier_1
mkdir -p books/voyage2_plus_it/data/essays/godard_poetique/tier_2

# Copy tier_1 and tier_2 from preprocessing output
cp preprocessing/04__generate_book_yaml/godard_poetique/tier_1/*.md \
   books/voyage2_plus_it/data/essays/godard_poetique/tier_1/
cp preprocessing/04__generate_book_yaml/godard_poetique/tier_2/*.md \
   books/voyage2_plus_it/data/essays/godard_poetique/tier_2/

# Copy YAML descriptor
cp preprocessing/04__generate_book_yaml/godard_poetique/godard_poetique.yaml \
   books/voyage2_plus_it/data/essays/godard_poetique/

# Copy filtered JSONL (already exists in data/essays/)
cp books/voyage2_plus_it/data/essays/godard-filtered.jsonl \
   books/voyage2_plus_it/data/essays/godard_poetique/godard_poetique-filtered.jsonl

# Copy sections JSON
cp books/voyage2_plus_it/data/essays/godard_sections.json \
   books/voyage2_plus_it/data/essays/godard_poetique/godard_poetique_sections.json

# Copy source PDF
cp books/voyage2_plus_it/data/essays/raw/godard.pdf \
   books/voyage2_plus_it/data/essays/godard_poetique/godard_poetique.pdf
```

**Step 2: Generate `_index.yaml` from the Godard YAML**

```bash
cd /home/rp/git/rfflpllcn-llm/book-expert
python -m lib.aggregate_essay_index books/voyage2_plus_it
```

Verify: `cat books/voyage2_plus_it/knowledge/tier_3/_index.yaml | head -20`
Expected: YAML with `essays: godard_poetique:` entry

**Step 3: Verify `cite_essay` works end-to-end**

```bash
python -m lib.cite_essay books/voyage2_plus_it godard_poetique --toc
python -m lib.cite_essay books/voyage2_plus_it godard_poetique 02_01_primato_stile
python -m lib.cite_essay books/voyage2_plus_it godard_poetique 410 420 --raw
```

Expected: TOC shows arc table, arc loads analytical summary, raw lines load from JSONL.

**Step 4: Regenerate CLAUDE.md**

```bash
python -m lib.generate_claude_md books/voyage2_plus_it
```

Verify: `grep cite_essay books/voyage2_plus_it/CLAUDE.md`
Expected: `cite_essay` tool is documented

**Step 5: Run full test suite**

Run: `cd /home/rp/git/rfflpllcn-llm/book-expert && uv run pytest tests/ -v`
Expected: all tests pass

**Step 6: Commit**

```bash
git add books/voyage2_plus_it/data/essays/godard_poetique/
git add books/voyage2_plus_it/knowledge/tier_3/_index.yaml
git add books/voyage2_plus_it/CLAUDE.md
git commit -m "feat: place Godard essay in new directory structure, generate _index.yaml"
```

---

## Task 7: Update documentation

Update docs that reference the old `_index.md` format and `heavy_with_commentary` semantics.

**Files:**
- Modify: `docs/adding-a-new-book.md:161-190`
- Modify: `docs/knowledge-base-guide.md:13-176`

**Step 1: Update `docs/adding-a-new-book.md`**

In the tier_3 section (around line 161), replace the `_index.md` instructions with:

```markdown
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
```

Remove references to creating `<slug>.md` commentary files.

**Step 2: Update `docs/knowledge-base-guide.md`**

In the tier_3 section (around line 13 and 152), replace `_index.md` with `_index.yaml` and update the description:

```markdown
├── tier_3/          # essay routing metadata — always loaded
│   └── _index.yaml  # structured YAML: essay summaries + section descriptions
```

Replace the `_index.md` — Routing Metadata section (around line 152) with:

```markdown
### `_index.yaml` — Essay Routing Metadata

Structured YAML file generated by `lib.aggregate_essay_index`. Contains per-essay
entries with: author, work, year, summary, stance, arcs, themes, characters, and
chapter-level section descriptions.

The agent reads these summaries to decide which essay arcs to load via `cite_essay`.
No keyword matching — the LLM routes semantically.
```

Remove the section about per-commentary `.md` files (around line 176).

**Step 3: Commit**

```bash
git add docs/adding-a-new-book.md docs/knowledge-base-guide.md
git commit -m "docs: update tier_3 documentation for _index.yaml and essay pipeline"
```

---

## Task 8: Clean up old tier_3 artifacts

Remove the old `_index.md` from the voyage2_plus_it book (now replaced by `_index.yaml`).

**Files:**
- Delete: `books/voyage2_plus_it/knowledge/tier_3/_index.md`

**Step 1: Verify `_index.yaml` exists and has content**

```bash
cat books/voyage2_plus_it/knowledge/tier_3/_index.yaml | head -5
```

Expected: `essays:` with at least `godard_poetique` entry

**Step 2: Delete old file**

```bash
git rm books/voyage2_plus_it/knowledge/tier_3/_index.md
```

**Step 3: Run full test suite**

Run: `cd /home/rp/git/rfflpllcn-llm/book-expert && uv run pytest tests/ -v`
Expected: all tests pass

**Step 4: Commit**

```bash
git commit -m "chore: remove old _index.md, replaced by _index.yaml"
```

---

## Task summary

| Task | What | Tests |
|------|------|-------|
| 1 | Migrate loader from `_index.md` to `_index.yaml` | Update 4 tests, remove 2 |
| 2 | Update CLAUDE.md generator for `_index.yaml` + `cite_essay` | Update 1 test, add 1 |
| 3 | Implement `cite_essay` tool | 5 new tests |
| 4 | Implement `aggregate_essay_index` | 4 new tests |
| 5 | Add CLI args to `convert.py` | Manual verify |
| 6 | Place Godard artifacts in new structure | Integration verify |
| 7 | Update documentation | No tests (docs only) |
| 8 | Clean up old `_index.md` | Full suite verify |

Total: 8 tasks, ~10 new tests, ~4 updated tests, ~2 removed tests.
