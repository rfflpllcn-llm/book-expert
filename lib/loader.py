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
