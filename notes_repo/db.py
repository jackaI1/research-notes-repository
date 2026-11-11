"""SQLite storage for notes, tags, drafts and approved summaries."""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id           INTEGER PRIMARY KEY,
    study        TEXT NOT NULL,
    title        TEXT NOT NULL,
    body         TEXT NOT NULL,
    note_date    TEXT,
    source_file  TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS tags (
    name TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS note_tags (
    note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    tag     TEXT NOT NULL REFERENCES tags(name),
    PRIMARY KEY (note_id, tag)
);
CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(title, body);
CREATE TABLE IF NOT EXISTS drafts (
    id          INTEGER PRIMARY KEY,
    study       TEXT NOT NULL,
    query       TEXT,
    drafter     TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected')),
    created_at  TEXT NOT NULL,
    claims_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS summaries (
    id           INTEGER PRIMARY KEY,
    draft_id     INTEGER NOT NULL UNIQUE REFERENCES drafts(id),
    study        TEXT NOT NULL,
    approved_at  TEXT NOT NULL,
    claims_json  TEXT NOT NULL
);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def content_hash(study: str, title: str, body: str) -> str:
    return hashlib.sha256("\x1f".join([study, title, body]).encode("utf-8")).hexdigest()


def sync_taxonomy(conn: sqlite3.Connection, names) -> None:
    conn.executemany("INSERT OR IGNORE INTO tags (name) VALUES (?)", [(n,) for n in names])


def add_note(conn, *, study, title, body, note_date, source_file, tags) -> int | None:
    """Insert one note. Returns None when an identical note is already stored."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO notes (study, title, body, note_date, source_file, content_hash) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (study, title, body, note_date, source_file, content_hash(study, title, body)),
    )
    if cur.rowcount == 0:
        return None
    note_id = cur.lastrowid
    conn.execute("INSERT INTO notes_fts (rowid, title, body) VALUES (?, ?, ?)", (note_id, title, body))
    conn.executemany(
        "INSERT OR IGNORE INTO note_tags (note_id, tag) VALUES (?, ?)",
        [(note_id, t) for t in sorted(tags)],
    )
    return note_id


def tags_for_note(conn, note_id: int) -> list[str]:
    rows = conn.execute("SELECT tag FROM note_tags WHERE note_id = ? ORDER BY tag", (note_id,))
    return [r["tag"] for r in rows]
