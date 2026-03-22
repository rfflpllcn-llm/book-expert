import json
import re

FIELDS = ["sc_id", "chunk_ids", "embedding_summary", "interpretive_layers"]


def compact_chunk_ids(ids: list[str]) -> str:
    """Convert ['FR84', 'FR85', ..., 'FR97'] to '84-97', or ['FR1'] to '1'."""
    nums = sorted(int(re.sub(r"[^0-9]", "", x)) for x in ids)
    if len(nums) == 1:
        return str(nums[0])
    return f"{nums[0]}-{nums[-1]}"


with open("data/processed_chunks.jsonl") as f:
    data = json.load(f)

filtered = []
for item in data:
    if item.get("chunk_type") != "main_text":
        continue
    row = {k: item[k] for k in FIELDS if k in item}
    row["sc_id"] = row["sc_id"].split("_")[1]
    if "chunk_ids" in row:
        row["chunk_ids"] = compact_chunk_ids(row["chunk_ids"])
    filtered.append(row)

with open("data/extracted_chunks.json", "w", encoding="utf-8") as f:
    json.dump(filtered, f, ensure_ascii=False, indent=2)

print(f"Wrote {len(filtered)} items to data/extracted_chunks.json")