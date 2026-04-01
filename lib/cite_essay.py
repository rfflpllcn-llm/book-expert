"""
Load critical essay content on demand.

CLI:
  python -m lib.cite_essay <book_dir> <slug> <arc_id>
  python -m lib.cite_essay <book_dir> <slug> --toc
  python -m lib.cite_essay <book_dir> <slug> --raw <start> <end>
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
    import argparse

    parser = argparse.ArgumentParser(
        description="Load critical essay content on demand",
        prog="python -m lib.cite_essay",
    )
    parser.add_argument("book_dir", type=Path, help="Book directory")
    parser.add_argument("slug", help="Essay slug (directory name under data/essays/)")
    parser.add_argument("--toc", action="store_true", help="Show table of contents (tier_1 index)")
    parser.add_argument("--raw", nargs=2, type=int, metavar=("START", "END"),
                        help="Load raw lines from JSONL by ID range")
    parser.add_argument("arc_id", nargs="?", help="Arc ID to load from tier_2")
    args = parser.parse_args()

    edir = _essay_dir(args.book_dir, args.slug)

    if args.toc:
        print(load_toc(edir))
    elif args.raw:
        print(load_raw_lines(edir, args.raw[0], args.raw[1]))
    elif args.arc_id:
        result = load_arc(edir, args.arc_id)
        if result:
            print(result)
        else:
            print(f"Arc '{args.arc_id}' not found in {edir / 'tier_2'}/", file=sys.stderr)
            sys.exit(1)
    else:
        parser.error("provide an arc_id, --toc, or --raw START END")
