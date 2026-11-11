"""Write a static HTML index for one study: its notes, tags and approved summaries."""
from __future__ import annotations

import html
import re
from pathlib import Path

from .db import tags_for_note
from .review import approved_summaries


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "study"


def _e(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def render_study_index(conn, study: str) -> str:
    notes = conn.execute(
        "SELECT id, title, body, note_date, source_file FROM notes WHERE study = ? ORDER BY note_date, id",
        (study,),
    ).fetchall()
    parts = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        f"<title>{_e(study)}</title>",
        "<style>body{font-family:system-ui,sans-serif;max-width:780px;margin:2em auto;line-height:1.5}"
        ".flag{color:#9a3412;font-weight:600}.tag{background:#eef;padding:0 .4em;border-radius:4px;margin-right:.3em}"
        "</style></head><body>",
        f"<h1>{_e(study)}</h1>",
        "<h2>Approved summaries</h2>",
    ]

    summaries = approved_summaries(conn, study)
    if not summaries:
        parts.append("<p>No approved summaries yet.</p>")
    for summary in summaries:
        parts.append(f"<section id=\"summary-{summary['id']}\"><ul>")
        for claim in summary["claims"]:
            links = " ".join(f'<a href="#note-{i}">[note {i}]</a>' for i in claim.note_ids) or "<span class=\"flag\">no source</span>"
            flag = f' <span class="flag">(unsupported, kept by reviewer: {_e("; ".join(claim.flags))})</span>' if claim.flags else ""
            parts.append(f"<li>{_e(claim.text)} {links}{flag}</li>")
        parts.append("</ul></section>")

    parts.append("<h2>Notes</h2>")
    for note in notes:
        tags = "".join(f'<span class="tag">{_e(t)}</span>' for t in tags_for_note(conn, note["id"]))
        parts.append(
            f'<section id="note-{note["id"]}"><h3>{_e(note["title"])}</h3>'
            f'<p>{_e(note["note_date"] or "no date")} · source: <code>{_e(note["source_file"])}</code> · {tags}</p>'
            f"<p>{_e(note['body'])}</p></section>"
        )
    parts.append("</body></html>")
    return "\n".join(parts)


def write_study_index(conn, study: str, out_dir: str | Path) -> Path:
    target_dir = Path(out_dir) / slugify(study)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "index.html"
    target.write_text(render_study_index(conn, study), encoding="utf-8")
    return target
