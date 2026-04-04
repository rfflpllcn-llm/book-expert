# Essay Integration Refactor — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve essay integration scalability and consistency — tiered summaries in `load_tier3()`, deterministic essay routing via `route_query()`, stricter YAML aggregation, and early-exit optimization in `load_raw_lines()`.

**Architecture:** Four independent refactorings to the essay subsystem: (1) split `_index.yaml` loading into header-only (always, in cached system prompt) vs section-detail (on-demand, in dynamic context) to prevent context blowup at 3+ essays, (2) extend `route_query()` to return essay matches using `author`/`work`/`themes`/`characters` fields already present in `_index.yaml`, (3) restrict `aggregate_essay_index.py` to only load `<dirname>.yaml` files, (4) add early-exit to `load_raw_lines()` once the requested range is fully collected.

**Runtime context:** `agent.py` calls `build_context()` which returns `(system_cached, dynamic_context)`. Only `system_cached` gets prompt-cached via Anthropic's `cache_control: {"type": "ephemeral"}` (`books/voyage/agent.py:76-79`). `dynamic_context` is injected into the user message and re-sent every turn (`agent.py:85-90`). This means essay headers must go into `system_cached` to benefit from caching.

**Tech Stack:** Python 3.11, pytest, PyYAML. All code under `lib/`, tests under `tests/`.

---

### Task 1: Tiered summaries in `load_tier3()` — header-only default

Currently `load_tier3()` (`lib/loader.py:92-117`) dumps all section summaries into `dynamic_context`. With 1 essay (Godard, 16KB YAML) this is fine, but 5+ essays would inject 80KB+ of uncached content on every turn.

Two changes:
1. **Split `load_tier3()` into two modes:**
   - **Default (header-only)**: author, work, year, stance, top-level summary, themes, characters. No arc IDs (they're machine-oriented and numerous — 19 for Godard). Compact enough for always-on injection (~200 tokens per essay).
   - **Detailed (sections)**: the current behavior — load everything including arc IDs. Called on-demand when the agent needs deeper routing for a specific essay.

2. **Move headers into `system_prompt` (cached part):**
   `build_context()` must append header-only summaries to the `system_prompt` return value, not to `dynamic_parts`. This way they benefit from Anthropic prompt caching. Only matched essay detail (sections) goes into `dynamic_context`.

**Files:**
- Modify: `lib/loader.py:92-117` — refactor `load_tier3()`
- Modify: `lib/loader.py:120-143` — update `build_context()` to use header-only mode
- Test: `tests/test_loader.py`

**Step 1: Write failing tests**

Add to `tests/test_loader.py`:

```python
def test_load_tier3_header_only(book_dir):
    """Default mode returns header info but NOT section summaries."""
    result = load_tier3(book_dir)
    assert "Test Critic" in result
    assert "Test Study" in result
    assert "structuralist" in result
    # Section detail should NOT be present in header-only mode
    assert "Chapter on Style" not in result


def test_load_tier3_detailed(book_dir):
    """Detailed mode returns full section summaries."""
    result = load_tier3(book_dir, detailed=True)
    assert "Test Critic" in result
    assert "Chapter on Style" in result
    assert "Analyzes core stylistic techniques" in result


def test_load_tier3_detailed_single_essay(book_dir):
    """Detailed mode for a specific essay slug."""
    result = load_tier3(book_dir, detailed=True, slug="test_commentary")
    assert "Test Critic" in result
    assert "Chapter on Style" in result


def test_load_tier3_detailed_unknown_slug(book_dir):
    """Detailed mode with unknown slug returns empty."""
    result = load_tier3(book_dir, detailed=True, slug="nonexistent")
    assert result == ""


def test_build_context_caches_essay_headers(book_dir):
    """build_context puts header-only essay summaries in system_cached, not dynamic."""
    system, dynamic = build_context("tell me about style", book_dir)
    # Headers are in the cached system prompt
    assert "Test Critic" in system
    assert "Test Study" in system
    # Section detail is NOT in either (no essay matched by routing)
    assert "Chapter on Style" not in system
    assert "Chapter on Style" not in dynamic
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_loader.py::test_load_tier3_header_only tests/test_loader.py::test_load_tier3_detailed tests/test_loader.py::test_load_tier3_detailed_single_essay tests/test_loader.py::test_load_tier3_detailed_unknown_slug tests/test_loader.py::test_build_context_uses_header_only -v`

Expected: `test_load_tier3_header_only` FAILS (currently includes section summaries). `test_load_tier3_detailed` passes (current behavior). Others fail.

**Step 3: Implement tiered `load_tier3()`**

Replace `load_tier3()` in `lib/loader.py:92-117`:

```python
def load_tier3(book_dir: Path, *, detailed: bool = False, slug: str | None = None) -> str:
    """Load essay summaries from _index.yaml.

    Args:
        detailed: If False (default), emit compact header per essay
                  (author/work/year/stance/summary/themes/characters).
                  Arc IDs are omitted — they are machine-oriented and
                  numerous (19 for Godard).
                  If True, include full section summaries and arc IDs.
        slug:     If set, only emit that essay. Returns "" if not found.
    """
    data = _load_tier3_index(book_dir)
    essays = data.get("essays", {})
    if not essays:
        return ""

    if slug and slug not in essays:
        return ""

    items = {slug: essays[slug]} if slug else essays

    parts = []
    for essay_slug, info in items.items():
        lines = [
            f"## {info.get('author', 'Unknown')} — *{info.get('work', essay_slug)}* ({info.get('year', '?')})",
            f"**Stance**: {info.get('stance', 'N/A')}",
            "",
            info.get("summary", ""),
        ]
        themes = info.get("themes", [])
        if themes:
            lines.append(f"\n**Themes**: {', '.join(themes)}")
        characters = info.get("characters", [])
        if characters:
            lines.append(f"**Characters/Figures**: {', '.join(characters)}")

        if detailed:
            arcs = info.get("arcs", [])
            if arcs:
                lines.append(f"**Arcs**: {', '.join(arcs)}")
            lines.append("\n**Sections:**")
            for sec in info.get("sections", []):
                lines.append(f"- **{sec.get('title', 'Untitled')}**: {sec.get('summary', '')}")

        parts.append("\n".join(lines))

    return "\n\n---\n\n".join(parts)
```

**Step 4: Fix existing test that expects old behavior**

Update `test_load_tier3_arc_match` in `tests/test_loader.py`:

```python
def test_load_tier3_arc_match(book_dir):
    """Header-only mode includes author/work but not section details or arcs."""
    result = load_tier3(book_dir)
    assert "Test Critic" in result
    assert "Test Study" in result
    # Header-only: section summaries and arc IDs are excluded
    assert "Chapter on Style" not in result
```

Update existing `build_context` tests that check for essay content:

```python
def test_build_context_no_match(book_dir):
    """No arc match; essay headers are in system prompt (cached)."""
    system, dynamic = build_context("completely unrelated", book_dir)
    assert "Index" in system  # tier_1 loaded
    assert "Test Critic" in system  # essay headers in cached prompt
    assert "ARC:" not in dynamic  # no tier_2 arcs matched


def test_build_context_with_commentary(book_dir):
    """Essay headers are in system prompt, not dynamic context."""
    system, dynamic = build_context("tell me about the beginning", book_dir)
    assert "Test Critic" in system
    assert "Test Study" in system
```

**Step 5: Run all tests**

Run: `python -m pytest tests/test_loader.py -v`

Expected: ALL PASS

**Step 6: Commit**

```bash
git add lib/loader.py tests/test_loader.py
git commit -m "refactor: split load_tier3 into header-only and detailed modes

Header-only mode (default) emits compact author/work/stance/summary/
themes/characters (~200 tokens per essay). Arc IDs excluded — they are
machine-oriented and add bloat. Headers go into the cached system
prompt (benefits from Anthropic prompt caching). Detailed mode with
full sections is loaded on demand into dynamic context."
```

---

### Task 2: Deterministic essay routing in `route_query()`

Currently `route_query()` (`lib/loader.py:35-63`) only matches novel arcs. Essay routing is entirely delegated to the LLM with zero deterministic hints. The `_index.yaml` already contains `author`, `work`, `themes`, and `characters` per essay — wire them all into `route_query()` so it returns essay matches alongside novel arcs. This ensures queries like "What does Godard argue..." or "In Poétique de Céline..." match the essay deterministically.

**Files:**
- Modify: `lib/loader.py:35-63` — extend `route_query()` return type
- Modify: `lib/loader.py:120-143` — update `build_context()` to use essay matches
- Test: `tests/test_loader.py`
- Modify: `tests/conftest.py` — add essay themes/characters to test fixture

**Step 1: Write failing tests**

Add to `tests/test_loader.py`:

```python
def test_route_query_returns_essay_matches(book_dir):
    """route_query returns essay slugs when themes match."""
    config = load_book_config(book_dir)
    tier3 = _load_tier3_index(book_dir)
    result = route_query("tell me about darkness", config, essays=tier3.get("essays", {}))
    assert result.essays == ["test_commentary"]


def test_route_query_essay_character_match(book_dir):
    """route_query returns essay slugs when essay characters match."""
    config = load_book_config(book_dir)
    tier3 = _load_tier3_index(book_dir)
    result = route_query("what does Céline say?", config, essays=tier3.get("essays", {}))
    assert "test_commentary" in result.essays


def test_route_query_essay_author_match(book_dir):
    """route_query returns essay slugs when author name matches."""
    config = load_book_config(book_dir)
    tier3 = _load_tier3_index(book_dir)
    result = route_query("what does Test Critic argue?", config, essays=tier3.get("essays", {}))
    assert "test_commentary" in result.essays


def test_route_query_essay_work_match(book_dir):
    """route_query returns essay slugs when work title matches."""
    config = load_book_config(book_dir)
    tier3 = _load_tier3_index(book_dir)
    result = route_query("in Test Study, chapter 3 says", config, essays=tier3.get("essays", {}))
    assert "test_commentary" in result.essays


def test_route_query_no_essay_match(book_dir):
    """Unrelated query returns no essay matches."""
    config = load_book_config(book_dir)
    tier3 = _load_tier3_index(book_dir)
    result = route_query("completely unrelated query", config, essays=tier3.get("essays", {}))
    assert result.essays == []


def test_route_query_backward_compatible(book_dir):
    """Novel arc matching still works, accessible via .arcs property."""
    config = load_book_config(book_dir)
    result = route_query("tell me about the beginning", config)
    assert "02_01_test_arc" in result.arcs


def test_route_query_result_is_list_like(book_dir):
    """RouteResult is backward-compatible: iterating yields arc IDs."""
    config = load_book_config(book_dir)
    result = route_query("tell me about the beginning", config)
    assert "02_01_test_arc" in list(result)


def test_build_context_includes_detailed_for_matched_essay(book_dir):
    """When an essay matches by theme, build_context includes detailed sections in dynamic."""
    system, dynamic = build_context("analysis of darkness", book_dir)
    # Header is in cached system prompt
    assert "Test Critic" in system
    # Matched essay detail is in dynamic context
    assert "Chapter on Style" in dynamic
    assert "ESSAY-DETAIL: test_commentary" in dynamic
```

Also update the import in `tests/test_loader.py` to include `_load_tier3_index`:

```python
from lib.loader import (
    load_book_config, route_query, load_tier1, load_tier2_file, load_tier3,
    build_context, append_to_qa_cache, _load_tier3_index,
)
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_loader.py::test_route_query_returns_essay_matches tests/test_loader.py::test_route_query_backward_compatible tests/test_loader.py::test_route_query_result_is_list_like -v`

Expected: FAIL — `route_query()` returns `list[str]`, not an object with `.arcs`/`.essays`.

**Step 3: Implement `RouteResult` and extended `route_query()`**

Add to `lib/loader.py` (after imports, before `load_book_config`):

```python
from dataclasses import dataclass, field


@dataclass
class RouteResult:
    """Result of routing a query — novel arcs + matched essay slugs."""
    arcs: list[str] = field(default_factory=list)
    essays: list[str] = field(default_factory=list)

    # Backward compatibility: iterating/indexing yields arcs
    def __iter__(self):
        return iter(self.arcs)

    def __getitem__(self, idx):
        return self.arcs[idx]

    def __len__(self):
        return len(self.arcs)

    def __contains__(self, item):
        return item in self.arcs
```

Modify `route_query()`:

```python
def route_query(query: str, config: dict, *, essays: dict | None = None) -> RouteResult:
    """Route a query to relevant tier_2 arc files and essay slugs.

    Args:
        query:  The user's question.
        config: Parsed book.yaml.
        essays: Optional dict from _index.yaml["essays"]. If provided,
                themes and characters in each essay are matched against the query.
    """
    query_lower = query.lower()
    matched_arcs = []

    # Keyword matching against arc keywords
    for arc_id, arc_config in config["arcs"].items():
        for kw in arc_config["keywords"]:
            if kw in query_lower:
                if arc_id not in matched_arcs:
                    matched_arcs.append(arc_id)
                break

    # Line references (L1234)
    for line_str in re.findall(r"L(\d{1,5})", query):
        line_num = int(line_str)
        for arc_id, arc_config in config["arcs"].items():
            lo, hi = arc_config["lines"]
            if lo <= line_num <= hi and arc_id not in matched_arcs:
                matched_arcs.append(arc_id)

    # Character routing (novel characters)
    for char_name, char_config in config.get("characters", {}).items():
        if char_name in query_lower:
            for arc_id in char_config["arcs"]:
                if arc_id not in matched_arcs:
                    matched_arcs.append(arc_id)

    # Essay routing via author, work title, themes, and characters
    matched_essays = []
    if essays:
        for slug, info in essays.items():
            if slug in matched_essays:
                continue
            # Check author and work title first (most common query pattern)
            author = info.get("author", "")
            work = info.get("work", "")
            if author and author.lower() in query_lower:
                matched_essays.append(slug)
                continue
            if work and work.lower() in query_lower:
                matched_essays.append(slug)
                continue
            # Then themes
            for theme in info.get("themes", []):
                if theme.lower() in query_lower:
                    matched_essays.append(slug)
                    break
            else:
                # Then characters/figures discussed in the essay
                for char in info.get("characters", []):
                    if char.lower() in query_lower:
                        matched_essays.append(slug)
                        break

    return RouteResult(arcs=matched_arcs[:4], essays=matched_essays[:3])
```

**Step 4: Update `build_context()` to use essay routing**

Replace `build_context()` in `lib/loader.py`:

```python
def build_context(query: str, book_dir: Path) -> tuple[str, str]:
    """Build full context for a query.
    Returns: (system_prompt_cached, dynamic_context)

    system_prompt_cached includes tier_1 + essay headers (small, stable,
    benefits from Anthropic prompt caching).
    dynamic_context includes matched tier_2 arcs + detailed sections for
    matched essays (varies per query, injected in user message).
    """
    config = load_book_config(book_dir)
    system_prompt = load_tier1(book_dir)

    # Essay headers go in cached system prompt (small fixed cost)
    commentary_header = load_tier3(book_dir)
    if commentary_header:
        system_prompt += f"\n\n---\n\n<!-- ESSAYS -->\n{commentary_header}"

    tier3_data = _load_tier3_index(book_dir)
    essays_dict = tier3_data.get("essays", {})

    result = route_query(query, config, essays=essays_dict)
    dynamic_parts = []

    # Load matched tier_2 arcs
    for arc_id in result.arcs:
        content = load_tier2_file(book_dir, arc_id)
        if content:
            dynamic_parts.append(f"<!-- ARC: {arc_id} -->\n{content}")

    # Detailed sections only for matched essays (per-query cost)
    for slug in result.essays:
        detail = load_tier3(book_dir, detailed=True, slug=slug)
        if detail:
            dynamic_parts.append(f"<!-- ESSAY-DETAIL: {slug} -->\n{detail}")

    dynamic_context = "\n\n---\n\n".join(dynamic_parts) if dynamic_parts else ""
    return system_prompt, dynamic_context
```

**Step 5: Fix existing tests that assume old return type**

Update tests in `tests/test_loader.py` that use `route_query()` directly:

```python
def test_route_query_keyword(book_dir):
    config = load_book_config(book_dir)
    result = route_query("tell me about the beginning", config)
    assert "02_01_test_arc" in result.arcs


def test_route_query_character(book_dir):
    config = load_book_config(book_dir)
    result = route_query("what happens to hero?", config)
    assert "02_01_test_arc" in result.arcs
    assert "02_02_test_arc_two" in result.arcs


def test_route_query_line_ref(book_dir):
    config = load_book_config(book_dir)
    result = route_query("explain L2", config)
    assert "02_01_test_arc" in result.arcs


def test_route_query_sc_ref_ignored(book_dir):
    config = load_book_config(book_dir)
    result = route_query("what is SC_00002?", config)
    assert result.arcs == []


def test_route_query_no_match(book_dir):
    config = load_book_config(book_dir)
    result = route_query("completely unrelated query", config)
    assert result.arcs == []


def test_route_query_cap_at_four(book_dir):
    config = load_book_config(book_dir)
    result = route_query("test beginning second ending hero sidekick", config)
    assert len(result.arcs) <= 4
```

**Step 6: Run all tests**

Run: `python -m pytest tests/ -v`

Expected: ALL PASS (backward compat via `__iter__`/`__contains__` ensures no breakage in `build_context` callers)

**Step 7: Commit**

```bash
git add lib/loader.py tests/test_loader.py
git commit -m "feat: add deterministic essay routing to route_query()

route_query() now accepts an optional essays dict and matches query
against essay author, work title, themes, and characters from
_index.yaml. Returns a RouteResult dataclass (backward-compatible
via __iter__) with both .arcs and .essays. build_context() uses
matched essays to inject detailed section summaries into dynamic
context only for relevant essays."
```

---

### Task 3: Stricter YAML glob in `aggregate_essay_index.py`

Currently `aggregate_essay_index.py:23` globs `*.yaml` in each essay subdirectory, which could accidentally ingest non-descriptor YAMLs. Restrict to `<dirname>.yaml` only.

**Files:**
- Modify: `lib/aggregate_essay_index.py:19-26`
- Test: `tests/test_aggregate_essay_index.py`

**Step 1: Write failing test**

Add to `tests/test_aggregate_essay_index.py`:

```python
def test_aggregate_ignores_non_descriptor_yaml(tmp_path):
    """Only <dirname>.yaml is loaded; other YAML files are ignored."""
    bd = tmp_path / "book"
    bd.mkdir()
    edir = bd / "data" / "essays" / "test_essay"
    edir.mkdir(parents=True)
    (bd / "knowledge" / "tier_3").mkdir(parents=True)

    # Main descriptor
    essay_yaml = {"essays": {"test_essay": {"author": "Real Author", "work": "W", "year": 1, "summary": "S.", "stance": "s", "arcs": [], "themes": [], "characters": [], "sections": []}}}
    with open(edir / "test_essay.yaml", "w") as f:
        yaml.safe_dump(essay_yaml, f, allow_unicode=True, sort_keys=False)

    # Stray YAML that should NOT be ingested
    stray_yaml = {"essays": {"stray": {"author": "Stray Author", "work": "X", "year": 2, "summary": "Bad.", "stance": "x", "arcs": [], "themes": [], "characters": [], "sections": []}}}
    with open(edir / "config.yaml", "w") as f:
        yaml.safe_dump(stray_yaml, f, allow_unicode=True, sort_keys=False)

    aggregate(bd)

    data = yaml.safe_load((bd / "knowledge" / "tier_3" / "_index.yaml").read_text())
    assert "test_essay" in data["essays"]
    assert "stray" not in data["essays"]
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_aggregate_essay_index.py::test_aggregate_ignores_non_descriptor_yaml -v`

Expected: FAIL — `stray` is present because `*.yaml` glob picks up `config.yaml`.

**Step 3: Restrict glob to `<dirname>.yaml`**

Replace lines 19-26 in `lib/aggregate_essay_index.py`:

```python
    if essays_dir.exists():
        for essay_subdir in sorted(essays_dir.iterdir()):
            if not essay_subdir.is_dir():
                continue
            descriptor = essay_subdir / f"{essay_subdir.name}.yaml"
            if not descriptor.exists():
                continue
            data = yaml.safe_load(descriptor.read_text(encoding="utf-8")) or {}
            for slug, info in data.get("essays", {}).items():
                merged["essays"][slug] = info
```

**Step 4: Run all aggregation tests**

Run: `python -m pytest tests/test_aggregate_essay_index.py -v`

Expected: ALL PASS

**Step 5: Commit**

```bash
git add lib/aggregate_essay_index.py tests/test_aggregate_essay_index.py
git commit -m "fix: restrict aggregate to <dirname>.yaml descriptors only

Previously globbed *.yaml which could accidentally ingest non-descriptor
YAML files (e.g. config.yaml, chunks metadata). Now only loads the
canonical <dirname>.yaml file from each essay subdirectory."
```

---

### Task 4: Early-exit optimization in `load_raw_lines()`

`load_raw_lines()` (`lib/cite_essay.py:35-49`) scans the entire JSONL (14K+ lines for Godard) even when the requested range is small and near the beginning. Since IDs are monotonically increasing, we can break early once we've passed the end of the range.

**Files:**
- Modify: `lib/cite_essay.py:35-49`
- Test: `tests/test_cite_essay.py`

**Step 1: Write failing test (behavioral — tests early-exit via a sentinel)**

The early-exit is a performance optimization that doesn't change behavior. We verify correctness with an existing test plus a new edge case. Add to `tests/test_cite_essay.py`:

```python
def test_load_raw_lines_mid_range(essay_dir):
    """Lines in the middle of the file are correctly loaded."""
    result = load_raw_lines(essay_dir, 10, 15)
    assert "Line 10 text." in result
    assert "Line 15 text." in result
    assert "Line 9 text." not in result
    assert "Line 16 text." not in result


def test_load_raw_lines_single(essay_dir):
    """Single-line range works."""
    result = load_raw_lines(essay_dir, 1, 1)
    assert "Line 1 text." in result
    assert "Line 2 text." not in result
```

**Step 2: Run tests to verify they pass (baseline)**

Run: `python -m pytest tests/test_cite_essay.py -v`

Expected: ALL PASS (these are just new correctness tests).

**Step 3: Add early-exit to `load_raw_lines()`**

Replace `load_raw_lines()` in `lib/cite_essay.py:35-49`:

```python
def load_raw_lines(essay_dir: Path, start: int, end: int) -> str:
    """Load raw lines from the essay's filtered JSONL by ID range.

    Assumes IDs are monotonically increasing — breaks early after end.
    """
    jsonl_files = list(essay_dir.glob("*-filtered.jsonl"))
    if not jsonl_files:
        return ""

    lines = []
    with open(jsonl_files[0], encoding="utf-8") as f:
        for raw in f:
            record = json.loads(raw)
            line_id = int(record["id"])
            if line_id > end:
                break
            if line_id >= start:
                lines.append(f"[{record['id']}] {record['t']}")

    return "\n".join(lines)
```

**Step 4: Run all cite_essay tests**

Run: `python -m pytest tests/test_cite_essay.py -v`

Expected: ALL PASS

**Step 5: Commit**

```bash
git add lib/cite_essay.py tests/test_cite_essay.py
git commit -m "perf: early-exit in load_raw_lines when past requested range

IDs in filtered JSONL are monotonically increasing, so we can break
as soon as line_id > end. Avoids scanning the full 14K+ line file
for small ranges near the beginning."
```

---

### Task 5: Fix `--raw` example order and update tier_3 docs in `generate_claude_md.py`

Two issues:
1. **Bug:** The generated `cite_essay_doc` example shows `python -m lib.cite_essay . <slug> 100 200 --raw` (`generate_claude_md.py:103`), but argparse would parse `100` as `arc_id` (positional `nargs="?"`) and fail on `200`. Correct order: `python -m lib.cite_essay . <slug> --raw 100 200`.
2. **Doc update:** After Task 1, tier_3 docs should mention that essay headers are always cached and `--toc` retrieves full chapter detail on demand.

**Files:**
- Modify: `lib/generate_claude_md.py:99-104` — fix `--raw` example order, update tier_3 text
- Test: `tests/test_generate.py`

**Step 1: Write failing test**

Add to `tests/test_generate.py`:

```python
def test_generate_cite_essay_raw_order(book_dir):
    """--raw must precede its START END args in the example."""
    result = generate(book_dir)
    # The correct order: --raw 100 200 (flag before args)
    assert "--raw 100 200" in result
    # The wrong order must NOT appear
    assert "100 200 --raw" not in result


def test_generate_essay_headers_cached(book_dir):
    """Tier_3 section mentions headers are cached in system prompt."""
    result = generate(book_dir)
    assert "headers" in result.lower() or "always loaded" in result.lower()
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_generate.py::test_generate_cite_essay_raw_order tests/test_generate.py::test_generate_essay_headers_cached -v`

Expected: `test_generate_cite_essay_raw_order` FAILS — current template has `100 200 --raw`.

**Step 3: Fix cite_essay_doc and tier_3 section**

In `lib/generate_claude_md.py`, replace the `cite_essay_doc` block (around line 99-104):

```python
    if has_essays:
        cite_essay_doc = (
            "- **Cite essay**: `python -m lib.cite_essay . <slug> <arc_id>`\n"
            "  Loads the analytical summary for a specific arc of a critical essay.\n"
            "  Use `--toc` to see all arcs: `python -m lib.cite_essay . <slug> --toc`\n"
            "  Use `--raw` for exact quotes: `python -m lib.cite_essay . <slug> --raw 100 200`"
        )
    else:
        cite_essay_doc = ""
```

Update the tier_3 section in the template string (around line 159-161). Replace:

```
### Tier 3 — Critical essays
Located in `knowledge/tier_3/`. Routing metadata in `_index.yaml`.
Essay summaries are loaded automatically. Use `cite_essay` to retrieve detailed analysis.
```

With:

```
### Tier 3 — Critical essays
Located in `knowledge/tier_3/`. Routing metadata in `_index.yaml`.
Essay headers (author, stance, themes) are always loaded in the cached system prompt.
Use `cite_essay <slug> --toc` to see full chapter details, then `cite_essay <slug> <arc_id>` for analysis.
```

**Step 4: Run all tests**

Run: `python -m pytest tests/ -v`

Expected: ALL PASS

**Step 5: Regenerate CLAUDE.md for voyage2_plus_it**

Run: `python -m lib.generate_claude_md books/voyage2_plus_it/`

**Step 6: Commit**

```bash
git add lib/generate_claude_md.py tests/test_generate.py books/voyage2_plus_it/CLAUDE.md
git commit -m "fix: correct --raw example arg order, update tier_3 docs

The cite_essay --raw example had arguments before the flag (100 200 --raw)
which would fail at argparse. Fixed to --raw 100 200. Also updated
tier_3 documentation to reflect that essay headers are now cached in
the system prompt and --toc retrieves detail on demand."
```

---

### Task 6: Run full test suite and verify

**Step 1: Run all tests**

Run: `python -m pytest tests/ -v`

Expected: ALL 59+ tests PASS (including new ones).

**Step 2: Verify no regressions in real book**

Run: `python -m lib.cite_essay books/voyage2_plus_it godard_poetique --toc`

Expected: Prints the Godard essay table of contents.

Run: `python -m lib.cite_essay books/voyage2_plus_it godard_poetique 02_07_argot_oscenita`

Expected: Prints the argot/obscenity arc markdown.

Run: `python -m lib.cite_essay books/voyage2_plus_it godard_poetique --raw 275 291`

Expected: Prints raw French lines 275-291.

**Step 3: Commit if any fixups needed, otherwise done**