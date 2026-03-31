# tests/test_cite.py
import pytest
from lib.cite import load_lines, format_citation


def test_load_lines(book_dir):
    lines = load_lines(book_dir, 1, 3)
    assert len(lines) == 3
    assert lines[0] == ("FR1", "First line of the test book.")
    assert lines[2] == ("FR3", "Third line wraps up.")


def test_load_lines_filters_non_main_text(book_dir):
    """FR6 is page_header — should be filtered out."""
    lines = load_lines(book_dir, 1, 6)
    assert len(lines) == 5
    assert all(lid != "FR6" for lid, _ in lines)


def test_load_lines_empty_range(book_dir):
    lines = load_lines(book_dir, 100, 200)
    assert lines == []


def test_format_citation_multiple():
    lines = [("FR1", "Hello."), ("FR2", "World.")]
    result = format_citation(lines)
    assert result == "> «Hello. World.» (FR1–FR2)"


def test_format_citation_single():
    lines = [("FR1", "Hello.")]
    result = format_citation(lines)
    assert result == "> «Hello.» (FR1)"


def test_format_citation_empty():
    result = format_citation([])
    assert "no lines found" in result


def test_load_alignment(bilingual_book_dir):
    from lib.cite import load_alignment
    beads = load_alignment(bilingual_book_dir, "it")
    assert len(beads) == 4
    assert beads[0]["src_lines"] == ["1", "2"]
    assert beads[0]["tgt_lines"] == [1]


def test_find_aligned_line_ids(bilingual_book_dir):
    from lib.cite import load_alignment, find_aligned_line_ids
    beads = load_alignment(bilingual_book_dir, "it")
    # Request FR lines 1-3 -> should find IT lines from beads covering FR1,2,3
    it_ids = find_aligned_line_ids(beads, 1, 3)
    assert it_ids == [1, 2, 3]


def test_find_aligned_line_ids_partial(bilingual_book_dir):
    from lib.cite import load_alignment, find_aligned_line_ids
    beads = load_alignment(bilingual_book_dir, "it")
    # Request only FR4 -> IT4
    it_ids = find_aligned_line_ids(beads, 4, 4)
    assert it_ids == [4]


def test_load_translation_lines(bilingual_book_dir):
    from lib.cite import load_translation_lines
    lines = load_translation_lines(bilingual_book_dir, "it", 1, 3)
    assert len(lines) == 3
    assert lines[0] == ("IT1", "Prima riga del libro di prova.")
    assert lines[2] == ("IT3", "La terza riga conclude.")


def test_format_bilingual_citation(bilingual_book_dir):
    from lib.cite import load_lines, load_translation_lines, format_citation
    fr_lines = load_lines(bilingual_book_dir, 1, 3)
    it_lines = load_translation_lines(bilingual_book_dir, "it", 1, 3)
    fr_cite = format_citation(fr_lines)
    it_cite = format_citation(it_lines)
    assert "FR1" in fr_cite
    assert "IT1" in it_cite


def test_format_citation_gap_aware():
    """Non-contiguous IDs should be formatted with + separator."""
    from lib.cite import format_citation
    lines = [("IT1", "Riga uno."), ("IT3", "Riga tre.")]
    result = format_citation(lines)
    # Should NOT say IT1–IT3 (that implies IT2 exists)
    assert "IT1 + IT3" in result


def test_load_translation_lines_no_translations(book_dir):
    """Books without translations section should raise a clear error."""
    from lib.cite import load_translation_lines
    with pytest.raises(KeyError):
        load_translation_lines(book_dir, "it", 1, 3)
