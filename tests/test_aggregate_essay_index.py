# tests/test_aggregate_essay_index.py
import yaml
from pathlib import Path

from lib.aggregate_essay_index import aggregate


def test_aggregate_single_essay(tmp_path):
    """Single essay YAML produces valid _index.yaml."""
    bd = tmp_path / "book"
    bd.mkdir()
    edir = bd / "data" / "essays" / "test_essay"
    edir.mkdir(parents=True)
    (bd / "knowledge" / "tier_3").mkdir(parents=True)

    essay_yaml = {
        "essays": {
            "test_essay": {
                "author": "Test Author",
                "work": "Test Work",
                "year": 2000,
                "summary": "A test summary.",
                "stance": "stylistic",
                "arcs": ["02_01_test"],
                "themes": ["style"],
                "characters": ["Foo"],
                "sections": [
                    {"id": 1, "title": "Ch 1", "summary": "First chapter.", "start_id": "1", "end_id": "50", "arcs": ["02_01_test"]},
                ],
            }
        }
    }
    with open(edir / "test_essay.yaml", "w") as f:
        yaml.safe_dump(essay_yaml, f, allow_unicode=True, sort_keys=False)

    aggregate(bd)

    index_path = bd / "knowledge" / "tier_3" / "_index.yaml"
    assert index_path.exists()
    data = yaml.safe_load(index_path.read_text())
    assert "test_essay" in data["essays"]
    assert data["essays"]["test_essay"]["author"] == "Test Author"


def test_aggregate_multiple_essays(tmp_path):
    """Multiple essay YAMLs are merged into one _index.yaml."""
    bd = tmp_path / "book"
    bd.mkdir()
    (bd / "knowledge" / "tier_3").mkdir(parents=True)

    for slug in ["essay_a", "essay_b"]:
        edir = bd / "data" / "essays" / slug
        edir.mkdir(parents=True)
        essay_yaml = {"essays": {slug: {"author": f"Author {slug}", "work": f"Work {slug}", "year": 2000, "summary": "Summary.", "stance": "s", "arcs": [], "themes": [], "characters": [], "sections": []}}}
        with open(edir / f"{slug}.yaml", "w") as f:
            yaml.safe_dump(essay_yaml, f, allow_unicode=True, sort_keys=False)

    aggregate(bd)

    data = yaml.safe_load((bd / "knowledge" / "tier_3" / "_index.yaml").read_text())
    assert "essay_a" in data["essays"]
    assert "essay_b" in data["essays"]


def test_aggregate_no_essays(tmp_path):
    """No essay directories -> _index.yaml with empty essays dict."""
    bd = tmp_path / "book"
    (bd / "data" / "essays").mkdir(parents=True)
    (bd / "knowledge" / "tier_3").mkdir(parents=True)

    aggregate(bd)

    data = yaml.safe_load((bd / "knowledge" / "tier_3" / "_index.yaml").read_text())
    assert data["essays"] == {}


def test_aggregate_ignores_non_descriptor_yaml(tmp_path):
    """Only <dirname>.yaml is loaded; other YAML files are ignored."""
    bd = tmp_path / "book"
    bd.mkdir()
    edir = bd / "data" / "essays" / "test_essay"
    edir.mkdir(parents=True)
    (bd / "knowledge" / "tier_3").mkdir(parents=True)

    # Main descriptor
    essay_yaml = {"essays": {"test_essay": {"author": "Real Author", "work": "W", "year": 1, "summary": "S.", "stance": "s", "arcs": [], "themes": [], "characters": [], "sections": []}}}
    with open(edir / "test_essay.yaml", "w") as f:
        yaml.safe_dump(essay_yaml, f, allow_unicode=True, sort_keys=False)

    # Stray YAML that should NOT be ingested
    stray_yaml = {"essays": {"stray": {"author": "Stray Author", "work": "X", "year": 2, "summary": "Bad.", "stance": "x", "arcs": [], "themes": [], "characters": [], "sections": []}}}
    with open(edir / "config.yaml", "w") as f:
        yaml.safe_dump(stray_yaml, f, allow_unicode=True, sort_keys=False)

    aggregate(bd)

    data = yaml.safe_load((bd / "knowledge" / "tier_3" / "_index.yaml").read_text())
    assert "test_essay" in data["essays"]
    assert "stray" not in data["essays"]


def test_aggregate_idempotent(tmp_path):
    """Running twice produces same result."""
    bd = tmp_path / "book"
    bd.mkdir()
    (bd / "knowledge" / "tier_3").mkdir(parents=True)
    edir = bd / "data" / "essays" / "test_essay"
    edir.mkdir(parents=True)
    essay_yaml = {"essays": {"test_essay": {"author": "A", "work": "W", "year": 1, "summary": "S.", "stance": "s", "arcs": [], "themes": [], "characters": [], "sections": []}}}
    with open(edir / "test_essay.yaml", "w") as f:
        yaml.safe_dump(essay_yaml, f, allow_unicode=True, sort_keys=False)

    aggregate(bd)
    first = (bd / "knowledge" / "tier_3" / "_index.yaml").read_text()
    aggregate(bd)
    second = (bd / "knowledge" / "tier_3" / "_index.yaml").read_text()
    assert first == second
