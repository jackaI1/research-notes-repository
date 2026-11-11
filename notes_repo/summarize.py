"""Draft a synthesis from notes, then check every claim against the notes it cites.

A drafter (a local Ollama model, or the offline extractive fallback) proposes claims.
Each claim must name the note numbers it came from. check_claim() flags any claim that
has no source, cites a note that is not in the set, or whose words mostly do not appear
in the cited notes. Flagged claims are kept for review, never silently fixed.
"""
from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import asdict, dataclass, field, replace

from . import db
from .search import search

# Share of a claim's content words that must appear in its cited notes.
SUPPORT_THRESHOLD = 0.6
STOPWORDS = {
    "about", "above", "after", "again", "against", "also", "because", "been", "before",
    "being", "between", "both", "could", "does", "done", "during", "each", "from", "have",
    "having", "into", "more", "most", "other", "over", "same", "should", "some", "such",
    "than", "that", "their", "them", "then", "there", "these", "they", "this", "those",
    "through", "under", "until", "very", "were", "what", "when", "where", "which", "while",
    "with", "would", "your", "will", "only", "just", "much", "many", "make", "made",
}


@dataclass
class Claim:
    text: str
    note_ids: list[int] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    @property
    def unsupported(self) -> bool:
        return bool(self.flags)


def content_words(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if len(w) >= 4 and w not in STOPWORDS}


def check_claim(claim: Claim, notes_by_id: dict[int, dict]) -> Claim:
    """Return a copy of the claim with flags for anything it cannot back up."""
    flags: list[str] = []
    if not claim.note_ids:
        flags.append("no source note is cited")
    missing = [i for i in claim.note_ids if i not in notes_by_id]
    if missing:
        flags.append(f"cites note(s) {missing} that were not given to the drafter")

    cited = [notes_by_id[i] for i in claim.note_ids if i in notes_by_id]
    cited_words: set[str] = set()
    for note in cited:
        cited_words |= content_words(f"{note['title']} {note['body']}")
    claim_words = content_words(claim.text)
    if claim_words and cited:
        overlap = len(claim_words & cited_words) / len(claim_words)
        if overlap < SUPPORT_THRESHOLD:
            flags.append(
                f"not supported: only {overlap:.0%} of its words appear in the cited notes"
            )
    return replace(claim, flags=flags)


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip() for p in parts if len(p.split()) >= 4]


class ExtractiveDrafter:
    """Offline fallback. Copies up to two sentences from each note and cites that note.

    It does not write new sentences, so it cannot invent facts. It is less readable than a
    language model, but it needs no model download.
    """

    name = "extractive"

    def draft(self, notes: list[dict]) -> list[Claim]:
        claims = []
        for note in notes:
            for sentence in split_sentences(note["body"])[:2]:
                claims.append(Claim(text=sentence, note_ids=[note["id"]]))
        return claims


def build_prompt(notes: list[dict]) -> str:
    listing = "\n".join(f"[note {n['id']}] {n['title']}: {n['body']}" for n in notes)
    return (
        "Write a short synthesis of the research notes below. Use only facts that are "
        "written in the notes. Do not add anything from outside knowledge.\n"
        'Reply with JSON only, in this form: {"claims": [{"text": "...", "sources": [note numbers]}]}\n'
        "Every claim must list the note numbers it comes from.\n\n" + listing
    )


def parse_claims(raw: str) -> list[Claim]:
    """Read the model's JSON reply. A reply that is not valid JSON becomes one unsourced claim."""
    try:
        items = json.loads(raw)["claims"]
        return [
            Claim(text=str(item["text"]).strip(), note_ids=[int(s) for s in item.get("sources", [])])
            for item in items
        ]
    except (ValueError, KeyError, TypeError):
        return [Claim(text=raw.strip() or "(empty reply from model)")]


class OllamaDrafter:
    """Sends the notes to a model served by Ollama on this machine (http://localhost:11434 by default).

    The model is not bundled. Pull one yourself, for example `ollama pull llama3.1`, and pass its name.
    """

    name = "ollama"

    def __init__(self, model: str, host: str = "http://localhost:11434", post=None, timeout: float = 300):
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout
        self._post = post or self._http_post

    def _http_post(self, payload: dict) -> dict:
        request = urllib.request.Request(
            f"{self.host}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def draft(self, notes: list[dict]) -> list[Claim]:
        reply = self._post({"model": self.model, "prompt": build_prompt(notes), "stream": False, "format": "json"})
        return parse_claims(reply.get("response", ""))


def study_notes(conn, study: str, query: str | None, limit: int) -> list[dict]:
    if query:
        return search(conn, query, study=study, limit=limit)
    rows = conn.execute(
        "SELECT id, study, title, body, note_date, source_file FROM notes "
        "WHERE study = ? ORDER BY note_date, id LIMIT ?",
        (study, limit),
    )
    return [dict(r) for r in rows]


def draft_summary(conn, study: str, drafter, query: str | None = None, limit: int = 8) -> int:
    """Create a pending draft. Nothing is written to summaries until a person approves it."""
    notes = study_notes(conn, study, query, limit)
    if not notes:
        raise ValueError(f"no notes found for study '{study}'" + (f" matching '{query}'" if query else ""))
    notes_by_id = {n["id"]: n for n in notes}
    claims = [check_claim(c, notes_by_id) for c in drafter.draft(notes)]
    cur = conn.execute(
        "INSERT INTO drafts (study, query, drafter, status, created_at, claims_json) VALUES (?, ?, ?, 'pending', ?, ?)",
        (study, query, drafter.name, db.now_iso(), json.dumps([asdict(c) for c in claims])),
    )
    conn.commit()
    return cur.lastrowid
