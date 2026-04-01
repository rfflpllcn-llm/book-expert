# Book Expert

Multi-book literary expert system powered by Claude. Each book is a
self-contained workspace with structured knowledge files and two-tier
prompt caching.

## Project structure

```
book-expert/
├── CLAUDE.md                          # Root agent identity
├── pyproject.toml
├── requirements.txt
├── books/
│   ├── voyage/                        # Voyage au bout de la nuit (Céline)
│   ├── voyage2/                       # Voyage — alternate build
│   └── portnoy/                       # Portnoy's Complaint (Roth)
├── lib/                               # Shared Python modules
│   ├── loader.py                      # Knowledge loading + query routing
│   ├── cite.py                        # Citation utilities
│   ├── generate_claude_md.py          # Generate per-book CLAUDE.md
│   └── save_qa.py                     # Q&A cache persistence
└── preprocessing/                     # Pipeline stages (PDF → knowledge)
    ├── 00__pdf2jsonl/
    ├── 01__book_natural_bounds/
    ├── 02__semantic_chunking/
    ├── 03__generate_knowledge/
    └── 04__generate_book_yaml/
```

Each book directory follows the same layout:

```
books/<slug>/
├── book.yaml                          # Book metadata and configuration
├── preferences.yaml                   # Agent behavior preferences
├── CLAUDE.md                          # Generated — agent identity for this book
├── data/                              # Source chunks (JSONL, JSON)
└── knowledge/
    ├── tier_1/                        # Always cached (index, synopsis, characters, themes, style, context, Q&A)
    ├── tier_2/                        # Loaded on demand (detailed scene/arc files)
    └── tier_3/                        # (if present) additional reference material
```

## How it works

1. **Tier 1** (index, synopsis, characters, themes, style, context) is loaded
   into the system prompt with `cache_control: ephemeral`. This gets cached
   by Anthropic for 5 minutes and reused across queries — ~90% cost reduction.

2. **Tier 2** (detailed scene-by-scene arc files) is loaded dynamically.
   The `loader.py` routes each query to the most relevant arc files
   based on keyword matching, references, and character mentions.

3. **Q&A cache** grows over time. Validated answers are appended to
   `08_qa_cache.md`, which is part of tier 1.

## Setup

```bash
uv pip install -e .
export ANTHROPIC_API_KEY=sk-ant-...
```

## Usage

### With Claude Code

```bash
cd books/voyage/
claude
# Claude Code reads the book's CLAUDE.md and becomes an expert on that book
```

### Adding a new book

1. Create `books/<slug>/` with `book.yaml`, `data/`, `knowledge/`
2. Run `python -m lib.generate_claude_md books/<slug>/`
3. `cd books/<slug>/` and start a Claude Code session
