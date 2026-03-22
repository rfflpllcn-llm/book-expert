"""
Voyage au bout de la nuit — Expert Agent

Uses Anthropic API with prompt caching:
- Tier 1 knowledge is cached in the system prompt (refreshed every 5 min)
- Tier 2 arc files are loaded dynamically per query
- Q&A cache grows over time to avoid re-derivation
"""

import anthropic
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.loader import build_context, route_query, append_to_qa_cache

# ── Configuration ─────────────────────────────────────────
MODEL = "claude-sonnet-4-20250514"   # or claude-opus-4-6 for deepest analysis
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


def create_client() -> anthropic.Anthropic:
    """Create Anthropic client. Expects ANTHROPIC_API_KEY in environment."""
    return anthropic.Anthropic()


def ask(client: anthropic.Anthropic, query: str, conversation: list = None) -> str:
    """
    Send a query to the Voyage expert agent.
    Uses prompt caching for tier 1, dynamic loading for tier 2.
    """
    system_cached, dynamic_context = build_context(query)

    # Build system prompt with cache control
    system_blocks = [
        # Agent identity (small, always first)
        {
            "type": "text",
            "text": AGENT_IDENTITY,
        },
        # Tier 1 knowledge (large, cached)
        {
            "type": "text",
            "text": f"<knowledge_base_core>\n{system_cached}\n</knowledge_base_core>",
            "cache_control": {"type": "ephemeral"},
        },
    ]

    # Build messages
    messages = conversation or []

    # Add dynamic context + user query as the latest user message
    user_content = ""
    if dynamic_context:
        arc_ids = route_query(query)
        user_content += f"<knowledge_base_detail arcs=\"{', '.join(arc_ids)}\">\n"
        user_content += dynamic_context
        user_content += "\n</knowledge_base_detail>\n\n"

    user_content += query
    messages.append({"role": "user", "content": user_content})

    # Call API
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system_blocks,
        messages=messages,
    )

    # Log cache stats
    usage = response.usage
    cache_read = getattr(usage, 'cache_read_input_tokens', 0) or 0
    cache_create = getattr(usage, 'cache_creation_input_tokens', 0) or 0
    input_tokens = usage.input_tokens

    print(f"\n  [tokens] input={input_tokens} cache_read={cache_read} "
          f"cache_create={cache_create} output={usage.output_tokens}")

    if cache_read > 0:
        print(f"  [cache]  HIT — {cache_read} tokens read from cache")
    elif cache_create > 0:
        print(f"  [cache]  MISS — {cache_create} tokens written to cache")

    # Extract response text
    answer = ""
    for block in response.content:
        if block.type == "text":
            answer += block.text

    return answer


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
            query = input("\n📖 > ").strip()
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
            cache_path = Path(__file__).parent.parent / "knowledge" / "tier_1" / "08_qa_cache.md"
            content = cache_path.read_text(encoding="utf-8")
            q_count = content.count("## Q:")
            print(f"  [cache] {q_count} validated Q&A pairs")
            print(content[-500:] if len(content) > 500 else content)
            continue

        if query.startswith("/save "):
            parts = query[6:].split("|||")
            if len(parts) == 2:
                append_to_qa_cache(parts[0].strip(), parts[1].strip())
                print("  [cache] Q&A pair saved")
            else:
                print("  Usage: /save question text ||| answer text")
            continue

        # Route and answer
        arc_ids = route_query(query)
        if arc_ids:
            print(f"  [routing] Loading: {', '.join(arc_ids)}")
        else:
            print(f"  [routing] Tier 1 only (no specific arc matched)")

        answer = ask(client, query, conversation)
        print(f"\n{answer}")

        # Keep conversation history (last 10 turns)
        conversation.append({"role": "user", "content": query})
        conversation.append({"role": "assistant", "content": answer})
        if len(conversation) > 20:
            conversation = conversation[-20:]


if __name__ == "__main__":
    interactive_session()
