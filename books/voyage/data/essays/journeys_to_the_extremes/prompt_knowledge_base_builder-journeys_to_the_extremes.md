You are building a structured knowledge base for the novel **[BOOK TITLE]** by **[AUTHOR]**.

I'm attaching two files:

1. **[BOOK_FILENAME]** — Full text of the book, one line per row.
   Columns: `id, t`.
   Lines are numbered sequentially.

2. **[CHUNKS_FILENAME]** — [N_CHUNKS] pre-extracted scene chunks.
   Each has: `sc_id` (scene ID), `chunk_ids` (line range), `embedding_summary` (in [SUMMARY_LANGUAGE]).

---

## INSTRUCTIONS

Analyze both files thoroughly and produce the knowledge base described below.
Write all notes and analysis in **[Italian]**.
Create each file as a separate Markdown (.md) file and save them all to **[OUTPUT_DIR]**.

Work methodically:
1. First, load and parse both files to understand the full scope.
2. Identify narrative arc boundaries by reading the chunk summaries sequentially.
3. Extract character appearances by scanning all `embedding_summary` fields.
4. Identify themes by scanning `embedding_summary` across all chunks.
5. Then generate each file in order.

---

## OUTPUT FILES

### `00_index.md` — Master Index

Structure:

```
# [BOOK TITLE] — Reference Index

## Corpus metadata
- **Chunks analyzed**: [total]
- **Lines covered**: [first]–[last] (complete novel)
- **Chunk structure**: each chunk has an analytical summary (embedding_summary) with cross-refs to characters and themes
- **Language of notes**: [OUTPUT_LANGUAGE]

## Available files
[Table: filename | content description]

## Narrative arc map
[Table with columns: #, Arc title, Line range, Chunk count, 1–2 sentence synopsis]

## Main characters
[Table with columns: Character, Total chunks, Principal arcs]

## How to use these notes
- What happens? → 01_synopsis.md or the relevant 02_* file
- A character? → 03_characters.md
- A theme? → 04_themes.md
- Style? → 05_style.md
- Historical context? → 06_context.md
- Already answered? → 08_qa_cache.md
```

### `01_synopsis.md` — Complete Synopsis

One section per narrative arc. Format:

```
# Complete Synopsis — [BOOK TITLE]

## [Arc title]
*(Lines X–Y, N passages)*

[3–8 sentence prose summary covering the main events, emotional arc, and key characters of this section.]

---
[repeat for each arc]
```

Cover the ENTIRE novel from first to last chunk. Typically 10–20 arcs.

### `02_XX_[slug].md` — Per-Arc Detail Files (one per arc)

One file per arc. Naming: `02_01_[slug].md`, `02_02_[slug].md`, etc.

Format:

```
# [Arc title]

**Lines**: X–Y | **Passages**: N | **SC range**: XXXXX–YYYYY

## Synopsis
[3–5 sentence summary of the arc]

---

## Scenes

### [SC_ID] (L[start]–L[end])
[1–4 sentence summary from embedding_summary, condensed and clear]

**Characters**: [names, only if present in this scene]
**Themes**: [theme tags, only if clearly surfaced — omit line if none]

[repeat for EVERY scene in the arc]
```

IMPORTANT:
- Include EVERY scene chunk that falls within the arc's line range.
- **Maximum 120 scenes per arc file.** If an arc contains more than 120 scenes, split it into sub-arcs (e.g., `02_02a_guerra_fronte_inizio.md`, `02_02b_guerra_fronte_notte.md`) with clear narrative boundaries between them. Update the arc map in `00_index.md` and `01_synopsis.md` accordingly.
- Each scene entry should be a concise but informative summary (not the raw embedding_summary verbatim — rephrase for clarity and concision).
- Only tag **Characters** and **Themes** when they are clearly present — omit those lines entirely for scenes where they don't apply.
- Use a consistent set of theme tags across all files (the same tags used in 04_themes.md).

### `03_characters.md` — Character Profiles

For each character appearing in ≥5 chunks:

```
## [Character Name]
- **Role**: one-line description
- **Traits**: key personality traits
- **Arc**: narrative trajectory across the book
- **Relationships**: connections to other characters
- **Presences**: ~N passages
- **Distribution**: [top 5 arcs by count, format: "Arc name (count)"]
```

Add a "Secondary characters" section for characters with <5 appearances: one-line entries.

Derive character counts by scanning ALL `embedding_summary` fields for character name mentions.

### `04_themes.md` — Thematic Analysis

Identify 8–15 major recurring themes. For each:

```
## [Theme Name]

[2–3 sentence description of how this theme functions in the novel]

**Relevant passages**: N out of [total]

**Distribution by arc**: [top 5 arcs with counts]

**Key examples**:

- **[SC_ID]** (L[line]): [1–2 sentence summary of the scene]
  - *Figurative*: [figurative layer note, if substantive — leave blank if generic]

[3–5 examples per theme]

---
```

Derive theme counts by scanning `embedding_summary` field for thematic keywords.

### `05_style.md` — Style and Narrative Technique

Analyze the writing style based on the text CSV and chunk summaries. Cover:

- **Narrative voice**: person, tense, tone, relationship to reader
- **Language and register**: dialect, orality, punctuation habits, mixed registers
- **Narrative structure**: chapter organization (or lack thereof), transitions, cyclical patterns
- **Recurring techniques**: allegory, interior monologue, irony, hyperbole, perceptual crises, accumulation/crescendo — give examples with SC IDs
- **Recurring metaphors**: identify 5–8 key metaphorical clusters with examples
- **Rhythm and musicality**: sentence structure, pacing devices

### `06_context.md` — Biographical, Historical, and Literary Context

Cover:
- **Bibliographic data**: title, author (real name if pseudonym used), publication date, publisher, genre, language
- **The author**: key biographical facts relevant to the novel
- **Historical context**: what period the novel covers, real events it references
- **Literary reception**: prizes, critical reception, influence on later writers
- **Biography/novel relationship**: what is autobiographical, what is transposed
- **Connections to other works**: by the same author and by others

### `08_qa_cache.md` — Validated Q&A Cache

Create as an empty template ready to be populated:

```
# Validated Answers — Q&A Cache

This file collects validated answers to frequent questions.
Claude should consult it before re-deriving an answer from the scene files.

---

*No answers registered yet. Populate progressively.*

## Format for new entries

## Q: [question]
**Reference SCs**: SC_xxxxx, SC_yyyyy
**Answer**: [validated answer]
**Full answer**: answers/[date]_[slug].md
**Date**: [validation date]
```

---

## QUALITY REQUIREMENTS

1. **Completeness**: every chunk must appear in exactly one `02_*` file. No gaps, no overlaps.
2. **Consistency**: theme tags in `02_*` files must match theme names in `04_themes.md` exactly.
3. **Counts must be derived from data**: character presences, theme counts, and arc chunk counts must come from actually scanning the JSON — do not estimate or round.
4. **Cross-referencing**: `00_index.md` arc table must match `01_synopsis.md` sections which must match `02_*` file boundaries exactly.
5. **Concision**: scene summaries in `02_*` files should be 1–4 sentences, not raw dumps of the embedding_summary.
6. **SC IDs and line numbers**: always include both for traceability.
7. **No invented content**: all factual claims about the novel must be grounded in the CSV text or chunk summaries. For `05_style.md` and `06_context.md`, you may draw on general literary knowledge of the author and work.

---

## WORKFLOW

Process the files in this order:
1. Parse the JSON and CSV fully.
2. Run character extraction across all chunks → build character frequency table.
3. Run theme identification across all chunks → build theme frequency table.
4. Define arc boundaries (group consecutive chunks into narrative arcs by identifying shifts in setting, time, or character focus).
5. Generate `00_index.md` (needs arc map + character table).
6. Generate `01_synopsis.md`.
7. Generate all `02_*` files (one per arc).
8. Generate `03_characters.md`.
9. Generate `04_themes.md`.
10. Generate `05_style.md`.
11. Generate `06_context.md`.
12. Generate `08_qa_cache.md` (empty template).
13. Present all files.

---

## PLACEHOLDER REFERENCE

| Placeholder | Example (Voyage au bout de la nuit) | Description                                |
|-------------|-------------------------------------|--------------------------------------------|
| `[BOOK TITLE]` | Poétique de Céline                  | Full title of the novel                    |
| `[AUTHOR]` | Henri Godard                        | Author name                                |
| `[YEAR]` | 1985                                | Publication year                           |
| `[BOOK_FILENAME]` | godard-filtered.jsonl               | Name of your jsonl file                    |
| `[N_CHUNKS]` | 332                                 | Total objects in the JSON array            |
| `[SUMMARY_LANGUAGE]` | Italian                             | Language of the embedding_summary fields   |
| `[OUTPUT_LANGUAGE]` | Italian                             | Language for all knowledge base notes      |

---

## TIPS AND NOTES

- **Arc identification is the hardest step.** The model needs to read through the chunk summaries sequentially to find natural narrative boundaries (changes in setting, time jumps, new character groups). 

- **Theme tags should emerge organically** from the `embedding_summary` content and the actual book. Don't force a predefined list — let the themes come from the data, then standardize the names into a consistent set of 8–15 tags.

- **The `02_*` files are the most token-intensive output.** For a 2630-chunk book, they totaled ~14,000 lines of Markdown. This will likely require splitting across multiple conversations. A good split point is after arc 7 or 8 (roughly the midpoint).

- **File `07` is intentionally skipped** — reserved for future use (e.g., relationship graph, timeline, motif index).

- **The Q&A cache (`08`)** is meant to be populated over time as you ask questions about the book and validate answers. Each validated answer gets added with SC references and a date.

- **If you want the knowledge base in a different language** than the chunk summaries, set `[OUTPUT_LANGUAGE]` accordingly. The model will translate/adapt the summaries as it writes.

- **To add a new book**, you need to first produce the two input files:
  1. Extract text line-by-line from PDF/ebook → CSV
  2. Group lines into scenes and generate analytical summaries → JSON
  These are separate preprocessing steps (typically done with a combination of PDF extraction tools and an LLM pass for the summaries).
