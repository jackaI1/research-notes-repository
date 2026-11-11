"""Read notes from Markdown, CSV and Excel files, then store them with tags."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from . import db
from .taxonomy import Taxonomy

MARKDOWN = {".md", ".markdown"}
SPREADSHEET = {".csv", ".xlsx"}


@dataclass
class RawNote:
    title: str
    body: str
    study: str
    source_file: str
    note_date: str | None = None
    tags: list[str] = field(default_factory=list)


@dataclass
class ImportReport:
    added: int = 0
    duplicates: int = 0
    errors: list[str] = field(default_factory=list)
    unknown_tags: list[str] = field(default_factory=list)


def parse_front_matter(text: str) -> tuple[dict, str]:
    """Split a leading '---' block of 'key: value' lines from the rest of the file."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text
    meta = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip().lower()] = value.strip().strip("\"'")
    return meta, text[end + 4:].lstrip("\n")


def default_study(path: Path, base: Path) -> str:
    """A file's study is its folder name, or the imported folder's name for loose files."""
    return path.parent.name if path.parent != base else base.name


def parse_markdown(path: Path, base: Path) -> RawNote:
    meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
    title = meta.get("title", "")
    if not title:
        lines = body.splitlines()
        for i, line in enumerate(lines):
            if line.startswith("# "):
                title = line[2:].strip()
                body = "\n".join(lines[:i] + lines[i + 1:])
                break
    study = meta.get("study") or default_study(path, base)
    tags = [t for t in meta.get("tags", "").split(",") if t.strip()]
    return RawNote(
        title=title or path.stem.replace("-", " "),
        body=body.strip(),
        study=study,
        source_file=path.relative_to(base).as_posix(),
        note_date=meta.get("date") or None,
        tags=tags,
    )


def _row_to_note(row: dict, default_study: str, source: str) -> RawNote | str:
    """Turn one spreadsheet row into a note, or return a message saying why it failed."""
    clean = {str(k).strip().lower(): ("" if v is None else str(v).strip()) for k, v in row.items() if k}
    title, body = clean.get("title", ""), clean.get("body", "")
    if not title or not body:
        return f"{source}: needs both 'title' and 'body'"
    return RawNote(
        title=title,
        body=body,
        study=clean.get("study") or default_study,
        source_file=source,
        note_date=clean.get("date") or None,
        tags=[t for t in clean.get("tags", "").split(",") if t.strip()],
    )


def parse_csv(path: Path, base: Path) -> tuple[list[RawNote], list[str]]:
    rel = path.relative_to(base).as_posix()
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    notes, errors = [], []
    for number, row in enumerate(rows, start=2):  # row 1 is the header
        result = _row_to_note(row, default_study(path, base), f"{rel}:row{number}")
        (errors if isinstance(result, str) else notes).append(result)
    return notes, errors


def parse_xlsx(path: Path, base: Path) -> tuple[list[RawNote], list[str]]:
    """Read the first sheet of an Excel file. The first row must be the header."""
    from openpyxl import load_workbook  # optional dependency, only needed for Excel

    rel = path.relative_to(base).as_posix()
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook.worksheets[0]
        rows_iter = sheet.iter_rows(values_only=True)
        header = [str(h).strip() if h is not None else "" for h in next(rows_iter, [])]
        notes, errors = [], []
        for number, values in enumerate(rows_iter, start=2):
            row = {
                key: _cell_text(v)
                for key, v in zip(header, values)
            }
            if not any(v not in (None, "") for v in row.values()):
                continue  # skip blank rows
            result = _row_to_note(row, default_study(path, base), f"{rel}:row{number}")
            (errors if isinstance(result, str) else notes).append(result)
        return notes, errors
    finally:
        workbook.close()


def _cell_text(value):
    """Excel dates arrive as Python date objects; store them as ISO text."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _files_under(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(p for p in path.rglob("*") if p.is_file())


def import_path(conn, taxonomy: Taxonomy, path: str | Path) -> ImportReport:
    """Import every supported file under path (a file or a folder) into the database."""
    path = Path(path)
    base = path if path.is_dir() else path.parent
    report = ImportReport()
    db.sync_taxonomy(conn, taxonomy.names())

    for file in _files_under(path):
        suffix = file.suffix.lower()
        rel = file.relative_to(base).as_posix()
        try:
            if suffix in MARKDOWN:
                notes, errors = [parse_markdown(file, base)], []
            elif suffix == ".csv":
                notes, errors = parse_csv(file, base)
            elif suffix == ".xlsx":
                notes, errors = parse_xlsx(file, base)
            else:
                continue
        except Exception as exc:  # a broken file should not stop the whole import
            report.errors.append(f"{rel}: could not read ({exc.__class__.__name__}: {exc})")
            continue
        report.errors.extend(errors)

        for note in notes:
            if not note.title or not note.body:
                report.errors.append(f"{note.source_file}: empty title or body")
                continue
            tags, unknown = taxonomy.resolve(note.tags, f"{note.title}\n{note.body}")
            report.unknown_tags.extend(f"{note.source_file}: '{t}' is not in the taxonomy" for t in unknown)
            note_id = db.add_note(
                conn,
                study=note.study,
                title=note.title,
                body=note.body,
                note_date=note.note_date,
                source_file=note.source_file,
                tags=tags,
            )
            if note_id is None:
                report.duplicates += 1
            else:
                report.added += 1

    conn.commit()
    return report
