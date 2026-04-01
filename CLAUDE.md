# Book Expert

Multi-book literary expert system. Each book is a self-contained workspace.

## Setup

```bash
uv pip install -e .
```

## Usage

To work with a specific book, `cd` into its directory:

```bash
cd books/voyage/
```

Claude Code will read the book's `CLAUDE.md` from that directory.

## Adding a new book

1. Create `books/<slug>/` with `book.yaml`, `data/`, `knowledge/`
2. Run `python -m lib.generate_claude_md books/<slug>/`
3. `cd books/<slug>/` and start a Claude Code session
