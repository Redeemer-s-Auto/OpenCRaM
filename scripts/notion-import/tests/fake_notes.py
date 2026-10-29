"""An in-memory stand-in for the Notes v1 API (only what the importer calls).

It copies the server rules the importer depends on: external_source +
external_id is unique per project and a duplicate answers 409 with the
existing id; select values must be option ids; relation values must be card
ids on the target board; formula fields with an unknown function are refused.
"""

import json
import re
import uuid
from urllib.parse import parse_qs, urlparse


def _id():
    return str(uuid.uuid4())


class FakeNotes:
    def __init__(self, members=None, rate_limit_every=0, support_private=True, support_templates=True):
        self.projects = {}
        self.states = {}
        self.fields = {}
        self.cards = {}
        self.comments = {}
        self.assets = {}
        self.attachments = {}
        self.templates = {}
        self.uploads = []
        self.calls = []
        self.members = members or [
            {"id": "user-pat", "email": "pat@example.org", "display_name": "pat"},
            {"id": "user-me", "email": "me@example.org", "display_name": "me"},
        ]
        self.rate_limit_every = rate_limit_every
        self.support_private = support_private
        self.support_templates = support_templates
        self.n = 0
        self.hidden_projects = set()  # projects the API key's user cannot see
        self.fail_uploads = 0  # how many storage uploads fail before they work
        self.refuse_field_names = set()  # PATCH values for these field names are refused (400)

    # transport signature: (method, url, headers, body) -> (status, headers, bytes)
    def __call__(self, method, url, headers, body):
        self.n += 1
        if self.rate_limit_every and self.n % self.rate_limit_every == 0:
            return 429, {"Retry-After": "1"}, b'{"error_code": 5900}'
        u = urlparse(url)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        data = json.loads(body) if body else {}
        self.calls.append((method, u.path, data))
        status, out = self.route(method, u.path, q, data)
        return status, {}, json.dumps(out).encode() if out is not None else b""

    def upload(self, method, url, headers, body):
        key = re.search(rb'name="key"\r\n\r\n([^\r]+)', body)
        if self.fail_uploads and key and key.group(1).decode() in self.assets:  # image uploads only
            self.fail_uploads -= 1
            return 503, {}, b"storage down"
        self.uploads.append((url, len(body)))
        if key and key.group(1).decode() in self.assets:
            self.assets[key.group(1).decode()]["stored"] = True
        return 204, {}, b""

    # ------------------------------------------------------------------
    def route(self, m, path, q, d):
        p = re.sub(r"^/api/v1", "", path)
        if p == "/users/me/":
            return 200, {"id": "user-me", "email": "me@example.org"}
        mm = re.match(r"^/workspaces/(?P<ws>[^/]+)/(?P<rest>.*)$", p)
        rest = mm.group("rest")
        if rest == "members/":
            return 200, self.members
        if rest.startswith("projects/") and rest.count("/") == 1:
            if m == "GET":
                seen = [p for p in self.projects.values() if p["id"] not in self.hidden_projects]
                return 200, {"results": seen, "next_page_results": False}
            for pr in self.projects.values():
                if pr["identifier"] == d["identifier"]:
                    return 409, {"identifier": "The project identifier is already taken"}
                if pr["name"].lower() == d["name"].lower():
                    return 409, {"name": "The project name is already taken"}
            pid = _id()
            pr = {
                "id": pid,
                "name": d["name"],
                "identifier": d["identifier"],
                "external_source": d.get("external_source"),
                "external_id": d.get("external_id"),
                "is_private": bool(d.get("is_private")) if self.support_private else False,
                "network": d.get("network", 2) if self.support_private else 2,
            }
            self.projects[pid] = pr
            self.states[pid] = [
                {"id": _id(), "name": n, "group": g}
                for n, g in [
                    ("Backlog", "backlog"),
                    ("Todo", "unstarted"),
                    ("In Progress", "started"),
                    ("Done", "completed"),
                    ("Cancelled", "cancelled"),
                ]
            ]
            self.fields[pid] = []
            self.templates[pid] = []
            return 201, pr
        mp = re.match(r"^projects/(?P<pid>[^/]+)/(?P<tail>.*)$", rest)
        if mp:
            return self.project_route(m, mp.group("pid"), mp.group("tail"), q, d)
        mm2 = re.match(r"^assets/(?:(?P<aid>[^/]+)/)?$", rest)
        if mm2:
            if m == "POST":
                for a in self.assets.values():
                    if a["external_id"] == d.get("external_id"):
                        return 409, {"message": "exists", "asset_id": a["id"]}
                aid = _id()
                self.assets[aid] = {
                    "id": aid,
                    "external_id": d.get("external_id"),
                    "uploaded": False,
                    "project_id": d.get("project_id"),
                }
                self.assets[aid]["stored"] = False
                return 200, {"asset_id": aid, "upload_data": {"url": "http://s3.invalid/up", "fields": {"key": aid}}}
            a = self.assets[mm2.group("aid")]
            if m == "GET":
                return (200, {"asset_url": "x"}) if a["uploaded"] else (400, {"error": "Asset not yet uploaded"})
            a["uploaded"] = bool(a.get("stored", True))
            return 204, None
        return 404, {"error": "no route " + p}

    def project_route(self, m, pid, tail, q, d):
        if pid not in self.projects or pid in self.hidden_projects:
            return 404, {"error": "Project does not exist"}
        if tail == "" and m == "PATCH":
            pr = self.projects[pid]
            if self.support_private:
                pr.update({k: d[k] for k in ("is_private", "network") if k in d})
            return 200, pr
        if tail == "states/":
            if m == "GET":
                return 200, {"results": self.states[pid], "next_page_results": False}
            for s in self.states[pid]:
                if s["name"].lower() == d["name"].lower():
                    return 409, {"error": "exists", "id": s["id"]}
            s = {"id": _id(), "name": d["name"], "group": d.get("group")}
            self.states[pid].append(s)
            return 200, s
        if tail.startswith("custom-fields/"):
            return self.field_route(m, pid, tail[len("custom-fields/") :], d)
        if tail.startswith("work-item-templates/"):
            if not self.support_templates:
                return 404, {"detail": "Not found."}
            tid = tail[len("work-item-templates/") :].strip("/")
            if not tid:
                if m == "GET":
                    return 200, self.templates[pid]
                if any(t["name"].lower() == d["name"].lower() for t in self.templates[pid]):
                    return 400, {"name": ["exists"]}
                t = {"id": _id(), **d}
                self.templates[pid].append(t)
                return 201, t
            t = next(t for t in self.templates[pid] if t["id"] == tid)
            t.update(d)
            return 200, t
        mw = re.match(r"^work-items/(?:(?P<cid>[^/]+)/)?(?P<sub>.*)$", tail)
        if mw:
            return self.card_route(m, pid, mw.group("cid"), mw.group("sub"), q, d)
        return 404, {"error": "no route " + tail}

    def field_route(self, m, pid, tail, d):
        fid = tail.strip("/").split("?")[0]
        if not fid:
            if m == "GET":
                return 200, self.fields[pid]
            if any(f["name"].lower() == d["name"].lower() for f in self.fields[pid]):
                return 400, {"name": "taken"}
            if d["field_type"] == "formula" and "map(" in d.get("settings", {}).get("expression", ""):
                return 400, {"settings": "Unknown function 'map'."}
            if d["field_type"] == "rollup" and d["settings"]["function"] not in (
                "count",
                "count_empty",
                "count_not_empty",
                "sum",
                "avg",
                "min",
                "max",
                "earliest",
                "latest",
                "unique",
                "percent_checked",
            ):
                return 400, {"settings": "bad function"}
            f = {
                "id": _id(),
                "name": d["name"],
                "field_type": d["field_type"],
                "external_source": d.get("external_source"),
                "external_id": d.get("external_id"),
                "options": [{"id": _id(), **o} for o in d.get("options") or []],
                "settings": dict(d.get("settings") or {}),
            }
            self.fields[pid].append(f)
            if f["field_type"] == "relation" and f["settings"].get("two_way"):
                tgt = f["settings"]["target_project_id"]
                mirror = {
                    "id": _id(),
                    "name": f["settings"].get("mirror_name") or "Linked",
                    "field_type": "relation",
                    "options": [],
                    "settings": {"is_mirror": True, "target_project_id": pid, "mirror_field_id": f["id"]},
                    "external_source": None,
                    "external_id": None,
                }
                self.fields[tgt].append(mirror)
                f["settings"]["mirror_field_id"] = mirror["id"]
            return 201, f
        f = next(f for f in self.fields[pid] if f["id"] == fid)
        if "options" in d:
            have = {o["name"]: o for o in f["options"]}
            f["options"] = [have.get(o["name"]) or {"id": o.get("id") or _id(), **o} for o in d["options"]]
        return 200, f

    def _check_values(self, pid, values, patch=False):
        for fid, v in (values or {}).items():
            f = next((f for f in self.fields[pid] if f["id"] == fid), None)
            if f is None:
                return {"custom_fields": {fid: "unknown field"}}
            if patch and f["name"] in self.refuse_field_names:
                return {"custom_fields": {fid: "refused"}}
            if v is None:
                continue
            ids = {o["id"] for o in f["options"]}
            if f["field_type"] == "select" and v not in ids:
                return {"custom_fields": {fid: "not an option"}}
            if f["field_type"] == "multi_select" and any(x not in ids for x in v):
                return {"custom_fields": {fid: "not an option"}}
            if f["field_type"] == "relation":
                tgt = f["settings"]["target_project_id"]
                if any(x not in self.cards or self.cards[x]["project"] != tgt for x in v):
                    return {"custom_fields": {fid: "not a card on the target board"}}
        return None

    def card_route(self, m, pid, cid, sub, q, d):
        if cid is None:
            if m == "GET":
                for c in self.cards.values():
                    if (
                        c["project"] == pid
                        and c["external_source"] == q.get("external_source")
                        and c["external_id"] == q.get("external_id")
                    ):
                        return 200, c
                return 404, {"error": "The requested resource does not exist."}
            for c in self.cards.values():
                if (
                    c["project"] == pid
                    and c["external_source"] == d.get("external_source")
                    and c["external_id"] == d.get("external_id")
                ):
                    return 409, {"error": "exists", "id": c["id"]}
            err = self._check_values(pid, d.get("custom_fields"))
            if err:
                return 400, err
            new = _id()
            seq = sum(1 for c in self.cards.values() if c["project"] == pid) + 1
            c = {"id": new, "project": pid, "sequence_id": seq, "custom_fields": {}, **d}
            c["custom_fields"] = dict(d.get("custom_fields") or {})
            self.cards[new] = c
            return 201, c
        c = self.cards.get(cid)
        if c is None:
            return 404, {"error": "missing"}
        if sub == "":
            if m == "GET":
                return 200, c
            err = self._check_values(pid, d.get("custom_fields"), patch=True)
            if err:
                return 400, err
            vals = dict(c.get("custom_fields") or {})
            vals.update(d.get("custom_fields") or {})
            c.update({k: v for k, v in d.items() if k != "custom_fields"})
            c["custom_fields"] = vals
            return 200, c
        if sub.startswith("comments/"):
            box = self.comments.setdefault(cid, [])
            rest = sub[len("comments/") :].strip("/")
            if rest:
                cm = next(x for x in box if x["id"] == rest)
                cm.update(d)
                return 200, cm
            for x in box:
                if x.get("external_id") == d.get("external_id"):
                    return 409, {"error": "exists", "id": x["id"]}
            cm = {"id": _id(), **d}
            box.append(cm)
            return 201, cm
        if sub.startswith("attachments/"):
            box = self.attachments.setdefault(cid, [])
            rest = sub[len("attachments/") :].strip("/")
            if rest:
                return 204, None
            for x in box:
                if x.get("external_id") == d.get("external_id"):
                    return 409, {"error": "exists", "id": x["id"]}
            a = {"id": _id(), **d}
            box.append(a)
            return 200, {"asset_id": a["id"], "upload_data": {"url": "http://s3.invalid/up", "fields": {"k": "v"}}}
        return 404, {"error": "no route"}
