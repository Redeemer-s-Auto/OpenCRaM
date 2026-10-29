"""Apply: create or update the planned boards, fields, cards and templates in Notes.

Re-runnable. Every object carries external_source="notion" and an external_id
(the Notion id), so a second run finds what the first one made and updates it
instead of making a duplicate.
"""

from __future__ import annotations

import mimetypes
import os
import re
import json
from collections import Counter
from typing import Optional

from .http import HTTPError
from .plan import SOURCE, FieldSpec, Plan, make_identifier
from .richtext import esc

LINKED = ("relation", "rollup", "formula")
STATE_FILE = "notes-state.json"


class ImportAborted(Exception):
    """Stop before anything lands somewhere it should not (a board that is not private, a lost board)."""


PLACEHOLDER = re.compile(r"@@(CARD|BOARD|ASSET|FILE):([0-9a-zA-Z]+)@@")
ANCHOR = re.compile(r'<a href="@@(CARD|BOARD|FILE):([0-9a-zA-Z]+)@@"([^>]*)>(.*?)</a>', re.S)
IMAGE = re.compile(r'<image-component src="@@ASSET:([0-9a-zA-Z]+)@@"[^>]*></image-component>')


def dashed(h: str) -> str:
    h = h.replace("-", "").lower()
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}" if len(h) == 32 else h


class Applier:
    def __init__(
        self,
        notes,
        plan: Plan,
        snapshot_dir: str,
        log=print,
        private: bool = True,
        public_url: Optional[str] = None,
        max_file_bytes: int = 10 * 1024 * 1024,
    ):
        self.n = notes
        self.plan = plan
        self.dir = snapshot_dir
        self.log = log
        self.private = private
        self.web = (public_url or notes.base).rstrip("/")
        self.max_file_bytes = max_file_bytes
        self.projects = {}  # board key -> project dict
        self.fields = {}  # field ext id -> Notes field dict
        self.used_fallback = set()  # primary ext ids replaced by their snapshot
        self.states = {}  # board key -> {lower name: state id}
        self.cards = {}  # notion page id -> {"id", "project", "sequence_id"}
        self.members = {}  # email -> user id
        self.result = {
            "created": Counter(),
            "updated": Counter(),
            "skipped": [],
            "errors": [],
            "warnings": [],
            "boards": {},
        }
        self.assets = {}  # (board, file key) -> asset id
        self.existing_cards = set()  # notion ids of cards found from an earlier run
        self.state_path = os.path.join(snapshot_dir, STATE_FILE)
        self.state = self._read_state()

    # -- local record of the boards this snapshot made (guards against duplicates) --
    def _state_key(self):
        return f"{self.n.base}|{self.n.ws}"

    def _read_state(self):
        try:
            with open(self.state_path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return {}

    def _write_state(self):
        boards = self.state.setdefault(self._state_key(), {})
        for key, p in self.projects.items():
            boards[key] = p.get("id")
        with open(self.state_path, "w", encoding="utf-8") as fh:
            json.dump(self.state, fh, indent=1)

    # -- entry ---------------------------------------------------------------
    def run(self):
        self._load_members()
        visible = self.n.projects()
        by_ext = {p.get("external_id"): p for p in visible if p.get("external_source") == SOURCE}
        visible_ids = {p.get("id") for p in visible}
        for key, pid in self.state.get(self._state_key(), {}).items():
            if key in self.plan.boards and pid not in visible_ids:
                raise ImportAborted(
                    f"The board for '{self.plan.boards[key].source_title}' was made by an earlier run "
                    f"(id {pid}) but this API key cannot see it. Run the import with the same person's "
                    "key, or add that person to the board. No second copy is made."
                )
        for b in self.plan.boards.values():
            self._project(b, by_ext)
            self._write_state()
        for b in self.plan.boards.values():
            self._states(b)
        for b in self.plan.boards.values():
            self._load_fields(b)
            for f in b.fields:
                if f.field_type not in LINKED and not f.mirror_of:
                    self._field(b, f)
        for b in self.plan.boards.values():
            for f in b.fields:
                if f.field_type == "relation" and not f.mirror_of:
                    self._field(b, f)
        for b in self.plan.boards.values():
            for f in b.fields:
                if f.mirror_of:
                    self._mirror(b, f)
        for b in self.plan.boards.values():  # formulas first: a rollup may total a formula field
            for f in self._formula_order(b):
                self._field(b, f)
        for b in self.plan.boards.values():
            for f in b.fields:
                if f.field_type == "rollup":
                    self._field(b, f)
        self._cards_pass1()
        self._cards_pass2()
        for b in self.plan.boards.values():
            self._templates(b)
        return self.result

    # -- people ----------------------------------------------------------------
    def _load_members(self):
        try:
            for m in self.n.members():
                member = m.get("member") if isinstance(m.get("member"), dict) else m
                email = (member.get("email") or "").lower()
                if email:
                    self.members[email] = member.get("id")
        except HTTPError as e:
            self.result["warnings"].append(f"Could not list workspace members ({e.status}); people stay as text.")

    # -- boards ----------------------------------------------------------------
    def _project(self, b, by_ext):
        ext = b.key
        p = by_ext.get(ext)
        if p:
            self.projects[b.key] = p
            self.result["updated"]["board"] += 1
            self.result["boards"][b.key] = {
                "name": p.get("name"),
                "id": p.get("id"),
                "identifier": p.get("identifier"),
                "private": p.get("is_private"),
            }
            return
        taken = {x.get("identifier") for x in self.n.projects()}
        ident = b.identifier
        if ident in taken:
            ident = make_identifier(b.name, set(taken))
        name = b.name
        payload = {
            "name": name,
            "identifier": ident,
            "external_source": SOURCE,
            "external_id": ext,
            "description": (
                f"Imported from Notion: {b.source_title}." + (f" {b.description}" if b.description else "")
            )[:2000],
        }
        if self.private:
            payload.update({"network": 0, "is_private": True})
        for attempt in range(6):
            try:
                p = self.n.create_project(payload)
                break
            except HTTPError as e:
                body = e.json() or {}
                if e.status == 409 and "identifier" in body:
                    taken.add(payload["identifier"])
                    payload["identifier"] = make_identifier(name, set(taken))
                    continue
                if e.status == 409 and "name" in body:
                    payload["name"] = f"{b.name} Notion {attempt + 1}" if attempt else f"{b.name} Notion"
                    continue
                raise
        else:
            raise RuntimeError(f"could not create board {b.name}")
        self.projects[b.key] = p
        if self.private and not p.get("is_private"):
            try:
                p = self.n.update_project(p["id"], {"is_private": True, "network": 0})
            except HTTPError:
                pass
            if not p.get("is_private"):
                self._write_state()
                raise ImportAborted(
                    f"Board '{p.get('name')}' was created but this Notes server did not make it private, "
                    "so the import stopped before any card was copied. Update the server (its v1 API "
                    "must accept is_private), or make the board private by hand and run again."
                )
            self.projects[b.key] = p
        self.result["created"]["board"] += 1
        self.result["boards"][b.key] = {
            "name": p.get("name"),
            "id": p.get("id"),
            "identifier": p.get("identifier"),
            "private": p.get("is_private"),
        }
        self.log(f"board: {p.get('name')} ({p.get('identifier')})")

    def _pid(self, board_key):
        return self.projects[board_key]["id"]

    def _states(self, b):
        pid = self._pid(b.key)
        have = {s["name"].lower(): s["id"] for s in self.n.states(pid)}
        for st in b.states:
            if st["name"].lower() in have:
                continue
            try:
                s = self.n.create_state(pid, {"name": st["name"], "group": st["group"], "color": st["color"]})
                have[st["name"].lower()] = s["id"]
                self.result["created"]["state"] += 1
            except HTTPError as e:
                if e.status == 409 and (e.json() or {}).get("id"):
                    have[st["name"].lower()] = e.json()["id"]
                else:
                    self.result["errors"].append(f"state '{st['name']}' on {b.name}: {e}")
        self.states[b.key] = have

    # -- fields ----------------------------------------------------------------
    def _load_fields(self, b):
        self._existing = getattr(self, "_existing", {})
        pid = self._pid(b.key)
        self._existing[b.key] = self.n.fields(pid)

    def _existing_field(self, b, ext=None, name=None):
        for f in self._existing.get(b.key, []):
            if ext and f.get("external_source") == SOURCE and f.get("external_id") == ext:
                return f
        if name:
            for f in self._existing.get(b.key, []):
                if (f.get("name") or "").lower() == name.lower():
                    return f
        return None

    def _payload(self, b, f: FieldSpec) -> Optional[dict]:
        p = {"name": f.name, "field_type": f.field_type, "external_source": SOURCE, "external_id": f.ext_id}
        if f.options:
            p["options"] = f.options
        settings = dict(f.settings)
        if f.field_type == "relation":
            if f.relation_target not in self.projects:
                return None
            settings = {"target_project_id": self._pid(f.relation_target), "two_way": bool(f.two_way)}
            if f.two_way and f.mirror_name:
                settings["mirror_name"] = f.mirror_name
        if f.field_type == "rollup":
            rel = self.fields.get(f.rollup["relation"])
            if rel is None or f.rollup["relation"] in self.used_fallback:
                return None
            target = f.rollup["target"]
            if not target.startswith("@"):
                tf = self.fields.get(target)
                if tf is None or target in self.used_fallback:
                    return None
                target = tf["id"]
            settings = {"relation_field_id": rel["id"], "target_field_id": target, "function": f.rollup["function"]}
        if settings:
            p["settings"] = settings
        return p

    def _field(self, b, f: FieldSpec):
        found = self._existing_field(b, ext=f.ext_id)
        if found:
            self.fields[f.ext_id] = found
            if f.options:
                self._add_missing_options(b, f.ext_id, [o["name"] for o in f.options])
            self.result["updated"]["field"] += 1
            return
        if f.fallback is not None:
            fb = self._existing_field(b, ext=f.fallback.ext_id)
            if fb:  # an earlier run already fell back
                self.fields[f.fallback.ext_id] = fb
                self.used_fallback.add(f.ext_id)
                return
        payload = self._payload(b, f)
        if payload is None:
            if f.fallback is not None:
                return self._use_fallback(b, f, "what it is built from did not come over")
            return
        clash = self._existing_field(b, name=f.name)
        if clash:
            payload["name"] = f"{f.name} Notion"[:255]
        try:
            res = self.n.create_field(self._pid(b.key), payload)
        except HTTPError as e:
            if f.fallback is not None and e.status == 400:
                return self._use_fallback(b, f, f"Notes refused it: {e.body[:200]}")
            self.result["errors"].append(f"field '{f.name}' on {b.name}: {e}")
            return
        self.fields[f.ext_id] = res
        self._existing[b.key].append(res)
        self.result["created"]["field"] += 1

    def _use_fallback(self, b, f, why):
        self.used_fallback.add(f.ext_id)
        b.changed[f"{f.field_type} kept as a frozen value ({why.split(':')[0]})"] += 1
        self.result["warnings"].append(f"{b.name}: '{f.name}' {f.field_type} became a frozen value - {why}")
        self._field(b, f.fallback)

    def _mirror(self, b, f: FieldSpec):
        primary = self.fields.get(f.mirror_of)
        mirror_id = ((primary or {}).get("settings") or {}).get("mirror_field_id")
        if primary is not None and f.mirror_of not in self.used_fallback and mirror_id:
            self.fields[f.ext_id] = {"id": mirror_id, "field_type": "relation", "mirror": True}
            return
        # no two-way partner: make this side its own one-way relation
        f.mirror_of = None
        self._field(b, f)

    def _formula_order(self, b):
        formulas = [f for f in b.fields if f.field_type == "formula"]
        ext = {f.ext_id for f in formulas}
        done, out = set(), []
        for _ in range(len(formulas) + 1):
            for f in formulas:
                if f.ext_id in done:
                    continue
                if all(r not in ext or r in done for r in f.formula_refs):
                    done.add(f.ext_id)
                    out.append(f)
        out.extend(f for f in formulas if f.ext_id not in done)  # loops: Notes will refuse, fallback
        return out

    def _add_missing_options(self, b, ext, names):
        field = self.fields.get(ext)
        if not field:
            return
        have = {(o.get("name") or "").lower() for o in field.get("options") or []}
        missing = [n for n in names if n and n.lower() not in have]
        if not missing:
            return
        options = list(field.get("options") or []) + [{"name": n} for n in missing]
        try:
            res = self.n.update_field(self._pid(b.key), field["id"], {"options": options[:500]})
            self.fields[ext] = res
        except HTTPError as e:
            self.result["errors"].append(f"options for '{field.get('name')}' on {b.name}: {e}")

    def _option_id(self, b, ext, name):
        field = self.fields.get(ext) or {}
        for o in field.get("options") or []:
            if (o.get("name") or "").lower() == (name or "").lower():
                return o.get("id")
        self._add_missing_options(b, ext, [name])
        for o in (self.fields.get(ext) or {}).get("options") or []:
            if (o.get("name") or "").lower() == (name or "").lower():
                return o.get("id")
        return None

    # -- values ----------------------------------------------------------------
    def _target_ext(self, f: FieldSpec) -> Optional[str]:
        """Which Notes field holds this spec's values (the field or its fallback)."""
        if f.ext_id in self.used_fallback:
            return f.fallback.ext_id if f.fallback else None
        return f.ext_id

    def _values(self, card, include_relations: bool, clear: bool = False) -> dict:
        b = self.plan.boards[card.board]
        out = {}
        for f in b.fields:
            spec = f
            if f.ext_id in self.used_fallback:
                spec = f.fallback
            if spec is None or spec.field_type in ("formula", "rollup", "created_time") or f.mirror_of:
                continue
            if f.field_type == "relation" and spec is f and not include_relations:
                continue
            field = self.fields.get(spec.ext_id)
            if not field or field.get("mirror"):
                continue
            v = card.values.get(spec.ext_id)
            if v is None:
                if clear:  # emptied in Notion since the last run: empty it here too
                    out[field["id"]] = None
                continue
            if spec.field_type in ("select", "status"):
                v = self._option_id(b, spec.ext_id, v)
            elif spec.field_type == "multi_select":
                v = [x for x in (self._option_id(b, spec.ext_id, n) for n in v) if x]
            elif spec.field_type == "person":
                ids = [self.members[e] for e in v if e in self.members]
                v = ids or None
            elif spec.role == "names":
                unmatched = [p["name"] for p in v if (p.get("email") or "").lower() not in self.members]
                v = ", ".join(unmatched)[:1000] or None
            elif spec.field_type == "relation":
                v = [self.cards[x]["id"] for x in v if x in self.cards]
            if v is None or v == []:
                if clear:
                    out[field["id"]] = None
                continue
            out[field["id"]] = v
        return out

    # -- cards -----------------------------------------------------------------
    def _ordered_cards(self):
        by_id = {c.notion_id: c for c in self.plan.cards}
        out, seen = [], set()

        def visit(c, depth=0):
            if c.notion_id in seen:
                return
            if c.parent and c.parent in by_id and depth < 50:
                visit(by_id[c.parent], depth + 1)
            seen.add(c.notion_id)
            out.append(c)

        for c in self.plan.cards:
            visit(c)
        return out

    def _card_payload(self, c, full: bool, clear: bool = False):
        p = {"name": c.name, "external_source": SOURCE, "external_id": dashed(c.notion_id)}
        if c.state:
            sid = self.states.get(c.board, {}).get(c.state.lower())
            if sid:
                p["state"] = sid
        if c.parent and c.parent in self.cards:
            p["parent"] = self.cards[c.parent]["id"]
        values = self._values(c, include_relations=full, clear=clear)
        if values:
            p["custom_fields"] = values
        body = c.body
        if "@@" not in body:
            p["description_html"] = body or "<p></p>"
        elif full:
            p["description_html"] = self._fill(c, body)
        return p

    def _cards_pass1(self):
        for c in self._ordered_cards():
            pid = self._pid(c.board)
            payload = self._card_payload(c, full=False)
            if c.created_at:
                payload["created_at"] = c.created_at
            if c.created_by_email and c.created_by_email in self.members:
                payload["created_by"] = self.members[c.created_by_email]
            try:
                res = self.n.create_card(pid, payload)
                self.result["created"]["card"] += 1
            except HTTPError as e:
                body = e.json() or {}
                if e.status == 409 and body.get("id"):
                    self.existing_cards.add(c.notion_id)
                    res = self._update_card(c, pid, body["id"], self._card_payload(c, full=False, clear=True))
                    self.result["updated"]["card"] += 1
                elif e.status == 400 and "custom_fields" in body:
                    # one bad value must not lose the card: save it without the values, report them
                    self.result["errors"].append(f"card '{c.name}' values refused: {e.body[:300]}")
                    payload.pop("custom_fields", None)
                    try:
                        res = self.n.create_card(pid, payload)
                        self.result["created"]["card"] += 1
                    except HTTPError as e2:
                        if e2.status == 409 and (e2.json() or {}).get("id"):
                            res = {"id": e2.json()["id"]}
                        else:
                            self.result["errors"].append(f"card '{c.name}': {e2}")
                            continue
                else:
                    self.result["errors"].append(f"card '{c.name}': {e}")
                    continue
            seq = res.get("sequence_id")
            if seq is None:
                try:
                    seq = self.n.get_card(pid, res["id"]).get("sequence_id")
                except HTTPError:
                    seq = None
            self.cards[c.notion_id] = {
                "id": res["id"],
                "project": pid,
                "sequence_id": seq,
                "identifier": self.projects[c.board].get("identifier"),
            }

    def _update_card(self, c, pid, card_id, payload):
        """PATCH a card; if a field value is refused, still save everything else."""
        try:
            return self.n.update_card(pid, card_id, payload)
        except HTTPError as e:
            if e.status == 400 and "custom_fields" in (e.json() or {}) and payload.get("custom_fields"):
                self.result["errors"].append(f"card '{c.name}' values refused: {e.body[:300]}")
                rest = {k: v for k, v in payload.items() if k != "custom_fields"}
                try:
                    return self.n.update_card(pid, card_id, rest)
                except HTTPError as e2:
                    self.result["errors"].append(f"card '{c.name}': {e2}")
            else:
                self.result["errors"].append(f"card '{c.name}': {e}")
            return {"id": card_id}

    def _cards_pass2(self):
        for c in self._ordered_cards():
            if c.notion_id not in self.cards:
                continue
            info = self.cards[c.notion_id]
            pid = info["project"]
            # files first: the body links to them
            for key in dict.fromkeys(c.attachments):
                self._attach(c, key)
            rerun = c.notion_id in self.existing_cards
            needs = (
                rerun
                or ("@@" in c.body)
                or any(
                    f.field_type == "relation"
                    and c.values.get(f.ext_id)
                    and f.ext_id not in self.used_fallback
                    and not f.mirror_of
                    for f in self.plan.boards[c.board].fields
                )
            )
            if needs:
                payload = {}
                values = self._values(c, include_relations=True, clear=rerun)
                if values:
                    payload["custom_fields"] = values
                if "@@" in c.body:
                    payload["description_html"] = self._fill(c, c.body)
                if payload:
                    self._update_card(c, pid, info["id"], payload)
            self._comments(c, info)

    # -- body ------------------------------------------------------------------
    def card_url(self, notion_id: str) -> Optional[str]:
        info = self.cards.get(notion_id)
        if not info or info.get("sequence_id") is None:
            return None
        return f"{self.web}/{self.n.ws}/browse/{info['identifier']}-{info['sequence_id']}/"

    def board_url(self, database_id: str) -> Optional[str]:
        key = self.plan.db_boards.get(database_id)
        if key and key in self.projects:
            return f"{self.web}/{self.n.ws}/projects/{self._pid(key)}/issues/"
        return None

    def _fill(self, c, body: str) -> str:
        b = self.plan.boards[c.board]

        def image(m):
            key = m.group(1)
            asset = self._image(c, key)
            if not asset:
                return "<p><em>[From Notion: image could not be uploaded]</em></p>"
            return m.group(0).replace(f"@@ASSET:{key}@@", asset)

        body = IMAGE.sub(image, body)

        def anchor(m):
            kind, key, attrs, text = m.group(1), m.group(2), m.group(3), m.group(4)
            url = None
            if kind == "CARD":
                url = self.card_url(key)
                if not url:
                    b.changed["link to a page that was not imported (kept as plain text)"] += 1
            elif kind == "BOARD":
                url = self.board_url(key)
            elif kind == "FILE":
                url = self.attachments_url(c)
            if not url:
                return text
            return f'<a href="{esc(url)}"{attrs}>{text}</a>'

        body = ANCHOR.sub(anchor, body)
        return PLACEHOLDER.sub("", body)

    def attachments_url(self, c) -> Optional[str]:
        info = self.cards.get(c.notion_id)
        return self.card_url(c.notion_id) if info else None

    def _file_bytes(self, key):
        rec = self.plan.files.get(key) or {}
        if rec.get("status") != "ok" or not rec.get("path"):
            return None, rec
        if rec.get("size") and rec["size"] > self.max_file_bytes:
            return None, rec
        path = os.path.join(self.dir, rec["path"])
        try:
            with open(path, "rb") as fh:
                return fh.read(), rec
        except OSError:
            return None, rec

    def _image(self, c, key) -> Optional[str]:
        if (c.board, key) in self.assets:
            return self.assets[(c.board, key)]
        data, rec = self._file_bytes(key)
        if data is None:
            self.result["skipped"].append(f"image '{rec.get('name')}' on '{c.name}': {rec.get('status')}")
            return None
        mime = mimetypes.guess_type(rec.get("name") or "")[0] or "image/png"
        try:
            asset = self.n.upload_image(
                self._pid(c.board), rec.get("name") or "image", mime, data, ext_id=f"{c.board}:{key}"
            )
        except (HTTPError, RuntimeError) as e:
            self.result["errors"].append(f"image '{rec.get('name')}' on '{c.name}': {e}")
            return None
        self.assets[(c.board, key)] = asset
        self.result["updated" if getattr(self.n, "last_image_reused", False) else "created"]["image"] += 1
        return asset

    def _attach(self, c, key):
        data, rec = self._file_bytes(key)
        if data is None:
            self.result["skipped"].append(f"file '{rec.get('name')}' on '{c.name}': {rec.get('status')}")
            return
        info = self.cards[c.notion_id]
        mime = mimetypes.guess_type(rec.get("name") or "")[0] or "application/octet-stream"
        try:
            res = self.n.attach(
                info["project"], info["id"], rec.get("name") or "file", mime, data, ext_id=f"{c.notion_id}:{key}"
            )
            self.result["updated" if res.get("existing") else "created"]["attachment"] += 1
        except HTTPError as e:
            self.result["errors"].append(f"file '{rec.get('name')}' on '{c.name}': {e}")

    # -- comments --------------------------------------------------------------
    def _comments(self, c, info):
        pid, cid = info["project"], info["id"]
        items = [("notion-history:" + c.notion_id, c.history, None, None)]
        users = self.plan.users
        for cm in c.comments:
            author = users.get(cm.get("created_by") or "") or {}
            email = (author.get("email") or "").lower()
            html = _rich_html(cm.get("rich_text"))
            uid = self.members.get(email) if email else None
            if not uid:
                html = f"<p><em>Originally by {esc(author.get('name') or 'a Notion user')}:</em></p>" + html
            items.append((cm.get("id"), html, uid, cm.get("created_time")))
        for ext, html, uid, when in items:
            if not html:
                continue
            payload = {"comment_html": html, "access": "INTERNAL", "external_source": SOURCE, "external_id": ext}
            if uid:
                payload["created_by"] = uid
            if when:
                payload["created_at"] = when
            try:
                self.n.add_comment(pid, cid, payload)
                self.result["created"]["comment"] += 1
            except HTTPError as e:
                if e.status == 409 and (e.json() or {}).get("id"):
                    try:
                        self.n.update_comment(pid, cid, e.json()["id"], {"comment_html": html})
                    except HTTPError:
                        pass
                    self.result["updated"]["comment"] += 1
                else:
                    self.result["errors"].append(f"comment on '{c.name}': {e}")

    # -- templates -------------------------------------------------------------
    def _templates(self, b):
        if not b.templates:
            return
        pid = self._pid(b.key)
        try:
            have = {t["name"].lower(): t for t in self.n.templates(pid)}
        except HTTPError as e:
            self.result["warnings"].append(
                f"{b.name}: card templates not available on this server ({e.status}); "
                f"{len(b.templates)} Notion template(s) not brought over."
            )
            return
        fake_card = type("C", (), {})()
        seen = Counter()
        for t in b.templates:
            seen[t["name"].lower()] += 1
            if seen[t["name"].lower()] > 1:  # two Notion templates with one name: keep both
                t = dict(t, name=f"{t['name']} {seen[t['name'].lower()]}"[:255])
            fake_card.board, fake_card.values, fake_card.notion_id = b.key, t["values"], t["notion_id"]
            values = self._values(fake_card, include_relations=False)
            body = PLACEHOLDER.sub("", ANCHOR.sub(lambda m: m.group(4), IMAGE.sub("", t["body"])))
            data = {"name": t.get("title") or "", "description_html": body or "<p></p>", "custom_fields": values}
            if t.get("state"):
                sid = self.states.get(b.key, {}).get(t["state"].lower())
                if sid:
                    data["state_id"] = sid
            payload = {"name": t["name"], "description": "Imported from a Notion database template", "data": data}
            try:
                if t["name"].lower() in have:
                    self.n.update_template(pid, have[t["name"].lower()]["id"], payload)
                    self.result["updated"]["template"] += 1
                else:
                    self.n.create_template(pid, payload)
                    self.result["created"]["template"] += 1
            except HTTPError as e:
                self.result["errors"].append(f"template '{t['name']}' on {b.name}: {e}")


def _rich_html(rich) -> str:
    from .richtext import to_html

    text = to_html(rich or [])
    return f"<p>{text}</p>" if text else ""
