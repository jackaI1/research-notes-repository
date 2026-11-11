from datetime import date
from pathlib import Path

import pytest

from notes_repo import db
from notes_repo.excel import export_workbook
from notes_repo.importers import import_path, parse_front_matter

SEED = Path(__file__).resolve().parent.parent / "seed" / "notes"

pytest.importorskip("openpyxl")


def test_seed_import_counts(conn, taxonomy):
    report = import_path(conn, taxonomy, SEED)
    assert report.added == 9  # 5 Markdown notes and 4 CSV rows
    assert report.errors == []


def test_reimport_skips_duplicates(conn, taxonomy):
    first = import_path(conn, taxonomy, SEED)
    second = import_path(conn, taxonomy, SEED)
    assert second.added == 0
    assert second.duplicates == first.added


def test_markdown_study_comes_from_folder_and_title_from_heading(seeded):
    row = seeded.execute("SELECT study, title, source_file FROM notes WHERE source_file LIKE '%supplier-call%'").fetchone()
    assert row["study"] == "graphene-coating-study"
    assert row["title"] == "Supplier call about precursor gas"
    assert row["source_file"] == "graphene-coating-study/2026-10-09-supplier-call.md"


def test_csv_rows_keep_their_row_number_as_source(seeded):
    row = seeded.execute("SELECT source_file FROM notes WHERE title = 'Holder swap trial'").fetchone()
    assert row["source_file"] == "graphene-coating-study/lab-log.csv:row4"


def test_front_matter_parser():
    meta, body = parse_front_matter('---\ndate: 2026-01-02\ntags: cost\n---\n# Title\nText')
    assert meta == {"date": "2026-01-02", "tags": "cost"}
    assert body.startswith("# Title")


def test_bad_rows_are_reported_not_stored(conn, taxonomy, tmp_path):
    folder = tmp_path / "study-x"
    folder.mkdir()
    (folder / "rows.csv").write_text("title,body\nGood one,Some real text here.\n,missing title\n", encoding="utf-8")
    report = import_path(conn, taxonomy, folder)
    assert report.added == 1
    assert any("needs both" in e for e in report.errors)


def test_unknown_tag_in_file_is_warned_about(conn, taxonomy, tmp_path):
    folder = tmp_path / "study-y"
    folder.mkdir()
    (folder / "note.md").write_text("---\ntags: nonsense-tag\n---\n# Hi\nSome body text.", encoding="utf-8")
    report = import_path(conn, taxonomy, folder)
    assert report.added == 1
    assert any("nonsense-tag" in w for w in report.unknown_tags)


def test_excel_intake_reads_first_sheet(conn, taxonomy, tmp_path):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["Title", "Study", "Date", "Body", "Tags"])
    ws.append(["Interview 9", "cleanroom-interviews", date(2026, 11, 1), "Technicians want a faster repeat run.", "interview"])
    ws.append([None, None, None, None, None])  # blank row is skipped
    ws.append(["Missing body", "cleanroom-interviews", None, None, None])
    path = tmp_path / "intake.xlsx"
    wb.save(path)

    report = import_path(conn, taxonomy, path)
    assert report.added == 1
    assert any("needs both" in e for e in report.errors)
    row = conn.execute("SELECT note_date FROM notes WHERE title = 'Interview 9'").fetchone()
    assert row["note_date"] == "2026-11-01"


def test_excel_tracking_export_counts(seeded, tmp_path):
    from openpyxl import load_workbook

    out = export_workbook(seeded, tmp_path / "tracking.xlsx")
    wb = load_workbook(out, read_only=True)
    notes_rows = list(wb["Notes"].iter_rows(values_only=True))
    assert notes_rows[0][:3] == ("id", "study", "title")
    assert len(notes_rows) - 1 == seeded.execute("SELECT COUNT(*) FROM notes").fetchone()[0]

    tracking = {r[0]: r for r in wb["Tracking"].iter_rows(min_row=2, values_only=True)}
    assert tracking["graphene-coating-study"][1] == 6  # 2 Markdown notes and 4 CSV rows
    assert tracking["cleanroom-interviews"][1] == 3
    wb.close()
