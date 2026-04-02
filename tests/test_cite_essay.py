# tests/test_cite_essay.py
import pytest
from pathlib import Path

from lib.cite_essay import load_arc, load_toc, load_raw_lines


@pytest.fixture
def essay_dir(tmp_path):
    """Create a minimal essay directory structure."""
    edir = tmp_path / "data" / "essays" / "test_essay"
    edir.mkdir(parents=True)

    # tier_2 arc file
    t2 = edir / "tier_2"
    t2.mkdir()
    (t2 / "02_01_test_arc.md").write_text(
        "# Test Arc\n\n## Synopsis\nArc synopsis.\n\n"
        "### SC1 (L10–L20)\nScene summary.\n\n**Figures**: Author\n**Themes**: Style\n"
    )

    # tier_1 index
    t1 = edir / "tier_1"
    t1.mkdir()
    (t1 / "00_index.md").write_text("# Index\n\n| # | Arc | Lines |\n|---|---|---|\n| 1 | Test Arc | 10–20 |\n")

    # filtered JSONL
    import json
    lines = [{"id": str(i), "t": f"Line {i} text."} for i in range(1, 25)]
    (edir / "test_essay-filtered.jsonl").write_text(
        "\n".join(json.dumps(l, ensure_ascii=False) for l in lines) + "\n"
    )

    return edir


def test_load_arc(essay_dir):
    result = load_arc(essay_dir, "02_01_test_arc")
    assert "Test Arc" in result
    assert "Scene summary" in result


def test_load_arc_missing(essay_dir):
    result = load_arc(essay_dir, "02_99_nonexistent")
    assert result == ""


def test_load_toc(essay_dir):
    result = load_toc(essay_dir)
    assert "Index" in result
    assert "Test Arc" in result


def test_load_raw_lines(essay_dir):
    result = load_raw_lines(essay_dir, 5, 10)
    assert "Line 5 text." in result
    assert "Line 10 text." in result
    assert "Line 11 text." not in result


def test_load_raw_lines_empty_range(essay_dir):
    result = load_raw_lines(essay_dir, 100, 200)
    assert result == ""


def test_load_raw_lines_mid_range(essay_dir):
    """Lines in the middle of the file are correctly loaded."""
    result = load_raw_lines(essay_dir, 10, 15)
    assert "Line 10 text." in result
    assert "Line 15 text." in result
    assert "Line 9 text." not in result
    assert "Line 16 text." not in result


def test_load_raw_lines_single(essay_dir):
    """Single-line range works."""
    result = load_raw_lines(essay_dir, 1, 1)
    assert "Line 1 text." in result
    assert "Line 2 text." not in result
