"""
Save validated Q&A pairs to the book's cache.

Importable: from lib.save_qa import save
CLI: python -m lib.save_qa <book_dir> "question" "summary" "sc_refs" [--link path]
"""

import sys
from pathlib import Path

from lib.loader import append_to_qa_cache


def save(book_dir: Path, question: str, summary: str,
         scene_refs: str = "", full_answer: str = ""):
    """Save a Q&A pair. Delegates to loader.append_to_qa_cache."""
    append_to_qa_cache(book_dir, question, summary, scene_refs, full_answer)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python -m lib.save_qa <book_dir> <question> <summary> [sc_refs] [--link path]")
        sys.exit(1)

    book_dir = Path(sys.argv[1])
    question = sys.argv[2]
    summary = sys.argv[3]

    # Parse sc_refs (4th positional arg, if not a flag)
    sc_refs = ""
    remaining = sys.argv[4:]
    if remaining and not remaining[0].startswith("--"):
        sc_refs = remaining.pop(0)

    # Handle --link: link to an existing answer file
    full_answer = ""
    if "--link" in remaining:
        idx = remaining.index("--link")
        if idx + 1 < len(remaining):
            linked = Path(remaining[idx + 1])
            knowledge_dir = book_dir / "knowledge"
            if not linked.is_absolute():
                linked = knowledge_dir / linked
            if not linked.exists():
                print(f"Error: --link target does not exist: {linked}")
                sys.exit(1)
            # For --link, we skip full_answer (file already exists).
            # Just write cache entry with the link.
            from datetime import date
            import re
            today = date.today().isoformat()
            cache_path = knowledge_dir / "tier_1" / "08_qa_cache.md"
            entry = f"\n\n## Q: {question}\n"
            if sc_refs:
                entry += f"**SC di riferimento**: {sc_refs}\n"
            entry += f"**Risposta**: {summary}\n"
            entry += f"**Risposta completa**: {linked.relative_to(knowledge_dir)}\n"
            entry += f"**Data**: {today}\n"
            with open(cache_path, "a", encoding="utf-8") as f:
                f.write(entry)
            print(f"Linked to {linked.relative_to(knowledge_dir)}")
            sys.exit(0)

    save(book_dir, question, summary, sc_refs, full_answer)
    print(f"Saved to cache.")
