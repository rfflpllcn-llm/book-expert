#!/usr/bin/env python3
"""Extract original French text from voyage-fr.csv by line range.

Usage:
    python cite.py <start> <end>
    python cite.py 2173 2183

Maps L-references from scene files to FR line_ids in the CSV.
Only returns main_text lines. Consecutive lines are joined into
a flowing passage.
"""

import csv
import sys
from pathlib import Path

CSV_PATH = Path(__file__).parent / "data" / "voyage-fr.csv"


def load_lines(start: int, end: int) -> list[tuple[str, str]]:
    """Return [(line_id, text), ...] for main_text lines in [start, end]."""
    target_ids = {f"FR{n}" for n in range(start, end + 1)}
    results = []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["line_id"] in target_ids and row["chunk_type"] == "main_text":
                results.append((row["line_id"], row["text"]))
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


def main():
    if len(sys.argv) != 3:
        print(f"Usage: python {sys.argv[0]} <start_line> <end_line>")
        print(f"Example: python {sys.argv[0]} 77 80")
        sys.exit(1)
    start, end = int(sys.argv[1]), int(sys.argv[2])
    lines = load_lines(start, end)
    print(format_citation(lines))


if __name__ == "__main__":
    main()