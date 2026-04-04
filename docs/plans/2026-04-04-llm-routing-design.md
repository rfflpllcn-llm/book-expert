# LLM-based Query Routing

**Date**: 2026-04-04
**Status**: Approved

## Problem

`route_query()` uses substring matching for routing queries to tier_2 arcs and tier_3 essays. This fails on accent mismatches (`celine` vs `Céline`), semantic gaps (biographical questions not matching any keyword), and generally lacks understanding of query intent.

## Solution

Replace deterministic routing with LLM-in-context routing: Claude reads the metadata already in the cached system prompt (arc keywords/line-ranges from `book.yaml`, essay headers from `_index.yaml`) and decides which sources to load.

## Changes

### 1. New CLI: `lib/load_arc.py`

```
python -m lib.load_arc . <arc_id>
```

- Prints content of `knowledge/tier_2/<arc_id>.md` to stdout
- Reuses `load_tier2_file()` from `loader.py`
- Exit 1 if file not found

### 2. Update `books/voyage/CLAUDE.md` workflow

Replace the current "Route to tier_2 if needed" step with LLM routing instructions:

> After checking the cache, evaluate the metadata available in the system prompt (arcs in `book.yaml` with keywords/line-ranges, essay headers in `_index.yaml` with author/stance/themes/sections) and decide which tier_2 and tier_3 sources are relevant to the query. For biographical queries, prefer essays with `biographical-*` stance. For stylistic/linguistic queries, prefer essays with `stylistic-*` stance. Load chosen sources with CLI tools.

Add `python -m lib.load_arc . <arc_id>` to the Tools section.

### 3. No changes to `loader.py`

`route_query()` and `build_context()` remain for potential programmatic use. The CLAUDE.md workflow no longer depends on them.