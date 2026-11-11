import pytest

from notes_repo import db
from notes_repo.taxonomy import Taxonomy


def tag_names(conn, title):
    row = conn.execute("SELECT id FROM notes WHERE title = ?", (title,)).fetchone()
    return db.tags_for_note(conn, row["id"])


def test_keyword_in_text_adds_tag(taxonomy):
    accepted, unknown = taxonomy.resolve([], "The sensor drifted during the calibration check.")
    assert accepted == {"measurement"}
    assert unknown == []


def test_keyword_must_start_a_word(taxonomy):
    # "cost" should not match inside "bookcase" or "coast"
    accepted, _ = taxonomy.resolve([], "The bookcase sits on the coast.")
    assert "cost" not in accepted


def test_explicit_tags_are_normalised(taxonomy):
    accepted, unknown = taxonomy.resolve(["  Cost ", "", "Safety"], "nothing relevant here")
    assert accepted == {"cost", "safety"}
    assert unknown == []


def test_unknown_explicit_tag_is_reported_not_stored(taxonomy):
    accepted, unknown = taxonomy.resolve(["made-up-tag"], "plain text")
    assert "made-up-tag" not in accepted
    assert unknown == ["made-up-tag"]


def test_taxonomy_rejects_bad_tag_names():
    with pytest.raises(ValueError):
        Taxonomy({"Not Valid": ["x"]})


def test_only_taxonomy_tags_reach_the_database(seeded):
    allowed = {r["name"] for r in seeded.execute("SELECT name FROM tags")}
    used = {r["tag"] for r in seeded.execute("SELECT DISTINCT tag FROM note_tags")}
    assert used <= allowed
    assert len(used) >= 5


def test_markdown_front_matter_tags_are_stored(seeded):
    tags = tag_names(seeded, "Technician A: logging particle counts")
    assert {"interview", "pain-point"} <= set(tags)


def test_csv_tags_column_is_stored(seeded):
    assert "measurement" in tag_names(seeded, "Sensor cable repaired")
    assert "safety" in tag_names(seeded, "Fume cabinet check")


def test_text_keywords_tag_notes_without_front_matter(seeded):
    # The technician B note has no 'cost' tag written, but its text mentions a supplier quote.
    assert "supplier" in tag_names(seeded, "Technician B: gowning and safety")
