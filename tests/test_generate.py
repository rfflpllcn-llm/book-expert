# tests/test_generate.py
from lib.generate_claude_md import generate


def test_generate_contains_identity(book_dir):
    result = generate(book_dir)
    assert "Test Book" in result
    assert "Test Author" in result
    assert "2000" in result


def test_generate_contains_tools(book_dir):
    result = generate(book_dir)
    assert "python -m lib.cite" in result
    assert "python -m lib.save_qa" in result


def test_generate_contains_dynamic_routing(book_dir):
    result = generate(book_dir)
    assert "book.yaml" in result
    assert "tier_3/_index.md" in result


def test_generate_contains_preferences(book_dir):
    result = generate(book_dir)
    # Per-book override: heavy_with_commentary
    assert "commentary" in result.lower() or "commentar" in result.lower()


def test_generate_contains_workflow(book_dir):
    result = generate(book_dir)
    assert "cache" in result.lower()
    assert "tier_1" in result
    assert "tier_2" in result


def test_generate_null_stance_renders_correctly(book_dir):
    """YAML null should render as balanced-instructions text, not 'None'."""
    result = generate(book_dir)
    assert "None" not in result
    assert "balanced" in result.lower()


def test_generate_bilingual_tools(bilingual_book_dir):
    """When translations exist, CLAUDE.md should document the --lang flag."""
    result = generate(bilingual_book_dir)
    assert "--lang it" in result
    assert "translation" in result.lower() or "bilingual" in result.lower()


def test_generate_no_bilingual_without_translations(book_dir):
    """Books without translations should NOT mention --lang."""
    result = generate(book_dir)
    assert "--lang" not in result
