"""Plan: turn a Notion snapshot into boards, fields, cards and templates.

Pure (no network). The plan is what a dry run prints and what the apply step
creates. Values stay in a neutral form (option names, emails, Notion page ids)
that the apply step resolves to Notes ids.
"""

from __future__ import annotations

import json
import re
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from typing import Any, Optional

from . import formula as fx
from .blocks import Renderer
from .inventory import norm
from .richtext import plain, esc

SOURCE = "notion"
FORBIDDEN = re.compile(r"[&+,:;$^}{*=?@#|'<>.()%!\-]")
NAME_MAX = 255
TEXT_MAX = 1000
LONG_MAX = 20000

# Notion status groups -> Notes state groups
STATUS_GROUP = {
    "to-do": "unstarted",
    "to do": "unstarted",
    "not started": "unstarted",
    "in progress": "started",
    "complete": "completed",
    "done": "completed",
}
# Notion status groups -> the groups of a Notes status field
STATUS_FIELD_GROUP = {
    "to-do": "todo",
    "to do": "todo",
    "not started": "todo",
    "in progress": "in_progress",
    "complete": "complete",
    "done": "complete",
}
# Notion select colors -> hex for Notes options
COLORS = {
    "default": "#9ca3af",
    "gray": "#9ca3af",
    "brown": "#a16207",
    "orange": "#f97316",
    "yellow": "#eab308",
    "green": "#22c55e",
    "blue": "#3b82f6",
    "purple": "#a855f7",
    "pink": "#ec4899",
    "red": "#ef4444",
}
ROLLUP_FN = {
    "count": "count",
    "count_values": "count_not_empty",
    "empty": "count_empty",
    "not_empty": "count_not_empty",
    "sum": "sum",
    "average": "avg",
    "min": "min",
    "max": "max",
    "earliest_date": "earliest",
    "latest_date": "latest",
    "percent_checked": "percent_checked",
    "unique": "unique",
}
NO_TARGET_FN = {"count"}


def clean_board_name(name: str) -> str:
    name = FORBIDDEN.sub(" ", name or "")
    name = " ".join(name.split())
    return (name or "Imported")[:NAME_MAX]


def make_identifier(name: str, taken: set) -> str:
    words = re.findall(r"[A-Za-z0-9]+", name.upper())
    base = "".join(w[0] for w in words)[:5] if len(words) > 1 else (words[0][:5] if words else "NI")
    base = base or "NI"
    ident, n = base, 2
    while ident in taken:
        ident = f"{base[: 12 - len(str(n))]}{n}"
        n += 1
    taken.add(ident)
    return ident


@dataclass
class FieldSpec:
    ext_id: str
    name: str
    field_type: str
    notion_prop: str = ""
    notion_type: str = ""
    role: str = "value"  # value | end | names | snapshot
    options: list = field(default_factory=list)
    settings: dict = field(default_factory=dict)
    # linked fields, resolved at apply time
    relation_target: Optional[str] = None  # board key
    two_way: bool = False
    mirror_of: Optional[str] = None  # ext id of the primary relation (this side is its mirror)
    mirror_name: Optional[str] = None
    rollup: Optional[dict] = None  # {"relation": ext_id, "target": ext_id|@title.., "function"}
    formula_refs: list = field(default_factory=list)  # ext ids this formula reads
    fallback: Optional["FieldSpec"] = None  # snapshot field if the server refuses this one
    note: str = ""


@dataclass
class CardSpec:
    notion_id: str
    board: str
    name: str
    parent: Optional[str] = None
    state: Optional[str] = None  # status option name
    values: dict = field(default_factory=dict)  # field ext id -> neutral value
    body: str = ""
    attachments: list = field(default_factory=list)
    comments: list = field(default_factory=list)
    history: str = ""
    created_at: Optional[str] = None
    created_by_email: Optional[str] = None
    url: str = ""


@dataclass
class BoardSpec:
    key: str
    name: str
    identifier: str
    kind: str  # database | docs
    source_title: str
    path: str = ""
    description: str = ""
    fields: list = field(default_factory=list)
    states: list = field(default_factory=list)  # [{"name","group","color"}]
    status_prop: Optional[str] = None
    templates: list = field(default_factory=list)
    lost: Counter = field(default_factory=Counter)
    changed: Counter = field(default_factory=Counter)
    came_over: Counter = field(default_factory=Counter)
    notes: list = field(default_factory=list)
    card_count: int = 0

    def field_by_ext(self, ext):
        for f in self.fields:
            if f.ext_id == ext:
                return f
        return None


@dataclass
class Plan:
    boards: "OrderedDict[str, BoardSpec]"
    cards: list
    files: dict
    users: dict
    notes: list
    missing: list
    snapshot_roots: list
    db_boards: dict = field(default_factory=dict)  # notion database id -> board key

    def card_ids(self):
        return {c.notion_id for c in self.cards}


class Planner:
    def __init__(
        self, snap: dict, docs_board_name: str = "Docs", icon_in_title: bool = True, exclude: Optional[set] = None
    ):
        self.s = snap
        self.docs_board_name = docs_board_name
        self.icon_in_title = icon_in_title
        self.exclude = {norm(x) for x in (exclude or set())}
        self.pages = snap.get("pages") or {}
        self.dss = snap.get("data_sources") or {}
        self.users = snap.get("users") or {}
        self.files = snap.get("files") or {}
        self.boards: "OrderedDict[str, BoardSpec]" = OrderedDict()
        self.cards: list = []
        self.taken_idents: set = set()
        self.taken_names: set = set()
        self.row_board = {}  # page id -> board key
        self.db_to_ds = {}  # database id -> [ds keys]
        for k, ds in self.dss.items():
            dbid = norm((ds.get("parent") or {}).get("database_id"))
            self.db_to_ds.setdefault(dbid, []).append(k)
            for r in ds.get("rows") or []:
                self.row_board[r] = k

    # ------------------------------------------------------------------
    def build(self) -> Plan:
        for key, ds in self.dss.items():
            if key in self.exclude or norm((ds.get("parent") or {}).get("database_id")) in self.exclude:
                continue
            self._board_for_ds(key, ds)
        for key, ds in self.dss.items():
            if key in self.boards:
                self._linked_fields(key, ds)
        # cards
        placed = set()
        for key, ds in self.dss.items():
            if key not in self.boards:
                continue
            for pid in ds.get("rows") or []:
                self._card_tree(pid, key, None, placed)
        for root in self.s.get("roots") or []:
            if root["kind"] == "page" and root["id"] not in placed:
                self._card_tree(root["id"], "docs", None, placed)
        for key, ds in self.dss.items():
            if key in self.boards:
                self._templates(key, ds)
        for b in self.boards.values():
            b.card_count = sum(1 for c in self.cards if c.board == b.key)
        db_boards = {}
        for dbid, keys in self.db_to_ds.items():
            for k in keys:
                if k in self.boards:
                    db_boards.setdefault(dbid, k)
        return Plan(
            self.boards,
            self.cards,
            self.files,
            self.users,
            list(self.s.get("notes") or []),
            list(self.s.get("missing") or []),
            list(self.s.get("roots") or []),
            db_boards,
        )

    # -- boards ----------------------------------------------------------
    def _unique_board_name(self, title: str, context: str) -> str:
        base = clean_board_name(title)
        name = base
        if name.lower() in self.taken_names and context:
            name = clean_board_name(f"{title} {context}")
        n = 2
        while name.lower() in self.taken_names:
            name = f"{base} {n}"
            n += 1
        self.taken_names.add(name.lower())
        return name

    def _context_title(self, ds: dict) -> str:
        par = ds.get("database_parent") or {}
        if par.get("type") == "page_id":
            p = self.pages.get(norm(par.get("page_id")))
            if p:
                return page_title(p)
        return ""

    def docs_board(self) -> BoardSpec:
        if "docs" not in self.boards:
            name = self._unique_board_name(self.docs_board_name, "")
            b = BoardSpec(
                key="docs",
                name=name,
                identifier=make_identifier(name, self.taken_idents),
                kind="docs",
                source_title="Plain Notion pages",
            )
            b.notes.append("Plain pages land here. Open the board's Pages link to see it as a page list.")
            self.boards["docs"] = b
        return self.boards["docs"]

    def _board_for_ds(self, key: str, ds: dict):
        title = plain(ds.get("title")) or "Untitled database"
        name = self._unique_board_name(title, self._context_title(ds))
        b = BoardSpec(
            key=key, name=name, identifier=make_identifier(name, self.taken_idents), kind="database", source_title=title
        )
        self.boards[key] = b
        props = ds.get("properties") or {}
        rows = [self.pages[r] for r in ds.get("rows") or [] if r in self.pages]
        if ds.get("views"):
            b.lost["saved views (filters, sorts, groups, layouts)"] += len(ds["views"])
        if ds.get("description") and plain(ds.get("description")):
            b.description = plain(ds.get("description"))
            b.changed["database description (put in the board description)"] += 1
        if ds.get("public_url"):
            b.lost["published-to-web setting"] += 1
        status_done = False
        for pname, p in props.items():
            t = p.get("type")
            ext = f"{key}:{p.get('id')}"
            values = [((r.get("properties") or {}).get(pname) or {}) for r in rows]
            if t == "title":
                continue
            if t == "status" and not status_done:
                status_done = True
                b.status_prop = pname
                st = p.get("status") or {}
                group_of = {}
                for g in st.get("groups") or []:
                    for oid in g.get("option_ids") or []:
                        group_of[oid] = STATUS_GROUP.get((g.get("name") or "").lower(), "unstarted")
                for o in st.get("options") or []:
                    b.states.append(
                        {
                            "name": o["name"][:255],
                            "group": group_of.get(o.get("id"), "unstarted"),
                            "color": COLORS.get(o.get("color") or "default", "#9ca3af"),
                        }
                    )
                b.came_over["status (became the card state)"] += 1
                continue
            spec = self._field(key, b, pname, p, ext, values)
            if spec is None:
                continue
            if isinstance(spec, list):
                b.fields.extend(spec)
            else:
                b.fields.append(spec)

    def _field(self, key, b, pname, p, ext, values):
        t = p.get("type")
        name = pname[:255]
        if t in ("rich_text",):
            longest = max([len(plain(v.get("rich_text") or [])) for v in values] or [0])
            b.came_over["text property"] += 1
            return FieldSpec(ext, name, "long_text" if longest > TEXT_MAX else "text", pname, t)
        if t == "number":
            fmt = (p.get("number") or {}).get("format") or "number"
            if fmt in ("dollar",):
                b.came_over["money property"] += 1
                return FieldSpec(ext, name, "money", pname, t)
            plain_number = FieldSpec(
                ext, name, "number", pname, t, settings={"decimals": 2}, note="percent" if fmt == "percent" else ""
            )
            if fmt == "percent":
                b.came_over["percent property"] += 1
                # an older Notes server refuses the percent type: the plain number is the fallback (50 = 50%)
                return FieldSpec(
                    ext, name, "percent", pname, t, settings={"decimals": 2}, note="percent", fallback=plain_number
                )
            if fmt not in ("number", "number_with_commas"):
                b.changed[f"number format '{fmt}' (shown as a plain number)"] += 1
            else:
                b.came_over["number property"] += 1
            return plain_number
        if t in ("select", "multi_select"):
            opts = (p.get(t) or {}).get("options") or []
            b.came_over[f"{t.replace('_', '-')} property"] += 1
            return FieldSpec(
                ext,
                name,
                t,
                pname,
                t,
                options=[{"name": o["name"][:255], "color": COLORS.get(o.get("color") or "default")} for o in opts][
                    :500
                ],
            )
        if t == "status":  # a second status property
            st = p.get("status") or {}
            opts = st.get("options") or []
            group_of = {}
            for g in st.get("groups") or []:
                for oid in g.get("option_ids") or []:
                    group_of[oid] = STATUS_FIELD_GROUP.get((g.get("name") or "").lower(), "todo")
            b.came_over["second status property (a Notes status field)"] += 1
            as_select = FieldSpec(
                ext,
                name,
                "select",
                pname,
                t,
                options=[{"name": o["name"][:255], "color": COLORS.get(o.get("color") or "default")} for o in opts],
            )
            return FieldSpec(
                ext,
                name,
                "status",
                pname,
                t,
                options=[
                    {
                        "name": o["name"][:255],
                        "color": COLORS.get(o.get("color") or "default"),
                        "group": group_of.get(o.get("id"), "todo"),
                    }
                    for o in opts
                ],
                fallback=as_select,
            )
        if t == "date":
            has_time = any(_has_time((v.get("date") or {}).get("start")) for v in values)
            has_end = any((v.get("date") or {}).get("end") for v in values)
            out = [FieldSpec(ext, name, "date", pname, t, settings={"include_time": has_time})]
            if has_end:
                out.append(
                    FieldSpec(
                        ext + ":end",
                        f"{name} end"[:255],
                        "date",
                        pname,
                        t,
                        role="end",
                        settings={"include_time": has_time},
                    )
                )
                b.changed["date range (end date in its own field)"] += 1
            if any((v.get("date") or {}).get("time_zone") for v in values):
                b.changed["date time zone (stored as UTC)"] += 1
            b.came_over["date property"] += 1
            return out
        if t == "checkbox":
            b.came_over["checkbox property"] += 1
            return FieldSpec(ext, name, "checkbox", pname, t)
        if t == "url":
            b.came_over["URL property"] += 1
            return FieldSpec(ext, name, "url", pname, t)
        if t in ("email", "phone_number"):
            kind = "email" if t == "email" else "phone"
            b.came_over[f"{kind} property"] += 1
            return FieldSpec(ext, name, kind, pname, t, fallback=FieldSpec(ext, name, "text", pname, t))
        if t in ("people", "created_by", "last_edited_by"):
            if t != "people":
                b.changed[f"{t.replace('_', ' ')} (kept in a text field)"] += 1
                return FieldSpec(ext, name, "text", pname, t, role="snapshot")
            b.came_over["person property (matched by email)"] += 1
            return [
                FieldSpec(ext, name, "person", pname, t, settings={"multiple": True}),
                FieldSpec(
                    ext + ":names",
                    f"{name} from Notion"[:255],
                    "text",
                    pname,
                    t,
                    role="names",
                    note="people not matched to a Notes member",
                ),
            ]
        if t == "created_time":
            # Notes works this out from the card, and the import sets the card's creation time from Notion
            b.came_over["created time property (a Notes created time field)"] += 1
            return FieldSpec(
                ext, name, "created_time", pname, t, fallback=FieldSpec(ext, name, "text", pname, t, role="snapshot")
            )
        if t == "last_edited_time":  # Notes would show the time of the import, so the Notion time stays as text
            b.changed["last edited time (kept in a text field)"] += 1
            return FieldSpec(ext, name, "text", pname, t, role="snapshot")
        if t == "files":
            b.changed["files property (files became card attachments)"] += 1
            return FieldSpec(ext, name, "text", pname, t, role="snapshot", note="file names")
        if t == "unique_id":
            b.changed["unique ID (kept as text; new cards get Notes ids)"] += 1
            return FieldSpec(ext, name, "text", pname, t, role="snapshot")
        if t in ("place", "location"):
            b.changed["place property (kept as text)"] += 1
            return FieldSpec(ext, name, "text", pname, t, role="snapshot")
        if t == "verification":
            b.lost["wiki verification (state kept as text, no expiry)"] += 1
            return FieldSpec(ext, name, "text", pname, t, role="snapshot")
        if t == "button":
            b.lost["button property"] += 1
            return None
        if t in ("formula", "relation", "rollup"):
            return None  # second pass (needs other boards and fields)
        b.lost[f"{t} property"] += 1
        return FieldSpec(ext, name, "text", pname, t, role="snapshot")

    def _snapshot_spec(self, ext, name, pname, t, values, kind):
        """A frozen copy of a computed value, typed from the values seen."""
        ftype = "text"
        types = Counter()
        for v in values:
            inner = v.get(kind) or {}
            if inner.get("type"):
                types[inner["type"]] += 1
        common = types.most_common(1)[0][0] if types else "string"
        if common == "number":
            ftype = "number"
        elif common == "boolean":
            ftype = "checkbox"
        elif common == "date":
            ftype = "date"
        return FieldSpec(
            ext + ":snapshot",
            name,
            ftype,
            pname,
            t,
            role="snapshot",
            settings={"decimals": 2} if ftype == "number" else ({"include_time": True} if ftype == "date" else {}),
        )

    def _linked_fields(self, key: str, ds: dict):
        b = self.boards[key]
        props = ds.get("properties") or {}
        rows = [self.pages[r] for r in ds.get("rows") or [] if r in self.pages]
        by_name = {f.notion_prop: f for f in b.fields if f.role == "value"}
        # relations first (rollups need them)
        for pname, p in props.items():
            if p.get("type") != "relation":
                continue
            ext = f"{key}:{p.get('id')}"
            rel = p.get("relation") or {}
            target = norm(rel.get("data_source_id") or "")
            if not target and rel.get("database_id"):
                target = (self.db_to_ds.get(norm(rel["database_id"])) or [""])[0]
            snap = FieldSpec(
                ext + ":snapshot",
                pname[:255],
                "text",
                pname,
                "relation",
                role="snapshot",
                note="titles of linked pages",
            )
            if target in self.boards:
                spec = FieldSpec(ext, pname[:255], "relation", pname, "relation", relation_target=target, fallback=snap)
                if rel.get("type") == "dual_property" and target != key:
                    other = rel.get("dual_property") or {}
                    other_name = other.get("synced_property_name")
                    other_id = other.get("synced_property_id")
                    other_ext = f"{target}:{other_id}"
                    if key < target:
                        spec.two_way = True
                        spec.mirror_name = other_name
                    else:
                        spec.mirror_of = other_ext  # the other board creates it; we use its mirror
                b.fields.append(spec)
                by_name[pname] = spec
                b.came_over["relation (linked cards)"] += 1
            else:
                b.fields.append(snap)
                by_name[pname] = snap
                b.changed["relation to a database that was not imported (titles kept as text)"] += 1
        for pname, p in props.items():
            t = p.get("type")
            ext = f"{key}:{p.get('id')}"
            values = [((r.get("properties") or {}).get(pname) or {}) for r in rows]
            if t == "rollup":
                r = p.get("rollup") or {}
                rel_field = by_name.get(r.get("relation_property_name"))
                fn = ROLLUP_FN.get(r.get("function"))
                snap = self._snapshot_spec(ext, pname[:255], pname, t, values, "rollup")
                spec = None
                if rel_field is not None and rel_field.field_type == "relation" and fn:
                    tgt_board = self.boards.get(rel_field.relation_target)
                    tgt_ds = self.dss.get(rel_field.relation_target) or {}
                    tprop = (tgt_ds.get("properties") or {}).get(r.get("rollup_property_name") or "") or {}
                    target = None
                    if fn in NO_TARGET_FN:
                        target = "@title"
                    elif tprop.get("type") == "title":
                        target = "@title"
                    elif tprop.get("type") == "status":
                        target = "@state"
                    elif tgt_board and tprop.get("id"):
                        target = f"{rel_field.relation_target}:{tprop['id']}"
                        tf = tgt_board.field_by_ext(target)
                        if (
                            tf is None
                            or tf.field_type in ("relation", "rollup", "text", "long_text")
                            and fn not in ("count_empty", "count_not_empty", "unique")
                        ):
                            target = None
                    if target:
                        spec = FieldSpec(
                            ext,
                            pname[:255],
                            "rollup",
                            pname,
                            t,
                            rollup={"relation": rel_field.ext_id, "target": target, "function": fn},
                            fallback=snap,
                        )
                if spec:
                    b.fields.append(spec)
                    b.came_over["rollup"] += 1
                else:
                    b.fields.append(snap)
                    b.changed["rollup that cannot be rebuilt (frozen value as text/number)"] += 1
            elif t == "formula":
                expr = names_for_ids((p.get("formula") or {}).get("expression") or "", props)
                snap = self._snapshot_spec(ext, pname[:255], pname, t, values, "formula")
                try:
                    out = fx.translate(expr, lambda n: self._formula_prop(key, n))
                    rtype = {"number": "number", "text": "text", "checkbox": "checkbox", "date": "date"}.get(
                        snap.field_type, "text"
                    )
                    refs = [f"{key}:{(props.get(n) or {}).get('id')}" for n in fx.referenced_props(expr)]
                    if rtype == "number" and any((self._field_type_of(b, r) == "money") for r in refs):
                        rtype = "money"
                    b.fields.append(
                        FieldSpec(
                            ext,
                            pname[:255],
                            "formula",
                            pname,
                            t,
                            settings={"expression": out, "result_type": rtype},
                            formula_refs=refs,
                            fallback=snap,
                        )
                    )
                    b.came_over["formula (rebuilt as a Notes formula)"] += 1
                except fx.Untranslatable as e:
                    snap.note = f"formula not translated: {e}"
                    b.fields.append(snap)
                    b.changed["formula that does not translate (frozen value)"] += 1

    def _field_type_of(self, b, ext):
        f = b.field_by_ext(ext)
        return f.field_type if f else None

    def _formula_prop(self, key: str, notion_name: str) -> Optional[str]:
        ds = self.dss[key]
        p = (ds.get("properties") or {}).get(notion_name)
        if not p:
            return None
        t = p.get("type")
        if t == "title":
            return "Title"
        if t == "status" and self.boards[key].status_prop == notion_name:
            return "State"
        if t == "created_time":
            return "Created"
        if t in (
            "relation",
            "rollup",
            "people",
            "files",
            "button",
            "created_by",
            "last_edited_by",
            "last_edited_time",
            "unique_id",
            "verification",
        ):
            return None
        if t == "formula":
            # formulas referencing formulas work only if that one translated (checked at apply)
            return notion_name[:255]
        return notion_name[:255]

    # -- cards -----------------------------------------------------------
    def _card_tree(self, pid: str, board: str, parent: Optional[str], placed: set):
        if pid in placed or pid in self.exclude:
            return
        page = self.pages.get(pid)
        if page is None or page.get("template_of"):
            return
        placed.add(pid)
        if board == "docs":
            self.docs_board()
        card = self._card(pid, page, board, parent)
        self.cards.append(card)
        for child in card._child_pages:  # type: ignore[attr-defined]
            # a child page lives on the same board as its parent card
            self._card_tree(child, board, pid, placed)

    def _card(self, pid: str, page: dict, board: str, parent: Optional[str]) -> CardSpec:
        b = self.boards[board]
        props = page.get("properties") or {}
        title = page_title(page)
        icon = page.get("icon") or {}
        if icon.get("type") == "emoji" and self.icon_in_title:
            title = f"{icon['emoji']} {title}"
            b.changed["page emoji icon (put in front of the title)"] += 1
        elif icon:
            b.lost["page icon image (Notes cards have no icon)"] += 1
        r = Renderer(self.files)
        body = r.render(page.get("blocks") or [])
        cover = page.get("cover") or {}
        cover_html = ""
        if cover.get("type") == "external" and (cover.get("external") or {}).get("url"):
            cover_html = (
                f'<image-component src="{esc(cover["external"]["url"])}" width="35%" height="auto" '
                f'alignment="left" status="uploaded"></image-component>'
            )
            b.changed["page cover (first image in the body; feeds the Gallery)"] += 1
        elif cover.get("type") == "file" and cover.get("_file"):
            rec = self.files.get(cover["_file"]) or {}
            if rec.get("status") in ("ok",) or str(rec.get("status", "")).startswith("not downloaded"):
                cover_html = (
                    f'<image-component src="@@ASSET:{cover["_file"]}@@" width="35%" height="auto" '
                    f'alignment="left" status="uploaded"></image-component>'
                )
                b.changed["page cover (first image in the body; feeds the Gallery)"] += 1
            else:
                b.lost["page cover over the size limit"] += 1
        for k, v in r.losses.items():
            b.lost[k] += v
        for k, v in r.changed.items():
            b.changed[k] += v
        if page.get("is_locked"):
            b.lost["page lock"] += 1
        if page.get("public_url"):
            b.lost["page published to the web"] += 1
        card = CardSpec(
            notion_id=pid,
            board=board,
            name=(title or "Untitled")[:NAME_MAX],
            parent=parent,
            body=cover_html + body,
            attachments=list(r.attachments),
            created_at=page.get("created_time"),
            created_by_email=self._email(page.get("created_by")),
            url=page.get("url") or "",
        )
        card._child_pages = r.child_pages  # type: ignore[attr-defined]
        # property values
        if b.kind == "database":
            for f in b.fields:
                v = self._value(f, props.get(f.notion_prop) or {}, card)
                if v is not None:
                    card.values[f.ext_id] = v
                if f.fallback is not None:
                    fv = self._value(f.fallback, props.get(f.notion_prop) or {}, card)
                    if fv is not None:
                        card.values[f.fallback.ext_id] = fv
            if b.status_prop:
                st = (props.get(b.status_prop) or {}).get("status") or {}
                card.state = st.get("name") or None
            for prop in props.values():
                if prop.get("type") == "files":
                    for fobj in prop.get("files") or []:
                        if fobj.get("_file"):
                            rec = self.files.get(fobj["_file"]) or {}
                            if rec.get("status") == "too big":
                                b.lost["file in a files property over the size limit"] += 1
                            else:
                                card.attachments.append(fobj["_file"])
        # comments and history
        for c in page.get("comments") or []:
            card.comments.append(c)
        b.came_over["comment"] += len(card.comments)
        card.history = self._history(page)
        b.came_over["page body"] += 1
        return card

    def _email(self, user) -> Optional[str]:
        if not user:
            return None
        email = ((user.get("person") or {}).get("email") or "").lower()
        if email:
            return email
        u = self.users.get(norm(user.get("id")))
        return (u or {}).get("email") or None

    def _user_name(self, user) -> str:
        if not user:
            return "someone"
        if user.get("name"):
            return user["name"]
        u = self.users.get(norm(user.get("id")))
        return (u or {}).get("name") or "a Notion user"

    def _history(self, page: dict) -> str:
        made = page.get("created_time") or ""
        edit = page.get("last_edited_time") or ""
        parts = ["Imported from Notion."]

        def by(user):
            return f" by {self._user_name(user)}" if user else ""

        if made:
            parts.append(f"Created in Notion {made[:16].replace('T', ' ')} UTC{by(page.get('created_by'))}.")
        if edit:
            parts.append(f"Last edited in Notion {edit[:16].replace('T', ' ')} UTC{by(page.get('last_edited_by'))}.")
        if page.get("url"):
            parts.append(f'Notion page: <a href="{esc(page["url"])}">{esc(page["url"])}</a>')
        return "<p>" + " ".join(parts) + "</p>"

    def _value(self, f: FieldSpec, prop: dict, card: CardSpec) -> Any:
        t = prop.get("type")
        if not t:
            return None
        if f.field_type in ("formula", "rollup"):
            return None  # computed by Notes
        if f.role == "end":
            d = prop.get("date") or {}
            return _date_value(d.get("end"), f.settings.get("include_time"))
        if f.role == "names":
            # everyone; the apply step keeps the ones it cannot match to a Notes member
            people = [{"name": self._user_name(u), "email": self._email(u) or ""} for u in prop.get("people") or []]
            return people or None
        if f.field_type == "relation":
            return [norm(x.get("id")) for x in prop.get("relation") or []]
        if f.role == "snapshot" or t == "created_time":  # created time: only the text fallback is ever written
            return _snapshot_value(f, prop, self)
        if t == "rich_text":
            text = plain(prop.get("rich_text"))
            return text[: LONG_MAX if f.field_type == "long_text" else TEXT_MAX] or None
        if t == "number":
            n = prop.get("number")
            if n is None:
                return None
            if f.field_type == "money":
                return int(round(n * 100))
            if f.note == "percent":
                return round(n * 100, 6)
            return n
        if t == "select":
            return (prop.get("select") or {}).get("name")
        if t == "status":
            return (prop.get("status") or {}).get("name")
        if t == "multi_select":
            return [o.get("name") for o in prop.get("multi_select") or []] or None
        if t == "date":
            d = prop.get("date") or {}
            return _date_value(d.get("start"), f.settings.get("include_time"))
        if t == "checkbox":
            return bool(prop.get("checkbox"))
        if t == "url":
            return prop.get("url") or None
        if t == "email":
            return prop.get("email") or None
        if t == "phone_number":
            return prop.get("phone_number") or None
        if t == "people":
            emails = [self._email(u) for u in prop.get("people") or []]
            return [e for e in emails if e] or None
        return None

    # -- templates -------------------------------------------------------
    def _templates(self, key: str, ds: dict):
        b = self.boards[key]
        for t in ds.get("templates") or []:
            page = self.pages.get(t.get("id"))
            if page is None:
                b.lost["database template (could not be read)"] += 1
                continue
            fake = CardSpec(notion_id=t["id"], board=key, name="")
            props = page.get("properties") or {}
            for f in b.fields:
                v = self._value(f, props.get(f.notion_prop) or {}, fake)
                if v is not None and f.field_type not in ("relation", "rollup", "formula"):
                    fake.values[f.ext_id] = v
            r = Renderer(self.files)
            body = r.render(page.get("blocks") or [])
            for k, v in r.losses.items():
                b.lost[f"{k} (in a template)"] += v
            st = None
            if b.status_prop:
                st = ((props.get(b.status_prop) or {}).get("status") or {}).get("name")
            b.templates.append(
                {
                    "notion_id": t["id"],
                    "name": (t.get("name") or page_title(page) or "Template")[:255],
                    "title": page_title(page) if page_title(page) != "Untitled" else "",
                    "body": body,
                    "values": fake.values,
                    "state": st,
                    "is_default": t.get("is_default", False),
                    "attachments": r.attachments,
                }
            )
            b.came_over["database template (became a card template)"] += 1
            if r.attachments:
                b.lost["file inside a template (templates hold no attachments)"] += len(r.attachments)
            if r.child_pages:
                b.lost["sub-page inside a template"] += len(r.child_pages)


_INTERNAL_REF = re.compile(r"\{\{notion:block_property:([^:}]+)(?::[^}]*)?\}\}")


def names_for_ids(expression: str, props: dict) -> str:
    """Some Notion API versions return formulas with internal property ids
    ({{notion:block_property:<id>:...}}) instead of prop("Name"); turn them back into names."""
    from urllib.parse import unquote

    by_id = {}
    for name, p in props.items():
        pid = p.get("id") or ""
        by_id[pid] = name
        by_id[unquote(pid)] = name

    def swap(m):
        name = by_id.get(m.group(1)) or by_id.get(unquote(m.group(1)))
        if name is None:
            return m.group(0)  # unknown id: the translator refuses it, value is frozen
        return "prop(" + json.dumps(name, ensure_ascii=False) + ")"

    return _INTERNAL_REF.sub(swap, expression or "")


def page_title(page: dict) -> str:
    for prop in (page.get("properties") or {}).values():
        if prop.get("type") == "title":
            return plain(prop.get("title") or []) or "Untitled"
    return "Untitled"


def _has_time(s: Optional[str]) -> bool:
    return bool(s and "T" in s)


def _date_value(s: Optional[str], include_time: bool) -> Optional[str]:
    if not s:
        return None
    if include_time:
        if "T" not in s:
            return s + "T00:00:00Z"
        return s
    return s[:10]


def _snapshot_value(f: FieldSpec, prop: dict, planner: Planner):
    t = prop.get("type")
    if t == "formula":
        v = prop.get("formula") or {}
        return _typed(f, v.get(v.get("type") or "string"), v.get("type"))
    if t == "rollup":
        v = prop.get("rollup") or {}
        rt = v.get("type")
        if rt == "array":
            parts = []
            for item in v.get("array") or []:
                parts.append(_plain_value(item, planner))
            return _typed(f, ", ".join(p for p in parts if p), "string")
        return _typed(f, v.get(rt), rt)
    if t == "relation":
        titles = []
        for x in prop.get("relation") or []:
            pg = planner.pages.get(norm(x.get("id")))
            titles.append(page_title(pg) if pg else "(page not imported)")
        return ", ".join(titles)[:TEXT_MAX] or None
    return (_plain_value(prop, planner) or None) if f.field_type in ("text", "long_text") else None


def _typed(f: FieldSpec, value, vtype):
    if value is None or value == "":
        return None
    if f.field_type == "number":
        return value if isinstance(value, (int, float)) else None
    if f.field_type == "checkbox":
        return bool(value)
    if f.field_type == "date":
        return _date_value((value or {}).get("start") if isinstance(value, dict) else value, True)
    if isinstance(value, dict) and "start" in value:
        return value.get("start")
    return str(value)[:TEXT_MAX]


def _plain_value(prop: dict, planner: Planner) -> str:
    """Any Notion property value as short plain text."""
    t = prop.get("type")
    v = prop.get(t)
    if t in ("title", "rich_text"):
        return plain(v)
    if t in ("select", "status"):
        return (v or {}).get("name") or ""
    if t == "multi_select":
        return ", ".join(o.get("name", "") for o in v or [])
    if t == "date":
        if not v:
            return ""
        return v.get("start", "") + (f" to {v['end']}" if v.get("end") else "")
    if t in ("created_time", "last_edited_time"):
        return (v or "")[:16].replace("T", " ")
    if t in ("created_by", "last_edited_by"):
        return planner._user_name(v)
    if t == "people":
        return ", ".join(planner._user_name(u) for u in v or [])
    if t == "files":
        return ", ".join(f.get("name", "") for f in v or [])
    if t == "unique_id":
        if not v:
            return ""
        return f"{v.get('prefix') + '-' if v.get('prefix') else ''}{v.get('number')}"
    if t == "verification":
        return (v or {}).get("state") or ""
    if t in ("place", "location"):
        if isinstance(v, dict):
            return v.get("address") or v.get("name") or ""
        return ""
    if t == "number":
        return "" if v is None else str(v)
    if t == "checkbox":
        return "Yes" if v else "No"
    if t in ("url", "email", "phone_number"):
        return v or ""
    if t == "formula":
        return str((v or {}).get((v or {}).get("type")) or "")
    return ""
