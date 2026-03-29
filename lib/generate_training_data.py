"""Generate a chat fine-tuning dataset (messages format) from book-expert artifacts.

Usage:
    python -m lib.generate_training_data books/<slug> --output dataset.jsonl

Reads the knowledge base (tier_1, tier_2), book.yaml, source text, and
extracted_chunks.json to produce a JSONL file where each line is a conversation
in OpenAI messages format:

    {"messages": [{"role": "system", ...}, {"role": "user", ...}, {"role": "assistant", ...}]}

The dataset covers 7 question categories per arc, plus cross-arc and
whole-book questions. Each example is grounded in the knowledge base with
scene IDs and line references.
"""

import json
import re
import random
import argparse
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def read_md(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_source_lines(book_dir: Path, cfg: dict) -> dict[str, str]:
    """Return {line_id: text} from source JSONL or CSV."""
    st = cfg["source_text"]
    src = book_dir / st["file"]
    lines = {}
    if st["format"] == "jsonl":
        for raw in src.read_text(encoding="utf-8").splitlines():
            rec = json.loads(raw)
            lines[str(rec[st["line_column"]])] = rec[st["text_column"]]
    elif st["format"] == "csv":
        import csv
        with open(src, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if st.get("filter_column") and row.get(st["filter_column"]) != st.get("filter_value"):
                    continue
                lines[str(row[st["line_column"]])] = row[st["text_column"]]
    return lines


def get_passage(source_lines: dict[str, str], start: int, end: int) -> str:
    """Extract a passage from source lines by numeric range."""
    parts = []
    for i in range(start, min(end + 1, start + 10)):  # cap at 10 lines
        text = source_lines.get(str(i), "")
        if text:
            parts.append(text)
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Parsers for knowledge artifacts
# ---------------------------------------------------------------------------

def parse_tier2_scenes(md_text: str) -> list[dict]:
    """Parse a tier_2 arc file into scene dicts."""
    scenes = []
    scene_pattern = re.compile(
        r"###\s+(SC_\d+)\s+\(L(\d+)[–-]L(\d+)\)\s*\n(.+?)(?=\n###|\n---|\Z)",
        re.DOTALL,
    )
    for m in scene_pattern.finditer(md_text):
        sc_id, l_start, l_end, body = m.group(1), m.group(2), m.group(3), m.group(4).strip()
        # Extract characters and themes lines
        chars_m = re.search(r"\*\*Personaggi\*\*:\s*(.+)", body)
        themes_m = re.search(r"\*\*Temi\*\*:\s*(.+)", body)
        # Summary is everything before the metadata lines
        summary_lines = []
        for line in body.splitlines():
            if line.startswith("**Personaggi**") or line.startswith("**Temi**") or line.startswith("**Tono**"):
                break
            if line.strip():
                summary_lines.append(line.strip())
        scenes.append({
            "sc_id": sc_id,
            "line_start": int(l_start),
            "line_end": int(l_end),
            "summary": " ".join(summary_lines),
            "characters": chars_m.group(1).strip() if chars_m else "",
            "themes": themes_m.group(1).strip() if themes_m else "",
        })
    return scenes


def parse_characters(md_text: str) -> list[dict]:
    """Parse tier_1/03_characters.md into character dicts."""
    characters = []
    char_pattern = re.compile(
        r"##\s+(.+?)(?:\s*\(.+?\))?\s*\n(.+?)(?=\n##|\Z)",
        re.DOTALL,
    )
    for m in char_pattern.finditer(md_text):
        name = m.group(1).strip()
        body = m.group(2).strip()
        fields = {}
        for line in body.splitlines():
            fm = re.match(r"-\s+\*\*(.+?)\*\*:\s*(.+)", line)
            if fm:
                fields[fm.group(1).lower()] = fm.group(2).strip()
        if fields:
            fields["name"] = name
            characters.append(fields)
    return characters


def parse_themes(md_text: str) -> list[dict]:
    """Parse tier_1/04_themes.md into theme dicts."""
    themes = []
    theme_pattern = re.compile(
        r"##\s+(.+?)\s*\n\n(.+?)(?=\n---|\n##\s|\Z)",
        re.DOTALL,
    )
    for m in theme_pattern.finditer(md_text):
        name = m.group(1).strip()
        body = m.group(2).strip()
        # First paragraph is description
        paragraphs = body.split("\n\n")
        desc = paragraphs[0] if paragraphs else ""
        themes.append({"name": name, "description": desc, "body": body})
    return themes


def parse_synopsis_arcs(md_text: str) -> list[dict]:
    """Parse tier_1/01_synopsis.md into arc summaries."""
    arcs = []
    arc_pattern = re.compile(
        r"##\s+\d+\.\s+(.+?)\s*\n\*\((.+?)\)\*\s*\n\n(.+?)(?=\n---|\n##|\Z)",
        re.DOTALL,
    )
    for m in arc_pattern.finditer(md_text):
        arcs.append({
            "title": m.group(1).strip(),
            "meta": m.group(2).strip(),
            "summary": m.group(3).strip(),
        })
    return arcs


# ---------------------------------------------------------------------------
# Message builders
# ---------------------------------------------------------------------------

def make_msg(system: str, user: str, assistant: str) -> dict:
    return {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ]
    }


def make_system_prompt(cfg: dict) -> str:
    return (
        f"You are a literary expert on {cfg['author']}'s *{cfg['title']}* ({cfg['year']}). "
        f"You have deep knowledge of the novel's plot, characters, themes, narrative techniques, "
        f"and historical context. Answer with specific scene references (SC_IDs) and line numbers "
        f"when relevant. Be precise and analytical."
    )


# ---------------------------------------------------------------------------
# Dataset generators — one function per question category
# ---------------------------------------------------------------------------

def gen_scene_summary(cfg, system, scenes, source_lines):
    """Category 1: 'What happens in scene X?' → scene summary."""
    pairs = []
    for sc in scenes:
        passage = get_passage(source_lines, sc["line_start"], sc["line_end"])
        questions = [
            f"What happens in {sc['sc_id']} (lines {sc['line_start']}–{sc['line_end']})?",
            f"Summarize the scene at lines {sc['line_start']}–{sc['line_end']}.",
        ]
        answer = sc["summary"]
        if sc["characters"]:
            answer += f"\n\nCharacters present: {sc['characters']}"
        if sc["themes"]:
            answer += f"\nThemes: {sc['themes']}"
        pairs.append(make_msg(system, random.choice(questions), answer))
    return pairs


def gen_passage_analysis(cfg, system, scenes, source_lines):
    """Category 2: Given a raw passage, analyze it."""
    pairs = []
    for sc in scenes:
        passage = get_passage(source_lines, sc["line_start"], sc["line_end"])
        if len(passage) < 50:
            continue
        # Truncate very long passages
        if len(passage) > 800:
            passage = passage[:800] + "..."
        q = f"Analyze this passage from *{cfg['title']}*:\n\n> {passage}"
        a = (
            f"This passage is from {sc['sc_id']} (L{sc['line_start']}–L{sc['line_end']}). "
            f"{sc['summary']}"
        )
        if sc["themes"]:
            a += f"\n\nThe key themes here are: {sc['themes']}."
        pairs.append(make_msg(system, q, a))
    return pairs


def gen_character_questions(cfg, system, characters):
    """Category 3: Character profile questions."""
    pairs = []
    for ch in characters:
        name = ch["name"]
        # Profile question
        profile_parts = []
        if ch.get("ruolo"):
            profile_parts.append(f"**Role**: {ch['ruolo']}")
        if ch.get("tratti"):
            profile_parts.append(f"**Traits**: {ch['tratti']}")
        if ch.get("arco narrativo"):
            profile_parts.append(f"**Arc**: {ch['arco narrativo']}")
        if ch.get("relazioni"):
            profile_parts.append(f"**Relationships**: {ch['relazioni']}")
        if profile_parts:
            pairs.append(make_msg(
                system,
                f"Who is {name} in *{cfg['title']}*? Describe their role and significance.",
                "\n".join(profile_parts),
            ))
        # Relationship question
        if ch.get("relazioni"):
            pairs.append(make_msg(
                system,
                f"What are {name}'s key relationships in the novel?",
                ch["relazioni"],
            ))
    return pairs


def gen_theme_questions(cfg, system, themes):
    """Category 4: Theme analysis questions."""
    pairs = []
    for th in themes:
        pairs.append(make_msg(
            system,
            f"How does the theme of '{th['name']}' manifest in *{cfg['title']}*?",
            th["body"],
        ))
        # Shorter version
        pairs.append(make_msg(
            system,
            f"What role does '{th['name']}' play in the novel?",
            th["description"],
        ))
    return pairs


def gen_arc_summary(cfg, system, synopsis_arcs):
    """Category 5: Arc-level plot questions."""
    pairs = []
    for arc in synopsis_arcs:
        pairs.append(make_msg(
            system,
            f"What happens in the '{arc['title']}' section of *{cfg['title']}*?",
            f"*({arc['meta']})*\n\n{arc['summary']}",
        ))
    return pairs


def gen_style_questions(cfg, system, style_md):
    """Category 6: Style and technique questions from tier_1/05_style.md."""
    pairs = []
    # Whole-file question
    pairs.append(make_msg(
        system,
        f"Describe the narrative style and techniques in *{cfg['title']}*.",
        style_md,
    ))
    # Parse sections
    sections = re.split(r"\n## ", style_md)
    for sec in sections[1:]:  # skip header
        lines = sec.strip().splitlines()
        title = lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        if body:
            pairs.append(make_msg(
                system,
                f"How does {cfg['author']} use {title.lower()} in *{cfg['title']}*?",
                body,
            ))
    return pairs


def gen_cross_arc(cfg, system, scenes, synopsis_arcs):
    """Category 7: Cross-arc comparison questions."""
    pairs = []
    if len(synopsis_arcs) < 2:
        return pairs
    # Compare consecutive arcs
    for i in range(len(synopsis_arcs) - 1):
        a1, a2 = synopsis_arcs[i], synopsis_arcs[i + 1]
        q = f"How does the '{a1['title']}' section contrast with '{a2['title']}' in *{cfg['title']}*?"
        answer = (
            f"**{a1['title']}** ({a1['meta']}): {a1['summary'][:300]}...\n\n"
            f"**{a2['title']}** ({a2['meta']}): {a2['summary'][:300]}..."
        )
        pairs.append(make_msg(system, q, answer))
    return pairs


def gen_multi_turn(cfg, system, characters, themes, scenes):
    """Category 8: Multi-turn conversations (2–3 turns) for richer training signal."""
    pairs = []
    for ch in characters[:5]:  # top 5 characters
        name = ch["name"]
        # Find scenes mentioning this character
        ch_scenes = [s for s in scenes if name.split()[0].lower() in s.get("characters", "").lower()][:3]
        if not ch_scenes:
            continue
        turn1_q = f"Tell me about {name} in *{cfg['title']}*."
        turn1_a = []
        if ch.get("ruolo"):
            turn1_a.append(ch["ruolo"])
        if ch.get("tratti"):
            turn1_a.append(f"Key traits: {ch['tratti']}")
        turn1_a_text = " ".join(turn1_a) if turn1_a else f"{name} is a character in the novel."

        turn2_q = f"Can you show me a specific scene where {name} is important?"
        sc = ch_scenes[0]
        turn2_a = f"In {sc['sc_id']} (L{sc['line_start']}–L{sc['line_end']}): {sc['summary']}"

        pairs.append({
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": turn1_q},
                {"role": "assistant", "content": turn1_a_text},
                {"role": "user", "content": turn2_q},
                {"role": "assistant", "content": turn2_a},
            ]
        })
    return pairs


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def generate_dataset(book_dir: Path) -> list[dict]:
    cfg = load_yaml(book_dir / "book.yaml")
    system = make_system_prompt(cfg)

    # Load source text
    source_lines = load_source_lines(book_dir, cfg)

    # Load and parse knowledge files
    tier1 = book_dir / "knowledge" / "tier_1"
    tier2 = book_dir / "knowledge" / "tier_2"

    characters = parse_characters(read_md(tier1 / "03_characters.md"))
    themes = parse_themes(read_md(tier1 / "04_themes.md"))
    synopsis_arcs = parse_synopsis_arcs(read_md(tier1 / "01_synopsis.md"))
    style_md = read_md(tier1 / "05_style.md")

    # Parse all tier_2 scene files
    all_scenes = []
    for f in sorted(tier2.glob("02_*.md")):
        all_scenes.extend(parse_tier2_scenes(read_md(f)))

    # Generate all categories
    dataset = []
    dataset.extend(gen_scene_summary(cfg, system, all_scenes, source_lines))
    dataset.extend(gen_passage_analysis(cfg, system, all_scenes, source_lines))
    dataset.extend(gen_character_questions(cfg, system, characters))
    dataset.extend(gen_theme_questions(cfg, system, themes))
    dataset.extend(gen_arc_summary(cfg, system, synopsis_arcs))
    dataset.extend(gen_style_questions(cfg, system, style_md))
    dataset.extend(gen_cross_arc(cfg, system, all_scenes, synopsis_arcs))
    dataset.extend(gen_multi_turn(cfg, system, characters, themes, all_scenes))

    random.shuffle(dataset)
    return dataset


def main():
    parser = argparse.ArgumentParser(description="Generate chat fine-tuning dataset from book-expert artifacts")
    parser.add_argument("book_dir", type=Path, help="Path to book directory (e.g. books/portnoy)")
    parser.add_argument("--output", "-o", type=Path, default=Path("dataset.jsonl"), help="Output JSONL file")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for shuffling")
    args = parser.parse_args()

    random.seed(args.seed)
    dataset = generate_dataset(args.book_dir)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for example in dataset:
            f.write(json.dumps(example, ensure_ascii=False) + "\n")

    # Print stats
    categories = {
        "single-turn": sum(1 for d in dataset if len(d["messages"]) == 3),
        "multi-turn": sum(1 for d in dataset if len(d["messages"]) > 3),
    }
    print(f"Generated {len(dataset)} examples → {args.output}")
    print(f"  Single-turn: {categories['single-turn']}")
    print(f"  Multi-turn:  {categories['multi-turn']}")


if __name__ == "__main__":
    main()
