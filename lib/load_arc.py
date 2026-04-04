"""
Load a tier_2 arc file from the novel's knowledge base.

Handles split arcs: if book.yaml defines a `split` key for the arc,
all split files are concatenated.

CLI:
  python -m lib.load_arc <book_dir> <arc_id>
  python -m lib.load_arc . 02_05_traversata_africa
"""

import sys
from pathlib import Path

from lib.loader import load_book_config, load_tier2_file


def load_arc(book_dir: Path, arc_id: str) -> str:
    """Load an arc, handling split arcs from book.yaml."""
    # Try direct file first
    result = load_tier2_file(book_dir, arc_id)
    if result:
        return result

    # Check book.yaml for split entries
    config = load_book_config(book_dir)
    arc_config = config.get("arcs", {}).get(arc_id)
    if not arc_config or "split" not in arc_config:
        return ""

    parts = []
    tier2_dir = book_dir / "knowledge" / "tier_2"
    for split_entry in arc_config["split"]:
        filepath = tier2_dir / split_entry["file"]
        if filepath.exists():
            parts.append(filepath.read_text(encoding="utf-8"))
    return "\n\n---\n\n".join(parts)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python -m lib.load_arc <book_dir> <arc_id>", file=sys.stderr)
        sys.exit(1)

    book_dir = Path(sys.argv[1])
    arc_id = sys.argv[2]

    result = load_arc(book_dir, arc_id)
    if result:
        print(result)
    else:
        print(f"Arc '{arc_id}' not found in {book_dir / 'knowledge' / 'tier_2'}/", file=sys.stderr)
        sys.exit(1)
