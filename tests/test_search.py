from notes_repo import db
from notes_repo.search import fts_query, search


def test_title_match_ranks_above_body_match(conn):
    db.add_note(conn, study="s", title="Notes about pricing", body="We talked about the weather.",
                note_date=None, source_file="a.md", tags=[])
    db.add_note(conn, study="s", title="Weather report", body="The pricing was discussed briefly.",
                note_date=None, source_file="b.md", tags=[])
    hits = search(conn, "pricing")
    assert [h["title"] for h in hits] == ["Notes about pricing", "Weather report"]


def test_more_occurrences_rank_higher(conn):
    db.add_note(conn, study="s", title="One", body="coating once", note_date=None, source_file="a.md", tags=[])
    db.add_note(conn, study="s", title="Two", body="coating coating coating", note_date=None, source_file="b.md", tags=[])
    hits = search(conn, "coating")
    assert hits[0]["title"] == "Two"


def test_tag_filter_only_returns_tagged_notes(seeded):
    tagged_ids = {r["note_id"] for r in seeded.execute("SELECT note_id FROM note_tags WHERE tag = 'cost'")}
    hits = search(seeded, "cost", tag="cost")
    assert hits, "the seed notes mention cost in several notes"
    assert {h["id"] for h in hits} <= tagged_ids
    untagged = search(seeded, "cost")
    assert len(untagged) >= len(hits)


def test_study_filter_restricts_to_one_study(seeded):
    hits = search(seeded, "coating")
    assert {h["study"] for h in hits} == {"cleanroom-interviews", "graphene-coating-study"}
    only = search(seeded, "coating", study="graphene-coating-study")
    assert only and {h["study"] for h in only} == {"graphene-coating-study"}


def test_search_finds_seed_note_by_content(seeded):
    hits = search(seeded, "gowning")
    assert hits and hits[0]["title"] == "Technician B: gowning and safety"
    assert "[gowning]" in hits[0]["snippet"]


def test_punctuation_in_query_does_not_break_search(seeded):
    assert search(seeded, 'safety" OR (') is not None
    assert search(seeded, "   ") == []


def test_fts_query_quotes_words():
    assert fts_query('a "b" c-d') == '"a" "b" "c" "d"'
