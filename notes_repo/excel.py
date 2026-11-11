"""Excel tracking export: one sheet of notes and one sheet of per-study progress."""
from __future__ import annotations

import json
from pathlib import Path

from .db import tags_for_note


def export_workbook(conn, path: str | Path) -> Path:
    from openpyxl import Workbook  # optional dependency, only needed for Excel

    wb = Workbook()
    notes_sheet = wb.active
    notes_sheet.title = "Notes"
    notes_sheet.append(["id", "study", "title", "date", "tags", "source file"])
    notes = conn.execute("SELECT id, study, title, note_date, source_file FROM notes ORDER BY study, note_date, id")
    for row in notes:
        notes_sheet.append([
            row["id"], row["study"], row["title"], row["note_date"] or "",
            ", ".join(tags_for_note(conn, row["id"])), row["source_file"],
        ])

    tracking = wb.create_sheet("Tracking")
    tracking.append(["study", "notes", "pending drafts", "approved summaries", "flagged claims in pending drafts"])
    studies = [r["study"] for r in conn.execute("SELECT DISTINCT study FROM notes ORDER BY study")]
    for study in studies:
        pending = conn.execute(
            "SELECT claims_json FROM drafts WHERE study = ? AND status = 'pending'", (study,)
        ).fetchall()
        flagged = sum(1 for r in pending for c in json.loads(r["claims_json"]) if c["flags"])
        tracking.append([
            study,
            conn.execute("SELECT COUNT(*) FROM notes WHERE study = ?", (study,)).fetchone()[0],
            len(pending),
            conn.execute("SELECT COUNT(*) FROM summaries WHERE study = ?", (study,)).fetchone()[0],
            flagged,
        ])

    target = Path(path)
    wb.save(target)
    return target
