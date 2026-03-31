"""
Bilingual line-level alignment using bertalign.

CLI: python -m preprocessing.alignment.align \
       --src data/voyage-fr.jsonl --tgt data/voyage-it.jsonl \
       --out data/alignment-fr-it.jsonl
"""

import argparse
import json
from pathlib import Path


def load_jsonl(path: Path) -> tuple[list, list[str]]:
    """Load JSONL file, return (ids, texts). Preserves original id types."""
    ids = []
    texts = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            ids.append(row["id"])
            texts.append(row["t"])
    return ids, texts


def beads_to_alignment(
    beads: list[tuple[list[int], list[int]]],
    src_ids: list,
    tgt_ids: list,
) -> list[dict]:
    """Convert bertalign bead tuples to output records.

    Skips beads where either side is empty (insertions/deletions).
    """
    records = []
    for src_bead, tgt_bead in beads:
        if not src_bead or not tgt_bead:
            continue
        src = [src_ids[i] for i in src_bead]
        tgt = [tgt_ids[i] for i in tgt_bead]
        records.append({
            "src_lines": src,
            "tgt_lines": tgt,
            "type": f"{len(src_bead)}-{len(tgt_bead)}",
        })
    return records


def write_alignment(records: list[dict], path: Path) -> None:
    """Write alignment records as JSONL."""
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def run_alignment(
    src_path: Path,
    tgt_path: Path,
    out_path: Path,
    max_align: int = 3,
    top_k: int = 10,
    win: int = 10,
    min_win_size: int = 1,
    percent: float = 0.15,
) -> None:
    """Run full alignment pipeline: load → bertalign → write."""
    from bertalign import Bertalign

    src_ids, src_texts = load_jsonl(src_path)
    tgt_ids, tgt_texts = load_jsonl(tgt_path)

    # Pre-flight: empty texts would silently break index mapping even with
    # the is_split patch, since bertalign embeds each line and empty strings
    # produce degenerate embeddings.
    empty_src = [i for i, t in enumerate(src_texts) if not t.strip()]
    empty_tgt = [i for i, t in enumerate(tgt_texts) if not t.strip()]
    if empty_src or empty_tgt:
        raise ValueError(
            f"Empty text lines break alignment index mapping. "
            f"src has {len(empty_src)} empty lines (first: {empty_src[:5]}), "
            f"tgt has {len(empty_tgt)} empty lines (first: {empty_tgt[:5]})"
        )

    src_blob = "\n".join(src_texts)
    tgt_blob = "\n".join(tgt_texts)

    aligner = Bertalign(
        src_blob, tgt_blob,
        is_split=True,
        max_align=max_align,
        top_k=top_k,
        win=win,
        min_win_size=min_win_size,
        percent=percent,
    )
    aligner.align_sents()

    records = beads_to_alignment(aligner.result, src_ids, tgt_ids)
    write_alignment(records, out_path)
    print(f"Wrote {len(records)} alignment beads to {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Align bilingual JSONL files")
    parser.add_argument("--src", type=Path, required=True, help="Source JSONL")
    parser.add_argument("--tgt", type=Path, required=True, help="Target JSONL")
    parser.add_argument("--out", type=Path, required=True, help="Output alignment JSONL")
    parser.add_argument("--max-align", type=int, default=3)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--win", type=int, default=10)
    parser.add_argument("--min-win-size", type=int, default=1)
    parser.add_argument("--percent", type=float, default=0.15)
    args = parser.parse_args()

    run_alignment(
        args.src, args.tgt, args.out,
        max_align=args.max_align,
        top_k=args.top_k,
        win=args.win,
        min_win_size=args.min_win_size,
        percent=args.percent,
    )
