"""
Knowledge loader for multi-book literary expert system.

All functions take book_dir (Path) as first argument.
Config-driven via book.yaml — no hardcoded routing.
"""

import re

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
