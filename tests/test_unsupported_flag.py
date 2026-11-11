import pytest

from notes_repo.review import ReviewError, approve_draft, get_draft
from notes_repo.summarize import Claim, OllamaDrafter, check_claim, draft_summary, parse_claims

STUDY = "graphene-coating-study"


def sample_notes():
    return {
        1: {"id": 1, "title": "Holder swap trial",
            "body": "A new substrate holder was tried. Thickness variation between runs dropped."},
        2: {"id": 2, "title": "Supplier call",
            "body": "The supplier quoted a lower price per cylinder if the order is placed early."},
    }


def holder_id(conn):
    """Database id of the 'Holder swap trial' note (ids depend on import order, so look it up)."""
    return conn.execute("SELECT id FROM notes WHERE title = 'Holder swap trial'").fetchone()["id"]


class FakeDrafter:
    """Returns exactly the claims it is given, so tests control what the drafter invents."""

    name = "fake"

    def __init__(self, claims):
        self._claims = claims

    def draft(self, notes):
        return list(self._claims)


def test_supported_claim_is_not_flagged():
    claim = check_claim(Claim("Thickness variation between runs dropped.", [1]), sample_notes())
    assert claim.flags == []
    assert not claim.unsupported


def test_invented_claim_is_flagged_as_unsupported():
    claim = check_claim(Claim("Every participant preferred the cheaper coating chemistry.", [1]), sample_notes())
    assert claim.unsupported
    assert any(f.startswith("not supported") for f in claim.flags)


def test_claim_without_a_source_is_flagged():
    claim = check_claim(Claim("The holder was replaced.", []), sample_notes())
    assert "no source note is cited" in claim.flags


def test_claim_citing_a_note_outside_the_set_is_flagged():
    claim = check_claim(Claim("The holder was replaced.", [99]), sample_notes())
    assert any("not given to the drafter" in f for f in claim.flags)


def test_check_does_not_change_the_original_claim():
    original = Claim("Every participant preferred the cheaper coating chemistry.", [1])
    check_claim(original, sample_notes())
    assert original.flags == []


def test_draft_with_flags_is_saved_as_pending_and_flags_are_stored(seeded):
    drafter = FakeDrafter([
        Claim("Thickness variation between runs dropped.", [holder_id(seeded)]),
        Claim("Every participant preferred the cheaper coating chemistry.", [holder_id(seeded)]),
        Claim("The supplier agreed to a discount for all future orders.", []),
    ])
    draft_id = draft_summary(seeded, STUDY, drafter)
    draft = get_draft(seeded, draft_id)
    assert draft["status"] == "pending"
    assert [c.unsupported for c in draft["claims"]] == [False, True, True]


def test_approval_is_refused_while_claims_are_flagged(seeded):
    drafter = FakeDrafter([Claim("Every participant preferred the cheaper coating chemistry.", [holder_id(seeded)])])
    draft_id = draft_summary(seeded, STUDY, drafter)
    with pytest.raises(ReviewError, match="flagged"):
        approve_draft(seeded, draft_id)
    assert seeded.execute("SELECT COUNT(*) FROM summaries").fetchone()[0] == 0


def test_drop_flagged_saves_only_supported_claims(seeded):
    drafter = FakeDrafter([
        Claim("Thickness variation between runs dropped.", [holder_id(seeded)]),
        Claim("Every participant preferred the cheaper coating chemistry.", [holder_id(seeded)]),
    ])
    draft_id = draft_summary(seeded, STUDY, drafter)
    approve_draft(seeded, draft_id, drop_flagged=True)
    saved = seeded.execute("SELECT claims_json FROM summaries").fetchone()["claims_json"]
    assert "Thickness variation" in saved
    assert "preferred the cheaper" not in saved


def test_keep_flagged_saves_flags_visibly(seeded, tmp_path):
    from notes_repo.index_page import render_study_index

    drafter = FakeDrafter([Claim("Every participant preferred the cheaper coating chemistry.", [holder_id(seeded)])])
    draft_id = draft_summary(seeded, STUDY, drafter)
    approve_draft(seeded, draft_id, keep_flagged=True)
    page = render_study_index(seeded, STUDY)
    assert "kept by reviewer" in page
    assert "not supported" in page


def test_cannot_choose_both_flag_options(seeded):
    draft_id = draft_summary(seeded, STUDY, FakeDrafter([Claim("Thickness variation between runs dropped.", [holder_id(seeded)])]))
    with pytest.raises(ReviewError):
        approve_draft(seeded, draft_id, drop_flagged=True, keep_flagged=True)


def test_drop_flagged_with_nothing_left_is_refused(seeded):
    draft_id = draft_summary(seeded, STUDY, FakeDrafter([Claim("Every participant preferred it.", [])]))
    with pytest.raises(ReviewError, match="nothing left"):
        approve_draft(seeded, draft_id, drop_flagged=True)


def test_approved_draft_cannot_be_approved_twice(seeded):
    draft_id = draft_summary(seeded, STUDY, FakeDrafter([Claim("Thickness variation between runs dropped.", [holder_id(seeded)])]))
    approve_draft(seeded, draft_id)
    with pytest.raises(ReviewError, match="already approved"):
        approve_draft(seeded, draft_id)


def test_model_reply_that_is_not_json_becomes_an_unsourced_flagged_claim():
    claims = parse_claims("Sure! Here is a summary of everything.")
    assert len(claims) == 1
    assert claims[0].note_ids == []
    claim = check_claim(claims[0], sample_notes())
    assert "no source note is cited" in claim.flags


def test_ollama_reply_is_parsed_into_claims_with_sources():
    reply = '{"response": "{\\"claims\\": [{\\"text\\": \\"Thickness variation dropped.\\", \\"sources\\": [1]}]}"}'
    sent = {}

    def fake_post(payload):
        sent.update(payload)
        import json

        return json.loads(reply)

    drafter = OllamaDrafter("test-model", post=fake_post)
    claims = drafter.draft([{"id": 1, "title": "t", "body": "Thickness variation dropped."}])
    assert sent["model"] == "test-model" and sent["format"] == "json"
    assert claims == [Claim("Thickness variation dropped.", [1])]
    assert "[note 1]" in sent["prompt"]
