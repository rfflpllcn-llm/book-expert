import pytest
from pathlib import Path


@pytest.fixture
def book_dir(tmp_path):
    """Create a minimal repo structure with a test book."""
    # Global preferences at repo root (tmp_path is the "repo root")
    (tmp_path / "preferences.yaml").write_text(
        "language: italiano\n"
        "tone: academic_formal\n"
        "citation_density: always\n"
        "interpretation_stance: null\n"
        "answer_length: detailed\n"
    )

    # Book directory: tmp_path/books/test_book/
    bd = tmp_path / "books" / "test_book"
    bd.mkdir(parents=True)

    # book.yaml
    (bd / "book.yaml").write_text(
        "title: Test Book\n"
        "author: Test Author\n"
        "year: 2000\n"
        "language: fr\n"
        "\n"
        "source_text:\n"
        "  file: data/test.csv\n"
        "  format: csv\n"
        "  line_prefix: FR\n"
        "  line_column: line_id\n"
        "  text_column: text\n"
        "  filter_column: chunk_type\n"
        "  filter_value: main_text\n"
        "\n"
        "arcs:\n"
        "  02_01_test_arc:\n"
        "    keywords: [test, beginning, hero]\n"
        "    lines: [1, 3]\n"
        "  02_02_test_arc_two:\n"
        "    keywords: [second, ending]\n"
        "    lines: [4, 5]\n"
        "\n"
        "characters:\n"
        "  hero:\n"
        "    arcs: [02_01_test_arc, 02_02_test_arc_two]\n"
        "  sidekick:\n"
        "    arcs: [02_02_test_arc_two]\n"
    )

    # Per-book preferences override
    (bd / "preferences.yaml").write_text("citation_density: heavy_with_commentary\n")

    # data/test.csv
    data_dir = bd / "data"
    data_dir.mkdir()
    (data_dir / "test.csv").write_text(
        "chunk_id,edition_id,line_id,page,line_no,box,text,text_hash,chunk_type\n"
        "1,1,FR1,1,1,1,First line of the test book.,hash1,main_text\n"
        "2,1,FR2,1,2,1,Second line continues here.,hash2,main_text\n"
        "3,1,FR3,1,3,1,Third line wraps up.,hash3,main_text\n"
        "4,1,FR4,2,1,1,Fourth line starts section two.,hash4,main_text\n"
        "5,1,FR5,2,2,1,Fifth and final line.,hash5,main_text\n"
        "6,1,FR6,2,3,1,A header line.,hash6,page_header\n"
    )

    # knowledge/tier_1
    t1 = bd / "knowledge" / "tier_1"
    t1.mkdir(parents=True)
    (t1 / "00_index.md").write_text("# Index\nTest book index.\n")
    (t1 / "08_qa_cache.md").write_text("# Q&A Cache\n\n---\n")

    # knowledge/tier_2
    t2 = bd / "knowledge" / "tier_2"
    t2.mkdir()
    (t2 / "02_01_test_arc.md").write_text("# Arc 1\nTest arc content.\n")
    (t2 / "02_02_test_arc_two.md").write_text("# Arc 2\nSecond arc content.\n")

    # knowledge/tier_3
    t3 = bd / "knowledge" / "tier_3"
    t3.mkdir()
    (t3 / "_index.md").write_text(
        "# Commentaries — Index\n\n"
        "## test_commentary\n"
        "- **Author**: Test Critic\n"
        "- **Work**: Test Study (2000)\n"
        "- **Covers**: style, themes\n"
        "- **Arcs**: 02_01_test_arc\n"
        "- **Themes**: test theme, darkness\n"
        "- **Stance**: structuralist\n"
    )
    (t3 / "test_commentary.md").write_text("# Test Commentary\n\nSome critical analysis.\n")

    # knowledge/answers
    (bd / "knowledge" / "answers").mkdir()

    return bd
