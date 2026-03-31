"""
Extract and format original text citations from a book's source text file.

Supports CSV and JSONL source formats (configured via ``format`` in book.yaml).

CLI: python -m lib.cite <book_dir> <start_line> <end_line>
"""

import csv
import json
import sys
from pathlib import Path

from lib.loader import load_book_config


def load_lines(book_dir: Path, start: int, end: int) -> list[tuple[str, str]]:
    """Return [(line_id, text), ...] for main_text lines in [start, end]."""
    config = load_book_config(book_dir)
    src = config["source_text"]
    fmt = src.get("format", "csv")

    if fmt == "jsonl":
        return _load_lines_jsonl(book_dir, src, start, end)
    return _load_lines_csv(book_dir, src, start, end)


def _load_lines_csv(
    book_dir: Path, src: dict, start: int, end: int
) -> list[tuple[str, str]]:
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


def _load_lines_jsonl(
    book_dir: Path, src: dict, start: int, end: int
) -> list[tuple[str, str]]:
    jsonl_path = book_dir / src["file"]
    prefix = src["line_prefix"]
    line_col = src["line_column"]
    text_col = src["text_column"]
    filter_col = src.get("filter_column")
    filter_val = src.get("filter_value")

    target_ids = {f"{prefix}{n}" for n in range(start, end + 1)}
    results = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            line_id = f"{prefix}{row[line_col]}"
            if line_id not in target_ids:
                continue
            if filter_col and row.get(filter_col) != filter_val:
                continue
            results.append((line_id, row[text_col]))
    return results


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
