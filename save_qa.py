#!/usr/bin/env python3
"""
Append a validated Q&A pair to the cache.
Usage: python save_qa.py "question" "answer" "SC_00019, SC_00025"
"""
import sys
from datetime import date
from pathlib import Path

CACHE = Path(__file__).parent / "knowledge" / "tier_1" / "08_qa_cache.md"

if len(sys.argv) < 3:
    print("Usage: python save_qa.py <question> <answer> [sc_refs]")
    sys.exit(1)

question = sys.argv[1]
answer = sys.argv[2]
sc_refs = sys.argv[3] if len(sys.argv) > 3 else ""

entry = f"\n\n## Q: {question}\n"
if sc_refs:
    entry += f"**SC di riferimento**: {sc_refs}\n"
entry += f"**Risposta**: {answer}\n"
entry += f"**Data**: {date.today().isoformat()}\n"

with open(CACHE, "a", encoding="utf-8") as f:
    f.write(entry)

print(f"✓ Saved to {CACHE.name} ({date.today().isoformat()})")
