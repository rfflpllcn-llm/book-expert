# tests/test_loader.py
from lib.loader import load_book_config, route_query


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


def test_route_query_sc_ref(book_dir):
    config = load_book_config(book_dir)
    arcs = route_query("what is SC_00002?", config)
    assert "02_01_test_arc" in arcs


def test_route_query_no_match(book_dir):
    config = load_book_config(book_dir)
    arcs = route_query("completely unrelated query", config)
    assert arcs == []


def test_route_query_cap_at_four(book_dir):
    config = load_book_config(book_dir)
    arcs = route_query("test beginning second ending hero sidekick", config)
    assert len(arcs) <= 4
