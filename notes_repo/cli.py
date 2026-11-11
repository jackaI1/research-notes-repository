"""Command line entry point. Run with: python -m notes_repo --help"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import db
from .excel import export_workbook
from .importers import import_path
from .index_page import write_study_index
from .review import ReviewError, approve_draft, get_draft, list_drafts, reject_draft
from .search import search
from .summarize import ExtractiveDrafter, OllamaDrafter, draft_summary
from .taxonomy import Taxonomy

DEFAULT_TAXONOMY = Path(__file__).resolve().parent.parent / "taxonomy.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="notes_repo", description="Import, tag, search and summarise research notes.")
    parser.add_argument("--db", default="notes.db", help="SQLite database file (default: notes.db)")
    parser.add_argument("--taxonomy", default=str(DEFAULT_TAXONOMY), help="tag list JSON file")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("import", help="import .md, .csv or .xlsx files from a file or folder")
    p.add_argument("path")

    p = sub.add_parser("search", help="full-text search, best matches first")
    p.add_argument("text")
    p.add_argument("--tag")
    p.add_argument("--study")
    p.add_argument("--limit", type=int, default=10)

    p = sub.add_parser("index", help="write an HTML index page for one study")
    p.add_argument("study")
    p.add_argument("--out", default="site")

    p = sub.add_parser("draft", help="draft a synthesis for review (nothing is saved yet)")
    p.add_argument("study")
    p.add_argument("--query", help="only use notes matching this search")
    p.add_argument("--limit", type=int, default=8)
    p.add_argument("--drafter", choices=["extractive", "ollama"], default="extractive")
    p.add_argument("--model", default=os.environ.get("NOTES_OLLAMA_MODEL"), help="Ollama model name")
    p.add_argument("--host", default=os.environ.get("OLLAMA_HOST", "http://localhost:11434"))

    p = sub.add_parser("review", help="list drafts waiting for review")
    p.add_argument("--status", default="pending", choices=["pending", "approved", "rejected"])

    p = sub.add_parser("show", help="show one draft with its claims and flags")
    p.add_argument("draft_id", type=int)

    p = sub.add_parser("approve", help="save a draft as an approved summary")
    p.add_argument("draft_id", type=int)
    group = p.add_mutually_exclusive_group()
    group.add_argument("--drop-flagged", action="store_true", help="save only the supported claims")
    group.add_argument("--keep-flagged", action="store_true", help="save all claims, flagged ones marked")

    p = sub.add_parser("reject", help="discard a draft")
    p.add_argument("draft_id", type=int)

    p = sub.add_parser("export-xlsx", help="write an Excel workbook of notes and tracking")
    p.add_argument("path")

    sub.add_parser("tags", help="list the controlled tags")
    return parser


def _print_hits(hits: list[dict]) -> None:
    if not hits:
        print("no matches")
    for hit in hits:
        print(f"[{hit['id']}] {hit['title']}  ({hit['study']}, {hit['note_date'] or 'no date'})")
        print(f"     {hit['snippet']}")
        print(f"     source: {hit['source_file']}")


def _print_draft(draft: dict) -> None:
    print(f"draft {draft['id']} for '{draft['study']}' ({draft['status']}, drafter: {draft['drafter']})")
    for i, claim in enumerate(draft["claims"], start=1):
        sources = ", ".join(f"note {n}" for n in claim.note_ids) or "none"
        print(f"  {i}. {claim.text}")
        print(f"     sources: {sources}")
        for flag in claim.flags:
            print(f"     FLAG: {flag}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    taxonomy = Taxonomy.load(args.taxonomy)

    if args.command == "tags":
        for name in taxonomy.names():
            print(name)
        return 0

    conn = db.connect(args.db)
    try:
        if args.command == "import":
            report = import_path(conn, taxonomy, args.path)
            print(f"added {report.added}, duplicates skipped {report.duplicates}")
            for line in report.unknown_tags + report.errors:
                print(f"  warning: {line}", file=sys.stderr)
        elif args.command == "search":
            _print_hits(search(conn, args.text, tag=args.tag, study=args.study, limit=args.limit))
        elif args.command == "index":
            print(write_study_index(conn, args.study, args.out))
        elif args.command == "draft":
            if args.drafter == "ollama":
                if not args.model:
                    print("error: --model is required for the ollama drafter", file=sys.stderr)
                    return 2
                drafter = OllamaDrafter(args.model, host=args.host)
            else:
                drafter = ExtractiveDrafter()
            draft_id = draft_summary(conn, args.study, drafter, query=args.query, limit=args.limit)
            _print_draft(get_draft(conn, draft_id))
            print(f"saved as pending draft {draft_id}; approve it with: approve {draft_id}")
        elif args.command == "review":
            for d in list_drafts(conn, args.status):
                print(f"[{d['id']}] {d['study']}: {d['claims']} claims, {d['flagged']} flagged ({d['created_at']})")
        elif args.command == "show":
            _print_draft(get_draft(conn, args.draft_id))
        elif args.command == "approve":
            summary_id = approve_draft(conn, args.draft_id, drop_flagged=args.drop_flagged, keep_flagged=args.keep_flagged)
            print(f"approved draft {args.draft_id} as summary {summary_id}")
        elif args.command == "reject":
            reject_draft(conn, args.draft_id)
            print(f"rejected draft {args.draft_id}")
        elif args.command == "export-xlsx":
            print(export_workbook(conn, args.path))
    except (ReviewError, ValueError, OSError) as exc:  # OSError: the Ollama server is not running
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    return 0
