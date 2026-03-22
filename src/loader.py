"""
Knowledge loader for Voyage au bout de la nuit expert agent.

Two-tier loading with Anthropic prompt caching:
- Tier 1: always in cached system prompt (~10K tokens)
- Tier 2: loaded per-query based on routing (~10-30K per arc file)
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent / "knowledge"
TIER1_DIR = BASE_DIR / "tier_1"
TIER2_DIR = BASE_DIR / "tier_2"

# ── Arc routing table ─────────────────────────────────────
# Maps keywords/topics to the relevant tier_2 arc file
ARC_ROUTES = {
    "02_01_incipit": {
        "keywords": ["incipit", "place clichy", "ganate", "arruolamento", "galera", "roi misère", "preghiera"],
        "line_range": (77, 230),
    },
    "02_02_guerra_fronte": {
        "keywords": ["fronte", "colonnello", "obus", "pallottole", "fiandre", "trincea"],
        "line_range": (230, 1050),
    },
    "02_03_guerra_notte": {
        "keywords": ["erranza", "notte fiandre", "noirceur"],
        "line_range": (1050, 1510),
    },
    "02_04_guerra_robinson": {
        "keywords": ["robinson guerra", "diserzione", "primo robinson", "capitano morente"],
        "line_range": (1510, 1770),
    },
    "02_05_lola_paris": {
        "keywords": ["lola", "beignet", "opéra-comique", "stand des nations", "duval", "convalescenza"],
        "line_range": (1770, 2500),
    },
    "02_06_musyne_retrovie": {
        "keywords": ["musyne", "olympia", "princhard", "retrovie"],
        "line_range": (2500, 3300),
    },
    "02_07_bestombes_teatro": {
        "keywords": ["bestombes", "elettroterapia", "branledore", "teatro", "poeta"],
        "line_range": (3300, 4500),
    },
    "02_08_nave_africa": {
        "keywords": ["africa", "nave", "amiral bragueton", "colonia", "pordurière", "foresta", "tropici", "bambo", "piroga"],
        "line_range": (4500, 7400),
    },
    "02_09_america_newyork": {
        "keywords": ["new york", "america", "quarantina", "manhattan", "grattacieli", "ellis island"],
        "line_range": (7400, 8500),
    },
    "02_10_detroit_molly": {
        "keywords": ["detroit", "ford", "fabbrica", "molly", "catena di montaggio"],
        "line_range": (8500, 9600),
    },
    "02_11_rancy_medicina": {
        "keywords": ["rancy", "medicina", "bébert", "pazient", "ambulatorio", "medico dei poveri"],
        "line_range": (9600, 11500),
    },
    "02_12_henrouille": {
        "keywords": ["henrouille", "bomba", "robinson cieco", "protiste", "vecchia", "nuora"],
        "line_range": (11500, 14600),
    },
    "02_13_toulouse": {
        "keywords": ["toulouse", "cripta", "mummie", "morte della vecchia"],
        "line_range": (14600, 15500),
    },
    "02_14_vigny_baryton": {
        "keywords": ["vigny", "baryton", "parapine", "manicomio", "asilo"],
        "line_range": (15500, 18800),
    },
    "02_15_sophie_finale": {
        "keywords": ["sophie", "madelon", "finale", "morte robinson", "rimorchiatore", "senna", "taxi", "batignolles"],
        "line_range": (18800, 20500),
    },
}


def load_tier1() -> str:
    """Load all tier 1 files concatenated. This goes in the cached system prompt."""
    content_parts = []
    for filepath in sorted(TIER1_DIR.glob("*.md")):
        text = filepath.read_text(encoding="utf-8")
        content_parts.append(f"<!-- FILE: {filepath.name} -->\n{text}")
    return "\n\n---\n\n".join(content_parts)


def load_tier2_file(arc_id: str) -> str:
    """Load a specific tier 2 arc file."""
    filepath = TIER2_DIR / f"{arc_id}.md"
    if filepath.exists():
        return filepath.read_text(encoding="utf-8")
    return ""


def route_query(query: str) -> list[str]:
    """
    Given a user query, determine which tier 2 files to load.
    Returns a list of arc_ids to load.
    """
    query_lower = query.lower()
    matched_arcs = []

    for arc_id, config in ARC_ROUTES.items():
        for kw in config["keywords"]:
            if kw in query_lower:
                matched_arcs.append(arc_id)
                break

    # Check for SC_xxxxx references
    import re
    sc_matches = re.findall(r'SC_?(\d{3,5})', query, re.IGNORECASE)
    if sc_matches:
        for sc_num_str in sc_matches:
            sc_line = int(sc_num_str)  # approximate: SC number ~ line number
            for arc_id, config in ARC_ROUTES.items():
                lo, hi = config["line_range"]
                if lo <= sc_line <= hi:
                    if arc_id not in matched_arcs:
                        matched_arcs.append(arc_id)

    # Check for line references (L1234)
    line_matches = re.findall(r'L(\d{2,5})', query)
    if line_matches:
        for line_str in line_matches:
            line_num = int(line_str)
            for arc_id, config in ARC_ROUTES.items():
                lo, hi = config["line_range"]
                if lo <= line_num <= hi:
                    if arc_id not in matched_arcs:
                        matched_arcs.append(arc_id)

    # If query mentions characters, route to their main arcs
    char_arcs = {
        "ganate": ["02_01_incipit"],
        "colonnello": ["02_02_guerra_fronte"],
        "lola": ["02_05_lola_paris", "02_09_america_newyork"],
        "musyne": ["02_06_musyne_retrovie"],
        "molly": ["02_10_detroit_molly"],
        "bébert": ["02_11_rancy_medicina"],
        "baryton": ["02_14_vigny_baryton"],
        "sophie": ["02_15_sophie_finale"],
        "madelon": ["02_13_toulouse", "02_14_vigny_baryton", "02_15_sophie_finale"],
    }
    for char, arcs in char_arcs.items():
        if char in query_lower:
            for arc in arcs:
                if arc not in matched_arcs:
                    matched_arcs.append(arc)

    # Robinson appears everywhere — load his main arcs
    if "robinson" in query_lower:
        robinson_arcs = ["02_04_guerra_robinson", "02_11_rancy_medicina",
                         "02_12_henrouille", "02_15_sophie_finale"]
        for arc in robinson_arcs:
            if arc not in matched_arcs:
                matched_arcs.append(arc)

    # Cap at 4 arcs to keep context manageable
    return matched_arcs[:4]


def build_context(query: str) -> tuple[str, str]:
    """
    Build the full context for a query.
    Returns: (system_prompt_cached, user_context_dynamic)
    """
    # System prompt = tier 1 (cached)
    system_prompt = load_tier1()

    # Dynamic context = routed tier 2 files
    arc_ids = route_query(query)
    dynamic_parts = []

    if arc_ids:
        for arc_id in arc_ids:
            content = load_tier2_file(arc_id)
            if content:
                dynamic_parts.append(f"<!-- ARC: {arc_id} -->\n{content}")

    dynamic_context = "\n\n---\n\n".join(dynamic_parts) if dynamic_parts else ""

    return system_prompt, dynamic_context


def append_to_qa_cache(question: str, summary: str, scene_refs: str = "",
                       full_answer: str = ""):
    """Append a Q&A pair to the cache and optionally save the full answer as .md."""
    import re
    from datetime import date

    today = date.today().isoformat()
    answers_dir = BASE_DIR / "answers"
    cache_path = TIER1_DIR / "08_qa_cache.md"

    # Save full answer as .md file if provided
    answer_file = None
    if full_answer:
        answers_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r'[^a-z0-9]+', '-', question.lower().strip())[:60].strip('-')
        answer_file = answers_dir / f"{today}_{slug}.md"
        content = f"# {question}\n\n**Data**: {today}\n**SC di riferimento**: {scene_refs}\n\n{full_answer}\n"
        answer_file.write_text(content, encoding="utf-8")

    # Append summary to cache
    entry = f"\n\n## Q: {question}\n"
    if scene_refs:
        entry += f"**SC di riferimento**: {scene_refs}\n"
    entry += f"**Risposta**: {summary}\n"
    if answer_file:
        entry += f"**Risposta completa**: {answer_file.relative_to(BASE_DIR)}\n"
    entry += f"**Data**: {today}\n"

    with open(cache_path, "a", encoding="utf-8") as f:
        f.write(entry)
