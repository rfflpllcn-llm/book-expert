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
