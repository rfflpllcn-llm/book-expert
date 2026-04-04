# Prompt: Generate book.yaml from a Knowledge Base

> **How to use**
> 1. Open a new Claude conversation.
> 2. Attach your two input files: the source text (JSONL/CSV) and the extracted_chunks JSON.
> 3. Attach all the knowledge base `.md` files (or at minimum: `00_index.md`, `03_characters.md`, `04_themes.md`).
> 4. Paste the prompt below, replacing every `[PLACEHOLDER]` with your values.
> 5. Optionally attach an existing `book.yaml` from another book as a structural reference.

---

## INPUT FILE SPECIFICATIONS

The prompt assumes these inputs:

### File 1 — Source text
Either a CSV or JSONL with one line of text per row.

| Field        | Description |
|--------------|-------------|
| `id` / `line_id` | Sequential integer, one per line |
| `t` / `text`     | The actual text of that line |

### File 2 — Extracted chunks JSON
An array of objects, each representing one analytical scene:
```json
{
  "sc_id": "00019",
  "chunk_ids": "77-83",
  "embedding_summary": "Analytical summary of the scene..."
}
```

### File 3+ — Knowledge base Markdown files
The output of the knowledge base builder prompt. At minimum:
- `00_index.md` (arc map, character table)
- `03_characters.md` (character profiles with presence counts)
- `04_themes.md` (theme analysis with frequencies)

The more files you attach, the more accurate the YAML will be. The `02_*` scene detail files are useful but not required — the arc structure can be reconstructed from `00_index.md`.

---

## THE PROMPT

````markdown
You are generating a structured `book.yaml` configuration file for the novel **[BOOK TITLE]** by **[AUTHOR]**.

I'm attaching:

1. **[SOURCE_FILENAME]** — Full text of the book, one line per row.
   Format: [csv|jsonl]. Line ID field: `[LINE_ID_FIELD]`. Text field: `[TEXT_FIELD]`.

2. **[CHUNKS_FILENAME]** — [N_CHUNKS] pre-extracted scene chunks.
   Each has: `sc_id`, `chunk_ids` (line range), `embedding_summary` (in [SUMMARY_LANGUAGE]).

3. **Knowledge base files** — The Markdown knowledge base previously generated for this book.

---

## INSTRUCTIONS

Parse all attached files and produce a single `book.yaml` that serves as the machine-readable index of the entire knowledge base. The YAML must be **fully derived from the data** — do not estimate counts or invent arc boundaries.

Work methodically:
1. Parse `00_index.md` to extract the arc map (titles, line ranges, chunk counts).
2. Parse `03_characters.md` to extract character names, presence counts, and arc distributions.
3. Parse `04_themes.md` to extract theme names, frequencies, and top arcs.
4. Cross-reference with the chunks JSON to verify SC ranges and chunk counts.
5. Identify which `02_*` files exist and how arcs were split.
6. Assemble the YAML.

---

## YAML STRUCTURE

The output must follow this exact schema:

```yaml
# ============================================================
# TOP-LEVEL METADATA
# ============================================================
title: [string]              # Full title of the novel
author: [string]             # Author name (pseudonym if applicable)
year: [integer]              # Publication year
language: [iso-639-1 code]   # Language of the source text (e.g., fr, it, en, de)

# ============================================================
# SOURCE TEXT REFERENCE
# ============================================================
source_text:
  file: [relative path]      # Path to the source text file
  format: [csv|jsonl]        # File format
  line_prefix: [string]      # Prefix for line references (e.g., FR, IT, EN)
  line_column: [string]      # Column/field name for line IDs
  text_column: [string]      # Column/field name for text content

# ============================================================
# CHUNKS REFERENCE
# ============================================================
chunks:
  file: [relative path]      # Path to the extracted chunks JSON
  format: json
  total: [integer]            # Total number of chunks
  sc_range: [first, last]    # First and last SC IDs
  fields:
    id: sc_id
    lines: chunk_ids
    summary: embedding_summary
    summary_language: [iso-639-1]  # Language of the summaries

# ============================================================
# NARRATIVE ARCS
# ============================================================
arcs:
  [arc_key]:                  # Slug-style key: 02_NN_short_name
    keywords: [list]          # 5–10 keywords for semantic search/matching
    lines: [start, end]       # Line range [inclusive start, inclusive end]
    chunks: [integer]         # Exact chunk count in this arc
    sc_range: [first, last]   # First and last SC IDs in this arc
    # Only if the arc was split across multiple files:
    split:
      - file: [filename.md]
        chunks: [integer]
      - file: [filename.md]
        chunks: [integer]
  # ... repeat for each arc

# ============================================================
# CHARACTERS
# ============================================================
characters:
  [character_key]:            # Lowercase slug: first name or surname
    role: [string]            # One-line role description
    presences: [integer]      # Total chunk count where character appears
    arcs: [list of arc_keys]  # Arcs where this character appears
  # ... repeat for each character (≥5 presences as main, <5 can be included or omitted)

# ============================================================
# THEMES
# ============================================================
themes:
  - name: [string]            # Theme name (must match 04_themes.md exactly)
    count: [integer]          # Total chunks where theme is detected
    top_arcs: [list]          # Top 5 arcs by count (arc_keys)
  # ... repeat for each theme, ordered by descending count

# ============================================================
# KNOWLEDGE BASE MANIFEST
# ============================================================
knowledge_base:
  language: [iso-639-1]       # Language of the knowledge base notes
  files:                      # List of non-arc files
    - 00_index.md
    - 01_synopsis.md
    - 03_characters.md
    - 04_themes.md
    - 05_style.md
    - 06_context.md
    - 08_qa_cache.md
  total_files: [integer]      # Total count including all 02_* files
  total_size_kb: [integer]    # Approximate total size in KB
```

---

## FIELD-BY-FIELD RULES

### `arcs`
- **Arc keys** use the pattern `02_NN_slug` where `NN` is a zero-padded sequence number and `slug` is a short snake_case descriptor.
- **`keywords`**: 5–10 terms that identify this arc. Include character names, place names, key events, and distinctive motifs. These are used for semantic retrieval — choose terms a user might search for when looking for this part of the story.
- **`lines`**: exact line range `[first_line_of_first_chunk, last_line_of_last_chunk]`. Derive from the chunks JSON, not from estimates.
- **`chunks`**: exact count. Must sum to `chunks.total` across all arcs.
- **`sc_range`**: `[first_sc_id, last_sc_id]`. Derive from chunks JSON.
- **`split`**: only present if the arc was split into multiple `02_*` files (because it exceeded 120 scenes). List each sub-file with its chunk count.

### `characters`
- Include every character with ≥5 chunk presences as a separate entry.
- **`presences`**: derived from scanning all `embedding_summary` fields, not estimated.
- **`arcs`**: list only arcs where the character actually appears (has ≥1 mention in that arc's chunks). Order arcs chronologically (by arc number).
- **`role`**: one short phrase (not a full sentence). Match the role from `03_characters.md`.

### `themes`
- Order themes by descending `count`.
- **`name`**: must exactly match the theme name in `04_themes.md`.
- **`top_arcs`**: the 5 arcs with the highest count for this theme, ordered by descending count. Use arc keys.

### `knowledge_base`
- **`files`**: list only the non-arc files (00, 01, 03–08). The arc files are already described in the `arcs` section.
- **`total_files`**: count of ALL `.md` files in the knowledge base, including all `02_*` splits.
- **`total_size_kb`**: approximate total size, rounded to nearest integer.

---

## QUALITY REQUIREMENTS

1. **Chunk accounting**: the sum of all `arcs[*].chunks` must equal `chunks.total` exactly. No gaps, no overlaps.
2. **SC range continuity**: SC ranges across consecutive arcs must be contiguous (last SC of arc N + gap ≤ first SC of arc N+1). Small gaps between arcs are acceptable if chunks were excluded during arc boundary detection.
3. **Line range continuity**: same rule as SC ranges. Line ranges should tile the full text with minimal gaps.
4. **Character counts from data**: `presences` must be derived by actually scanning the JSON, not copied loosely from memory.
5. **Arc keys stable**: arc keys must match the `02_*` filenames in the knowledge base. If the knowledge base has `02_06a_africa_coloniale_inizio.md`, the arc key should be `02_06_africa_coloniale` and the split should reference that filename.
6. **Valid YAML**: the output must be syntactically valid YAML. Test by mentally parsing it. Watch for unescaped colons, quotes in strings, and indentation.

---

## OUTPUT

Produce a single file: `book.yaml`. Save it to **[OUTPUT_DIR]**.

Do not produce any other files. Do not include explanatory text outside the YAML — the file should be pure YAML (comments within the file are fine).
````

---

## PLACEHOLDER REFERENCE

| Placeholder            | Example                                | Description                                      |
|------------------------|----------------------------------------|--------------------------------------------------|
| `[BOOK TITLE]`         | Voyage au bout de la nuit              | Full title of the novel                          |
| `[AUTHOR]`             | Louis-Ferdinand Céline                 | Author name                                      |
| `[SOURCE_FILENAME]`    | voyage-fr.jsonl                        | Name of the source text file                     |
| `[LINE_ID_FIELD]`      | id                                     | Field/column name for line IDs                   |
| `[TEXT_FIELD]`          | t                                      | Field/column name for text content               |
| `[CHUNKS_FILENAME]`    | extracted_chunks.json                  | Name of the chunks JSON file                     |
| `[N_CHUNKS]`           | 2630                                   | Total number of chunks                           |
| `[SUMMARY_LANGUAGE]`   | it                                     | ISO 639-1 code for summary language              |
| `[OUTPUT_DIR]`         | /mnt/user-data/outputs                 | Where to save the YAML file                      |

---

## TIPS AND NOTES

- **The YAML is a machine-readable index**, not a human document. Its purpose is to let downstream tools (RAG pipelines, search systems, Claude conversations with the knowledge base) quickly locate the right files, arcs, characters, and themes without parsing all the Markdown.

- **Keywords matter for retrieval.** When choosing arc keywords, think like a user: "Where does Bardamu go to Africa?" → keywords should include `africa`, `nave`, `traversata`. "What happens with the old woman Henrouille?" → keywords should include `henrouille`, `vecchia`, `bomba`, `cripta`.

- **If attaching an existing `book.yaml` as reference**: tell Claude to use it as a structural template but derive all values from the actual data. This prevents copy-paste errors from a different book's YAML.

- **The YAML pairs with the knowledge base.** Together they form a complete system:
  - `book.yaml` → machine index (what exists, where, how much)
  - `00_index.md` → human index (same info, readable)
  - `01_synopsis.md` → narrative overview
  - `02_*` files → scene-level detail
  - `03–06` files → analytical layers
  - `08_qa_cache.md` → validated answers accumulator

- **For multi-language setups** (e.g., French source text, Italian summaries, Italian knowledge base), the YAML captures all three language codes in their respective fields: `language` (source), `chunks.fields.summary_language` (summaries), `knowledge_base.language` (notes).

- **Validation checklist** after generation:
  - [ ] Sum of all arc chunks = total chunks
  - [ ] SC ranges are contiguous across arcs
  - [ ] Line ranges tile the full text
  - [ ] All `02_*` filenames in `split` blocks match actual files
  - [ ] Character presence counts are plausible (Bardamu should dominate)
  - [ ] Theme counts are ordered descending
  - [ ] YAML parses without errors (`python3 -c "import yaml; yaml.safe_load(open('book.yaml'))"`)
