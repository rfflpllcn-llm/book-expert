"""
Knowledge loader for multi-book literary expert system.

All functions take book_dir (Path) as first argument.
Config-driven via book.yaml — no hardcoded routing.
"""

import re
from dataclasses import dataclass, field

import yaml
from pathlib import Path


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

    def __bool__(self):
        return bool(self.arcs) or bool(self.essays)

    def __len__(self):
        return len(self.arcs)

    def __contains__(self, item):
        return item in self.arcs


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


def route_query(query: str, config: dict, *, essays: dict | None = None) -> RouteResult:
    """Route a query to relevant tier_2 arc files and essay slugs.

    Args:
        query:  The user's question.
        config: Parsed book.yaml.
        essays: Optional dict from _index.yaml["essays"]. If provided,
                author, work, themes and characters are matched against the query.
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

    # Essay routing: exact substring matching for author, work, themes,
    # characters.  Fuzzy/semantic matching is delegated to the LLM which
    # already has essay headers in the cached system prompt.
    matched_essays = []
    if essays:
        for slug, info in essays.items():
            if slug in matched_essays:
                continue
            author = info.get("author", "")
            work = info.get("work", "")
            if author and author.lower() in query_lower:
                matched_essays.append(slug)
                continue
            if work and work.lower() in query_lower:
                matched_essays.append(slug)
                continue
            for theme in info.get("themes", []):
                if theme.lower() in query_lower:
                    matched_essays.append(slug)
                    break
            else:
                for char in info.get("characters", []):
                    if char.lower() in query_lower:
                        matched_essays.append(slug)
                        break

    return RouteResult(arcs=matched_arcs[:4], essays=matched_essays[:3])


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


def _load_tier3_index(book_dir: Path) -> dict:
    """Load tier_3/_index.yaml. Returns the parsed dict or empty."""
    index_path = book_dir / "knowledge" / "tier_3" / "_index.yaml"
    if not index_path.exists():
        return {}
    return yaml.safe_load(index_path.read_text(encoding="utf-8")) or {}


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


def append_to_qa_cache(book_dir: Path, question: str, summary: str,
                       scene_refs: str = "", full_answer: str = ""):
    """Append a Q&A pair to cache and optionally save the full answer."""
    from datetime import date

    knowledge_dir = book_dir / "knowledge"
    cache_path = knowledge_dir / "tier_1" / "08_qa_cache.md"
    answers_dir = knowledge_dir / "answers"
    today = date.today().isoformat()

    # Save full answer as .md file
    answer_file = None
    if full_answer:
        answers_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "-", question.lower().strip())[:60].strip("-")
        answer_file = answers_dir / f"{today}_{slug}.md"
        content = f"# {question}\n\n**Data**: {today}\n**SC di riferimento**: {scene_refs}\n\n{full_answer}\n"
        answer_file.write_text(content, encoding="utf-8")

    # Append summary to cache
    entry = f"\n\n## Q: {question}\n"
    if scene_refs:
        entry += f"**SC di riferimento**: {scene_refs}\n"
    entry += f"**Risposta**: {summary}\n"
    if answer_file:
        rel = answer_file.relative_to(knowledge_dir)
        entry += f"**Risposta completa**: {rel}\n"
    entry += f"**Data**: {today}\n"

    with open(cache_path, "a", encoding="utf-8") as f:
        f.write(entry)
