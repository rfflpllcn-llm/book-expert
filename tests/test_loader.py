# tests/test_loader.py
from lib.loader import (
    load_book_config, route_query, load_tier1, load_tier2_file, load_tier3,
    build_context, append_to_qa_cache,
)


def test_load_book_config_basic(book_dir):
    config = load_book_config(book_dir)
    assert config["title"] == "Test Book"
    assert config["author"] == "Test Author"
    assert config["year"] == 2000
    assert len(config["arcs"]) == 2
    assert "02_01_test_arc" in config["arcs"]
    assert len(config["characters"]) == 2


def test_load_book_config_merges_preferences(book_dir):
    """Per-book preferences override global defaults."""
    config = load_book_config(book_dir)
    prefs = config["preferences"]
    # Global default
    assert prefs["language"] == "italiano"
    assert prefs["tone"] == "academic_formal"
    # Per-book override
    assert prefs["citation_density"] == "heavy_with_commentary"


def test_load_book_config_source_text(book_dir):
    config = load_book_config(book_dir)
    src = config["source_text"]
    assert src["file"] == "data/test.csv"
    assert src["line_prefix"] == "FR"
    assert src["text_column"] == "text"


def test_route_query_keyword(book_dir):
    config = load_book_config(book_dir)
    arcs = route_query("tell me about the beginning", config)
    assert "02_01_test_arc" in arcs


def test_route_query_character(book_dir):
    config = load_book_config(book_dir)
    arcs = route_query("what happens to hero?", config)
    assert "02_01_test_arc" in arcs
    assert "02_02_test_arc_two" in arcs


def test_route_query_line_ref(book_dir):
    config = load_book_config(book_dir)
    arcs = route_query("explain L2", config)
    assert "02_01_test_arc" in arcs


def test_route_query_sc_ref_ignored(book_dir):
    """SC refs are scene IDs, not line numbers — should not route."""
    config = load_book_config(book_dir)
    arcs = route_query("what is SC_00002?", config)
    assert arcs == []


def test_route_query_no_match(book_dir):
    config = load_book_config(book_dir)
    arcs = route_query("completely unrelated query", config)
    assert arcs == []


def test_route_query_cap_at_four(book_dir):
    config = load_book_config(book_dir)
    arcs = route_query("test beginning second ending hero sidekick", config)
    assert len(arcs) <= 4


def test_load_tier1(book_dir):
    content = load_tier1(book_dir)
    assert "Index" in content
    assert "Q&A Cache" in content
    assert "00_index.md" in content


def test_load_tier2_file(book_dir):
    content = load_tier2_file(book_dir, "02_01_test_arc")
    assert "Arc 1" in content
    assert "Test arc content" in content


def test_load_tier2_file_missing(book_dir):
    content = load_tier2_file(book_dir, "02_99_nonexistent")
    assert content == ""


def test_load_tier3_arc_match(book_dir):
    result = load_tier3(book_dir)
    assert "Test Critic" in result
    assert "Test Study" in result
    assert "Chapter on Style" in result


def test_load_tier3_missing_index(book_dir):
    """Gracefully handle missing tier_3."""
    import shutil
    shutil.rmtree(book_dir / "knowledge" / "tier_3")
    result = load_tier3(book_dir)
    assert result == ""


def test_build_context_with_match(book_dir):
    system, dynamic = build_context("tell me about the beginning", book_dir)
    assert "Index" in system  # tier_1 loaded
    assert "Arc 1" in dynamic  # matched tier_2 loaded


def test_build_context_no_match(book_dir):
    """No arc match, but essay summaries are still included."""
    system, dynamic = build_context("completely unrelated", book_dir)
    assert "Index" in system
    # No tier_2 arcs matched, but essays are always present
    assert "ARC:" not in dynamic
    assert "Test Critic" in dynamic


def test_build_context_with_commentary(book_dir):
    """Essay summaries are always included in dynamic context."""
    system, dynamic = build_context("tell me about the beginning", book_dir)
    assert "Test Critic" in dynamic
    assert "Test Study" in dynamic


def test_append_to_qa_cache(book_dir):
    append_to_qa_cache(book_dir, "Test Q?", "Test summary.", "SC_00001", "Full answer.")
    cache = (book_dir / "knowledge" / "tier_1" / "08_qa_cache.md").read_text()
    assert "## Q: Test Q?" in cache
    assert "Test summary." in cache
    assert "SC_00001" in cache
    # Full answer file created
    answers = list((book_dir / "knowledge" / "answers").glob("*.md"))
    assert len(answers) == 1
    content = answers[0].read_text()
    assert "Full answer." in content


def test_append_to_qa_cache_links_answer(book_dir):
    append_to_qa_cache(book_dir, "Q2?", "Summary2.", full_answer="Answer2.")
    cache = (book_dir / "knowledge" / "tier_1" / "08_qa_cache.md").read_text()
    assert "**Risposta completa**:" in cache
    assert "answers/" in cache
