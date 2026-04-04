# Bilingual Alignment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add bilingual (FR+IT) alignment and citation support to book-expert, starting with `books/voyage2_plus_it`.

**Architecture:** A new preprocessing stage (02a) runs bertalign to produce a line-level alignment JSONL. At runtime, `lib/cite.py --lang it` loads the alignment, finds matching beads, and returns both original and translation citations. The knowledge base, routing, and loader are untouched.

**Tech Stack:** bertalign (LaBSE), sentence-transformers, faiss-cpu, Python 3.11, pytest

**Design doc:** `docs/plans/2026-03-29-bilingual-alignment-design.md`

---

## Task 1: Copy bertalign into project and add dependencies

No TDD — this is scaffolding.

**Files:**
- Create: `bertalign/` (copy from external repo)
- Modify: `pyproject.toml`

**Step 1: Copy bertalign package**

```bash
cp -r /home/rp/git/rfflpllcn-llm/pdfalign-aligner/bertalign/ \
      /home/rp/git/rfflpllcn-llm/book-expert/bertalign/
```

Remove `__pycache__/` if copied:

```bash
rm -rf /home/rp/git/rfflpllcn-llm/book-expert/bertalign/__pycache__
```

**Step 2: Patch bertalign to skip `clean_text()` when `is_split=True`**

bertalign's `__init__` runs `clean_text()` unconditionally, which drops empty/whitespace-only lines and shifts bead indices. When `is_split=True` the caller controls the input, so `clean_text()` must be skipped to preserve the 1:1 mapping between bead indices and input lines.

In `bertalign/aligner.py`, replace lines 31–38:

```python
        src = clean_text(src)
        tgt = clean_text(tgt)
        src_lang = detect_lang(src)
        tgt_lang = detect_lang(tgt)

        if is_split:
            src_sents = src.splitlines()
            tgt_sents = tgt.splitlines()
```

with:

```python
        if is_split:
            src_lang = detect_lang(src)
            tgt_lang = detect_lang(tgt)
            src_sents = src.splitlines()
            tgt_sents = tgt.splitlines()
        else:
            src = clean_text(src)
            tgt = clean_text(tgt)
            src_lang = detect_lang(src)
            tgt_lang = detect_lang(tgt)
            src_sents = split_sents(src, src_lang)
            tgt_sents = split_sents(tgt, tgt_lang)
```

This way `clean_text()` only runs when bertalign is responsible for sentence splitting (`is_split=False`). When `is_split=True`, the input is used as-is.

**Step 3: Add dependencies to pyproject.toml**

In `pyproject.toml`, add to `dependencies`:

```toml
dependencies = [
    "pyyaml",
    "anthropic",
    "marker-pdf>=1.10.2",
    "pymupdf>=1.27.2.2",
    "sentence-transformers",
    "faiss-cpu",
    "sentence-splitter",
    "numba",
    "langdetect",
]
```

Also add `bertalign` to `[tool.setuptools.packages.find]`:

```toml
[tool.setuptools.packages.find]
include = ["lib*", "bertalign*"]
```

**Step 4: Install and regenerate lock file**

```bash
cd /home/rp/git/rfflpllcn-llm/book-expert
uv pip install -e .
uv lock
python -c "from bertalign import Bertalign; print('OK')"
```

Expected: `OK` (model downloads on first run). `uv.lock` is updated with the new dependencies.

**Step 5: Commit**

```bash
git add bertalign/ pyproject.toml uv.lock
git commit -m "feat: add bertalign package, patch is_split to skip clean_text"
```

---

## Task 2: Create preprocessing stage 02a — alignment

**Files:**
- Create: `preprocessing/alignment/__init__.py`
- Create: `preprocessing/alignment/align.py`
- Create: `tests/test_align.py`

### Step 1: Write failing tests for I/O helpers

Create `tests/test_align.py`:

```python
# tests/test_align.py
import json
import pytest
from pathlib import Path


@pytest.fixture
def alignment_data(tmp_path):
    """Create minimal FR and IT JSONL files for alignment tests."""
    fr_lines = [
        {"id": "77", "t": "First sentence."},
        {"id": "78", "t": "Second sentence."},
        {"id": "79", "t": "Third sentence."},
    ]
    it_lines = [
        {"id": 1, "t": "Prima frase."},
        {"id": 2, "t": "Seconda frase."},
        {"id": 3, "t": "Terza frase."},
    ]
    fr_path = tmp_path / "fr.jsonl"
    it_path = tmp_path / "it.jsonl"
    out_path = tmp_path / "alignment.jsonl"

    fr_path.write_text("\n".join(json.dumps(r) for r in fr_lines) + "\n")
    it_path.write_text("\n".join(json.dumps(r) for r in it_lines) + "\n")

    return fr_path, it_path, out_path, fr_lines, it_lines


def test_load_jsonl_texts(alignment_data):
    from preprocessing.alignment.align import load_jsonl
    fr_path, _, _, _, _ = alignment_data
    ids, texts = load_jsonl(fr_path)
    assert ids == ["77", "78", "79"]
    assert texts == ["First sentence.", "Second sentence.", "Third sentence."]


def test_load_jsonl_texts_int_ids(alignment_data):
    """IT file has integer IDs — should be coerced to int list."""
    from preprocessing.alignment.align import load_jsonl
    _, it_path, _, _, _ = alignment_data
    ids, texts = load_jsonl(it_path)
    assert ids == [1, 2, 3]
    assert texts[0] == "Prima frase."


def test_beads_to_alignment():
    """Convert bertalign bead tuples to output dicts."""
    from preprocessing.alignment.align import beads_to_alignment

    src_ids = ["77", "78", "79"]
    tgt_ids = [1, 2, 3]
    beads = [
        ([0, 1], [0]),       # FR77+FR78 -> IT1
        ([2], [1, 2]),       # FR79 -> IT2+IT3
    ]
    result = beads_to_alignment(beads, src_ids, tgt_ids)
    assert result == [
        {"src_lines": ["77", "78"], "tgt_lines": [1], "type": "2-1"},
        {"src_lines": ["79"], "tgt_lines": [2, 3], "type": "1-2"},
    ]


def test_beads_to_alignment_skips_empty():
    """Beads with empty src or tgt (insertions/deletions) are skipped."""
    from preprocessing.alignment.align import beads_to_alignment

    src_ids = ["77", "78"]
    tgt_ids = [1, 2]
    beads = [
        ([0], []),           # deletion — skip
        ([], [0]),           # insertion — skip
        ([1], [1]),          # 1-1 — keep
    ]
    result = beads_to_alignment(beads, src_ids, tgt_ids)
    assert len(result) == 1
    assert result[0]["type"] == "1-1"


def test_write_alignment(alignment_data):
    from preprocessing.alignment.align import write_alignment

    _, _, out_path, _, _ = alignment_data
    records = [
        {"src_lines": ["77"], "tgt_lines": [1], "type": "1-1"},
        {"src_lines": ["78", "79"], "tgt_lines": [2, 3], "type": "2-2"},
    ]
    write_alignment(records, out_path)

    lines = out_path.read_text().strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0]) == records[0]
    assert json.loads(lines[1]) == records[1]


def test_run_alignment_rejects_empty_texts(tmp_path):
    """Empty t values would break bead-to-ID mapping — must be caught."""
    from preprocessing.alignment.align import run_alignment

    fr_lines = [
        {"id": "1", "t": "First sentence."},
        {"id": "2", "t": ""},  # empty — should trigger ValueError
        {"id": "3", "t": "Third sentence."},
    ]
    it_lines = [
        {"id": 1, "t": "Prima frase."},
        {"id": 2, "t": "Seconda frase."},
    ]
    fr_path = tmp_path / "fr.jsonl"
    it_path = tmp_path / "it.jsonl"
    out_path = tmp_path / "alignment.jsonl"

    fr_path.write_text("\n".join(json.dumps(r) for r in fr_lines) + "\n")
    it_path.write_text("\n".join(json.dumps(r) for r in it_lines) + "\n")

    with pytest.raises(ValueError, match="Empty text lines"):
        run_alignment(fr_path, it_path, out_path)
```

### Step 2: Run tests to verify they fail

```bash
pytest tests/test_align.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'preprocessing'`

### Step 3: Implement I/O helpers

Create `preprocessing/alignment/__init__.py` (empty file).

Create `preprocessing/alignment/align.py`:

```python
"""
Bilingual line-level alignment using bertalign.

CLI: python -m preprocessing.alignment.align \
       --src data/voyage-fr.jsonl --tgt data/voyage-it.jsonl \
       --out data/alignment-fr-it.jsonl
"""

import argparse
import json
from pathlib import Path


def load_jsonl(path: Path) -> tuple[list, list[str]]:
    """Load JSONL file, return (ids, texts). Preserves original id types."""
    ids = []
    texts = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            ids.append(row["id"])
            texts.append(row["t"])
    return ids, texts


def beads_to_alignment(
    beads: list[tuple[list[int], list[int]]],
    src_ids: list,
    tgt_ids: list,
) -> list[dict]:
    """Convert bertalign bead tuples to output records.

    Skips beads where either side is empty (insertions/deletions).
    """
    records = []
    for src_bead, tgt_bead in beads:
        if not src_bead or not tgt_bead:
            continue
        src = [src_ids[i] for i in src_bead]
        tgt = [tgt_ids[i] for i in tgt_bead]
        records.append({
            "src_lines": src,
            "tgt_lines": tgt,
            "type": f"{len(src_bead)}-{len(tgt_bead)}",
        })
    return records


def write_alignment(records: list[dict], path: Path) -> None:
    """Write alignment records as JSONL."""
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def run_alignment(
    src_path: Path,
    tgt_path: Path,
    out_path: Path,
    max_align: int = 3,
    top_k: int = 10,
    win: int = 10,
    min_win_size: int = 1,
    percent: float = 0.15,
) -> None:
    """Run full alignment pipeline: load → bertalign → write."""
    from bertalign import Bertalign

    src_ids, src_texts = load_jsonl(src_path)
    tgt_ids, tgt_texts = load_jsonl(tgt_path)

    # Pre-flight: empty texts would silently break index mapping even with
    # the is_split patch, since bertalign embeds each line and empty strings
    # produce degenerate embeddings.
    empty_src = [i for i, t in enumerate(src_texts) if not t.strip()]
    empty_tgt = [i for i, t in enumerate(tgt_texts) if not t.strip()]
    if empty_src or empty_tgt:
        raise ValueError(
            f"Empty text lines break alignment index mapping. "
            f"src has {len(empty_src)} empty lines (first: {empty_src[:5]}), "
            f"tgt has {len(empty_tgt)} empty lines (first: {empty_tgt[:5]})"
        )

    src_blob = "\n".join(src_texts)
    tgt_blob = "\n".join(tgt_texts)

    aligner = Bertalign(
        src_blob, tgt_blob,
        is_split=True,
        max_align=max_align,
        top_k=top_k,
        win=win,
        min_win_size=min_win_size,
        percent=percent,
    )
    aligner.align_sents()

    records = beads_to_alignment(aligner.result, src_ids, tgt_ids)
    write_alignment(records, out_path)
    print(f"Wrote {len(records)} alignment beads to {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Align bilingual JSONL files")
    parser.add_argument("--src", type=Path, required=True, help="Source JSONL")
    parser.add_argument("--tgt", type=Path, required=True, help="Target JSONL")
    parser.add_argument("--out", type=Path, required=True, help="Output alignment JSONL")
    parser.add_argument("--max-align", type=int, default=3)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--win", type=int, default=10)
    parser.add_argument("--min-win-size", type=int, default=1)
    parser.add_argument("--percent", type=float, default=0.15)
    args = parser.parse_args()

    run_alignment(
        args.src, args.tgt, args.out,
        max_align=args.max_align,
        top_k=args.top_k,
        win=args.win,
        min_win_size=args.min_win_size,
        percent=args.percent,
    )
```

Also create `preprocessing/__init__.py` if it doesn't exist.

### Step 4: Run tests to verify they pass

```bash
pytest tests/test_align.py -v
```

Expected: all 5 tests PASS

### Step 5: Commit

```bash
git add preprocessing/alignment/ tests/test_align.py
git commit -m "feat: add alignment preprocessing stage 02a with I/O helpers"
```

### Step 6: Run alignment on voyage2_plus_it (manual, GPU-intensive)

```bash
cd /home/rp/git/rfflpllcn-llm/book-expert
python -m preprocessing.alignment.align \
  --src books/voyage2_plus_it/data/voyage-fr.jsonl \
  --tgt books/voyage2_plus_it/data/voyage-it.jsonl \
  --out books/voyage2_plus_it/data/alignment-fr-it.jsonl
```

Expected: produces `alignment-fr-it.jsonl` with ~15k–19k beads. Takes several minutes.

### Step 7: Spot-check alignment output

```bash
head -5 books/voyage2_plus_it/data/alignment-fr-it.jsonl
python3 -c "
import json
with open('books/voyage2_plus_it/data/alignment-fr-it.jsonl') as f:
    beads = [json.loads(l) for l in f]
from collections import Counter
types = Counter(b['type'] for b in beads)
print(f'Total beads: {len(beads)}')
for t, c in types.most_common():
    print(f'  {t}: {c}')
"
```

Expected: majority `1-1` type, some `1-2`, `2-1`, occasional `2-3` or `3-2`.

### Step 8: Commit alignment data

```bash
git add books/voyage2_plus_it/data/alignment-fr-it.jsonl
git commit -m "data: add FR-IT alignment for voyage2_plus_it"
```

---

## Task 3: Extend `lib/cite.py` with `--lang` support

This is the core runtime change. TDD throughout.

**Files:**
- Modify: `lib/cite.py`
- Modify: `tests/test_cite.py`
- Modify: `tests/conftest.py`

### Step 1: Extend the test fixture with bilingual data

Add to `tests/conftest.py`, inside the `book_dir` fixture, after the CSV data block:

```python
    # JSONL source variant (for bilingual book tests)
    (data_dir / "source.jsonl").write_text(
        '{"id": "1", "t": "First line of the test book."}\n'
        '{"id": "2", "t": "Second line continues here."}\n'
        '{"id": "3", "t": "Third line wraps up."}\n'
        '{"id": "4", "t": "Fourth line starts section two."}\n'
        '{"id": "5", "t": "Fifth and final line."}\n'
    )

    # Italian translation
    (data_dir / "translation-it.jsonl").write_text(
        '{"id": 1, "t": "Prima riga del libro di prova."}\n'
        '{"id": 2, "t": "La seconda riga continua qui."}\n'
        '{"id": 3, "t": "La terza riga conclude."}\n'
        '{"id": 4, "t": "La quarta riga inizia la sezione due."}\n'
        '{"id": 5, "t": "Quinta e ultima riga."}\n'
    )

    # Alignment file: FR1+FR2 -> IT1, FR3 -> IT2+IT3, FR4 -> IT4, FR5 -> IT5
    (data_dir / "alignment-fr-it.jsonl").write_text(
        '{"src_lines": ["1", "2"], "tgt_lines": [1], "type": "2-1"}\n'
        '{"src_lines": ["3"], "tgt_lines": [2, 3], "type": "1-2"}\n'
        '{"src_lines": ["4"], "tgt_lines": [4], "type": "1-1"}\n'
        '{"src_lines": ["5"], "tgt_lines": [5], "type": "1-1"}\n'
    )
```

### Step 2: Add a bilingual book fixture

Add a second fixture to `tests/conftest.py`:

```python
@pytest.fixture
def bilingual_book_dir(book_dir):
    """Extend book_dir with JSONL source + Italian translation + alignment."""
    # Rewrite book.yaml to use JSONL source and add translations
    (book_dir / "book.yaml").write_text(
        "title: Test Book\n"
        "author: Test Author\n"
        "year: 2000\n"
        "language: fr\n"
        "\n"
        "source_text:\n"
        "  file: data/source.jsonl\n"
        "  format: jsonl\n"
        "  line_prefix: FR\n"
        "  line_column: id\n"
        "  text_column: t\n"
        "\n"
        "translations:\n"
        "  it:\n"
        "    file: data/translation-it.jsonl\n"
        "    format: jsonl\n"
        "    line_prefix: IT\n"
        "    line_column: id\n"
        "    text_column: t\n"
        "    alignment: data/alignment-fr-it.jsonl\n"
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
    return book_dir
```

### Step 3: Write failing tests for bilingual citation

Add to `tests/test_cite.py` (at the top, add `import pytest` alongside the existing imports):

```python
import pytest
```

Then add the new test functions:

```python
def test_load_alignment(bilingual_book_dir):
    from lib.cite import load_alignment
    beads = load_alignment(bilingual_book_dir, "it")
    assert len(beads) == 4
    assert beads[0]["src_lines"] == ["1", "2"]
    assert beads[0]["tgt_lines"] == [1]


def test_find_aligned_line_ids(bilingual_book_dir):
    from lib.cite import load_alignment, find_aligned_line_ids
    beads = load_alignment(bilingual_book_dir, "it")
    # Request FR lines 1-3 -> should find IT lines from beads covering FR1,2,3
    it_ids = find_aligned_line_ids(beads, 1, 3)
    assert it_ids == [1, 2, 3]


def test_find_aligned_line_ids_partial(bilingual_book_dir):
    from lib.cite import load_alignment, find_aligned_line_ids
    beads = load_alignment(bilingual_book_dir, "it")
    # Request only FR4 -> IT4
    it_ids = find_aligned_line_ids(beads, 4, 4)
    assert it_ids == [4]


def test_load_translation_lines(bilingual_book_dir):
    from lib.cite import load_translation_lines
    lines = load_translation_lines(bilingual_book_dir, "it", 1, 3)
    assert len(lines) == 3
    assert lines[0] == ("IT1", "Prima riga del libro di prova.")
    assert lines[2] == ("IT3", "La terza riga conclude.")


def test_format_bilingual_citation(bilingual_book_dir):
    from lib.cite import load_lines, load_translation_lines, format_citation
    fr_lines = load_lines(bilingual_book_dir, 1, 3)
    it_lines = load_translation_lines(bilingual_book_dir, "it", 1, 3)
    fr_cite = format_citation(fr_lines)
    it_cite = format_citation(it_lines)
    assert "FR1" in fr_cite
    assert "IT1" in it_cite


def test_format_citation_gap_aware():
    """Non-contiguous IDs should be formatted with + separator."""
    from lib.cite import format_citation
    lines = [("IT1", "Riga uno."), ("IT3", "Riga tre.")]
    result = format_citation(lines)
    # Should NOT say IT1–IT3 (that implies IT2 exists)
    assert "IT1 + IT3" in result


def test_load_translation_lines_no_translations(book_dir):
    """Books without translations section should raise a clear error."""
    from lib.cite import load_translation_lines
    with pytest.raises(KeyError):
        load_translation_lines(book_dir, "it", 1, 3)
```

### Step 4: Run tests to verify they fail

```bash
pytest tests/test_cite.py -v
```

Expected: FAIL — `ImportError: cannot import name 'load_alignment' from 'lib.cite'`

### Step 5: Implement bilingual citation functions in `lib/cite.py`

Add these functions to `lib/cite.py` (after `_load_lines_jsonl`, before `format_citation`):

```python
def load_alignment(book_dir: Path, lang: str) -> list[dict]:
    """Load alignment beads from the translations config for *lang*."""
    config = load_book_config(book_dir)
    trans = config["translations"][lang]
    align_path = book_dir / trans["alignment"]
    beads = []
    with open(align_path, encoding="utf-8") as f:
        for line in f:
            beads.append(json.loads(line))
    return beads


def find_aligned_line_ids(
    beads: list[dict], src_start: int, src_end: int
) -> list:
    """Return sorted target line IDs aligned to source lines in [src_start, src_end].

    Source line IDs in beads may be str or int; compared as str against the
    requested range (which is always built from ints).
    """
    requested = {str(n) for n in range(src_start, src_end + 1)}
    target_ids = []
    for bead in beads:
        src_ids = {str(x) for x in bead["src_lines"]}
        if src_ids & requested:
            target_ids.extend(bead["tgt_lines"])
    return sorted(set(target_ids))


def load_translation_lines(
    book_dir: Path, lang: str, src_start: int, src_end: int
) -> list[tuple[str, str]]:
    """Load translated lines aligned to source lines [src_start, src_end]."""
    config = load_book_config(book_dir)
    trans = config["translations"][lang]

    beads = load_alignment(book_dir, lang)
    target_ids = find_aligned_line_ids(beads, src_start, src_end)
    if not target_ids:
        return []

    # Load target lines by scanning the translation file
    prefix = trans["line_prefix"]
    line_col = trans["line_column"]
    text_col = trans["text_column"]
    target_set = set(target_ids)

    results = []
    tgt_path = book_dir / trans["file"]
    with open(tgt_path, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if row[line_col] in target_set:
                results.append((f"{prefix}{row[line_col]}", row[text_col]))
    # Sort by the numeric part of the ID
    results.sort(key=lambda r: int(r[0].lstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")))
    return results
```

### Step 6: Update `format_citation` to handle non-contiguous IDs

Replace the existing `format_citation` in `lib/cite.py`:

```python
def format_citation(lines: list[tuple[str, str]]) -> str:
    """Join lines into a blockquote with line range reference.

    Detects gaps in numeric IDs and formats as separate ranges
    joined by ' + ' (e.g. "IT1–IT2 + IT5").
    """
    if not lines:
        return "(no main_text lines found in this range)"
    text = " ".join(t for _, t in lines)

    # Build contiguous groups of IDs
    ids = [lid for lid, _ in lines]
    groups = _group_contiguous_ids(ids)
    ref = " + ".join(_format_range(g) for g in groups)
    return f"> «{text}» ({ref})"


def _extract_numeric(line_id: str) -> int:
    """Extract the numeric suffix from a line ID like 'FR77' or 'IT3'."""
    return int("".join(c for c in line_id if c.isdigit()))


def _group_contiguous_ids(ids: list[str]) -> list[list[str]]:
    """Group line IDs into contiguous runs based on numeric part."""
    if not ids:
        return []
    groups = [[ids[0]]]
    for i in range(1, len(ids)):
        if _extract_numeric(ids[i]) == _extract_numeric(ids[i - 1]) + 1:
            groups[-1].append(ids[i])
        else:
            groups.append([ids[i]])
    return groups


def _format_range(group: list[str]) -> str:
    """Format a contiguous group as 'FR1' or 'FR1–FR3'."""
    if len(group) == 1:
        return group[0]
    return f"{group[0]}–{group[-1]}"
```

### Step 7: Update CLI in `lib/cite.py`

Replace the `if __name__` block:

```python
if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python -m lib.cite <book_dir> <start_line> <end_line> [--lang LANG]")
        print("Example: python -m lib.cite . 77 80")
        print("Example: python -m lib.cite . 77 80 --lang it")
        sys.exit(1)
    book_dir = Path(sys.argv[1])
    start, end = int(sys.argv[2]), int(sys.argv[3])

    lang = None
    if "--lang" in sys.argv:
        lang_idx = sys.argv.index("--lang") + 1
        lang = sys.argv[lang_idx]

    lines = load_lines(book_dir, start, end)
    print(format_citation(lines))

    if lang:
        tl = load_translation_lines(book_dir, lang, start, end)
        print(format_citation(tl))
```

### Step 8: Run all cite tests

```bash
pytest tests/test_cite.py -v
```

Expected: all tests PASS (old + new)

### Step 9: Run full test suite to check for regressions

```bash
pytest -v
```

Expected: all tests PASS. The existing `format_citation` tests still pass because contiguous IDs produce the same `FR1–FR2` format as before.

### Step 10: Commit

```bash
git add lib/cite.py tests/test_cite.py tests/conftest.py
git commit -m "feat: add bilingual citation support (--lang flag) to lib/cite.py"
```

---

## Task 4: Update `lib/generate_claude_md.py` for bilingual instructions

**Files:**
- Modify: `lib/generate_claude_md.py`
- Modify: `tests/test_generate.py`

### Step 1: Write failing test

Add to `tests/test_generate.py`:

```python
def test_generate_bilingual_tools(bilingual_book_dir):
    """When translations exist, CLAUDE.md should document the --lang flag."""
    result = generate(bilingual_book_dir)
    assert "--lang it" in result
    assert "translation" in result.lower() or "bilingual" in result.lower()


def test_generate_no_bilingual_without_translations(book_dir):
    """Books without translations should NOT mention --lang."""
    result = generate(book_dir)
    assert "--lang" not in result
```

### Step 2: Run tests to verify they fail

```bash
pytest tests/test_generate.py -v
```

Expected: `test_generate_bilingual_tools` FAIL (no `--lang` in output yet)

### Step 3: Implement conditional bilingual section

In `lib/generate_claude_md.py`, inside the `generate()` function, after `cite_density = ...` line, add:

```python
    translations = config.get("translations", {})
```

Then modify the Tools section in the f-string. Replace the current Tools block:

```python
    # Build bilingual tools documentation
    bilingual_tools = ""
    if translations:
        langs = ", ".join(translations.keys())
        bilingual_tools = (
            f"\n- **Cite with translation**: `python -m lib.cite . <start_line> <end_line> --lang <{langs}>`"
            f"\n  Example: `python -m lib.cite . 77 80 --lang it`"
            f"\n  Shows the original text followed by the aligned translation."
        )

    bilingual_note = ""
    if translations:
        bilingual_note = (
            "\n\n### Bilingual citation\n"
            "- When the user asks about a translation, or when comparing original and translation, "
            "use `--lang` to show both versions side-by-side.\n"
            "- The alignment is approximate (sentence-level); minor boundary mismatches are normal.\n"
        )
```

Then update the f-string to include these variables in the Tools section:

```
## Tools

- **Cite original text**: `python -m lib.cite . <start_line> <end_line>`
  Example: `python -m lib.cite . 77 80`{bilingual_tools}
- **Save Q&A to cache**: `python -m lib.save_qa . "question" "summary" "10, 25" --link answers/YYYY-MM-DD_<slug>.md`
```

And append `{bilingual_note}` after the "Q&A cache — IMPORTANT" behavior rules block.

### Step 4: Run tests to verify they pass

```bash
pytest tests/test_generate.py -v
```

Expected: all tests PASS

### Step 5: Run full suite

```bash
pytest -v
```

Expected: all tests PASS

### Step 6: Commit

```bash
git add lib/generate_claude_md.py tests/test_generate.py
git commit -m "feat: add conditional bilingual instructions to generate_claude_md"
```

---

## Task 5: Update `books/voyage2_plus_it/book.yaml` with translations section

**Files:**
- Modify: `books/voyage2_plus_it/book.yaml`

### Step 1: Add translations section to book.yaml

Append after the `source_text:` block (before `chunks:`):

```yaml
translations:
  it:
    file: data/voyage-it.jsonl
    format: jsonl
    line_prefix: IT
    line_column: id
    text_column: t
    alignment: data/alignment-fr-it.jsonl
```

### Step 2: Regenerate CLAUDE.md

```bash
python -m lib.generate_claude_md books/voyage2_plus_it/
```

### Step 3: Verify the generated CLAUDE.md includes --lang

```bash
grep -c "\-\-lang" books/voyage2_plus_it/CLAUDE.md
```

Expected: 2+ matches (tool doc + example)

### Step 4: Commit

```bash
git add books/voyage2_plus_it/book.yaml books/voyage2_plus_it/CLAUDE.md
git commit -m "feat: add IT translation config to voyage2_plus_it book.yaml"
```

---

## Task 6: Integration verification

### Step 1: Run full test suite

```bash
pytest -v
```

Expected: all tests PASS

### Step 2: Test cite CLI with real data (after alignment exists)

```bash
cd books/voyage2_plus_it
python -m lib.cite . 77 80
python -m lib.cite . 77 80 --lang it
```

Expected: first command shows FR citation only, second shows FR + IT side-by-side.

### Step 3: Spot-check alignment quality

Pick 3-5 well-known passages and verify the aligned IT text makes sense:
- Opening (FR77–83): Bardamu's first words
- Africa (FR ~3000): colonial scenes
- Ending (FR ~19500): final lines

```bash
python -m lib.cite . 77 83 --lang it
```

### Step 4: Final commit (if any fixes needed)

Only stage the specific files that were modified during integration fixes:

```bash
git add lib/cite.py books/voyage2_plus_it/book.yaml  # adjust to actual changed files
git commit -m "fix: integration fixes for bilingual alignment"
```

---

## Dependency graph

```
Task 1 (bertalign + deps)
    └─> Task 2 (align.py + run alignment)
            └─> Task 5 (book.yaml translations section)
                    └─> Task 6 (integration)
Task 3 (cite.py --lang)  ── can run in parallel with Tasks 1-2
Task 4 (generate_claude_md) ── can run in parallel with Tasks 1-2
```

Tasks 3 and 4 only need the test fixtures (not real alignment data), so they can proceed independently of Tasks 1-2.