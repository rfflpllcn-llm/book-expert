# Voyage au bout de la nuit — Expert Agent

A Claude-powered literary expert on Céline's novel, using structured knowledge
files with two-tier prompt caching.

## Project structure

```
voyage-expert/
├── CLAUDE.md                          # Agent identity for Claude Code
├── requirements.txt
├── knowledge/
│   ├── tier_1/                        # Always cached (~10K tokens)
│   │   ├── 00_index.md               # Master index
│   │   ├── 01_synopsis.md            # Full plot summary
│   │   ├── 03_characters.md          # Character profiles
│   │   ├── 04_themes.md              # Thematic analysis
│   │   ├── 05_style.md               # Style and technique
│   │   ├── 06_context.md             # Historical/biographical context
│   │   └── 08_qa_cache.md            # Validated Q&A (grows over time)
│   └── tier_2/                        # Loaded on demand (~195K tokens)
│       ├── 02_01_incipit.md           # 15 arc files with all 2,630 scenes
│       ├── 02_02_guerra_fronte.md
│       ├── ...
│       └── 02_15_sophie_finale.md
└── src/
    ├── loader.py                      # Knowledge loading + query routing
    └── agent.py                       # Interactive agent with API calls
```

## How it works

1. **Tier 1** (index, synopsis, characters, themes, style, context) is loaded
   into the system prompt with `cache_control: ephemeral`. This gets cached
   by Anthropic for 5 minutes and reused across queries — ~90% cost reduction.

2. **Tier 2** (detailed scene-by-scene arc files) is loaded dynamically.
   The `loader.py` routes each query to the 1–4 most relevant arc files
   based on keyword matching, SC/line references, and character mentions.

3. **Q&A cache** grows over time. Validated answers are appended to
   `08_qa_cache.md`, which is part of tier 1. On subsequent queries,
   Claude sees prior answers and doesn't need to re-derive them.

## Setup

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
```

## Usage

### Interactive session
```bash
python src/agent.py
```

### With Claude Code
```bash
cd voyage-expert
claude
# Claude Code reads CLAUDE.md and understands the project
# Ask: "Chi è Robinson e qual è il suo ruolo nel romanzo?"
```

### Programmatic
```python
from src.loader import build_context, route_query
from src.agent import ask, create_client

client = create_client()
answer = ask(client, "Qual è il significato della scena al Stand des Nations?")
```

## Extending

- **Add more scenes**: Re-run `build_full_md.py` with updated JSON
- **Add secondary criticism**: Create `knowledge/tier_2/08_criticism.md`
- **Add other Céline works**: Create `knowledge/tier_2/09_mort_a_credit.md`
- **Upgrade to RAG**: When tier_2 exceeds ~500K tokens, add a vector store
  for retrieval while keeping tier_1 cached (hybrid approach)
