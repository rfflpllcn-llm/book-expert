"""
Voyage au bout de la nuit — Expert Agent

Uses Anthropic API with prompt caching:
- Tier 1 knowledge is cached in the system prompt (refreshed every 5 min)
- Tier 2 arc files are loaded dynamically per query
- Q&A cache grows over time to avoid re-derivation
"""

import re
import anthropic
from pathlib import Path

from lib.loader import build_context, route_query, load_book_config, append_to_qa_cache
from lib.cite import load_lines, format_citation

# ── Configuration ─────────────────────────────────────────
BOOK_DIR = Path(".")
MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 4096

AGENT_IDENTITY = """You are a literary expert on Céline's Voyage au bout de la nuit.
You answer questions using the structured knowledge base provided.

Rules:
- Answer in the user's language
- Cite specific scenes: "In SC_00367 (L1880), Bardamu..."
- Distinguish literal / figurative / ideological readings
- Say explicitly when the knowledge base doesn't cover something
- After answering, suggest which scenes the user might want to explore next
"""


# ── Citation post-processing ─────────────────────────────
_CITE_RE = re.compile(r"\(L(\d+)\s*[–\-]\s*L?(\d+)\)")


def append_citations(answer: str) -> str:
    """Parse L-range references and append French text as citations."""
    matches = _CITE_RE.findall(answer)
    if not matches:
        return answer

    seen = set()
    unique_ranges = []
    for start_s, end_s in matches:
        key = (int(start_s), int(end_s))
        if key not in seen:
            seen.add(key)
            unique_ranges.append(key)

    citations = []
    for start, end in unique_ranges:
        lines = load_lines(BOOK_DIR, start, end)
        if lines:
            citations.append(format_citation(lines))

    if not citations:
        return answer

    return answer + "\n\n---\n### Citazioni\n\n" + "\n\n".join(citations)


def create_client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


def ask(client: anthropic.Anthropic, query: str, conversation: list = None) -> str:
    """Send a query to the expert agent with prompt caching."""
    config = load_book_config(BOOK_DIR)
    system_cached, dynamic_context = build_context(query, BOOK_DIR)

    system_blocks = [
        {"type": "text", "text": AGENT_IDENTITY},
        {
            "type": "text",
            "text": f"<knowledge_base_core>\n{system_cached}\n</knowledge_base_core>",
            "cache_control": {"type": "ephemeral"},
        },
    ]

    messages = conversation or []

    user_content = ""
    if dynamic_context:
        arc_ids = route_query(query, config)
        user_content += f'<knowledge_base_detail arcs="{", ".join(arc_ids)}">\n'
        user_content += dynamic_context
        user_content += "\n</knowledge_base_detail>\n\n"

    user_content += query
    messages.append({"role": "user", "content": user_content})

    response = client.messages.create(
        model=MODEL, max_tokens=MAX_TOKENS, system=system_blocks, messages=messages
    )

    usage = response.usage
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_create = getattr(usage, "cache_creation_input_tokens", 0) or 0

    print(f"\n  [tokens] input={usage.input_tokens} cache_read={cache_read} "
          f"cache_create={cache_create} output={usage.output_tokens}")

    if cache_read > 0:
        print(f"  [cache]  HIT — {cache_read} tokens read from cache")
    elif cache_create > 0:
        print(f"  [cache]  MISS — {cache_create} tokens written to cache")

    answer = ""
    for block in response.content:
        if block.type == "text":
            answer += block.text

    return append_citations(answer)


def interactive_session():
    """Run an interactive Q&A session."""
    client = create_client()
    conversation = []

    print("=" * 60)
    print("  VOYAGE AU BOUT DE LA NUIT — Expert Agent")
    print("=" * 60)
    print("  Commands:")
    print("    /quit          — Exit")
    print("    /cache         — Show Q&A cache stats")
    print("    /save Q|||A    — Save a Q&A pair to cache")
    print("    /clear         — Clear conversation history")
    print("    (anything else) — Ask a question")
    print("=" * 60)

    while True:
        try:
            query = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nArrivederci.")
            break

        if not query:
            continue

        if query == "/quit":
            print("Arrivederci.")
            break

        if query == "/clear":
            conversation = []
            print("  [conversation cleared]")
            continue

        if query == "/cache":
            cache_path = BOOK_DIR / "knowledge" / "tier_1" / "08_qa_cache.md"
            content = cache_path.read_text(encoding="utf-8")
            q_count = content.count("## Q:")
            print(f"  [cache] {q_count} validated Q&A pairs")
            print(content[-500:] if len(content) > 500 else content)
            continue

        if query.startswith("/save "):
            parts = query[6:].split("|||")
            if len(parts) == 2:
                append_to_qa_cache(BOOK_DIR, parts[0].strip(), parts[1].strip())
                print("  [cache] Q&A pair saved")
            else:
                print("  Usage: /save question text ||| answer text")
            continue

        # Route and answer
        config = load_book_config(BOOK_DIR)
        arc_ids = route_query(query, config)
        if arc_ids:
            print(f"  [routing] Loading: {', '.join(arc_ids)}")
        else:
            print("  [routing] Tier 1 only (no specific arc matched)")

        answer = ask(client, query, conversation)
        print(f"\n{answer}")

        # Auto-save
        sentences = answer.split(". ")
        summary = ". ".join(sentences[:3])
        if len(summary) > 500:
            summary = summary[:497] + "..."
        if not summary.endswith("."):
            summary += "."
        append_to_qa_cache(BOOK_DIR, query, summary, full_answer=answer)
        print("  [saved] Answer cached")

        conversation.append({"role": "user", "content": query})
        conversation.append({"role": "assistant", "content": answer})
        if len(conversation) > 20:
            conversation = conversation[-20:]


if __name__ == "__main__":
    interactive_session()
