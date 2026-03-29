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

### Phase 3: Generate training data

At this point you have a complete knowledge base. Now convert it into training formats.

#### Strategy A: Use Claude Code as a Q&A generator

This is the highest-quality approach. Set up the book workspace fully:

```bash
python -m lib.generate_claude_md books/$SLUG
cd books/$SLUG
```

Then use Claude Code sessions to systematically generate Q&A pairs:

```
# In a Claude Code session inside books/$SLUG/:

For each arc in book.yaml, generate 10-15 questions covering:
- Plot events ("What happens when X?")
- Character analysis ("How does character Y change in this section?")
- Thematic interpretation ("What role does theme Z play here?")
- Style/technique ("What narrative techniques are used in SC_00150?")
- Textual evidence ("Which passage best illustrates X?")
- Comparative ("How does this scene contrast with SC_00200?")

Answer each question using the full knowledge base + source text citations.
```

Every Q&A pair generated this way is grounded in the actual text with scene IDs and line references. The agent caches answers in `knowledge/answers/` and `tier_1/08_qa_cache.md`, so you accumulate a growing dataset.

#### Strategy B: Direct conversion of knowledge files

Transform the existing knowledge artifacts into instruction-completion pairs programmatically:

**From tier_2 arc files (scene summaries → Q&A):**

```python
# Pseudo-code: parse tier_2 markdown into training pairs
for scene in parse_scenes("knowledge/tier_2/02_01_*.md"):
    # Scene summary → completion pair
    pairs.append({
        "instruction": f"Summarize what happens in lines {scene.lines} of [Book Title].",
        "completion": scene.summary
    })
    # Character extraction
    pairs.append({
        "instruction": f"Which characters appear in {scene.sc_id}?",
        "completion": f"Characters: {scene.characters}. Themes: {scene.themes}."
    })
```

**From extracted_chunks.json (embeddings + summaries):**

```python
# Each chunk already has an embedding_summary
for chunk in extracted_chunks:
    # The source text lines for this chunk
    text = get_lines(chunk["chunk_ids"])
    pairs.append({
        "instruction": "Analyze this passage from [Book Title].",
        "input": text,
        "completion": chunk["embedding_summary"]
    })
```

**From tier_1 files (structured reference → instruction pairs):**

- `01_synopsis.md` → "Summarize the plot of [Book]" / "What happens in arc X?"
- `03_characters.md` → "Describe character X" / "What is X's relationship with Y?"
- `04_themes.md` → "What are the major themes?" / "How does theme X manifest?"
- `05_style.md` → "Describe the narrative style" / "What techniques does the author use?"

#### Strategy C: Hybrid — bootstrap with B, refine with A

1. Run Strategy B to generate a base dataset (500–1000 pairs from knowledge files)
2. Use Strategy A (Claude Code sessions) to generate harder, more nuanced questions that require cross-referencing multiple arcs
3. Use the Q&A cache (`08_qa_cache.md` + `answers/`) as additional high-quality pairs

### Phase 4: Format for training

Convert your pairs into the format your training framework expects:

**For instruction fine-tuning (Alpaca/ShareGPT format):**

```json
{
  "instruction": "What role does the theme of desire play in the Vaubyessard ball scene?",
  "input": "",
  "output": "In the Vaubyessard ball (SC_00150–SC_00165, L500–L620), desire operates on multiple levels..."
}
```

**For chat fine-tuning (messages format):**

```json
{
  "messages": [
    {"role": "system", "content": "You are an expert on [Book Title] by [Author]."},
    {"role": "user", "content": "Analyze Emma's behavior at the ball."},
    {"role": "assistant", "content": "At the Vaubyessard ball (Arc 02_02, SC_00150–SC_00165)..."}
  ]
}
```

**For continued pretraining (raw text):**

Use the source text JSONL directly, optionally interleaved with knowledge base content to teach the model both the text and analytical frameworks.

## Dataset composition recommendations

| Category | Source | % of dataset | Purpose |
|----------|--------|-------------|---------|
| Raw text passages | `data/*.jsonl` | 15-20% | Teach the model the actual text |
| Scene summaries | `tier_2/*.md` | 20-25% | Teach analytical comprehension |
| Character/theme analysis | `tier_1/03,04,05` | 10-15% | High-level literary understanding |
| Generated Q&A pairs | Claude Code sessions | 30-40% | Instruction following |
| Cross-arc comparisons | Claude Code sessions | 10-15% | Complex reasoning |

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
