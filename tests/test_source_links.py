from notes_repo.index_page import render_study_index, write_study_index
from notes_repo.review import approve_draft, approved_summaries
from notes_repo.summarize import ExtractiveDrafter, draft_summary

STUDY = "graphene-coating-study"


def note_ids_in_study(conn, study):
    return {r["id"] for r in conn.execute("SELECT id FROM notes WHERE study = ?", (study,))}


def test_every_drafted_claim_cites_a_note_in_the_study(seeded):
    draft_id = draft_summary(seeded, STUDY, ExtractiveDrafter())
    row = seeded.execute("SELECT claims_json FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    import json

    claims = json.loads(row["claims_json"])
    assert claims
    allowed = note_ids_in_study(seeded, STUDY)
    for claim in claims:
        assert claim["note_ids"], claim
        assert set(claim["note_ids"]) <= allowed
        assert claim["flags"] == []


def test_nothing_is_saved_until_a_person_approves(seeded):
    draft_summary(seeded, STUDY, ExtractiveDrafter())
    assert seeded.execute("SELECT COUNT(*) FROM summaries").fetchone()[0] == 0
    assert approved_summaries(seeded, STUDY) == []

    approve_draft(seeded, 1)
    assert seeded.execute("SELECT COUNT(*) FROM summaries").fetchone()[0] == 1
    assert seeded.execute("SELECT status FROM drafts WHERE id = 1").fetchone()["status"] == "approved"


def test_approved_summary_keeps_its_source_links(seeded):
    draft_id = draft_summary(seeded, STUDY, ExtractiveDrafter())
    approve_draft(seeded, draft_id)
    summaries = approved_summaries(seeded, STUDY)
    assert len(summaries) == 1
    for claim in summaries[0]["claims"]:
        assert claim.note_ids


def test_study_index_links_each_claim_to_its_note(seeded, tmp_path):
    draft_id = draft_summary(seeded, STUDY, ExtractiveDrafter())
    approve_draft(seeded, draft_id)
    page = render_study_index(seeded, STUDY)

    for claim in approved_summaries(seeded, STUDY)[0]["claims"]:
        for note_id in claim.note_ids:
            assert f'href="#note-{note_id}"' in page
            assert f'id="note-{note_id}"' in page


def test_index_page_is_written_per_study(seeded, tmp_path):
    path = write_study_index(seeded, STUDY, tmp_path)
    assert path == tmp_path / STUDY / "index.html"
    text = path.read_text(encoding="utf-8")
    assert "No approved summaries yet." in text
    assert "Sensor cable repaired" in text


def test_index_page_escapes_note_text(conn, tmp_path):
    from notes_repo import db

    db.add_note(conn, study="s", title="<script>alert(1)</script>", body="a & b",
                note_date=None, source_file="x.md", tags=[])
    page = render_study_index(conn, "s")
    assert "<script>alert" not in page
    assert "&lt;script&gt;" in page
