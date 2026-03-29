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

#### The generation tool: `lib/generate_training_data.py`

A ready-made script that reads all your book-expert artifacts and produces a chat fine-tuning dataset:

```bash
python -m lib.generate_training_data books/<slug> --output dataset.jsonl
```

It parses your knowledge base and generates **8 categories** of training examples:

| # | Category | Source artifact | What it generates |
|---|----------|----------------|-------------------|
| 1 | Scene summary | `tier_2/02_*.md` | "What happens in SC_00042?" → scene summary + characters + themes |
| 2 | Passage analysis | `tier_2/*.md` + source JSONL | Raw passage as input → analytical response with SC_ID + line refs |
| 3 | Character profile | `tier_1/03_characters.md` | "Who is X?" → role, traits, arc, relationships |
| 4 | Theme analysis | `tier_1/04_themes.md` | "How does theme X manifest?" → description + arc distribution + examples |
| 5 | Arc summary | `tier_1/01_synopsis.md` | "What happens in section Y?" → plot summary for that arc |
| 6 | Style & technique | `tier_1/05_style.md` | "How does the author use Z?" → technique analysis with SC examples |
| 7 | Cross-arc comparison | `tier_1/01_synopsis.md` | "How does arc A contrast with arc B?" → paired summaries |
| 8 | Multi-turn conversation | all of the above | 2-turn dialogue: character intro → specific scene follow-up |

**Example output** (from Portnoy's Complaint, 502 examples generated):

```json
{"messages": [
  {"role": "system", "content": "You are a literary expert on Philip Roth's *Portnoy's Complaint* (1969). You have deep knowledge of the novel's plot, characters, themes, narrative techniques, and historical context. Answer with specific scene references (SC_IDs) and line numbers when relevant. Be precise and analytical."},
  {"role": "user", "content": "What happens in SC_00097 (lines 1821–1829)?"},
  {"role": "assistant", "content": "Così dicevano le leggi kasher al bambino cresciuto sotto la tutela di Sophie e Jack P., in un quartiere scolastico di Newark dove nella sua intera classe c'erano solo due bambini cristiani..."}
]}
```

```json
{"messages": [
  {"role": "system", "content": "..."},
  {"role": "user", "content": "Tell me about The Monkey in *Portnoy's Complaint*."},
  {"role": "assistant", "content": "Modella e amante principale del narratore nella vita adulta. Key traits: Bellissima, sessualmente sfrenata, semianalfabeta..."},
  {"role": "user", "content": "Can you show me a specific scene where The Monkey is important?"},
  {"role": "assistant", "content": "In SC_00114 (L2326–L2368): Il narratore chiede perché dovrebbe sposarsi..."}
]}
```

#### How the tool maps artifacts → training examples

**Tier 2 arc files** are the richest source. Each file has this structure:

```markdown
### SC_00002 (L2–L16)
Il narratore racconta che da bambino credeva che le sue maestre...

**Personaggi**: Sophie Portnoy (la madre)
**Temi**: Complesso edipico e rapporto madre-figlio, Nostalgia e infanzia perduta
```

The parser extracts `sc_id`, `line_start`, `line_end`, `summary`, `characters`, `themes` from each scene block. This produces two examples per scene:
- **Scene summary**: question about the SC_ID → summary + metadata
- **Passage analysis**: raw source text lines as input → grounded analytical response

**Tier 1 files** produce structured examples:
- `03_characters.md` → one profile Q&A + one relationship Q&A per character
- `04_themes.md` → one detailed + one concise Q&A per theme
- `01_synopsis.md` → one Q&A per arc
- `05_style.md` → one per subsection (voice, language, structure, techniques, metaphors)

**Cross-arc + multi-turn** examples are synthesized by combining data across files.

#### Augmenting with Claude Code sessions (Strategy A+B hybrid)

The tool gives you a solid base (~500 examples for a 6000-line novel). To reach the 1000–2000 range recommended for fine-tuning, augment with Claude Code:

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

The agent stores every answer in `knowledge/answers/` and indexes it in `08_qa_cache.md`. After the session, convert those cached answers into additional training examples:

```python
# Convert cached answers to messages format
import json, re
from pathlib import Path

answers_dir = Path("books/<slug>/knowledge/answers")
cfg = {"title": "...", "author": "...", "year": "..."}
system = f"You are a literary expert on {cfg['author']}'s *{cfg['title']}* ({cfg['year']})..."

for md_file in sorted(answers_dir.glob("*.md")):
    content = md_file.read_text()
    # Extract question from filename or first heading
    question = md_file.stem.split("_", 1)[-1].replace("-", " ")
    print(json.dumps({
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": question},
            {"role": "assistant", "content": content},
        ]
    }, ensure_ascii=False))
```

#### Dataset quality controls

Before training, validate your dataset:

1. **Length filtering** — remove examples where the assistant response is < 50 chars (too thin) or > 4000 chars (may dilute signal)
2. **Deduplication** — the tool uses random question variants but check for near-duplicate answers
3. **Language consistency** — if your knowledge base mixes languages (e.g., Italian analysis of English text), decide whether to keep or filter
4. **Citation grounding** — every assistant response should contain at least one SC_ID or line reference; discard ungrounded examples

```python
# Quick validation
import json
with open("dataset.jsonl") as f:
    examples = [json.loads(line) for line in f]

valid = []
for ex in examples:
    assistant = ex["messages"][-1]["content"]
    if len(assistant) < 50:
        continue  # too short
    if len(assistant) > 4000:
        assistant = assistant[:4000]  # truncate
        ex["messages"][-1]["content"] = assistant
    valid.append(ex)

print(f"Kept {len(valid)}/{len(examples)} examples")
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
| Scene summaries | `tier_2/*.md` → tool | ~200 | Core comprehension |
| Passage analysis | `tier_2` + source text → tool | ~200 | Text → analysis mapping |
| Character profiles | `tier_1/03_characters.md` → tool | ~20–30 | Character knowledge |
| Theme analysis | `tier_1/04_themes.md` → tool | ~20–30 | Thematic reasoning |
| Arc summaries | `tier_1/01_synopsis.md` → tool | ~15–20 | Plot-level understanding |
| Style questions | `tier_1/05_style.md` → tool | ~10–15 | Craft analysis |
| Cross-arc comparisons | tool | ~15–20 | Complex reasoning |
| Multi-turn dialogues | tool | ~5–10 | Conversational flow |
| Claude Code Q&A | `answers/*.md` | ~100–300 | Hard, nuanced questions |
| **Total** | | **~600–900** | |

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
