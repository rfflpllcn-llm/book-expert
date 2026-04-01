# tests/test_save_qa.py
from lib.save_qa import save


def test_save_basic(book_dir):
    save(book_dir, "Test question?", "Test summary.", "SC_00001", "Full answer text.")
    cache = (book_dir / "knowledge" / "tier_1" / "08_qa_cache.md").read_text()
    assert "## Q: Test question?" in cache
    assert "Test summary." in cache
    assert "SC_00001" in cache


def test_save_creates_answer_file(book_dir):
    save(book_dir, "Q?", "S.", "SC_00001", "Full answer.")
    answers = list((book_dir / "knowledge" / "answers").glob("*.md"))
    assert len(answers) == 1
    assert "Full answer." in answers[0].read_text()


def test_save_without_full_answer(book_dir):
    save(book_dir, "Q?", "S.", "SC_00001")
    cache = (book_dir / "knowledge" / "tier_1" / "08_qa_cache.md").read_text()
    assert "## Q: Q?" in cache
    # No answer file created
    answers = list((book_dir / "knowledge" / "answers").glob("*.md"))
    assert len(answers) == 0
    # No "Risposta completa" link
    assert "Risposta completa" not in cache
