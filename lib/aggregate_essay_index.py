"""
Aggregate per-essay YAML descriptors into knowledge/tier_3/_index.yaml.

CLI: python -m lib.aggregate_essay_index <book_dir>
"""

import sys

import yaml
from pathlib import Path


def aggregate(book_dir: Path) -> None:
    """Merge all data/essays/<slug>/<slug>.yaml into _index.yaml."""
    essays_dir = book_dir / "data" / "essays"
    merged = {"essays": {}}

    if essays_dir.exists():
        for essay_subdir in sorted(essays_dir.iterdir()):
            if not essay_subdir.is_dir():
                continue
            yaml_files = list(essay_subdir.glob("*.yaml"))
            for yf in yaml_files:
                data = yaml.safe_load(yf.read_text(encoding="utf-8")) or {}
                for slug, info in data.get("essays", {}).items():
                    merged["essays"][slug] = info

    output = book_dir / "knowledge" / "tier_3" / "_index.yaml"
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        yaml.safe_dump(merged, f, allow_unicode=True, sort_keys=False, width=120)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m lib.aggregate_essay_index <book_dir>")
        sys.exit(1)
    aggregate(Path(sys.argv[1]))
    print("Done: _index.yaml updated")
