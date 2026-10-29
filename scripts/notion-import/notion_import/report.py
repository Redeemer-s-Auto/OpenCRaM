"""Reports: what was (or would be) imported, changed, skipped, and why."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone

SHARING_RULE = (
    "Notion's API does not say who a page is shared with (people, groups, guests, or the "
    "whole workspace), so the importer cannot copy sharing. It never guesses wider: every board it "
    "makes is a **private board** (only members see it, workspace admins included), and the only "
    "member is the person whose Notes API key ran the import. After you check a board, add the "
    "people who should see it, or turn private off. Boards that already existed from an earlier run "
    "keep whatever sharing you gave them."
)

# Notion feature -> what happens in Notes. Checked against the Notion API (2025-09-03) and
# the Notes v1 API.
GENERAL = [
    ("Database", "Comes over", "Becomes a board (project). Rows become cards."),
    ("Page body: headings, paragraphs, lists, quotes, dividers, code", "Comes over", "Same blocks in the card body."),
    ("To-do blocks", "Comes over", "Checklist items, ticked state kept."),
    (
        "Toggles and toggle headings",
        "Comes over changed",
        "Toggle blocks; a toggle heading becomes a toggle with a bold title.",
    ),
    ("Columns", "Comes over changed", "2 or 3 columns kept; 4 or more are stacked one under another."),
    (
        "Callouts",
        "Comes over changed",
        "Callout block; emoji kept, custom image icons replaced, colours matched to the nearest Notes colour.",
    ),
    ("Simple tables", "Comes over", "Table, header row and header column kept."),
    (
        "Images and files stored in Notion",
        "Comes over",
        "Downloaded and re-uploaded (images in the body, other files as card attachments). Notion's links expire after an hour, so nothing is hot-linked.",
    ),
    (
        "Files over the Notes size limit (10 MB)",
        "Does not come over",
        "Listed by name in the report; a placeholder line marks the spot.",
    ),
    ("Images and files from outside links", "Comes over changed", "Kept as links to the outside site."),
    (
        "Bookmarks, link previews, embeds",
        "Comes over changed",
        "A plain link. Embedded maps, videos and widgets do not play inside the card.",
    ),
    ("Sub-pages", "Comes over", "Sub-cards (pages inside pages), linked from the parent's body."),
    (
        "Plain pages (not in a database)",
        "Comes over",
        "Cards on a 'Docs' board; open its Pages link to see the page-list layout.",
    ),
    ("Inline databases inside a page", "Comes over changed", "Their own board; the page shows a link to it."),
    (
        "Linked database views",
        "Does not come over",
        "The Notion API cannot read linked views. A placeholder line marks the spot; import the source database instead.",
    ),
    (
        "Database views (filters, sorts, groups, layouts)",
        "Does not come over",
        "Counted per database. Set up the board's layout and filters again in Notes.",
    ),
    ("Synced blocks", "Comes over changed", "The content is copied; it no longer stays in sync."),
    ("Text, number, select, multi-select, date, checkbox, URL", "Comes over", "Custom fields of the same kind."),
    ("Dollar numbers", "Comes over", "Money fields."),
    (
        "Other number formats (percent, euro, ...)",
        "Comes over changed",
        "Plain number fields (percent 0.5 becomes 50).",
    ),
    ("Email and phone properties", "Comes over changed", "Text fields."),
    ("Status property", "Comes over", "The card state, with Notion's groups (to do / in progress / complete)."),
    (
        "Person property",
        "Comes over",
        "Person field, matched by email to Notes members; anyone not matched is listed in a text field next to it.",
    ),
    (
        "Relation",
        "Comes over",
        "Relation field when both databases are imported (two-way kept). Otherwise the linked titles as text.",
    ),
    (
        "Rollup",
        "Comes over changed",
        "Rollup field when its relation came over and the calculation exists in Notes; otherwise a frozen copy of the value.",
    ),
    (
        "Formula",
        "Comes over changed",
        "A Notes formula when it translates; otherwise a frozen copy of the value as it was on export day.",
    ),
    (
        "Created / edited time and by",
        "Comes over changed",
        "Kept as text fields; the card's created date and author are set from Notion (author when the email matches); an activity note on each card records both.",
    ),
    ("Unique ID property", "Comes over changed", "Text field; cards also get their own Notes ids."),
    ("Files property", "Comes over changed", "Files become card attachments; a text field keeps the names."),
    ("Button property and button blocks", "Does not come over", "The API returns nothing to copy."),
    ("Database automations", "Does not come over", "Not exposed by the Notion API."),
    (
        "Database templates",
        "Comes over changed",
        "Card templates on that board (title, body, field values, state). Files and sub-pages inside templates are left out.",
    ),
    (
        "Page and block comments",
        "Comes over changed",
        "Card comments, author matched by email (else 'Originally by <name>'). Only open comments: the API does not return resolved ones. Needs the integration's 'Read comments' capability.",
    ),
    ("Page icon", "Comes over changed", "An emoji icon goes in front of the card title; image icons are dropped."),
    ("Page cover", "Comes over changed", "The first image in the card body, so the Gallery layout shows it."),
    ("@mention of a person", "Comes over changed", "Plain text '@Name'."),
    ("@mention of a date, reminders", "Comes over changed", "Plain text; the reminder does not come over."),
    (
        "@mention of a page, links to Notion pages",
        "Comes over changed",
        "A link to the imported card; plain text when that page was not imported.",
    ),
    ("Equations", "Comes over changed", "Shown as code text."),
    ("Table of contents, breadcrumb", "Does not come over", "A placeholder line marks the spot."),
    (
        "AI blocks, meeting notes, forms, charts, other blocks the API calls 'unsupported'",
        "Does not come over",
        "A placeholder line names the block type.",
    ),
    (
        "Page history / versions",
        "Does not come over",
        "Not in the Notion API. Notes keeps its own history from the import on.",
    ),
    ("Page lock", "Does not come over", "Notes has no page lock; counted per database."),
    ("Wiki verification", "Comes over changed", "The state (verified/unverified) as text; no expiry."),
    ("Published-to-web pages", "Does not come over", "Notes cards are never published."),
    ("Page sharing and permissions", "Does not come over", "See the sharing rule below."),
]


def general_table() -> str:
    lines = ["| Notion feature | In Notes | Detail |", "|---|---|---|"]
    for a, b, c in GENERAL:
        lines.append(f"| {a} | {b} | {c} |")
    return "\n".join(lines)


def _counter_lines(c: Counter) -> list:
    return [f"- {n} x {k}" for k, n in sorted(c.items(), key=lambda kv: (-kv[1], kv[0])) if n]


def board_section(b, files_too_big: list) -> str:
    out = [
        f"### {b.name}",
        "",
        f"- From Notion: **{b.source_title}**" + (f" ({b.path})" if b.path else ""),
        f"- Cards: {b.card_count}",
        f"- Fields: {len(b.fields)}"
        + (f" ({', '.join(sorted(Counter(f.field_type for f in b.fields).elements()))})" if b.fields else ""),
        f"- States from Notion status: {len(b.states)}" if b.states else "- States: the Notes defaults",
        f"- Card templates: {len(b.templates)}" if b.templates else "- Card templates: none",
    ]
    if b.lost:
        out += ["", "**Does not come over:**"] + _counter_lines(b.lost)
    if b.changed:
        out += ["", "**Comes over changed:**"] + _counter_lines(b.changed)
    if b.came_over:
        out += ["", "**Comes over:**"] + _counter_lines(b.came_over)
    for n in b.notes:
        out.append(f"- Note: {n}")
    return "\n".join(out)


def too_big(plan) -> list:
    return [(rec.get("name"), rec.get("where")) for rec in plan.files.values() if rec.get("status") == "too big"]


def plan_report(plan, title: str = "Notion import - dry run") -> str:
    big = too_big(plan)
    out = [
        f"# {title}",
        "",
        f"Made {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}.",
        "",
        f"- Boards: {len(plan.boards)}",
        f"- Cards: {len(plan.cards)}",
        f"- Files: {sum(1 for f in plan.files.values() if f.get('status') == 'ok')} downloaded, "
        f"{len(big)} over the size limit, "
        f"{sum(1 for f in plan.files.values() if str(f.get('status')).startswith('download failed'))} failed",
        "",
    ]
    if plan.notes:
        out += ["## Export notes", ""] + [f"- {n}" for n in plan.notes] + [""]
    out += ["## Sharing rule", "", SHARING_RULE, ""]
    out += ["## Per board", ""]
    for b in plan.boards.values():
        out += [board_section(b, big), ""]
    if big:
        out += ["## Files over the size limit (not brought over)", ""] + [f"- {n} ({w})" for n, w in big] + [""]
    failed = [
        (r.get("name"), r.get("status"))
        for r in plan.files.values()
        if str(r.get("status")).startswith("download failed")
    ]
    if failed:
        out += ["## Files that failed to download", ""] + [f"- {n}: {s}" for n, s in failed] + [""]
    if plan.missing:
        why = Counter(f"{m['kind']}: {m['why']}" for m in plan.missing)
        out += ["## Skipped while reading Notion", ""] + _counter_lines(why) + [""]
    out += ["## What happens to each Notion feature", "", general_table(), ""]
    return "\n".join(out)


def apply_report(plan, result: dict, web: str, workspace: str) -> str:
    out = [plan_report(plan, title="Notion import - result"), "## Result", ""]
    for k, v in sorted(result["created"].items()):
        out.append(f"- Created {v} {k}(s)")
    for k, v in sorted(result["updated"].items()):
        out.append(f"- Found and updated {v} {k}(s) from an earlier run")
    out.append("")
    out += ["## Boards in Notes", ""]
    for key, info in result["boards"].items():
        out.append(
            f"- {info['name']} ({info['identifier']}) - private: {info.get('private')} - "
            f"{web}/{workspace}/projects/{info['id']}/issues/ - page list: {web}/{workspace}/projects/{info['id']}/pages/"
        )
    out.append("")
    if result["warnings"]:
        out += ["## Warnings", ""] + [f"- {w}" for w in result["warnings"]] + [""]
    if result["skipped"]:
        out += ["## Skipped", ""] + [f"- {s}" for s in result["skipped"]] + [""]
    if result["errors"]:
        out += ["## Errors", ""] + [f"- {e}" for e in result["errors"]] + [""]
    return "\n".join(out)


def plan_json(plan) -> dict:
    return {
        "boards": [
            {
                "key": b.key,
                "name": b.name,
                "identifier": b.identifier,
                "kind": b.kind,
                "source": b.source_title,
                "cards": b.card_count,
                "fields": [
                    {
                        "name": f.name,
                        "type": f.field_type,
                        "from": f.notion_type,
                        "fallback": f.fallback.field_type if f.fallback else None,
                    }
                    for f in b.fields
                ],
                "states": b.states,
                "templates": [t["name"] for t in b.templates],
                "lost": dict(b.lost),
                "changed": dict(b.changed),
                "came_over": dict(b.came_over),
            }
            for b in plan.boards.values()
        ],
        "cards": len(plan.cards),
    }


def dump_json(obj, path):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1, default=str)
