# Distilling a Book into an LLM Training Dataset with book-expert

How to use book-expert's preprocessing pipeline and knowledge architecture to produce a structured dataset suitable for fine-tuning or training an LLM on a specific book.

## Why book-expert is a good fit

The system already solves the hard problems:

1. **PDF to structured text** — clean line-by-line extraction with IDs
2. **Semantic chunking** — scene-level segmentation with summaries via LLM batch processing
3. **Multi-tier knowledge distillation** — synopsis, characters, themes, style, context, and scene-level detail
4. **Routing metadata** — arcs, keywords, character mappings, line ranges

The output of the full pipeline is effectively a knowledge dataset. The remaining step is reshaping it into training-ready formats (instruction pairs, completions, etc.).

## Recommended Workflow

### Phase 1: Ingest the book (preprocessing stages 00–02)

```bash
# Create workspace
SLUG=my-book
mkdir -p books/$SLUG/{data,knowledge/{tier_1,tier_2,tier_3,answers}}
```

**Step 1 — PDF to JSONL** (`preprocessing/00__pdf2jsonl/`)

```bash
python preprocessing/00__pdf2jsonl/convert.py
# Edit the script's __main__ to point to your PDF
# Produces: <name>.jsonl (full) and <name>-filtered.jsonl (id + text only)
```

**Step 2 — Identify chapter boundaries** (`preprocessing/01__book_natural_bounds/`)

Use the prompt in `preprocessing/01__book_natural_bounds/prompt.md` with Claude (attach the PDF + JSONL). This produces a JSON array of sections with start/end line IDs and sub-parts for long sections (>1000 lines).

**Step 3 — Semantic chunking** (`preprocessing/02__semantic_chunking/`)

```bash
python preprocessing/02__semantic_chunking/batch_processor.py \
  --provider claude --mode batch
```

This runs Claude in parallel over sliding windows (50 lines, 10 overlap) and produces `extracted_chunks.json` — an array of scene objects:

```json
{"sc_id": "00019", "chunk_ids": "77-83", "embedding_summary": "..."}
```

This is the **most important intermediate artifact** — it gives you semantically meaningful segments of the book with summaries.

### Phase 2: Build the knowledge base (preprocessing stages 03–04)

**Step 4 — Generate knowledge files** (`preprocessing/03__generate_knowledge/`)

Use the prompt in `prompt_knowledge_base_builder.md` with Claude. Attach:
- The filtered JSONL (full text)
- The `extracted_chunks.json`

This produces the 7 tier_1 files + all tier_2 arc files:

| File | Training value |
|------|---------------|
| `00_index.md` | Arc structure, scene map — good for structural Q&A |
| `01_synopsis.md` | Plot summary — instruction data for "summarize" tasks |
| `03_characters.md` | Character profiles — instruction data for character analysis |
| `04_themes.md` | Thematic analysis with scene refs — instruction data for theme questions |
| `05_style.md` | Narrative techniques — instruction data for style/craft questions |
| `06_context.md` | Historical/biographical context — factual grounding |
| `02_*.md` (tier_2) | Scene-by-scene detail — the richest source for granular Q&A |

**Step 5 — Generate `book.yaml`** (`preprocessing/04__generate_book_yaml/`)

Use the prompt in `prompt_book_yaml_generator.md`. This produces the routing config that maps arcs to keywords, line ranges, and characters.

### Phase 3: Generate training data (chat fine-tuning format)

At this point you have a complete knowledge base. The goal is to produce JSONL where each line is a conversation in **messages format**:

```json
{"messages": [
  {"role": "system", "content": "..."},
  {"role": "user", "content": "..."},
  {"role": "assistant", "content": "..."}
]}
```

There are two tools: a **rule-based** baseline (free, fast, ~500 examples) and an **LLM-based** generator (higher quality, natural questions, synthesized answers).

#### Tool 1 (baseline): `lib/generate_training_data.py`

Deterministic, no API calls. Parses knowledge artifacts and produces templated Q&A:

```bash
python -m lib.generate_training_data books/<slug> --output baseline.jsonl
```

Useful for: validating your pipeline end-to-end, getting a quick dataset to test training infrastructure, and establishing a floor for comparison. Produces ~500 examples with fixed question templates like "What happens in SC_00042?" → copy-pasted scene summary.

**Limitation**: questions are formulaic, answers are stitched-together fields rather than synthesized analysis, and multi-turn conversations are trivial.

#### Tool 2 (recommended): `lib/generate_training_data_llm.py`

Uses an LLM to generate diverse, natural Q&A pairs grounded in your knowledge artifacts:

```bash
# Synchronous (immediate, good for small books)
python -m lib.generate_training_data_llm books/<slug> -o dataset.jsonl

# Batch mode (~50% cost savings, good for large books)
python -m lib.generate_training_data_llm books/<slug> -o dataset.jsonl --mode batch

# With a different provider/model
python -m lib.generate_training_data_llm books/<slug> -o dataset.jsonl --provider openai
```

**How it works**: the tool parses all knowledge artifacts using the same parsers as the rule-based tool, then builds **generation prompts** — one per task — that feed the parsed context to an LLM and ask it to produce diverse Q&A pairs.

For a book like Portnoy's Complaint (200 scenes, 12 characters, 14 themes, 20 arcs), it creates **24 prompts**:

| Prompt type | Count | What the LLM generates |
|-------------|-------|----------------------|
| Scene-level (one per arc) | 20 | Per-scene questions + character-in-scene + theme connections + passage analysis + multi-turn |
| Character-focused | 1 | Identity, relationships, evolution, comparisons, multi-turn |
| Theme-focused | 1 | Overview, theme-in-scene, intersections, interpretive, multi-turn |
| Style & technique | 1 | Technique ID, language register, metaphors, structure, multi-turn |
| Cross-arc & whole-book | 1 | Plot progression, turning points, foreshadowing, arc contrasts, multi-turn |

Each prompt includes the actual knowledge base content (scene summaries, source text excerpts, character profiles, etc.) so the LLM generates grounded answers with real SC_IDs and line references.

**What makes LLM-generated examples better:**

1. **Natural question variety** — instead of "What happens in SC_00097?", the LLM generates questions like "Why does Portnoy feel guilt about the lobster incident?" or "How does Sophie's knife scene foreshadow Alex's later impotence?"

2. **Synthesized answers** — the LLM weaves together summary + thematic interpretation + textual evidence + cross-references into coherent analytical responses, which is exactly the behavior you want the fine-tuned model to learn

3. **Real multi-turn conversations** — 2-3 turn dialogues where follow-up questions drill deeper, the user pushes back, asks for evidence, or shifts angle

4. **Cross-referencing** — the LLM connects scenes across arcs, links characters to themes, and identifies patterns that the rule-based tool cannot

**Example prompt** (scene-level, for one arc):

The tool sends the LLM all scenes from an arc with their summaries, characters, themes, and source text. Then asks for:
- 1 scene-specific question per scene
- Character-in-scene questions for scenes with named characters
- 2-3 theme questions connecting scenes in the arc
- 2-3 passage analysis examples (raw text → analytical commentary)
- 1-2 multi-turn conversations

The LLM returns a JSON array of conversation objects, which the tool validates and injects with the system prompt.

**Built-in validation**: the tool automatically filters examples where:
- Assistant responses are < 50 characters (too thin)
- Assistant responses are > 4000 characters (truncated)
- Messages are missing user or assistant roles
- JSON parsing failed

#### Combining both tools

The recommended workflow:

1. Run the rule-based tool first to validate your knowledge base is correctly structured
2. Run the LLM tool to generate the actual training dataset
3. Concatenate both outputs and deduplicate
4. Optionally augment with Claude Code sessions for the hardest questions (see below)

#### Augmenting with Claude Code sessions

For the most nuanced questions — those requiring deep cross-arc reasoning or interpretive debate — use interactive Claude Code sessions:

```bash
python -m lib.generate_claude_md books/$SLUG
cd books/$SLUG
```

Then in a Claude Code session:

```
For each arc in book.yaml, generate 5 hard questions that require
cross-referencing multiple arcs or combining character + theme analysis.
Answer each using the full knowledge base with citations.
Save each answer with /cache.
```

The agent stores every answer in `knowledge/answers/` and indexes it in `08_qa_cache.md`. Convert cached answers into additional training examples:

```python
# Convert cached answers to messages format
import json
from pathlib import Path

answers_dir = Path("books/<slug>/knowledge/answers")
cfg = {"title": "...", "author": "...", "year": "..."}
system = f"You are a literary expert on {cfg['author']}'s *{cfg['title']}* ({cfg['year']})..."

for md_file in sorted(answers_dir.glob("*.md")):
    content = md_file.read_text()
    question = md_file.stem.split("_", 1)[-1].replace("-", " ")
    print(json.dumps({
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": question},
            {"role": "assistant", "content": content},
        ]
    }, ensure_ascii=False))
```

### Phase 4: Format for your training framework

The tool outputs OpenAI messages format by default. Convert to other formats as needed:

**Anthropic fine-tuning format:**

```python
# Convert messages → Anthropic format
for ex in dataset:
    msgs = ex["messages"]
    anthropic_ex = {
        "system": msgs[0]["content"],
        "messages": [
            {"role": m["role"], "content": m["content"]}
            for m in msgs[1:]
        ]
    }
```

**Alpaca/instruction format** (for frameworks like Axolotl):

```json
{
  "instruction": "What role does the theme of desire play in the Vaubyessard ball scene?",
  "input": "",
  "output": "In the Vaubyessard ball (SC_00150–SC_00165, L500–L620), desire operates on multiple levels..."
}
```

**Continued pretraining** (raw text interleaved with analysis):

Use the source text JSONL directly, optionally interleaved with knowledge base content to teach the model both the text and analytical frameworks simultaneously.

## Dataset composition recommendations

For a book with ~200 scenes and 10+ characters:

| Category | Source | # examples | Purpose |
|----------|--------|-----------|---------|
| Scene-level Q&A (all types) | LLM tool → 20 arc prompts | ~300–500 | Core: plot, characters-in-scene, themes, passage analysis |
| Character-focused | LLM tool → 1 prompt | ~30–50 | Identity, evolution, relationships, comparisons |
| Theme-focused | LLM tool → 1 prompt | ~30–50 | Theme analysis, intersections, interpretation |
| Style & technique | LLM tool → 1 prompt | ~10–15 | Narrative craft, metaphor, structure |
| Cross-arc & whole-book | LLM tool → 1 prompt | ~15–20 | Synthesis, foreshadowing, arc contrasts |
| Rule-based baseline | `generate_training_data.py` | ~500 | Factual grounding, coverage guarantee |
| Claude Code Q&A | `answers/*.md` | ~100–300 | Hardest, most nuanced questions |
| **Total** | | **~1000–1500** | |

## Key artifacts for training

After running the full pipeline, these are the files most useful for training:

```
books/<slug>/
├── data/<source>-filtered.jsonl          # Raw text with line IDs
├── data/extracted_chunks.json            # Semantic chunks with summaries
├── knowledge/tier_1/01_synopsis.md       # Plot summary
├── knowledge/tier_1/03_characters.md     # Character profiles
├── knowledge/tier_1/04_themes.md         # Theme analysis
├── knowledge/tier_1/05_style.md          # Style analysis
├── knowledge/tier_2/02_*.md              # Scene-level detail (all arc files)
├── knowledge/tier_1/08_qa_cache.md       # Accumulated Q&A pairs
├── knowledge/answers/*.md                # Full cached answers
└── book.yaml                             # Routing metadata (arc→keyword map)
```

## Scaling tips

- **Batch API for chunking**: Stage 02 supports `--mode batch` with Claude, OpenAI, and Nebius. Use batch mode for books over 2000 lines to reduce costs ~50%.
- **Split large knowledge generation**: For books with 2000+ chunks, split the knowledge base generation across two Claude conversations (arcs 1–10 in one, 11–20 in another).
- **Iterative refinement**: After an initial round of Q&A generation, review the answers, identify gaps, and generate targeted questions for under-covered arcs or themes.
- **Multi-language**: The `preferences.yaml` language setting controls output language. Generate training data in the book's original language for best results, or in your target language if building a cross-lingual model.
