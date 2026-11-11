"""Human review of drafts. Only an approved draft is written to the summaries table."""
from __future__ import annotations

import json
from dataclasses import asdict

from . import db
from .summarize import Claim


class ReviewError(Exception):
    pass


def get_draft(conn, draft_id: int) -> dict:
    row = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    if row is None:
        raise ReviewError(f"no draft with id {draft_id}")
    draft = dict(row)
    draft["claims"] = [Claim(**c) for c in json.loads(draft.pop("claims_json"))]
    return draft


def list_drafts(conn, status: str = "pending") -> list[dict]:
    rows = conn.execute(
        "SELECT id, study, query, drafter, status, created_at, claims_json FROM drafts "
        "WHERE status = ? ORDER BY id",
        (status,),
    ).fetchall()
    result = []
    for row in rows:
        claims = json.loads(row["claims_json"])
        result.append({
            "id": row["id"],
            "study": row["study"],
            "query": row["query"],
            "drafter": row["drafter"],
            "status": row["status"],
            "created_at": row["created_at"],
            "claims": len(claims),
            "flagged": sum(1 for c in claims if c["flags"]),
        })
    return result


def approve_draft(conn, draft_id: int, *, drop_flagged: bool = False, keep_flagged: bool = False) -> int:
    """Save a pending draft as an approved summary.

    A draft with flagged claims is refused unless the reviewer chooses what to do with them:
    drop_flagged saves only the supported claims, keep_flagged saves everything as it is.
    """
    if drop_flagged and keep_flagged:
        raise ReviewError("choose either drop_flagged or keep_flagged, not both")
    draft = get_draft(conn, draft_id)
    if draft["status"] != "pending":
        raise ReviewError(f"draft {draft_id} is already {draft['status']}")

    claims = draft["claims"]
    flagged = [c for c in claims if c.unsupported]
    if flagged and not (drop_flagged or keep_flagged):
        raise ReviewError(
            f"{len(flagged)} claim(s) are flagged as unsupported. Re-run with drop_flagged "
            "to save only the supported claims, or keep_flagged to save them as they are."
        )
    if drop_flagged:
        claims = [c for c in claims if not c.unsupported]
    if not claims:
        raise ReviewError("nothing left to save after dropping flagged claims; reject the draft instead")

    cur = conn.execute(
        "INSERT INTO summaries (draft_id, study, approved_at, claims_json) VALUES (?, ?, ?, ?)",
        (draft_id, draft["study"], db.now_iso(), json.dumps([asdict(c) for c in claims])),
    )
    conn.execute("UPDATE drafts SET status = 'approved' WHERE id = ?", (draft_id,))
    conn.commit()
    return cur.lastrowid


def reject_draft(conn, draft_id: int) -> None:
    draft = get_draft(conn, draft_id)
    if draft["status"] != "pending":
        raise ReviewError(f"draft {draft_id} is already {draft['status']}")
    conn.execute("UPDATE drafts SET status = 'rejected' WHERE id = ?", (draft_id,))
    conn.commit()


def approved_summaries(conn, study: str) -> list[dict]:
    rows = conn.execute(
        "SELECT id, draft_id, approved_at, claims_json FROM summaries WHERE study = ? ORDER BY id",
        (study,),
    ).fetchall()
    return [
        {
            "id": r["id"],
            "draft_id": r["draft_id"],
            "approved_at": r["approved_at"],
            "claims": [Claim(**c) for c in json.loads(r["claims_json"])],
        }
        for r in rows
    ]
