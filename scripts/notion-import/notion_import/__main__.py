"""Command line: python -m notion_import <command> ...

  inventory  list the databases and top-level pages the Notion token can see
  export     read chosen Notion databases/pages into a snapshot folder
  plan       dry run: show what an import of a snapshot would create (no writes)
  apply      create or update boards and cards in Notes from a snapshot
  run        export then apply (or, with --dry-run, export without files then plan)

Credentials are read from files or environment variables, never from the
command line: --token-file / NOTION_TOKEN and --api-key-file / NOTES_API_KEY.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .export import DEFAULT_MAX_FILE, Exporter, load_snapshot
from .inventory import Inventory, ds_title, page_title, norm
from .notion import Notion
from .plan import Planner
from . import report


def _secret(path, env):
    if path:
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()
    value = os.environ.get(env)
    if not value:
        sys.exit(f"missing credential: pass a file or set {env}")
    return value.strip()


def _roots(values):
    roots = []
    for v in values or []:
        kind, _, rid = v.partition(":")
        if kind not in ("ds", "db", "page") or not rid:
            sys.exit(f"--root must look like ds:<id>, db:<id> or page:<id> (got {v})")
        roots.append(({"ds": "data_source", "db": "database", "page": "page"}[kind], rid))
    return roots


def _exclude(args):
    ids = set(args.exclude or [])
    if getattr(args, "exclude_file", None):
        with open(args.exclude_file, encoding="utf-8") as fh:
            for line in fh:
                line = line.split("#")[0].strip()
                if line:
                    ids.add(line)
    return {norm(i) for i in ids}


def cmd_inventory(args):
    n = Notion(_secret(args.token_file, "NOTION_TOKEN"))
    print("reading the workspace (search)...", file=sys.stderr)
    inv = Inventory(list(n.search("data_source")), list(n.search("page")))
    out = {"data_sources": [], "top_level_pages": []}
    for ds in inv.data_sources:
        out["data_sources"].append(
            {
                "id": ds["id"],
                "title": ds_title(ds),
                "path": inv.path(ds),
                "rows": inv.rows[norm(ds["id"])],
                "last_edited": ds.get("last_edited_time"),
                "inline": bool(ds.get("is_inline")),
                "property_types": dict(inv.schema_counts(ds)),
            }
        )
    for p in inv.top_level_pages():
        out["top_level_pages"].append(
            {
                "id": p["id"],
                "title": page_title(p),
                "parent": inv.parent_title(p),
                "child_pages": inv.child_pages[norm(p["id"])],
                "last_edited": p.get("last_edited_time"),
            }
        )
    report.dump_json(out, args.out)
    print(f"wrote {args.out}: {len(out['data_sources'])} databases, {len(out['top_level_pages'])} top-level pages")


def _export(args, dry):
    n = Notion(_secret(args.token_file, "NOTION_TOKEN"))
    os.makedirs(args.out, exist_ok=True)
    ex = Exporter(
        n,
        args.out,
        max_file_bytes=int(args.max_file_mb * 1024 * 1024),
        download_files=not dry and not args.no_files,
        exclude=_exclude(args),
        block_comments=args.block_comments,
        log=lambda m: print(m, file=sys.stderr),
    )
    ex.run(_roots(args.root))
    path = ex.save()
    print(
        f"snapshot: {path} ({len(ex.snap['pages'])} pages, {len(ex.snap['data_sources'])} databases, "
        f"{len(ex.snap['files'])} files; {n.http.calls} Notion calls, {n.http.retries} retries)",
        file=sys.stderr,
    )
    return args.out


def cmd_export(args):
    _export(args, dry=False)


def _plan(snapshot_dir, args):
    snap = load_snapshot(snapshot_dir)
    return Planner(snap, docs_board_name=args.docs_board, exclude=_exclude(args)).build()


def _print_plan(plan, list_cards=False):
    for b in plan.boards.values():
        print(
            f"board {b.name!r} [{b.identifier}] from {b.source_title!r}: {b.card_count} cards, "
            f"{len(b.fields)} fields, {len(b.states)} states, {len(b.templates)} templates"
        )
        for f in b.fields:
            extra = f" (falls back to {f.fallback.field_type})" if f.fallback else ""
            print(f"    field {f.name!r}: {f.field_type}{extra}")
        if list_cards:
            for c in plan.cards:
                if c.board == b.key:
                    print(f"    card {c.name!r}" + (" (sub-card)" if c.parent else ""))


def cmd_plan(args):
    plan = _plan(args.snapshot, args)
    _print_plan(plan, args.list_cards)
    text = report.plan_report(plan)
    path = args.report or os.path.join(args.snapshot, "dry-run-report.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    report.dump_json(report.plan_json(plan), os.path.splitext(path)[0] + ".json")
    print(f"report: {path}")


def cmd_apply(args):
    from .apply import Applier
    from .notes import Notes

    plan = _plan(args.snapshot, args)
    notes = Notes(args.notes_url, _secret(args.api_key_file, "NOTES_API_KEY"), args.workspace)
    ap = Applier(
        notes,
        plan,
        args.snapshot,
        log=lambda m: print(m, file=sys.stderr),
        private=not args.not_private,
        public_url=args.public_url,
        max_file_bytes=int(args.max_file_mb * 1024 * 1024),
    )
    failure = None
    try:
        result = ap.run()
    except Exception as e:  # write the report of what happened before stopping
        failure = e
        result = ap.result
        result["errors"].append(f"IMPORT STOPPED: {type(e).__name__}: {e}")
    text = report.apply_report(plan, result, ap.web, args.workspace)
    path = args.report or os.path.join(args.snapshot, "import-report.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    report.dump_json(
        {"result": result, "cards": {k: v for k, v in ap.cards.items()}}, os.path.splitext(path)[0] + ".json"
    )
    print(f"report: {path}")
    print(
        json.dumps(
            {
                "created": result["created"],
                "updated": result["updated"],
                "errors": len(result["errors"]),
                "skipped": len(result["skipped"]),
            }
        )
    )
    if failure is not None:
        print(f"import stopped: {failure}", file=sys.stderr)
    return 1 if result["errors"] else 0


def cmd_run(args):
    out = _export(args, dry=args.dry_run)
    args.snapshot = out
    if args.dry_run:
        return cmd_plan(args)
    return cmd_apply(args)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="notion_import", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    def notion_args(p):
        p.add_argument("--token-file", help="file holding the Notion integration token (else NOTION_TOKEN)")

    def select_args(p):
        p.add_argument("--root", action="append", help="ds:<data source id>, db:<database id> or page:<page id>")
        p.add_argument("--exclude", action="append", help="Notion id to leave out (page, database or data source)")
        p.add_argument("--exclude-file", help="file with one Notion id per line to leave out")
        p.add_argument("--out", required=True, help="snapshot folder")
        p.add_argument("--no-files", action="store_true", help="do not download files")
        p.add_argument("--block-comments", action="store_true", help="also read comments on every block (slow)")
        p.add_argument("--max-file-mb", type=float, default=DEFAULT_MAX_FILE / 1024 / 1024)

    def plan_args(p):
        p.add_argument("--docs-board", default="Docs", help="board name for plain pages")
        p.add_argument("--report", help="report file (default: inside the snapshot folder)")
        p.add_argument("--list-cards", action="store_true", help="print every card title in the dry run")

    def notes_args(p):
        p.add_argument("--notes-url", help="Notes base URL, e.g. https://notes.example.org")
        p.add_argument("--public-url", help="URL people use to open Notes (for card links), if different")
        p.add_argument("--workspace", help="Notes workspace slug")
        p.add_argument("--api-key-file", help="file holding the Notes API key (else NOTES_API_KEY)")
        p.add_argument("--not-private", action="store_true", help="do NOT make new boards private")

    p = sub.add_parser("inventory")
    notion_args(p)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_inventory)

    p = sub.add_parser("export")
    notion_args(p)
    select_args(p)
    p.set_defaults(fn=cmd_export)

    p = sub.add_parser("plan")
    p.add_argument("--snapshot", required=True)
    p.add_argument("--exclude", action="append")
    p.add_argument("--exclude-file")
    plan_args(p)
    p.set_defaults(fn=cmd_plan)

    p = sub.add_parser("apply")
    p.add_argument("--snapshot", required=True)
    p.add_argument("--exclude", action="append")
    p.add_argument("--exclude-file")
    p.add_argument("--max-file-mb", type=float, default=DEFAULT_MAX_FILE / 1024 / 1024)
    plan_args(p)
    notes_args(p)
    p.set_defaults(fn=cmd_apply)

    p = sub.add_parser("run")
    notion_args(p)
    select_args(p)
    plan_args(p)
    notes_args(p)
    p.add_argument("--dry-run", action="store_true", help="read Notion and report; write nothing to Notes")
    p.set_defaults(fn=cmd_run)

    args = ap.parse_args(argv)
    if args.cmd in ("apply",) or (args.cmd == "run" and not args.dry_run):
        if not args.notes_url or not args.workspace:
            ap.error("--notes-url and --workspace are needed to import")
    return args.fn(args) or 0


if __name__ == "__main__":
    sys.exit(main())
