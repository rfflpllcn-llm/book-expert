"""LLM-based chat fine-tuning dataset generator.

Uses Claude (or OpenAI-compatible providers) to generate diverse, natural
question-answer pairs from book-expert knowledge artifacts. Supports both
synchronous and batch modes.

Usage:
    # Synchronous (small books, immediate results)
    python -m lib.generate_training_data_llm books/portnoy -o dataset.jsonl

    # Batch mode (large books, ~50% cost savings)
    python -m lib.generate_training_data_llm books/portnoy -o dataset.jsonl --mode batch

    # Custom provider
    python -m lib.generate_training_data_llm books/portnoy -o dataset.jsonl --provider openai
"""

import argparse
import json
import os
import random
import re
import sys
import time
from pathlib import Path

import yaml

# Re-use parsers from the rule-based generator
from lib.generate_training_data import (
    load_yaml,
    read_md,
    load_source_lines,
    get_passage,
    make_system_prompt,
    parse_tier2_scenes,
    parse_characters,
    parse_themes,
    parse_synopsis_arcs,
)

# ---------------------------------------------------------------------------
# Provider config
# ---------------------------------------------------------------------------

PROVIDER_CONFIG = {
    "claude": {
        "model": "claude-sonnet-4-20250514",
        "supports_batch": True,
        "batch_type": "claude",
    },
    "openai": {
        "model": "gpt-4.1-mini-2025-04-14",
        "supports_batch": True,
        "batch_type": "openai",
    },
}

# ---------------------------------------------------------------------------
# LLM client (simplified from batch_processor.py)
# ---------------------------------------------------------------------------

class LLMClient:
    def __init__(self, provider: str, model: str | None = None):
        self.provider = provider
        self.model = model or PROVIDER_CONFIG[provider]["model"]
        self.supports_batch = PROVIDER_CONFIG[provider]["supports_batch"]
        self.batch_type = PROVIDER_CONFIG[provider].get("batch_type", "claude")

        if provider == "claude":
            import anthropic
            self.client = anthropic.Anthropic()
        elif provider == "openai":
            from openai import OpenAI
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY not set")
            base_url = os.environ.get("OPENAI_BASE_URL")
            self.client = OpenAI(base_url=base_url, api_key=api_key) if base_url else OpenAI(api_key=api_key)
        else:
            raise ValueError(f"Unknown provider: {provider}")

    def complete(self, system_prompt: str, user_content: str, max_tokens: int = 4096) -> str:
        if self.provider == "claude":
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user_content}],
            )
            return response.content[0].text.strip()
        else:
            response = self.client.chat.completions.create(
                model=self.model,
                max_completion_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
            )
            return response.choices[0].message.content.strip()

    def submit_batch(self, requests: list[dict]) -> str:
        if self.batch_type == "claude":
            batch = self.client.messages.batches.create(requests=requests)
            return batch.id
        elif self.batch_type == "openai":
            import io
            jsonl = ""
            for req in requests:
                jsonl += json.dumps({
                    "custom_id": req["custom_id"],
                    "method": "POST",
                    "url": "/v1/chat/completions",
                    "body": {
                        "model": req["params"]["model"],
                        "max_completion_tokens": req["params"]["max_tokens"],
                        "messages": [
                            {"role": "system", "content": req["params"]["system"][0]["text"]},
                            *req["params"]["messages"],
                        ],
                    },
                }, ensure_ascii=False) + "\n"
            f = io.BytesIO(jsonl.encode("utf-8"))
            f.name = "batch_input.jsonl"
            uploaded = self.client.files.create(file=f, purpose="batch")
            batch = self.client.batches.create(
                input_file_id=uploaded.id,
                endpoint="/v1/chat/completions",
                completion_window="24h",
            )
            return batch.id
        raise ValueError(f"Unknown batch type: {self.batch_type}")

    def poll_batch(self, batch_id: str, poll_interval: int = 30, timeout: int = 7200) -> object:
        start = time.time()
        terminal = {"ended", "completed", "failed", "expired", "canceled", "cancelled"}
        success = "ended" if self.batch_type == "claude" else "completed"
        while True:
            if time.time() - start > timeout:
                raise TimeoutError(f"Batch {batch_id} timed out after {timeout}s")
            if self.batch_type == "claude":
                batch = self.client.messages.batches.retrieve(batch_id)
                status = batch.processing_status
            else:
                batch = self.client.batches.retrieve(batch_id)
                status = batch.status
            if status in terminal:
                if status != success:
                    raise RuntimeError(f"Batch {batch_id} ended with status: {status}")
                return batch
            print(f"  Batch {batch_id}: {status} ({int(time.time()-start)}s elapsed)", file=sys.stderr)
            time.sleep(poll_interval)

    def retrieve_batch_results(self, batch_id: str) -> dict[str, str]:
        """Return {custom_id: response_text}."""
        results = {}
        if self.batch_type == "claude":
            for result in self.client.messages.batches.results(batch_id):
                if result.result.type == "succeeded":
                    text = "".join(b.text for b in result.result.message.content if hasattr(b, "text"))
                    results[result.custom_id] = text
        elif self.batch_type == "openai":
            batch = self.client.batches.retrieve(batch_id)
            content = self.client.files.content(batch.output_file_id).content
            if isinstance(content, bytes):
                content = content.decode("utf-8")
            for line in content.splitlines():
                if not line.strip():
                    continue
                rec = json.loads(line)
                cid = rec.get("custom_id", "")
                choices = (rec.get("response") or {}).get("body", {}).get("choices", [])
                if choices:
                    text = choices[0].get("message", {}).get("content", "")
                    results[cid] = text
        return results


# ---------------------------------------------------------------------------
# Generation meta-prompt (the core innovation over rule-based)
# ---------------------------------------------------------------------------

GENERATOR_SYSTEM = """\
You are an expert dataset creator for LLM fine-tuning. You generate high-quality \
question-answer pairs about literary works. Your output must be valid JSON — an \
array of conversation objects.

Rules:
- Questions must sound natural, like a curious student or scholar would ask
- Answers must be grounded: cite specific scenes (SC_IDs), line numbers, and quote key phrases
- Vary question difficulty: mix factual recall, analysis, interpretation, comparison
- Vary question style: direct questions, "explain...", "compare...", "why does...", "what is the significance of..."
- Answers should synthesize information, not just copy-paste from the knowledge base
- Include multi-turn conversations (2-3 turns) where follow-up questions drill deeper
- Write all answers in the same language as the knowledge base content provided
- Never fabricate scenes or line numbers not present in the provided context\
"""


def build_scene_gen_prompt(cfg: dict, scenes: list[dict], source_lines: dict, arc_title: str) -> str:
    """Build a prompt for generating Q&A pairs about a group of scenes."""
    book = f"{cfg['title']} by {cfg['author']} ({cfg['year']})"

    scene_blocks = []
    for sc in scenes:
        passage = get_passage(source_lines, sc["line_start"], sc["line_end"])
        if len(passage) > 600:
            passage = passage[:600] + "..."
        scene_blocks.append(
            f"### {sc['sc_id']} (L{sc['line_start']}–L{sc['line_end']})\n"
            f"**Summary**: {sc['summary']}\n"
            f"**Characters**: {sc['characters']}\n"
            f"**Themes**: {sc['themes']}\n"
            f"**Source text**: {passage}"
        )

    return f"""\
Generate training data for a literary expert chatbot about **{book}**.

Below are scenes from the arc **"{arc_title}"**. For these scenes, generate \
question-answer pairs in the following mix:

1. **Scene-specific questions** (1 per scene): "What happens when...?", grounded in the scene details
2. **Character-in-scene questions** (for scenes with named characters): "How does [character] behave in...?"
3. **Theme questions** (2-3 total): connect themes across multiple scenes in this arc
4. **Passage analysis** (2-3 total): given the source text excerpt, provide analytical commentary
5. **Multi-turn conversations** (1-2 total): a 2-3 turn dialogue where the user asks a broad question, then drills into specifics

Return a JSON array. Each element is either a single-turn or multi-turn conversation:

```json
[
  {{
    "messages": [
      {{"role": "user", "content": "..."}},
      {{"role": "assistant", "content": "..."}}
    ]
  }},
  {{
    "messages": [
      {{"role": "user", "content": "..."}},
      {{"role": "assistant", "content": "..."}},
      {{"role": "user", "content": "..."}},
      {{"role": "assistant", "content": "..."}}
    ]
  }}
]
```

Do NOT include the system message — it will be prepended later.

---

## Scenes

{chr(10).join(scene_blocks)}
"""


def build_character_gen_prompt(cfg: dict, characters: list[dict], all_scenes: list[dict]) -> str:
    """Build a prompt for generating character-focused Q&A pairs."""
    book = f"{cfg['title']} by {cfg['author']} ({cfg['year']})"

    char_blocks = []
    for ch in characters:
        # Find scenes for this character
        first_name = ch["name"].split()[0].lower()
        ch_scenes = [s for s in all_scenes if first_name in s.get("characters", "").lower()][:5]
        scene_refs = ", ".join(f"{s['sc_id']} (L{s['line_start']}–L{s['line_end']})" for s in ch_scenes)
        char_blocks.append(
            f"### {ch['name']}\n"
            + "\n".join(f"- **{k}**: {v}" for k, v in ch.items() if k != "name")
            + f"\n- **Key scenes**: {scene_refs}"
        )

    return f"""\
Generate character-focused training data for a literary expert chatbot about **{book}**.

For the characters below, generate question-answer pairs covering:
1. **Identity questions** (1 per character): "Who is X?" — synthesize role, traits, arc
2. **Relationship questions** (1 per character with relationships): "What is X's relationship with Y?"
3. **Character evolution** (1 per major character): "How does X change over the course of the novel?"
4. **Comparative** (2-3 total): "How do X and Y differ in their approach to...?"
5. **Multi-turn** (1-2 total): user asks about a character, then probes a specific scene

Return a JSON array of conversation objects (same format as before, no system message).

---

## Characters

{chr(10).join(char_blocks)}
"""


def build_theme_gen_prompt(cfg: dict, themes: list[dict]) -> str:
    """Build a prompt for generating theme-focused Q&A pairs."""
    book = f"{cfg['title']} by {cfg['author']} ({cfg['year']})"

    theme_blocks = []
    for th in themes:
        # Truncate body for context window efficiency
        body = th["body"][:800] + "..." if len(th["body"]) > 800 else th["body"]
        theme_blocks.append(f"### {th['name']}\n{body}")

    return f"""\
Generate theme-focused training data for a literary expert chatbot about **{book}**.

For the themes below, generate question-answer pairs covering:
1. **Theme overview** (1 per theme): "What role does [theme] play in the novel?"
2. **Theme-in-scene** (1 per theme): "Where do we see [theme] most clearly?" — cite specific SC_IDs
3. **Theme intersections** (3-4 total): "How do [theme A] and [theme B] interact?" — show how themes reinforce or contradict each other
4. **Interpretive** (2-3 total): "Why does [author] emphasize [theme]?" — invite analysis
5. **Multi-turn** (1-2 total): broad question → specific scene follow-up

Return a JSON array of conversation objects (no system message).

---

## Themes

{chr(10).join(theme_blocks)}
"""


def build_style_gen_prompt(cfg: dict, style_md: str) -> str:
    """Build a prompt for generating style/technique Q&A pairs."""
    book = f"{cfg['title']} by {cfg['author']} ({cfg['year']})"

    return f"""\
Generate style and technique training data for a literary expert chatbot about **{book}**.

Below is the style analysis for this novel. Generate 10-15 question-answer pairs covering:
1. **Technique identification**: "What narrative techniques does [author] use?"
2. **Technique-in-context**: "How does [technique] work in [specific scene]?"
3. **Language and register**: "Describe the language register in the novel"
4. **Metaphor analysis**: "What is the significance of [recurring metaphor]?"
5. **Structural questions**: "How is the novel structured?"
6. **Comparative technique**: "How does [technique A] contrast with [technique B]?"
7. **Multi-turn** (2-3): user asks about style → follow-up on specific technique with scene refs

Return a JSON array of conversation objects (no system message).

---

## Style Analysis

{style_md}
"""


def build_cross_arc_gen_prompt(cfg: dict, synopsis_arcs: list[dict]) -> str:
    """Build a prompt for cross-arc and whole-book Q&A pairs."""
    book = f"{cfg['title']} by {cfg['author']} ({cfg['year']})"

    arc_blocks = []
    for arc in synopsis_arcs:
        summary = arc["summary"][:400] + "..." if len(arc["summary"]) > 400 else arc["summary"]
        arc_blocks.append(f"### {arc['title']}\n*({arc['meta']})*\n{summary}")

    return f"""\
Generate cross-arc and whole-book training data for a literary expert chatbot about **{book}**.

Below are summaries of all narrative arcs. Generate 15-20 question-answer pairs covering:
1. **Plot progression**: "How does the story develop from [arc A] to [arc B]?"
2. **Turning points**: "What is the most important turning point in the novel?"
3. **Foreshadowing**: "How does [early event] foreshadow [later event]?"
4. **Arc contrasts**: "How does the tone/focus shift between [arc A] and [arc B]?"
5. **Whole-book synthesis**: "What is the overall arc of the protagonist's journey?"
6. **Opening/closing**: "How does the ending relate to the opening?"
7. **Multi-turn** (3-4): broad structural question → specific arc → specific scene

Return a JSON array of conversation objects (no system message).

---

## Arcs

{chr(10).join(arc_blocks)}
"""


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def group_scenes_by_arc(book_dir: Path, cfg: dict, all_scenes: list[dict]) -> list[tuple[str, list[dict]]]:
    """Group scenes by arc file, returning (arc_title, scenes) pairs."""
    tier2 = book_dir / "knowledge" / "tier_2"
    groups = []
    for f in sorted(tier2.glob("02_*.md")):
        md = read_md(f)
        # Extract arc title from first heading
        title_m = re.match(r"#\s+(.+)", md)
        title = title_m.group(1).strip() if title_m else f.stem
        scenes = parse_tier2_scenes(md)
        if scenes:
            groups.append((title, scenes))
    return groups


def parse_llm_response(text: str) -> list[dict]:
    """Extract JSON array from LLM response, handling markdown fences."""
    # Try to find JSON array in the response
    # Strip markdown code fences
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = text.strip()

    # Find the array
    start = text.find("[")
    if start == -1:
        return []
    # Find matching bracket
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "[":
            depth += 1
        elif text[i] == "]":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i+1])
                except json.JSONDecodeError:
                    return []
    return []


def inject_system_prompt(examples: list[dict], system: str) -> list[dict]:
    """Prepend system message to each conversation."""
    result = []
    for ex in examples:
        if not isinstance(ex, dict) or "messages" not in ex:
            continue
        msgs = ex["messages"]
        if not msgs or msgs[0].get("role") == "system":
            result.append(ex)
        else:
            result.append({"messages": [{"role": "system", "content": system}] + msgs})
    return result


def generate_sync(client: LLMClient, prompts: list[tuple[str, str]], system_prompt: str) -> list[dict]:
    """Generate dataset synchronously, one prompt at a time."""
    all_examples = []
    for i, (label, prompt) in enumerate(prompts):
        print(f"  [{i+1}/{len(prompts)}] Generating: {label}...", file=sys.stderr)
        try:
            response = client.complete(GENERATOR_SYSTEM, prompt, max_tokens=8192)
            examples = parse_llm_response(response)
            examples = inject_system_prompt(examples, system_prompt)
            all_examples.extend(examples)
            print(f"    → {len(examples)} examples", file=sys.stderr)
        except Exception as e:
            print(f"    → ERROR: {e}", file=sys.stderr)
    return all_examples


def generate_batch(client: LLMClient, prompts: list[tuple[str, str]], system_prompt: str) -> list[dict]:
    """Generate dataset using batch API."""
    requests = []
    for i, (label, prompt) in enumerate(prompts):
        custom_id = f"gen_{i:03d}_{label.replace(' ', '_')[:40]}"
        if client.batch_type == "claude":
            requests.append({
                "custom_id": custom_id,
                "params": {
                    "model": client.model,
                    "max_tokens": 8192,
                    "system": [{"type": "text", "text": GENERATOR_SYSTEM}],
                    "messages": [{"role": "user", "content": prompt}],
                },
            })
        else:
            requests.append({
                "custom_id": custom_id,
                "params": {
                    "model": client.model,
                    "max_tokens": 8192,
                    "system": [{"type": "text", "text": GENERATOR_SYSTEM}],
                    "messages": [{"role": "user", "content": prompt}],
                },
            })

    # Submit in chunks of 50
    chunk_size = 50
    all_results = {}
    for start in range(0, len(requests), chunk_size):
        chunk = requests[start:start + chunk_size]
        print(f"  Submitting batch {start//chunk_size + 1} ({len(chunk)} requests)...", file=sys.stderr)
        batch_id = client.submit_batch(chunk)
        print(f"  Batch ID: {batch_id}", file=sys.stderr)
        client.poll_batch(batch_id)
        results = client.retrieve_batch_results(batch_id)
        all_results.update(results)

    # Parse all results
    all_examples = []
    for custom_id, text in all_results.items():
        examples = parse_llm_response(text)
        examples = inject_system_prompt(examples, system_prompt)
        all_examples.extend(examples)

    return all_examples


def validate_examples(examples: list[dict], min_assistant_len: int = 50, max_assistant_len: int = 4000) -> list[dict]:
    """Filter and clean examples."""
    valid = []
    for ex in examples:
        msgs = ex.get("messages", [])
        if len(msgs) < 2:
            continue
        # Check that we have at least one user and one assistant message
        has_user = any(m.get("role") == "user" for m in msgs)
        has_assistant = any(m.get("role") == "assistant" for m in msgs)
        if not has_user or not has_assistant:
            continue
        # Check assistant message length
        last_assistant = [m for m in msgs if m.get("role") == "assistant"][-1]
        content = last_assistant.get("content", "")
        if len(content) < min_assistant_len:
            continue
        # Truncate overly long responses
        if len(content) > max_assistant_len:
            last_assistant["content"] = content[:max_assistant_len]
        valid.append(ex)
    return valid


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="LLM-based chat fine-tuning dataset generator")
    parser.add_argument("book_dir", type=Path, help="Path to book directory")
    parser.add_argument("--output", "-o", type=Path, default=Path("dataset.jsonl"))
    parser.add_argument("--provider", default="claude", choices=PROVIDER_CONFIG.keys())
    parser.add_argument("--model", default=None, help="Override model")
    parser.add_argument("--mode", default="sync", choices=["sync", "batch"])
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)

    book_dir = args.book_dir
    cfg = load_yaml(book_dir / "book.yaml")
    system_prompt = make_system_prompt(cfg)

    print(f"Book: {cfg['title']} by {cfg['author']}", file=sys.stderr)
    print(f"Provider: {args.provider} ({args.model or PROVIDER_CONFIG[args.provider]['model']})", file=sys.stderr)
    print(f"Mode: {args.mode}", file=sys.stderr)

    # Load artifacts
    tier1 = book_dir / "knowledge" / "tier_1"

    source_lines = load_source_lines(book_dir, cfg)
    characters = parse_characters(read_md(tier1 / "03_characters.md"))
    themes = parse_themes(read_md(tier1 / "04_themes.md"))
    synopsis_arcs = parse_synopsis_arcs(read_md(tier1 / "01_synopsis.md"))
    style_md = read_md(tier1 / "05_style.md")
    all_scenes = []
    arc_groups = group_scenes_by_arc(book_dir, cfg, all_scenes)
    for _, scenes in arc_groups:
        all_scenes.extend(scenes)

    # Build prompts — one per generation task
    prompts: list[tuple[str, str]] = []

    # Scene-level prompts (one per arc)
    for arc_title, scenes in arc_groups:
        prompts.append((
            f"scenes: {arc_title}",
            build_scene_gen_prompt(cfg, scenes, source_lines, arc_title),
        ))

    # Character prompt
    if characters:
        prompts.append(("characters", build_character_gen_prompt(cfg, characters, all_scenes)))

    # Theme prompt
    if themes:
        prompts.append(("themes", build_theme_gen_prompt(cfg, themes)))

    # Style prompt
    if style_md:
        prompts.append(("style", build_style_gen_prompt(cfg, style_md)))

    # Cross-arc prompt
    if synopsis_arcs:
        prompts.append(("cross-arc", build_cross_arc_gen_prompt(cfg, synopsis_arcs)))

    print(f"Prepared {len(prompts)} generation prompts", file=sys.stderr)

    # Generate
    client = LLMClient(args.provider, args.model)

    if args.mode == "sync":
        examples = generate_sync(client, prompts, system_prompt)
    else:
        examples = generate_batch(client, prompts, system_prompt)

    # Validate
    before = len(examples)
    examples = validate_examples(examples)
    print(f"Validated: {len(examples)}/{before} examples passed", file=sys.stderr)

    random.shuffle(examples)

    # Write output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    single = sum(1 for e in examples if len(e["messages"]) == 3)
    multi = sum(1 for e in examples if len(e["messages"]) > 3)
    print(f"\nGenerated {len(examples)} examples → {args.output}", file=sys.stderr)
    print(f"  Single-turn: {single}", file=sys.stderr)
    print(f"  Multi-turn:  {multi}", file=sys.stderr)


if __name__ == "__main__":
    main()
