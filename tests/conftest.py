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

    # JSONL source variant (for bilingual book tests)
    (data_dir / "source.jsonl").write_text(
        '{"id": "1", "t": "First line of the test book."}\n'
        '{"id": "2", "t": "Second line continues here."}\n'
        '{"id": "3", "t": "Third line wraps up."}\n'
        '{"id": "4", "t": "Fourth line starts section two."}\n'
        '{"id": "5", "t": "Fifth and final line."}\n'
    )

    # Italian translation
    (data_dir / "translation-it.jsonl").write_text(
        '{"id": 1, "t": "Prima riga del libro di prova."}\n'
        '{"id": 2, "t": "La seconda riga continua qui."}\n'
        '{"id": 3, "t": "La terza riga conclude."}\n'
        '{"id": 4, "t": "La quarta riga inizia la sezione due."}\n'
        '{"id": 5, "t": "Quinta e ultima riga."}\n'
    )

    # Alignment file: FR1+FR2 -> IT1, FR3 -> IT2+IT3, FR4 -> IT4, FR5 -> IT5
    (data_dir / "alignment-fr-it.jsonl").write_text(
        '{"src_lines": ["1", "2"], "tgt_lines": [1], "type": "2-1"}\n'
        '{"src_lines": ["3"], "tgt_lines": [2, 3], "type": "1-2"}\n'
        '{"src_lines": ["4"], "tgt_lines": [4], "type": "1-1"}\n'
        '{"src_lines": ["5"], "tgt_lines": [5], "type": "1-1"}\n'
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
    import yaml as _yaml
    _yaml.safe_dump(
        {"essays": {
            "test_commentary": {
                "author": "Test Critic",
                "work": "Test Study",
                "year": 2000,
                "summary": "A structuralist analysis of style and themes in the test book.",
                "stance": "structuralist",
                "arcs": ["02_01_test_arc"],
                "themes": ["test theme", "darkness"],
                "characters": ["Céline"],
                "sections": [
                    {
                        "id": 1,
                        "title": "Chapter on Style",
                        "summary": "Analyzes core stylistic techniques.",
                        "start_id": "1",
                        "end_id": "100",
                        "arcs": ["02_01_test_arc"],
                    },
                ],
            },
        }},
        (t3 / "_index.yaml").open("w"),
        allow_unicode=True,
        sort_keys=False,
    )

    # knowledge/answers
    (bd / "knowledge" / "answers").mkdir()

    return bd


@pytest.fixture
def bilingual_book_dir(book_dir):
    """Extend book_dir with JSONL source + Italian translation + alignment."""
    # Rewrite book.yaml to use JSONL source and add translations
    (book_dir / "book.yaml").write_text(
        "title: Test Book\n"
        "author: Test Author\n"
        "year: 2000\n"
        "language: fr\n"
        "\n"
        "source_text:\n"
        "  file: data/source.jsonl\n"
        "  format: jsonl\n"
        "  line_prefix: FR\n"
        "  line_column: id\n"
        "  text_column: t\n"
        "\n"
        "translations:\n"
        "  it:\n"
        "    file: data/translation-it.jsonl\n"
        "    format: jsonl\n"
        "    line_prefix: IT\n"
        "    line_column: id\n"
        "    text_column: t\n"
        "    alignment: data/alignment-fr-it.jsonl\n"
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
    return book_dir
