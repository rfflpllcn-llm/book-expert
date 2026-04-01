# Prompt: Generate a Knowledge Base for a New Book

Use this prompt with GPT-4, Claude, or any capable LLM to generate the knowledge base files for a new book. You will need to provide the book's full text (or large excerpts) in the context.

## How to use

1. Copy the system prompt below into your LLM session
2. Attach or paste the book's full text
3. Run each task prompt one at a time — each produces one file
4. Save each output to the corresponding path under `books/<slug>/knowledge/`
5. Review and edit the outputs before using them

The prompts are designed to be run sequentially: later files reference earlier ones. Run them in order.

---

## System Prompt

Paste this once at the start of the session:

```
You are a literary analyst building a structured knowledge base for an AI expert agent. The agent will use these files to answer questions about a novel.

Rules:
- Write in Italian (the knowledge base language for this project)
- Be precise and analytical, not flowery
- Always include line references when possible (e.g., L77, L230)
- Use the exact formatting templates provided — the agent parses these files programmatically
- Scene IDs are sequential five-digit numbers starting from 00001 (SC_00001, SC_00002, ...)
- When listing distributions, use the format: Arc Name (count)
```

---

## Task 1: Define the arc structure

Run this first. The arc breakdown drives everything else.

```
Analyze the full text and divide the novel into 10–20 narrative arcs. Each arc should be a coherent section with its own setting, characters, and dramatic tension.

For each arc, provide:
- A short Italian title
- The line range (start–end)
- A one-sentence description
- The approximate number of scenes/passages

Output as a markdown table:

| # | Arc ID | Title | Lines | Scenes | Description |
|---|--------|-------|-------|--------|-------------|
| 1 | 02_01_<slug> | ... | 1–500 | ~30 | ... |

Arc IDs must follow the pattern: 02_XX_short_slug (lowercase, underscores, no accents).
```

Save the output — you'll reference this arc table in every subsequent task.

---

## Task 2: `00_index.md`

```
Generate the master index file for the knowledge base. Use this template:

# [Book Title] — Indice di Riferimento

## Informazioni sul corpus
- **Chunk analizzati**: [total scene count] scene/passaggi
- **Righe coperte**: [first line]–[last line] (romanzo completo)
- **Struttura di ogni chunk**: riassunto analitico con cross-ref a personaggi e temi
- **Lingua delle note**: italiano

## File disponibili

[Table listing every file in tier_1 and tier_2, with a description column]

## Mappa degli archi narrativi

[The arc table from Task 1, with a longer description column — 1-2 sentences each]

## Convenzioni
- Scene IDs: SC_00001 through SC_[last]
- Line refs: L[first] through L[last] (map to [PREFIX][n] in CSV)
```

---

## Task 3: `01_synopsis.md`

```
Write a complete plot synopsis organized by narrative arc. Use this format:

# Sinossi completa — [Book Title]

## [Arc Title]
*(Righe [start]–[end], [count] passaggi)*

[3-5 sentence summary of this arc. Include key events, character actions, and thematic significance. Name specific characters and reference notable scenes.]

---

[Repeat for each arc]

Guidelines:
- Each arc summary: 3-5 sentences, dense with plot information
- Name every significant character that appears in each arc
- Mention key locations, objects, or symbolic moments
- Use present tense
- Total target: ~2000 words
```

---

## Task 4: `03_characters.md`

```
Generate character profiles for every named character in the novel. Use this format for each:

# Personaggi — [Book Title]

## [Character Name]
- **Ruolo**: [Role in the story — narrator, protagonist, antagonist, etc.]
- **Tratti**: [Key personality traits, comma-separated]
- **Arco**: [Brief description of their arc across the novel]
- **Relazioni**: [Name (relationship type) for each significant relation]
- **Presenze**: ~[count] passaggi
- **Distribuzione**: [Arc Name] ([count]), [Arc Name] ([count]), ...

Rules:
- Include ALL named characters, even minor ones
- Major characters (10+ scenes): full profile as shown above
- Minor characters (fewer than 10 scenes): shorter entry with Ruolo, Arco, and Presenze only
- Order by number of appearances (most to fewest)
- List the top 5 arcs by appearance count in Distribuzione
- Total target: ~2000 words
```

---

## Task 5: `04_themes.md`

```
Identify 8-12 recurring themes in the novel. For each theme, use this format:

# Temi — [Book Title]

## [Theme Name]

[2-3 sentence description of how this theme manifests in the novel.]

**Passaggi pertinenti**: [count] su [total scenes]

**Distribuzione per arco**: [Arc Name] ([count]), [Arc Name] ([count]), ...

**Esempi chiave**:

- **[SC_ID]** (L[line]): [1-2 sentence description of how the theme appears in this scene]
  - *Figurativo*: [What it symbolizes or suggests, if applicable]
- [4 more key examples per theme]

---

Rules:
- List top 5 arcs by theme presence in Distribuzione
- Choose 5 key examples per theme that best illustrate it
- Examples should span different arcs when possible
- Separate each theme with ---
- Total target: ~3000 words
```

---

## Task 6: `05_style.md`

```
Analyze the novel's style and narrative technique. Use this structure:

# Stile e tecnica narrativa — [Book Title]

## Voce narrante
[Point of view, narrative distance, reliability, direct address to reader]

## Lingua e registro
[Language register, dialect/argot, orality markers, punctuation habits, mix of registers]

## Struttura narrativa
[Chapter structure, transitions, temporal organization, recurring patterns, structural elements]

## Tecniche narrative ricorrenti

### [Technique Name]
[1-2 sentence description with specific examples from the text]

[Repeat for 5-8 techniques. Examples: allegory, interior monologue, irony, hyperbole, accumulation, free indirect discourse, unreliable narration, etc.]

## Metafore e immagini ricorrenti
[List 5-10 recurring metaphors/images with brief descriptions and line references]

Rules:
- Be specific — name techniques with examples, don't just describe in general terms
- Include line references for examples where possible
- Total target: ~1500 words
```

---

## Task 7: `06_context.md`

```
Write the biographical, historical, and literary context. Use this structure:

# Contesto — [Book Title]

## Dati bibliografici
- **Titolo**: [Full title]
- **Autore**: [Full name (birth name if different, dates)]
- **Pubblicazione**: [Year, publisher]
- **Genere**: [genre descriptors]
- **Lingua**: [language and register notes]

## L'autore
[5-8 bullet points of biographical facts relevant to the novel. Focus on experiences that directly fed into the book — wars served in, places lived, professions practiced.]

## Contesto storico del romanzo
[What historical period does the novel cover? What events, movements, or social conditions are depicted? 3-5 bullet points.]

## Ricezione letteraria
[How was the novel received? Awards, controversy, critical responses, influence on later writers. 5-8 bullet points.]

## Influenza e eredità
[How did this novel influence literature? Which authors cite it? What movements did it inspire? 3-5 bullet points.]

Rules:
- Stick to facts, not interpretation
- Note any controversies about the author that readers should be aware of
- Total target: ~1000 words
```

---

## Task 8: `08_qa_cache.md`

This one is just a scaffold — no LLM generation needed:

```markdown
# Risposte validate — Q&A Cache

Questo file raccoglie risposte già validate a domande frequenti.

---
```

---

## Task 9: Tier 2 arc files (one per arc)

Run this prompt once for each arc, providing the relevant text section:

```
Generate a detailed scene-by-scene summary for this narrative arc. I'm providing the text for lines [start] through [end].

Use this format:

# [Arc Title]

**Righe**: [start]–[end] | **Passaggi**: [count] | **SC range**: [first_SC]–[last_SC]

## Sinossi
[3-5 sentence arc summary — same as in 01_synopsis.md]

---

## Scene

### [SC_ID] (L[start]–L[end])
[2-4 sentence summary of what happens in this scene. Include actions, dialogue topics, revelations, emotional shifts.]

**Personaggi**: [comma-separated list]
**Temi**: [comma-separated list, only if strongly present]

[Repeat for every scene in the arc]

Rules:
- One ### entry per scene (a scene is a coherent narrative unit, typically 3-15 lines)
- Scene IDs are sequential across the whole novel, not per-arc
- Include **Personaggi** for every scene
- Include **Temi** only when a theme is strongly present (not every scene needs it)
- Summaries should be analytical, not just plot description — note irony, tone shifts, narrative technique
- If a scene contains a famous passage or key quote, mention it
```

Save each output as `books/<slug>/knowledge/tier_2/[arc_id].md`.

---

## Tips

- **Context window limits**: If the full text doesn't fit, process arc by arc. Tasks 2-7 (tier_1) can be done with a synopsis + key excerpts. Task 9 (tier_2) needs the actual text for each arc.

- **Review is essential**: LLM-generated scene counts and line attributions will have errors. Cross-check against the actual text, especially line ranges and scene boundaries.

- **Iterative refinement**: After the first generation pass, run the agent and see where it struggles. Add detail to the tier_2 files for those areas.

- **Scene ID assignment**: If you have a pre-chunked version of the text (e.g., from an embedding pipeline), use those chunk boundaries as scene boundaries and their IDs as SC_IDs. If not, let the LLM segment naturally and number sequentially.
