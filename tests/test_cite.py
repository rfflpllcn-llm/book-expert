# tests/test_cite.py
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
    assert "no main_text" in result
