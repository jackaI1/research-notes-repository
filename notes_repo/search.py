"""Full-text search with ranking, optionally filtered by tag or study."""
from __future__ import annotations

import re

# Title matches count five times as much as body matches.
TITLE_WEIGHT = 5.0
BODY_WEIGHT = 1.0


def fts_query(text: str) -> str:
    """Quote each word so punctuation in the search box cannot break the query."""
    words = re.findall(r"\w+", text)
    return " ".join('"' + w.replace('"', '""') + '"' for w in words)


def search(conn, text: str, *, tag: str | None = None, study: str | None = None, limit: int = 10) -> list[dict]:
    match = fts_query(text)
    if not match:
        return []
    sql = """
        SELECT n.id, n.study, n.title, n.body, n.note_date, n.source_file,
               snippet(notes_fts, 1, '[', ']', '...', 12) AS snippet,
               bm25(notes_fts, ?, ?) AS score
        FROM notes_fts
        JOIN notes n ON n.id = notes_fts.rowid
        WHERE notes_fts MATCH ?
    """
    params: list = [TITLE_WEIGHT, BODY_WEIGHT, match]
    if tag:
        sql += " AND n.id IN (SELECT note_id FROM note_tags WHERE tag = ?)"
        params.append(tag)
    if study:
        sql += " AND n.study = ?"
        params.append(study)
    # bm25 scores are lower for better matches, so ascending order puts the best first.
    sql += " ORDER BY score ASC, n.id ASC LIMIT ?"
    params.append(limit)
    return [dict(row) for row in conn.execute(sql, params)]
