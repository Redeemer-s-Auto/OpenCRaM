"""Unit tests for the Notion importer. Fixtures are hand-written Notion JSON (fake data).

Run: python -m unittest discover -s scripts/notion-import/tests
"""

import copy
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from notion_import import formula as fx  # noqa: E402
from notion_import.apply import Applier, ImportAborted  # noqa: E402
from notion_import.blocks import Renderer  # noqa: E402
from notion_import.export import Exporter  # noqa: E402
from notion_import.http import HTTPError, JSONClient, RateLimiter  # noqa: E402
from notion_import.notes import Notes  # noqa: E402
from notion_import.notion import Notion, WriteBlocked  # noqa: E402
from notion_import.plan import Planner, clean_board_name, make_identifier, names_for_ids  # noqa: E402
from notion_import.report import plan_report, apply_report  # noqa: E402
from notion_import.richtext import to_html  # noqa: E402

from fake_notes import FakeNotes  # noqa: E402


def fixture(name):
    with open(os.path.join(HERE, "fixtures", name), encoding="utf-8") as fh:
        return json.load(fh)


class NoSleep:
    def __init__(self):
        self.waits = []
        self.t = 0.0

    def sleep(self, s):
        self.waits.append(s)
        self.t += s

    def clock(self):
        return self.t


# ---------------------------------------------------------------------------
class TestBlocks(unittest.TestCase):
    def setUp(self):
        self.r = Renderer({})
        self.html = self.r.render(fixture("blocks_all.json"))

    def test_headings_paragraph_marks(self):
        self.assertIn("<h1>Big title</h1>", self.html)
        self.assertIn("<strong>bold</strong>", self.html)
        self.assertIn("<em> &lt;tag&gt; &amp; </em>", self.html)  # escaped, never raw HTML
        self.assertIn('href="https://example.org/x"', self.html)

    def test_lists_grouped_and_nested(self):
        self.assertIn("<ul><li><p>One</p><ul><li><p>Nested</p></li></ul></li><li><p>Two</p></li></ul>", self.html)
        self.assertIn("<ol><li><p>First</p></li></ol>", self.html)

    def test_todos_become_checklist(self):
        self.assertIn('<ul data-type="taskList">', self.html)
        self.assertIn('data-checked="true"><label><input type="checkbox" checked>', self.html)
        self.assertIn('data-checked="false"><label><input type="checkbox">', self.html)

    def test_toggle_columns_table_callout_code(self):
        self.assertIn('<details data-block-type="toggle"', self.html)
        self.assertIn('<summary data-block-type="toggle-title">Click me</summary>', self.html)
        self.assertIn('<div data-block-type="toggle-content"><p>Hidden text</p></div>', self.html)
        self.assertIn(
            '<div data-block-type="column-list" data-columns="2"><div data-block-type="column"><p>Left</p>', self.html
        )
        self.assertIn(
            "<table><tbody><tr><th><p>Col A</p></th><th><p>Col B</p></th></tr>"
            "<tr><td><p>1</p></td><td><p></p></td></tr></tbody></table>",
            self.html,
        )
        self.assertIn(
            'data-block-type="callout-component" data-background="orange" data-logo-in-use="emoji" '
            'data-emoji-unicode="9888"',
            self.html,
        )
        self.assertIn('<pre><code class="language-python">print(&#x27;&lt;hi&gt;&#x27;)</code></pre>', self.html)
        self.assertIn("<hr>", self.html)

    def test_toggle_heading(self):
        self.assertIn('<summary data-block-type="toggle-title"><strong>Toggle heading</strong></summary>', self.html)

    def test_files_and_links_use_placeholders(self):
        self.assertIn("@@CARD:aaaaaaaa000000000000000000000002@@", self.html)  # page mention
        self.assertIn("@@CARD:b0000001000000000000000000000019@@", self.html)  # child page
        self.assertEqual(self.r.child_pages, ["b0000001000000000000000000000019"])
        self.assertIn("@@BOARD:b0000001000000000000000000000026@@", self.html)  # inline database
        self.assertIn('<a href="https://example.org/read"', self.html)  # bookmark

    def test_nothing_silently_dropped(self):
        self.assertIn("[From Notion: block type the Notion API does not return - not brought over]", self.html)
        self.assertIn("table of contents block", self.html)
        self.assertEqual(self.r.losses["table of contents block"], 1)
        self.assertIn("synced block original (content copied, no longer syncs)", self.r.changed)
        self.assertIn("Synced text", self.html)
        self.assertIn("<pre><code>a^2+b^2</code></pre>", self.html)
        self.assertEqual(self.r.changed["@mention of a person (kept as plain text)"], 1)
        self.assertIn("@Pat Example", self.html)
        # file blocks with no download record are flagged, not lost silently
        self.assertTrue(any("image" in k for k in self.r.losses))

    def test_four_columns_stack(self):
        cols = {
            "type": "column_list",
            "id": "x",
            "children": [
                {
                    "type": "column",
                    "id": str(i),
                    "children": [
                        {
                            "type": "paragraph",
                            "id": f"p{i}",
                            "paragraph": {"rich_text": [{"type": "text", "plain_text": f"C{i}"}]},
                        }
                    ],
                }
                for i in range(4)
            ],
        }
        r = Renderer({})
        html = r.render([cols])
        self.assertNotIn("column-list", html)
        self.assertEqual(html, "<p>C0</p><p>C1</p><p>C2</p><p>C3</p>")
        self.assertEqual(sum(r.changed.values()), 1)

    def test_linked_view_and_excluded(self):
        r = Renderer({})
        html = r.render(
            [
                {
                    "type": "child_database",
                    "id": "d1",
                    "child_database": {"title": "View"},
                    "database_data_sources": [],
                },
                {"type": "child_page", "id": "p1", "child_page": {"title": "Private"}, "excluded": True},
            ]
        )
        self.assertIn("linked database view", html)
        self.assertIn("was left out of this import", html)
        self.assertEqual(r.child_pages, [])


class TestRichText(unittest.TestCase):
    def test_notion_url_link_rewritten(self):
        rich = [
            {
                "type": "text",
                "plain_text": "go",
                "href": "https://www.notion.so/My-page-0123456789abcdef0123456789abcdef?pvs=4",
                "text": {"content": "go"},
            }
        ]
        html = to_html(rich, resolve=lambda pid: f"@@CARD:{pid}@@")
        self.assertIn('href="@@CARD:0123456789abcdef0123456789abcdef@@"', html)

    def test_outside_link_kept(self):
        rich = [{"type": "text", "plain_text": "x", "href": "https://example.org/?a=1&b=2"}]
        self.assertIn('href="https://example.org/?a=1&amp;b=2"', to_html(rich, resolve=lambda p: "nope"))

    def test_date_mention_becomes_a_date_chip(self):
        rich = [{"type": "mention", "plain_text": "Oct 30, 2026 2:30 PM", "mention": {"type": "date", "date": {"start": "2026-10-30T14:30:00.000-05:00", "end": None}}}]
        out = to_html(rich)
        self.assertIn('data-type="date-mention" data-date="2026-10-30" data-time="14:30" data-mention-id="', out)
        self.assertIn(">Oct 30, 2026 2:30 PM</span>", out)
        day = [{"type": "mention", "plain_text": "Oct 30, 2026", "mention": {"type": "date", "date": {"start": "2026-10-30", "end": None}}}]
        self.assertNotIn("data-time", to_html(day))
        span = [{"type": "mention", "plain_text": "Oct 30 to Nov 2", "mention": {"type": "date", "date": {"start": "2026-10-30", "end": "2026-11-02"}}}]
        self.assertEqual(to_html(span), "Oct 30 to Nov 2")

    def test_javascript_text_is_escaped(self):
        rich = [{"type": "text", "plain_text": "<script>alert(1)</script>"}]
        self.assertEqual(to_html(rich), "&lt;script&gt;alert(1)&lt;/script&gt;")


# ---------------------------------------------------------------------------
class TestFormula(unittest.TestCase):
    def tr(self, text, names=None):
        names = names or {"Hours": "Hours", "Cost": "Cost", "Due": "Due", "Name": "Title", "Tags": "Tags"}
        return fx.translate(text, lambda n: names.get(n))

    def test_arithmetic(self):
        self.assertEqual(self.tr('prop("Hours") * prop("Cost")'), '(prop("Hours") * prop("Cost"))')

    def test_method_call_becomes_function(self):
        self.assertEqual(self.tr('prop("Due").dateAdd(5, "days")'), 'dateAdd(prop("Due"), 5, "days")')

    def test_empty_and_if(self):
        self.assertEqual(
            self.tr('if(empty(prop("Due")), empty(), prop("Due"))'), 'if(empty(prop("Due")), toNumber(""), prop("Due"))'
        )

    def test_ifs_and_ternary(self):
        self.assertEqual(
            self.tr('ifs(prop("Hours") > 2, "long", prop("Hours") > 1, "mid", "short")'),
            'if((prop("Hours") > 2), "long", if((prop("Hours") > 1), "mid", "short"))',
        )
        self.assertEqual(self.tr('prop("Hours") > 1 ? "a" : "b"'), 'if((prop("Hours") > 1), "a", "b")')

    def test_title_and_date_function(self):
        self.assertEqual(
            self.tr('date(prop("Due")) + length(prop("Name"))'), '(day(prop("Due")) + length(prop("Title")))'
        )

    def test_internal_property_ids_become_names(self):
        props = {"Hours": {"id": "a%3Bb"}, "Cost": {"id": "xyz"}}
        text = names_for_ids(
            "{{notion:block_property:a%3Bb:00000000-0000:8994905a}} * {{notion:block_property:xyz:1:2}}", props
        )
        self.assertEqual(text, 'prop("Hours") * prop("Cost")')
        self.assertEqual(self.tr(text), '(prop("Hours") * prop("Cost"))')
        self.assertIn("{{notion:", names_for_ids("{{notion:block_property:gone:1}}", props))

    def test_refuses_what_notes_cannot_do(self):
        for text in [
            'prop("Tags").map(current + "!")',
            "now()",
            "let(x, 1, x)",
            "[1, 2]",
            'prop("Rel")',
            'dateAdd(prop("Due"), 1, "quarters")',
            "{{notion:block_property:abc}}",
        ]:
            with self.assertRaises(fx.Untranslatable, msg=text):
                self.tr(text)


# ---------------------------------------------------------------------------
class TestPlan(unittest.TestCase):
    def setUp(self):
        self.snap = fixture("snapshot_small.json")
        self.plan = Planner(copy.deepcopy(self.snap)).build()
        self.tasks = self.plan.boards["11111111111111111111111111111111"]
        self.projects = self.plan.boards["22222222222222222222222222222222"]

    def f(self, board, name):
        return next(f for f in board.fields if f.name == name)

    def test_boards(self):
        self.assertEqual([b.name for b in self.plan.boards.values()], ["Tasks", "Projects", "Docs"])
        self.assertEqual(self.plan.boards["docs"].kind, "docs")

    def test_property_types(self):
        t = {f.name: f.field_type for f in self.tasks.fields}
        self.assertEqual(t["Notes"], "text")
        self.assertEqual(t["Hours"], "number")
        self.assertEqual(t["Cost"], "money")
        self.assertEqual(t["Kind"], "select")
        self.assertEqual(t["Tags"], "multi_select")
        self.assertEqual(t["Due"], "date")
        self.assertEqual(t["Due end"], "date")
        self.assertEqual(t["Checked"], "checkbox")
        self.assertEqual(t["Link"], "url")
        self.assertEqual(t["Mail"], "email")
        self.assertEqual(t["Phone"], "phone")
        self.assertEqual(t["Owner"], "person")
        self.assertEqual(t["Owner from Notion"], "text")
        self.assertEqual(t["Project"], "relation")
        self.assertEqual(t["Total"], "formula")
        self.assertEqual(t["Next"], "formula")
        self.assertEqual(t["Odd"], "text")  # .map() does not translate -> frozen
        self.assertEqual(t["Made"], "created_time")
        self.assertEqual(t["Done pct"], "percent")
        self.assertNotIn("Press", t)  # button: nothing to copy
        self.assertNotIn("Status", t)  # status -> card state

    def test_formula_details(self):
        total = self.f(self.tasks, "Total")
        self.assertEqual(total.settings["result_type"], "money")
        self.assertEqual(total.settings["expression"], '(prop("Hours") * prop("Cost"))')
        self.assertEqual(self.f(self.tasks, "Next").settings["result_type"], "date")
        self.assertIsNotNone(total.fallback)

    def test_states_from_status(self):
        self.assertEqual(
            [(s["name"], s["group"]) for s in self.tasks.states],
            [("Not started", "unstarted"), ("Working", "started"), ("Finished", "completed")],
        )

    def test_relations_two_way_and_rollups(self):
        rel = self.f(self.tasks, "Project")
        self.assertTrue(rel.two_way)
        self.assertEqual(rel.mirror_name, "Tasks")
        back = self.f(self.projects, "Tasks")
        self.assertEqual(back.mirror_of, "11111111111111111111111111111111:p_pj")
        roll = self.f(self.projects, "Total hours")
        self.assertEqual(roll.field_type, "rollup")
        self.assertEqual(roll.rollup["function"], "sum")
        self.assertEqual(roll.rollup["target"], "11111111111111111111111111111111:p_hr")
        self.assertEqual(self.f(self.projects, "Medians").field_type, "number")  # median: frozen copy
        self.assertEqual(self.f(self.projects, "Elsewhere").field_type, "text")  # target not imported

    def test_card_values(self):
        card = next(c for c in self.plan.cards if c.name.endswith("Fix lift"))
        self.assertEqual(card.name, "\U0001f527 Fix lift")
        v = {
            self.tasks.field_by_ext(k).name if self.tasks.field_by_ext(k) else k: val for k, val in card.values.items()
        }
        self.assertEqual(v["Cost"], 1234)
        self.assertEqual(v["Done pct"], 50.0)
        self.assertEqual(v["Kind"], "Shop")
        self.assertEqual(v["Tags"], ["Quick", "Brand new"])
        self.assertEqual(v["Due"], "2026-02-01")
        self.assertEqual(v["Due end"], "2026-02-03")
        self.assertEqual(v["Owner"], ["pat@example.org"])
        self.assertEqual(
            v["Owner from Notion"],
            [{"name": "Pat Example", "email": "pat@example.org"}, {"name": "Sam Guest", "email": ""}],
        )
        self.assertEqual(v["Project"], ["bbbbbbbb000000000000000000000001"])
        self.assertEqual(card.state, "Working")
        self.assertEqual(card.created_by_email, "pat@example.org")
        self.assertIn("f3", card.attachments)
        self.assertTrue(card.body.startswith('<image-component src="https://img.example.org/cover.jpg"'))
        self.assertIn("is over the Notes file size limit", card.body)

    def test_sub_pages_and_docs(self):
        sub = next(c for c in self.plan.cards if c.name == "Steps")
        self.assertEqual(sub.parent, "aaaaaaaa000000000000000000000001")
        self.assertEqual(sub.board, "11111111111111111111111111111111")
        ch = next(c for c in self.plan.cards if c.name == "Chapter 1")
        self.assertEqual((ch.board, ch.parent), ("docs", "dddddddd000000000000000000000001"))
        self.assertFalse(any(c.notion_id.startswith("eeee") for c in self.plan.cards))  # template is not a card

    def test_templates(self):
        self.assertEqual(len(self.tasks.templates), 1)
        t = self.tasks.templates[0]
        self.assertEqual((t["name"], t["title"], t["state"]), ("Weekly task", "Weekly check", "Not started"))
        self.assertIn("Do the weekly check", t["body"])

    def test_loss_counts_and_report(self):
        self.assertEqual(self.tasks.lost["saved views (filters, sorts, groups, layouts)"], 2)
        self.assertEqual(self.tasks.lost["button property"], 1)
        self.assertEqual(self.tasks.lost["page lock"], 1)
        self.assertEqual(self.tasks.changed["formula that does not translate (frozen value)"], 1)
        text = plan_report(self.plan)
        self.assertIn("## Sharing rule", text)
        self.assertIn("huge.mov", text)
        self.assertIn("| Linked database views | Does not come over |", text)
        self.assertNotIn("Use the blue kit", text)  # report shows titles and counts only, no row contents

    def test_exclude(self):
        plan = Planner(copy.deepcopy(self.snap), exclude={"aaaaaaaa000000000000000000000002"}).build()
        self.assertFalse(any(c.name == "Order oil" for c in plan.cards))

    def test_board_names(self):
        self.assertEqual(clean_board_name("Parts (old) - 2026: A&B"), "Parts old 2026 A B")
        taken = set()
        self.assertEqual(make_identifier("Service Advisor Checklists", taken), "SAC")
        self.assertEqual(make_identifier("Service Advisor Checklists", taken), "SAC2")


# ---------------------------------------------------------------------------
class TestApply(unittest.TestCase):
    def run_import(self, fake, snap=None, keep_dir=None, **kw):
        snap = snap or fixture("snapshot_small.json")
        plan = Planner(copy.deepcopy(snap)).build()
        ns = NoSleep()
        notes = Notes(
            "https://notes.example.org",
            "key",
            "ws",
            transport=fake,
            sleep=ns.sleep,
            clock=ns.clock,
            upload_transport=fake.upload,
        )

        def go(d):
            os.makedirs(os.path.join(d, "files"), exist_ok=True)
            for name in ("abc", "def"):
                with open(os.path.join(d, "files", name), "wb") as fh:
                    fh.write(b"data")
            ap = Applier(notes, plan, d, log=lambda m: None, **kw)
            return ap, ap.run()

        if keep_dir:
            ap, result = go(keep_dir)
        else:
            with tempfile.TemporaryDirectory() as d:
                ap, result = go(d)
        return ap, result, ns

    def test_first_run_builds_everything(self):
        fake = FakeNotes()
        ap, result, _ = self.run_import(fake)
        self.assertEqual(result["errors"], [])
        self.assertEqual(len(fake.projects), 3)
        self.assertTrue(all(p["is_private"] and p["network"] == 0 for p in fake.projects.values()))
        self.assertEqual(result["created"]["card"], 6)
        tasks_pid = ap.projects["11111111111111111111111111111111"]["id"]
        names = {f["name"]: f for f in fake.fields[tasks_pid]}
        self.assertEqual(names["Odd"]["field_type"], "text")
        self.assertEqual(names["Total"]["field_type"], "formula")
        # two-way relation: one primary on Tasks, its mirror on Projects named after the Notion side
        proj_pid = ap.projects["22222222222222222222222222222222"]["id"]
        mirror = [f for f in fake.fields[proj_pid] if f["settings"].get("is_mirror")]
        self.assertEqual([m["name"] for m in mirror], ["Tasks"])
        rollup = next(f for f in fake.fields[proj_pid] if f["name"] == "Total hours")
        self.assertEqual(rollup["settings"]["relation_field_id"], mirror[0]["id"])

        fix = next(c for c in fake.cards.values() if c["name"].endswith("Fix lift"))
        self.assertEqual(fix["external_source"], "notion")
        self.assertEqual(fix["external_id"], "aaaaaaaa-0000-0000-0000-000000000001")
        self.assertEqual(fix["created_by"], "user-pat")
        working = next(s for s in fake.states[tasks_pid] if s["name"] == "Working")
        self.assertEqual(fix["state"], working["id"])
        big = next(c for c in fake.cards.values() if c["name"] == "Big project")
        rel_id = names["Project"]["id"]
        self.assertEqual(fix["custom_fields"][rel_id], [big["id"]])
        # people: Pat matched by email to a Notes member; Sam (no match) kept by name in the text field
        self.assertEqual(fix["custom_fields"][names["Owner"]["id"]], ["user-pat"])
        self.assertEqual(fix["custom_fields"][names["Owner from Notion"]["id"]], "Sam Guest")
        # link rewriting: mention of an imported page -> its Notes card; missing page -> plain text
        self.assertIn(
            f'href="https://notes.example.org/ws/browse/{ap.projects["22222222222222222222222222222222"]["identifier"]}-1/"',
            fix["description_html"],
        )
        self.assertIn(" and Gone page", fix["description_html"])
        self.assertNotIn("@@", fix["description_html"])
        # image re-uploaded (never the Notion link), file attached, over-limit file skipped
        self.assertIn('<image-component src="', fix["description_html"])
        self.assertNotIn("files.example.invalid", fix["description_html"])
        self.assertEqual(len(fake.assets), 1)
        self.assertEqual(len(fake.attachments[fix["id"]]), 1)
        # sub-card under its parent
        steps = next(c for c in fake.cards.values() if c["name"] == "Steps")
        self.assertEqual(steps["parent"], fix["id"])
        self.assertIn('data-type="taskList"', steps["description_html"])
        # docs page links to the imported card through a notion.so URL
        handbook = next(c for c in fake.cards.values() if c["name"] == "Handbook")
        self.assertIn("/ws/browse/", handbook["description_html"])
        # comments: history note + two comments; the unmatched author is named
        texts = [c["comment_html"] for c in fake.comments[fix["id"]]]
        self.assertEqual(len(texts), 3)
        self.assertTrue(texts[0].startswith("<p>Imported from Notion."))
        self.assertIn("Originally by Sam Guest", texts[2])
        self.assertEqual(fake.comments[fix["id"]][1]["created_by"], "user-pat")
        # template
        self.assertEqual([t["name"] for t in fake.templates[tasks_pid]], ["Weekly task"])
        self.assertEqual(fake.templates[tasks_pid][0]["data"]["name"], "Weekly check")

    def test_rerun_updates_instead_of_duplicating(self):
        fake = FakeNotes()
        self.run_import(fake)
        counts = (
            len(fake.projects),
            len(fake.cards),
            sum(len(v) for v in fake.fields.values()),
            sum(len(v) for v in fake.comments.values()),
            len(fake.assets),
            sum(len(v) for v in fake.attachments.values()),
            sum(len(v) for v in fake.templates.values()),
        )
        snap = fixture("snapshot_small.json")
        snap["pages"]["aaaaaaaa000000000000000000000002"]["properties"]["Name"]["title"][0]["plain_text"] = (
            "Order more oil"
        )
        ap, result, _ = self.run_import(fake, snap)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["created"].get("card", 0), 0)
        self.assertEqual(result["updated"]["card"], 6)
        after = (
            len(fake.projects),
            len(fake.cards),
            sum(len(v) for v in fake.fields.values()),
            sum(len(v) for v in fake.comments.values()),
            len(fake.assets),
            sum(len(v) for v in fake.attachments.values()),
            sum(len(v) for v in fake.templates.values()),
        )
        self.assertEqual(counts, after)
        self.assertTrue(any(c["name"] == "Order more oil" for c in fake.cards.values()))

    def test_rate_limit_retry(self):
        fake = FakeNotes(rate_limit_every=7)
        ap, result, ns = self.run_import(fake)
        self.assertEqual(result["errors"], [])
        self.assertEqual(len(fake.cards), 6)
        self.assertGreater(ap.n.http.retries, 0)
        self.assertIn(1.0, ns.waits)

    def test_stops_before_copying_when_server_cannot_make_board_private(self):
        fake = FakeNotes(support_private=False)
        with self.assertRaises(ImportAborted) as ctx:
            self.run_import(fake)
        self.assertIn("did not make it private", str(ctx.exception))
        self.assertEqual(len(fake.projects), 1)
        self.assertEqual(fake.cards, {})  # nothing landed on a board everyone can see

    def test_newer_field_types_are_made_and_audit_fields_get_no_values(self):
        fake = FakeNotes()
        ap, result, _ = self.run_import(fake)
        self.assertEqual(result["errors"], [])
        tasks_pid = ap.projects["11111111111111111111111111111111"]["id"]
        got = {f["name"]: f for f in fake.fields[tasks_pid]}
        self.assertEqual((got["Mail"]["field_type"], got["Mail"]["settings"]["format"]), ("text", "email"))
        self.assertEqual(got["Phone"]["settings"]["format"], "phone")
        self.assertEqual(got["Done pct"]["settings"]["format"], "percent")
        self.assertEqual(got["Made"]["field_type"], "created_time")
        sent = [c for c in fake.cards.values() if c["project"] == tasks_pid]
        self.assertTrue(all(got["Made"]["id"] not in (c.get("custom_fields") or {}) for c in sent))

    def test_old_server_without_the_newer_field_types_uses_text_and_number(self):
        fake = FakeNotes(support_new_types=False)
        ap, result, _ = self.run_import(fake)
        self.assertEqual(result["errors"], [])
        tasks_pid = ap.projects["11111111111111111111111111111111"]["id"]
        got = {f["name"]: f["field_type"] for f in fake.fields[tasks_pid]}
        self.assertEqual((got["Mail"], got["Phone"], got["Made"], got["Done pct"]), ("text", "text", "text", "number"))
        self.assertTrue(any("became a frozen value" in w for w in result["warnings"]))

    def test_old_server_without_templates_warns(self):
        fake = FakeNotes(support_templates=False)
        _, result, _ = self.run_import(fake)
        self.assertTrue(any("card templates not available" in w for w in result["warnings"]))

    def test_rerun_with_a_key_that_cannot_see_the_board_makes_no_copy(self):
        fake = FakeNotes()
        snap = fixture("snapshot_small.json")
        with tempfile.TemporaryDirectory() as d:
            self.run_import(fake, snap, keep_dir=d)
            hidden = next(iter(fake.projects))
            fake.hidden_projects.add(hidden)
            before = (len(fake.projects), len(fake.cards))
            with self.assertRaises(ImportAborted):
                self.run_import(fake, snap, keep_dir=d)
            self.assertEqual((len(fake.projects), len(fake.cards)), before)

    def test_rerun_clears_values_emptied_in_notion(self):
        fake = FakeNotes()
        self.run_import(fake)
        snap = fixture("snapshot_small.json")
        props = snap["pages"]["aaaaaaaa000000000000000000000001"]["properties"]
        props["Kind"]["select"] = None
        props["Project"]["relation"] = []
        ap, result, _ = self.run_import(fake, snap)
        self.assertEqual(result["errors"], [])
        pid = ap.projects["11111111111111111111111111111111"]["id"]
        names = {f["name"]: f["id"] for f in fake.fields[pid]}
        fix = next(c for c in fake.cards.values() if c["name"].endswith("Fix lift"))
        self.assertIsNone(fix["custom_fields"][names["Kind"]])
        self.assertIsNone(fix["custom_fields"][names["Project"]])

    def test_refused_value_on_rerun_keeps_the_rest_of_the_update(self):
        fake = FakeNotes()
        self.run_import(fake)
        fake.refuse_field_names.add("Kind")
        snap = fixture("snapshot_small.json")
        snap["pages"]["aaaaaaaa000000000000000000000001"]["properties"]["Name"]["title"][0]["plain_text"] = (
            "Fix lift now"
        )
        _, result, _ = self.run_import(fake, snap)
        self.assertTrue(any("values refused" in e for e in result["errors"]))
        self.assertTrue(any(c["name"].endswith("Fix lift now") for c in fake.cards.values()))

    def test_image_whose_upload_failed_is_uploaded_again(self):
        fake = FakeNotes()
        fake.fail_uploads = 1
        _, first, _ = self.run_import(fake)
        self.assertTrue(any("photo.png" in e for e in first["errors"]))
        _, second, _ = self.run_import(fake)
        uploaded = [a for a in fake.assets.values() if a["uploaded"]]
        self.assertEqual(len(uploaded), 1)
        self.assertTrue(uploaded[0]["external_id"].endswith(":retry1"))
        fix = next(c for c in fake.cards.values() if c["name"].endswith("Fix lift"))
        self.assertIn(f'src="{uploaded[0]["id"]}"', fix["description_html"])

    def test_duplicate_template_names_both_kept(self):
        fake = FakeNotes()
        snap = fixture("snapshot_small.json")
        ds = snap["data_sources"]["11111111111111111111111111111111"]
        ds["templates"].append({"id": "eeeeeeee000000000000000000000001", "name": "Weekly task", "is_default": False})
        ap, result, _ = self.run_import(fake, snap)
        pid = ap.projects["11111111111111111111111111111111"]["id"]
        self.assertEqual(sorted(t["name"] for t in fake.templates[pid]), ["Weekly task", "Weekly task 2"])

    def test_report_after_apply(self):
        fake = FakeNotes()
        ap, result, _ = self.run_import(fake)
        text = apply_report(ap.plan, result, ap.web, "ws")
        self.assertIn("## Boards in Notes", text)
        self.assertIn("/pages/", text)


# ---------------------------------------------------------------------------
class TestHttp(unittest.TestCase):
    def test_retry_after_honoured(self):
        replies = [(429, {"Retry-After": "3"}, b""), (502, {}, b""), (200, {}, b'{"ok": true}')]
        ns = NoSleep()
        c = JSONClient(
            "https://x.invalid", {}, rate=100, transport=lambda *a: replies.pop(0), sleep=ns.sleep, clock=ns.clock
        )
        self.assertEqual(c.get("/a"), {"ok": True})
        self.assertIn(3.0, ns.waits)
        self.assertEqual(c.retries, 2)

    def test_gives_up(self):
        ns = NoSleep()
        c = JSONClient(
            "https://x.invalid",
            {},
            rate=100,
            transport=lambda *a: (429, {}, b"slow down"),
            sleep=ns.sleep,
            clock=ns.clock,
            max_retries=2,
        )
        with self.assertRaises(HTTPError):
            c.get("/a")

    def test_rate_limiter_spacing(self):
        ns = NoSleep()
        r = RateLimiter(3.0, clock=ns.clock, sleep=ns.sleep)
        for _ in range(4):
            r.wait()
        self.assertAlmostEqual(ns.t, 1.0, places=5)  # 4 calls at 3/s: three gaps of 1/3 s

    def test_notes_rate_limit_reset_header(self):
        import time as _t

        calls = []

        def transport(m, u, h, b):
            calls.append(u)
            if len(calls) == 1:
                return 429, {"X-RateLimit-Reset": str(_t.time() + 5)}, b""
            return 200, {}, b"[]"

        ns = NoSleep()
        n = Notes("https://n.invalid", "k", "ws", transport=transport, sleep=ns.sleep, clock=ns.clock)
        n.members()
        self.assertTrue(any(4 <= w <= 7 for w in ns.waits), ns.waits)


class TestNotionReadOnly(unittest.TestCase):
    def test_writes_refused_before_sending(self):
        sent = []
        n = Notion("t", transport=lambda *a: sent.append(a) or (200, {}, b"{}"))
        for method, path in [
            ("PATCH", "/v1/pages/x"),
            ("POST", "/v1/pages"),
            ("DELETE", "/v1/blocks/x"),
            ("POST", "/v1/comments"),
            ("PATCH", "/v1/data_sources/x"),
        ]:
            with self.assertRaises(WriteBlocked):
                n._req(method, path)
        self.assertEqual(sent, [])
        n._req("POST", "/v1/search", {})
        n._req("POST", "/v1/data_sources/abc-123/query", {})
        self.assertEqual(len(sent), 2)


class FakeNotion:
    """Serves hand-written Notion objects to the exporter."""

    def __init__(self):
        self.ds = {
            "id": "11111111-1111-1111-1111-111111111111",
            "object": "data_source",
            "title": [{"plain_text": "Tasks"}],
            "properties": {"Name": {"id": "title", "type": "title"}},
            "parent": {"type": "database_id", "database_id": "aaaa1111-0000-0000-0000-000000000000"},
        }
        self.rows = [
            {
                "object": "page",
                "id": "aaaaaaaa-0000-0000-0000-000000000001",
                "parent": {"type": "data_source_id", "data_source_id": self.ds["id"]},
                "properties": {"Name": {"id": "title", "type": "title", "title": [{"plain_text": "Row one"}]}},
            },
            {
                "object": "page",
                "id": "aaaaaaaa-0000-0000-0000-000000000002",
                "parent": {"type": "data_source_id", "data_source_id": self.ds["id"]},
                "properties": {"Name": {"id": "title", "type": "title", "title": [{"plain_text": "Secret row"}]}},
            },
        ]
        self.blocks = {
            "aaaaaaaa-0000-0000-0000-000000000001": [
                {
                    "id": "b1",
                    "type": "image",
                    "has_children": False,
                    "image": {"type": "file", "file": {"url": "https://f.invalid/small.png?sig=1"}},
                },
                {
                    "id": "b2",
                    "type": "file",
                    "has_children": False,
                    "file": {"type": "file", "name": "big.zip", "file": {"url": "https://f.invalid/big.zip?sig=1"}},
                },
                {"id": "b3", "type": "toggle", "has_children": True, "toggle": {"rich_text": []}},
            ],
            "b3": [{"id": "b4", "type": "paragraph", "has_children": False, "paragraph": {"rich_text": []}}],
        }

    def users(self):
        return [
            {"id": "u1", "type": "person", "name": "Pat", "person": {"email": "PAT@example.org"}},
            {"id": "bot", "type": "bot", "name": "Bot"},
        ]

    def data_source(self, i):
        return self.ds

    def views(self, i):
        return [{"id": "v1"}]

    def templates(self, i):
        return []

    def query(self, i):
        return iter(self.rows)

    def page(self, i):
        raise AssertionError("rows come from the query")

    def children(self, i):
        return iter(self.blocks.get(i, []))

    def comments(self, i):
        return None  # the integration lacks "Read comments"

    def page_property(self, *a):
        return iter([])

    def database(self, i):
        raise HTTPError(404, "", "x")

    def download(self, url, max_bytes=None):
        data = b"x" * (10 if "small" in url else 50)
        return None if max_bytes is not None and len(data) > max_bytes else data


class TestExport(unittest.TestCase):
    def test_stopped_export_still_saves_what_it_read(self):
        class Broken(FakeNotion):
            def query(self, i):
                yield self.rows[0]
                raise HTTPError(500, "boom", "x")

        with tempfile.TemporaryDirectory() as d:
            ex = Exporter(Broken(), d, log=lambda m: None)
            with self.assertRaises(HTTPError):
                ex.run([("data_source", "11111111-1111-1111-1111-111111111111")])
            with open(os.path.join(d, "snapshot.json"), encoding="utf-8") as fh:
                snap = json.load(fh)
            self.assertFalse(snap["complete"])
            self.assertIn("aaaaaaaa000000000000000000000001", snap["pages"])
            self.assertTrue(any("stopped early" in n for n in snap["notes"]))

    def test_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            ex = Exporter(
                FakeNotion(), d, max_file_bytes=20, log=lambda m: None, exclude={"aaaaaaaa-0000-0000-0000-000000000002"}
            )
            snap = ex.run([("data_source", "11111111-1111-1111-1111-111111111111")])
            ex.save()
            self.assertTrue(os.path.exists(os.path.join(d, "snapshot.json")))
            ds = snap["data_sources"]["11111111111111111111111111111111"]
            self.assertEqual(ds["rows"], ["aaaaaaaa000000000000000000000001", "aaaaaaaa000000000000000000000002"])
            self.assertNotIn("aaaaaaaa000000000000000000000002", snap["pages"])  # excluded: never read
            page = snap["pages"]["aaaaaaaa000000000000000000000001"]
            self.assertEqual(page["blocks"][2]["children"][0]["id"], "b4")
            statuses = sorted(f["status"] for f in snap["files"].values())
            self.assertEqual(statuses, ["ok", "too big"])
            self.assertFalse(snap["comments_readable"])
            self.assertTrue(any("Read comments" in n for n in snap["notes"]))
            self.assertEqual(snap["users"], {"u1": {"name": "Pat", "email": "pat@example.org"}})
            ok = next(f for f in snap["files"].values() if f["status"] == "ok")
            self.assertTrue(os.path.exists(os.path.join(d, ok["path"])))
            # the plan then leaves the excluded row out and lists the big file
            plan = Planner(snap).build()
            self.assertEqual([c.name for c in plan.cards], ["Row one"])
            self.assertIn("big.zip", plan_report(plan))


if __name__ == "__main__":
    unittest.main()
