# Design notes

## Storage

One SQLite file (`notes.db` by default). Tables:

- `notes`: one row per note. `content_hash` is a SHA-256 of study, title and body, with a UNIQUE constraint, so importing the same file twice adds nothing.
- `tags` and `note_tags`: the controlled vocabulary and the tags on each note. `note_tags.tag` is a foreign key to `tags`, so a tag that is not in the taxonomy cannot be stored.
- `notes_fts`: an FTS5 virtual table (SQLite full-text search) holding title and body. Ranking uses `bm25()` with the title weighted 5 and the body weighted 1.
- `drafts`: a draft summary and its claims as JSON. `status` is `pending`, `approved` or `rejected`.
- `summaries`: written only by `approve_draft()`. Each row points to its draft, so there is one summary per draft.

## Tagging

`taxonomy.json` maps each tag to a list of keywords. A keyword matches at the start of a word, so "frustrat" matches "frustrated" but "cost" does not match "coast". A note gets the tags its author wrote (if they are on the list) plus the tags whose keywords appear in its title or body.

## Drafting and the unsupported flag

A drafter returns a list of `Claim` objects, each with text and a list of note ids. `check_claim()` returns a copy with `flags` set:

1. no note id: "no source note is cited"
2. a note id that was not in the set given to the drafter: flagged
3. fewer than 60% of the claim's content words appear in the cited notes: "not supported"

The check is deterministic and does not call a model, so the same input always gets the same flags. Tests use a fake drafter that returns invented claims.

The Ollama drafter sends one request to `/api/generate` with `stream: false` and `format: json`. The reply is parsed by `parse_claims()`. Invalid JSON becomes a single claim with no source, which is then flagged.

## Approval

`approve_draft()` refuses a draft with flagged claims unless the caller passes `drop_flagged=True` (save supported claims only) or `keep_flagged=True` (save everything, and the study page marks the flagged ones). A draft can only be approved or rejected once.

## Importing

- Markdown: optional `key: value` block at the top, first `# heading` as the title, folder name as the study.
- CSV and Excel: a header row, with `title` and `body` required. Rows that miss either are reported and skipped. Excel dates are converted to ISO text.
- A file that cannot be read is reported and the rest of the import continues.

## Not done yet

- No editing of notes after import. To change a note, edit the file and import into a new database.
- No way to delete a note.
- The study page is static HTML generated on demand. There is no server.
