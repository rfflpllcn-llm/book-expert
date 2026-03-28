You are given two files:

1. **A PDF book** (e.g. `portnoy_s_complaint_en.pdf`)
2. **A JSONL file** (e.g. `portnoy_s_complaint_en-filtered.jsonl`) where each line is a JSON object with an `"id"` (string) and a `"t"` (text content) field, representing sequential lines of the book.

**Task:**

1. Analyze the PDF to identify the book's natural boundaries (chapters, sections, named parts, or any other structural divisions used by the author).

2. For each section found, locate the corresponding start and end `"id"` values in the JSONL file by matching section titles and content.

3. **Splitting rule:** If any section contains more than 1000 lines (i.e. `end_id - start_id + 1 > 1000`), that section **must** be further split into at least 2 sub-parts. Each sub-part should be as semantically self-contained as possible — look for natural narrative shifts, topic changes, time jumps, or thematic transitions within the section to determine the best split points. Sub-parts should be given a short descriptive label summarizing their content.

4. Return the result as a **JSON array** with the following structure:

```json
[
  {
    "section": 1,
    "title": "SECTION TITLE",
    "start_id": "...",
    "end_id": "...",
    "sub_parts": null
  },
  {
    "section": 2,
    "title": "LONG SECTION TITLE",
    "start_id": "...",
    "end_id": "...",
    "sub_parts": [
      {"part": 1, "label": "Short descriptive label", "start_id": "...", "end_id": "..."},
      {"part": 2, "label": "Short descriptive label", "start_id": "...", "end_id": "..."}
    ]
  }
]
```

**Rules:**
- Section boundaries must be exhaustive and non-overlapping: every `"id"` in the JSONL must belong to exactly one section.
- `"sub_parts"` is `null` when the section has 1000 lines or fewer.
- When splitting, prefer break points at paragraph boundaries (blank lines or natural pauses) rather than mid-sentence.
- Sub-part labels should reflect the narrative content (e.g. "Childhood memories with father", "First encounter with Mary Jane"), not generic labels like "Part A / Part B".
