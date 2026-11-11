# research-notes-repository
Project by Jack Lai

I built a small research notes repository that imports my interview and lab notes, tags them, lets me search them, and drafts a summary where every sentence points back to the note it came from, because my notes were in different formats (Markdown files, CSV exports, a spreadsheet), and when I tried to write a summary I could not easily tell which statement came from which note. The tool never saves a summary on its own. It drafts one, marks anything it cannot back up, and waits for me to approve it.

## What it does, in plain words

- **Imports notes** from a folder of Markdown files, CSV files or an Excel file. Each note keeps the name of the file (and row number, for spreadsheets) it came from, so I can always go back to the original.
- **Tags notes** using a fixed list of tags in `taxonomy.json`. A tag is added when the note's text uses one of its keywords (for example "cleanroom" or "particle" adds `cleanroom`), or when I write it in the note. Tags that are not on the list are rejected and shown as a warning, so the tag list does not slowly turn into a mess.
- **Searches notes** and shows the best matches first. A word in a note's title counts more than a word in its body.
- **Writes a study page** for each study: the approved summaries, with a link from each sentence to its note, and every note with its tags and source file.
- **Drafts a summary for review.** The drafter reads the notes and proposes sentences. Each sentence must name the note numbers it came from. The tool checks each one. If a sentence names no note, names a note that was not given to the drafter, or uses words that mostly do not appear in the notes it cites, it is marked **unsupported**. The tool does not fix these for me.
- **Waits for my approval.** A draft stays pending until I approve it. If there are unsupported sentences, I have to choose: drop them, or keep them with a visible warning. Rejected drafts are kept in the database but never shown as summaries.
- **Exports to Excel.** One sheet lists every note with its tags and source. A second sheet tracks each study: how many notes, how many drafts are waiting, how many summaries are approved, and how many flagged sentences are still in drafts.

## How I use it

Install the two small libraries (`openpyxl` reads and writes Excel files, `pytest` runs the tests):

```
pip install -r requirements.txt
```

Import the example notes that come with the repository. They are made up for this demo:

```
python -m notes_repo import seed/notes
```

Search them:

```
python -m notes_repo search "gowning"
python -m notes_repo search "cost" --tag cost
```

Draft a summary of one study. It is saved as pending, not as a summary:

```
python -m notes_repo draft graphene-coating-study --query thickness
python -m notes_repo show 1
```

Approve it. If the draft has flagged sentences, the tool refuses until I pick one of the two options:

```
python -m notes_repo approve 1 --drop-flagged
python -m notes_repo approve 1 --keep-flagged
python -m notes_repo reject 1
```

Make the study page and the Excel tracking file:

```
python -m notes_repo index graphene-coating-study --out site
python -m notes_repo export-xlsx tracking.xlsx
```

Open `site/graphene-coating-study/index.html` in a browser to see the page. Run `python -m notes_repo --help` for the full list.

Every command takes `--db` to choose the database file. The default is `notes.db` in the folder I run it from.

## Writing a note

A note is a Markdown file (`.md`) or a row in a CSV or Excel file.

For a Markdown note, the first `# heading` is the title. A block at the top, between two lines of `---`, can hold optional fields:

```
---
date: 2026-10-02
study: graphene-coating-study
tags: coating, measurement
---
# Deposition run notes, week 1

The text of the note goes here.
```

If `study` is not written, the folder name is used. A CSV or Excel file needs `title` and `body` columns. `study`, `date` and `tags` are optional. Tags are separated by commas.

## The drafting step, in more detail

There are two ways to draft:

1. **`extractive` (the default).** This does not use a language model. It copies up to two sentences from each note and cites that note. It cannot invent anything, but it reads like a list of quotes. It works offline with nothing to download.
2. **`ollama`.** This sends the notes to a language model running on my own computer through [Ollama](https://ollama.com), which serves models at `http://localhost:11434`. The model is not in this repository. I install one myself, for example `ollama pull llama3.1`, then run `python -m notes_repo draft <study> --drafter ollama --model llama3.1`. The model is asked to return JSON with a list of claims and the note numbers for each claim. Anything it returns is checked by the same rules as the offline drafter. If the reply is not valid JSON, the whole reply becomes one claim with no source, which is flagged.

Whichever drafter is used, the check runs on every claim. The check looks at the note numbers, and it compares the words in the claim with the words in the cited notes. A claim needs at least 60% of its content words (words with four or more letters, not common words like "about" or "there") to appear in the cited notes. That number is in `notes_repo/summarize.py` as `SUPPORT_THRESHOLD`.

## What is in the repository

- `notes_repo/` the Python package
  - `cli.py` the commands
  - `importers.py` reads Markdown, CSV and Excel files
  - `taxonomy.py` the controlled tag list and tag matching
  - `db.py` the SQLite database layout
  - `search.py` full-text search with ranking
  - `summarize.py` the drafters and the claim check
  - `review.py` approving, rejecting and listing drafts
  - `index_page.py` the study page
  - `excel.py` the Excel tracking export
- `taxonomy.json` the tag list, with the keywords for each tag
- `seed/notes/` made-up notes for two studies (every one is marked `synthetic: true`)
- `tests/` the tests
- `docs/design.md` the design notes, for anyone who wants more detail

## Tests and CI

Run the tests with `python -m pytest -v`. Locally, 48 tests pass on Python 3.9. They cover:

- tagging: keywords, explicit tags, unknown tags, and the check that only listed tags are stored
- search ranking: a title match ranks above a body match, tag and study filters, and punctuation in a search
- source links: every drafted claim cites a note in its study, nothing is saved before approval, and the study page links each claim to its note
- the unsupported flag: an invented claim is flagged, a claim with no source is flagged, approval is refused until I choose, and "drop" and "keep" do what they say
- importers and Excel: duplicate notes are skipped on a second import, bad rows are reported and not stored, and the Excel export counts match the database

GitHub Actions runs the same tests on Python 3.9 and 3.12 for every push and pull request, then runs the command line on the seed notes from start to finish.

## Limitations

- The offline drafter is not a language model. Its summaries are quotes from the notes, joined up by the study page. It is a safe default, not a good writer.
- The Ollama path is tested with a fake model reply, not with a real model. I have not run a real model on this project yet.
- The seed notes are invented. The tag list and keywords are my first guess and will need tuning on real notes.
- Search uses SQLite's built-in full-text index, so it does not understand synonyms.
