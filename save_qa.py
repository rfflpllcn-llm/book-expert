#!/usr/bin/env python3
"""
Append a validated Q&A pair to the cache and optionally save/link the full answer.

Usage:
  python save_qa.py "question" "summary" "SC_refs"                    # summary only
  python save_qa.py "question" "summary" "SC_refs" --stdin            # full answer from stdin
  python save_qa.py "question" "summary" "SC_refs" --file X.md        # full answer from file
  python save_qa.py "question" "summary" "SC_refs" --link answers/X.md # link existing answer file

The full answer is saved as a separate .md in knowledge/answers/ and linked from the cache.
With --link, the answer file must already exist (e.g. written by Claude Code's Write tool).
"""
import re
import sys
from datetime import date
from pathlib import Path

CACHE = Path(__file__).parent / "knowledge" / "tier_1" / "08_qa_cache.md"
ANSWERS_DIR = Path(__file__).parent / "knowledge" / "answers"

if len(sys.argv) < 3:
    print("Usage: python save_qa.py <question> <summary> [sc_refs] [--stdin | --file PATH | --link PATH]")
    sys.exit(1)

question = sys.argv[1]
summary = sys.argv[2]
sc_refs = sys.argv[3] if len(sys.argv) > 3 and not sys.argv[3].startswith("--") else ""

today = date.today().isoformat()
args = sys.argv[3:]

# Determine answer file
answer_file = None

if "--link" in args:
    # Link to an existing answer file (written externally, e.g. by Claude Code Write tool)
    idx = args.index("--link")
    if idx + 1 < len(args):
        linked = Path(args[idx + 1])
        # Resolve relative to knowledge/ dir
        if not linked.is_absolute():
            linked = CACHE.parent.parent / linked
        if not linked.exists():
            print(f"Error: --link target does not exist: {linked}")
            sys.exit(1)
        answer_file = linked
        print(f"✓ Linked to {answer_file.relative_to(answer_file.parent.parent.parent)}")
    else:
        print("Error: --link requires a path argument")
        sys.exit(1)

elif "--stdin" in args or "--file" in args:
    # Read full answer and write it to answers/
    full_answer = ""
    if "--stdin" in args:
        full_answer = sys.stdin.read().strip()
    elif "--file" in args:
        idx = args.index("--file")
        if idx + 1 < len(args):
            full_answer = Path(args[idx + 1]).read_text(encoding="utf-8").strip()
        else:
            print("Error: --file requires a path argument")
            sys.exit(1)

    if full_answer:
        ANSWERS_DIR.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r'[^a-z0-9]+', '-', question.lower().strip())[:60].strip('-')
        answer_file = ANSWERS_DIR / f"{today}_{slug}.md"
        content = f"# {question}\n\n**Data**: {today}\n**SC di riferimento**: {sc_refs}\n\n{full_answer}\n"
        answer_file.write_text(content, encoding="utf-8")
        print(f"✓ Full answer saved to {answer_file.relative_to(answer_file.parent.parent.parent)}")

# Append summary to cache
entry = f"\n\n## Q: {question}\n"
if sc_refs:
    entry += f"**SC di riferimento**: {sc_refs}\n"
entry += f"**Risposta**: {summary}\n"
if answer_file:
    entry += f"**Risposta completa**: {answer_file.relative_to(CACHE.parent.parent)}\n"
entry += f"**Data**: {today}\n"

with open(CACHE, "a", encoding="utf-8") as f:
    f.write(entry)

print(f"✓ Saved to {CACHE.name} ({today})")
