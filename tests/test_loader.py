# tests/test_loader.py
from lib.loader import (
    load_book_config, route_query, load_tier1, load_tier2_file, load_tier3,
    build_context, append_to_qa_cache, _load_tier3_index,
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
    result = route_query("tell me about the beginning", config)
    assert "02_01_test_arc" in result.arcs


def test_route_query_character(book_dir):
    config = load_book_config(book_dir)
    result = route_query("what happens to hero?", config)
    assert "02_01_test_arc" in result.arcs
    assert "02_02_test_arc_two" in result.arcs


def test_route_query_line_ref(book_dir):
    config = load_book_config(book_dir)
    result = route_query("explain L2", config)
    assert "02_01_test_arc" in result.arcs


def test_route_query_sc_ref_ignored(book_dir):
    """SC refs are scene IDs, not line numbers — should not route."""
    config = load_book_config(book_dir)
    result = route_query("what is SC_00002?", config)
    assert result.arcs == []


def test_route_query_no_match(book_dir):
    config = load_book_config(book_dir)
    result = route_query("completely unrelated query", config)
    assert result.arcs == []


def test_route_query_cap_at_four(book_dir):
    config = load_book_config(book_dir)
    result = route_query("test beginning second ending hero sidekick", config)
    assert len(result.arcs) <= 4


def test_route_query_backward_compatible(book_dir):
    """RouteResult is backward-compatible: iterating yields arc IDs."""
    config = load_book_config(book_dir)
    result = route_query("tell me about the beginning", config)
    assert "02_01_test_arc" in list(result)


def test_route_query_returns_essay_matches(book_dir):
    """route_query returns essay slugs when themes match."""
    config = load_book_config(book_dir)
    tier3 = _load_tier3_index(book_dir)
    result = route_query("tell me about darkness", config, essays=tier3.get("essays", {}))
    assert result.essays == ["test_commentary"]


def test_route_query_essay_character_match(book_dir):
    """route_query returns essay slugs when essay characters match."""
    config = load_book_config(book_dir)
    tier3 = _load_tier3_index(book_dir)
    result = route_query("what does Céline say?", config, essays=tier3.get("essays", {}))
    assert "test_commentary" in result.essays


def test_route_query_essay_author_match(book_dir):
    """route_query returns essay slugs when author name matches."""
    config = load_book_config(book_dir)
    tier3 = _load_tier3_index(book_dir)
    result = route_query("what does Test Critic argue?", config, essays=tier3.get("essays", {}))
    assert "test_commentary" in result.essays


def test_route_query_essay_work_match(book_dir):
    """route_query returns essay slugs when work title matches."""
    config = load_book_config(book_dir)
    tier3 = _load_tier3_index(book_dir)
    result = route_query("in Test Study, chapter 3 says", config, essays=tier3.get("essays", {}))
    assert "test_commentary" in result.essays


def test_route_query_no_essay_match(book_dir):
    """Unrelated query returns no essay matches."""
    config = load_book_config(book_dir)
    tier3 = _load_tier3_index(book_dir)
    result = route_query("completely unrelated query", config, essays=tier3.get("essays", {}))
    assert result.essays == []


def test_build_context_includes_detailed_for_matched_essay(book_dir):
    """When an essay matches by theme, build_context includes detailed sections in dynamic."""
    system, dynamic = build_context("analysis of darkness", book_dir)
    # Header is in cached system prompt
    assert "Test Critic" in system
    # Matched essay detail is in dynamic context
    assert "Chapter on Style" in dynamic
    assert "ESSAY-DETAIL: test_commentary" in dynamic


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


def test_load_tier3_header_only(book_dir):
    """Default mode returns header info but NOT section summaries."""
    result = load_tier3(book_dir)
    assert "Test Critic" in result
    assert "Test Study" in result
    assert "structuralist" in result
    # Section detail should NOT be present in header-only mode
    assert "Chapter on Style" not in result


def test_load_tier3_detailed(book_dir):
    """Detailed mode returns full section summaries."""
    result = load_tier3(book_dir, detailed=True)
    assert "Test Critic" in result
    assert "Chapter on Style" in result
    assert "Analyzes core stylistic techniques" in result


def test_load_tier3_detailed_single_essay(book_dir):
    """Detailed mode for a specific essay slug."""
    result = load_tier3(book_dir, detailed=True, slug="test_commentary")
    assert "Test Critic" in result
    assert "Chapter on Style" in result


def test_load_tier3_detailed_unknown_slug(book_dir):
    """Detailed mode with unknown slug returns empty."""
    result = load_tier3(book_dir, detailed=True, slug="nonexistent")
    assert result == ""


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


def test_build_context_caches_essay_headers(book_dir):
    """build_context puts header-only essay summaries in system_cached, not dynamic."""
    system, dynamic = build_context("tell me about style", book_dir)
    # Headers are in the cached system prompt
    assert "Test Critic" in system
    assert "Test Study" in system
    # Section detail is NOT in either (no essay matched by routing)
    assert "Chapter on Style" not in system
    assert "Chapter on Style" not in dynamic


def test_build_context_no_match(book_dir):
    """No arc match; essay headers are in system prompt (cached)."""
    system, dynamic = build_context("completely unrelated", book_dir)
    assert "Index" in system  # tier_1 loaded
    assert "Test Critic" in system  # essay headers in cached prompt
    assert "ARC:" not in dynamic  # no tier_2 arcs matched


def test_build_context_with_commentary(book_dir):
    """Essay headers are in system prompt, not dynamic context."""
    system, dynamic = build_context("tell me about the beginning", book_dir)
    assert "Test Critic" in system
    assert "Test Study" in system


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
