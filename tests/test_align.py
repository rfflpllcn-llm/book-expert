# tests/test_align.py
import json
import pytest
from pathlib import Path


@pytest.fixture
def alignment_data(tmp_path):
    """Create minimal FR and IT JSONL files for alignment tests."""
    fr_lines = [
        {"id": "77", "t": "First sentence."},
        {"id": "78", "t": "Second sentence."},
        {"id": "79", "t": "Third sentence."},
    ]
    it_lines = [
        {"id": 1, "t": "Prima frase."},
        {"id": 2, "t": "Seconda frase."},
        {"id": 3, "t": "Terza frase."},
    ]
    fr_path = tmp_path / "fr.jsonl"
    it_path = tmp_path / "it.jsonl"
    out_path = tmp_path / "alignment.jsonl"

    fr_path.write_text("\n".join(json.dumps(r) for r in fr_lines) + "\n")
    it_path.write_text("\n".join(json.dumps(r) for r in it_lines) + "\n")

    return fr_path, it_path, out_path, fr_lines, it_lines


def test_load_jsonl_texts(alignment_data):
    from preprocessing.alignment.align import load_jsonl
    fr_path, _, _, _, _ = alignment_data
    ids, texts = load_jsonl(fr_path)
    assert ids == ["77", "78", "79"]
    assert texts == ["First sentence.", "Second sentence.", "Third sentence."]


def test_load_jsonl_texts_int_ids(alignment_data):
    """IT file has integer IDs — should be coerced to int list."""
    from preprocessing.alignment.align import load_jsonl
    _, it_path, _, _, _ = alignment_data
    ids, texts = load_jsonl(it_path)
    assert ids == [1, 2, 3]
    assert texts[0] == "Prima frase."


def test_beads_to_alignment():
    """Convert bertalign bead tuples to output dicts."""
    from preprocessing.alignment.align import beads_to_alignment

    src_ids = ["77", "78", "79"]
    tgt_ids = [1, 2, 3]
    beads = [
        ([0, 1], [0]),       # FR77+FR78 -> IT1
        ([2], [1, 2]),       # FR79 -> IT2+IT3
    ]
    result = beads_to_alignment(beads, src_ids, tgt_ids)
    assert result == [
        {"src_lines": ["77", "78"], "tgt_lines": [1], "type": "2-1"},
        {"src_lines": ["79"], "tgt_lines": [2, 3], "type": "1-2"},
    ]


def test_beads_to_alignment_skips_empty():
    """Beads with empty src or tgt (insertions/deletions) are skipped."""
    from preprocessing.alignment.align import beads_to_alignment

    src_ids = ["77", "78"]
    tgt_ids = [1, 2]
    beads = [
        ([0], []),           # deletion — skip
        ([], [0]),           # insertion — skip
        ([1], [1]),          # 1-1 — keep
    ]
    result = beads_to_alignment(beads, src_ids, tgt_ids)
    assert len(result) == 1
    assert result[0]["type"] == "1-1"


def test_write_alignment(alignment_data):
    from preprocessing.alignment.align import write_alignment

    _, _, out_path, _, _ = alignment_data
    records = [
        {"src_lines": ["77"], "tgt_lines": [1], "type": "1-1"},
        {"src_lines": ["78", "79"], "tgt_lines": [2, 3], "type": "2-2"},
    ]
    write_alignment(records, out_path)

    lines = out_path.read_text().strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0]) == records[0]
    assert json.loads(lines[1]) == records[1]


def test_run_alignment_rejects_empty_texts(tmp_path):
    """Empty t values would break bead-to-ID mapping — must be caught."""
    from preprocessing.alignment.align import run_alignment

    fr_lines = [
        {"id": "1", "t": "First sentence."},
        {"id": "2", "t": ""},  # empty — should trigger ValueError
        {"id": "3", "t": "Third sentence."},
    ]
    it_lines = [
        {"id": 1, "t": "Prima frase."},
        {"id": 2, "t": "Seconda frase."},
    ]
    fr_path = tmp_path / "fr.jsonl"
    it_path = tmp_path / "it.jsonl"
    out_path = tmp_path / "alignment.jsonl"

    fr_path.write_text("\n".join(json.dumps(r) for r in fr_lines) + "\n")
    it_path.write_text("\n".join(json.dumps(r) for r in it_lines) + "\n")

    with pytest.raises(ValueError, match="Empty text lines"):
        run_alignment(fr_path, it_path, out_path)
