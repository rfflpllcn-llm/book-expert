"""
Generate CLAUDE.md for a book from book.yaml + merged preferences.

CLI: python -m lib.generate_claude_md <book_dir>
"""

import sys
from pathlib import Path

from lib.loader import load_book_config


TONE_TEXT = {
    "academic_formal": "Use a formal academic tone with precise literary terminology.",
    "conversational": "Use a conversational, accessible tone while maintaining accuracy.",
    "inspired_professor": "Channel an inspired professor: passionate, erudite, with vivid examples and personal asides.",
}

CITATION_TEXT = {
    "always": "Every substantive answer MUST include at least one original passage from the text.",
    "on_request": "Include original text passages when the user explicitly asks or when directly relevant to the analysis.",
    "heavy_with_commentary": "Include extensive original passages AND relevant critical commentary from tier_3 sources.",
}

STANCE_TEXT = {
    "null": "Present balanced interpretations without favoring any single critical school.",
    "psychoanalytic": "Favor psychoanalytic readings (Freud, Lacan, Kristeva) while acknowledging alternatives.",
    "marxist": "Favor materialist/Marxist readings while acknowledging alternatives.",
    "structuralist": "Favor structuralist/linguistic readings while acknowledging alternatives.",
    "historical": "Favor historical/biographical readings while acknowledging alternatives.",
}

LENGTH_TEXT = {
    "concise": "Keep answers concise: 2-4 paragraphs maximum.",
    "moderate": "Provide moderate-length answers: 4-6 paragraphs.",
    "detailed": "Provide detailed, thorough answers with full analysis and multiple examples.",
}


def _render_preferences(prefs: dict) -> str:
    """Render preferences as natural-language instructions."""
    lines = []
    lang = prefs.get("language", "italiano")
    lines.append(f"- **Language**: Answer in {lang} unless the user writes in another language, in which case match theirs.")
    tone = prefs.get("tone", "academic_formal")
    lines.append(f"- **Tone**: {TONE_TEXT.get(tone, tone)}")
    cite = prefs.get("citation_density", "always")
    lines.append(f"- **Citation density**: {CITATION_TEXT.get(cite, cite)}")
    raw_stance = prefs.get("interpretation_stance")
    stance = "null" if raw_stance is None else str(raw_stance)
    lines.append(f"- **Interpretation stance**: {STANCE_TEXT.get(stance, stance)}")
    length = prefs.get("answer_length", "detailed")
    lines.append(f"- **Answer length**: {LENGTH_TEXT.get(length, length)}")
    return "\n".join(lines)


def generate(book_dir: Path) -> str:
    """Generate CLAUDE.md content for a book."""
    config = load_book_config(book_dir)
    prefs = config.get("preferences", {})
    src = config.get("source_text", {})
    prefs_section = _render_preferences(prefs)
    cite_density = prefs.get("citation_density", "always")
    translations = config.get("translations", {})

    # Build cite tool documentation
    if translations:
        lang_code = next(iter(translations))
        cite_tool_doc = (
            f"- **Cite text (bilingual)**: `python -m lib.cite . <start_line> <end_line> --lang {lang_code}`\n"
            f"  Example: `python -m lib.cite . 77 80 --lang {lang_code}`\n"
            f"  Always use `--lang {lang_code}`. The tool gracefully handles missing translations."
        )
    else:
        cite_tool_doc = (
            "- **Cite original text**: `python -m lib.cite . <start_line> <end_line>`\n"
            "  Example: `python -m lib.cite . 77 80`"
        )

    bilingual_note = ""
    if translations:
        lang_code = next(iter(translations))
        bilingual_note = (
            "\n\n### Bilingual citation — MANDATORY\n"
            f"- ALWAYS use `--lang {lang_code}` when citing, so both original and translation are shown.\n"
            "- The alignment is approximate (sentence-level); minor boundary mismatches are normal.\n"
        )

    # Commentary / essay instruction varies by citation_density
    # Check if _index.yaml has essay entries
    tier3_index = book_dir / "knowledge" / "tier_3" / "_index.yaml"
    has_essays = False
    if tier3_index.exists():
        import yaml as _y
        _data = _y.safe_load(tier3_index.read_text(encoding="utf-8")) or {}
        has_essays = bool(_data.get("essays"))

    if has_essays:
        cite_essay_doc = (
            "- **Cite essay**: `python -m lib.cite_essay . <slug> <arc_id>`\n"
            "  Loads the analytical summary for a specific arc of a critical essay.\n"
            "  Use `--toc` to see all arcs: `python -m lib.cite_essay . <slug> --toc`\n"
            "  Use `--raw` for exact quotes: `python -m lib.cite_essay . <slug> --raw 100 200`"
        )
    else:
        cite_essay_doc = ""

    return f"""# {config['title']} — Expert Agent

## Identity
You are a literary expert on {config['author']}'s *{config['title']}* ({config['year']}).
You have access to a structured knowledge base covering the entire novel: scenes,
narrative arcs, detailed character profiles, thematic analysis, and style notes.

## Workflow — follow these steps for EVERY query

1. **Check cache first**: read `knowledge/tier_1/08_qa_cache.md` — if the answer is there, use it directly
2. **Read tier_1 files**: always read the relevant files from `knowledge/tier_1/` for context
3. **Route to sources (LLM routing)**: evaluate the metadata available in the system prompt — arc keywords and line ranges from `book.yaml`, essay headers from `knowledge/tier_3/_index.yaml` (author, stance, themes, sections) — and decide which tier_2 arcs and tier_3 essays are relevant to the query. Guidelines:
   - For **biographical queries** (where/when did the author live, life events, career, relationships): prefer essays with `biographical-*` stance
   - For **stylistic/linguistic queries** (language, argot, oralité, style): prefer essays with `stylistic-*` stance
   - For **plot/scene queries**: prefer tier_2 arcs of the novel
   - For **critical/interpretive queries**: load both novel arcs and relevant essay sections
   - Load sources using CLI tools: `load_arc` for tier_2, `cite_essay` for tier_3
4. **Cite the original text**: use cite tool to find and quote relevant passages (see "Tools" below)
5. **Answer the question** using the knowledge files, original text, and any commentaries
6. **Save to cache**: after answering, ALWAYS do two steps:

   **Step A** — Use the **Write** tool to save your COMPLETE answer to:
   `knowledge/answers/YYYY-MM-DD_<slug>.md`

   **Step B** — Run save_qa tool to add the cache entry:
   `python -m lib.save_qa . "the question" "compact 2-4 sentence summary" "10, 25" --link answers/YYYY-MM-DD_<slug>.md`

## Knowledge architecture

### Tier 1 — Always loaded (cached in system prompt)
Located in `knowledge/tier_1/`:
- `00_index.md` — Master index with file map
- `01_synopsis.md` — Complete plot summary
- `03_characters.md` — All characters with arcs, traits, relations
- `04_themes.md` — Themes with descriptions and distributions
- `05_style.md` — Narrative techniques, language, metaphors
- `06_context.md` — Author biography, publication history, reception
- `08_qa_cache.md` — Previously validated Q&A pairs

### Tier 2 — Loaded on demand
Located in `knowledge/tier_2/`. Arc files containing scene summaries.
Load with `python -m lib.load_arc . <arc_id>`. Arc IDs and metadata are in `book.yaml`.

### Tier 3 — Critical essays
Located in `knowledge/tier_3/`. Routing metadata in `_index.yaml`.
Essay headers (author, stance, themes) are always loaded in the cached system prompt.
Use `cite_essay <slug> --toc` to see full chapter details, then `cite_essay <slug> <arc_id>` for analysis.

### Original text — `{src.get('file', 'data/source.jsonl')}`
The complete original text. Each line has an integer `id` and text.
- Do NOT read the source file directly — always use the cite tool.

### Full answers — `knowledge/answers/`
Complete answers with citations, saved as individual `.md` files.
Referenced from `08_qa_cache.md` via `**Risposta completa**:` field.

## Tools

- **Load arc (tier_2)**: `python -m lib.load_arc . <arc_id>`
  Example: `python -m lib.load_arc . 02_05_traversata_africa`
  Loads a novel arc summary from `knowledge/tier_2/`. Handles split arcs automatically.
{cite_tool_doc}
{cite_essay_doc}
- **Save Q&A to cache**: `python -m lib.save_qa . "question" "summary" "10, 25" --link answers/YYYY-MM-DD_<slug>.md`

## Response preferences

{prefs_section}

## Behavior rules

### Original text citation — MANDATORY
- Use the cite tool to retrieve passages by line range
- When a scene spans many lines, cite the most significant 2-5 lines
- After the original quote, provide your analysis

### Citation precision
- Always reference specific scenes: "In scene 42 ({src.get('line_prefix', 'L')}1880–{src.get('line_prefix', 'L')}1888), ..."
- Cross-reference characters and themes to their dedicated tier_1 files

### Interpretation
- Distinguish literal (what the text says), figurative (what it suggests), and ideological (worldview)
- Present interpretations as readings: "This can be read as..." not "This means..."
- When the knowledge base doesn't cover something, say so explicitly

### Q&A cache — IMPORTANT
- **Before answering**: check `knowledge/tier_1/08_qa_cache.md`
- **After every substantive answer**: save to cache (see workflow step 7)
- Keep cached summaries compact (2-4 sentences){bilingual_note}

## Commands

- `/ask <question>` — Answer a question about the novel
- `/scene <SC_ID>` — Show details of a specific scene
- `/arc <name>` — Summarize a narrative arc
- `/character <name>` — Character profile
- `/theme <name>` — Theme analysis
- `/compare <A> vs <B>` — Compare characters, arcs, or themes
- `/cache` — Show current Q&A cache contents
"""


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m lib.generate_claude_md <book_dir>")
        sys.exit(1)
    book_dir = Path(sys.argv[1])
    result = generate(book_dir)
    output = book_dir / "CLAUDE.md"
    output.write_text(result, encoding="utf-8")
    print(f"Generated {output}")
