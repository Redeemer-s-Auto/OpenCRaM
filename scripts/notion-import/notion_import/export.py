"""Export: read chosen Notion databases and pages into a local snapshot folder.

The snapshot is plain JSON plus downloaded files, so the import step can run
anywhere (and be re-run) without the Notion token, and Notion's expiring file
links are saved before they lapse.

    snapshot/
      snapshot.json   users, data sources, pages (with block trees), files
      files/<sha256>  downloaded Notion-hosted files
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from typing import Optional

from .http import HTTPError
from .inventory import norm

DEFAULT_MAX_FILE = 10 * 1024 * 1024  # Notes FILE_SIZE_LIMIT default (10 MB)
FILE_BLOCKS = ("image", "file", "pdf", "video", "audio")


def dashed(i: str) -> str:
    h = norm(i)
    if len(h) != 32:
        return i
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


def safe_name(name: str) -> str:
    name = re.sub(r"[^\w.\- ]+", "_", name or "file").strip() or "file"
    return name[:120]


def file_name_from_url(url: str) -> str:
    from urllib.parse import unquote, urlparse

    path = urlparse(url).path
    return safe_name(unquote(path.rsplit("/", 1)[-1]) or "file")


class Exporter:
    def __init__(
        self,
        notion,
        out_dir: str,
        max_file_bytes: int = DEFAULT_MAX_FILE,
        download_files: bool = True,
        log=print,
        max_pages: Optional[int] = None,
        block_comments: bool = False,
        exclude: Optional[set] = None,
    ):
        self.n = notion
        self.exclude = {norm(x) for x in (exclude or set())}
        self.out_dir = out_dir
        self.files_dir = os.path.join(out_dir, "files")
        self.max_file_bytes = max_file_bytes
        self.download_files = download_files
        self.log = log
        self.max_pages = max_pages
        self.block_comments = block_comments
        self.snap = {
            "version": 1,
            "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "roots": [],
            "users": {},
            "data_sources": {},
            "pages": {},
            "files": {},
            "missing": [],  # objects we could not read (not shared, linked views)
            "notes": [],  # export-wide notes (e.g. comments not readable)
            "comments_readable": True,
        }
        self._seen_pages = set()

    # -- entry -------------------------------------------------------------
    def run(self, roots: list) -> dict:
        os.makedirs(self.files_dir, exist_ok=True)
        self._load_users()
        self.snap["complete"] = False
        try:
            for root in roots:
                kind, rid = root
                self.snap["roots"].append({"kind": kind, "id": norm(rid)})
                if kind == "data_source":
                    self.export_data_source(rid)
                elif kind == "database":
                    self.export_database(rid)
                else:
                    self.export_page(rid)
            self.snap["complete"] = True
        except BaseException as e:
            # keep what was read so far; the plan report says the export stopped early
            self.snap["notes"].append(
                f"The export stopped early ({type(e).__name__}: {str(e)[:200]}); "
                "the snapshot holds only what was read before that."
            )
            self.save()
            raise
        return self.snap

    def save(self) -> str:
        path = os.path.join(self.out_dir, "snapshot.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.snap, fh, ensure_ascii=False, indent=1)
        return path

    # -- users -------------------------------------------------------------
    def _load_users(self):
        for u in self.n.users():
            if u.get("type") != "person":
                continue
            self.snap["users"][norm(u["id"])] = {
                "name": u.get("name") or "",
                "email": ((u.get("person") or {}).get("email") or "").lower(),
            }

    # -- databases ---------------------------------------------------------
    def _excluded(self, kind: str, oid: str) -> bool:
        if norm(oid) in self.exclude:
            self.snap["missing"].append({"kind": kind, "id": norm(oid), "why": "excluded"})
            return True
        return False

    def export_database(self, database_id: str):
        if self._excluded("database", database_id):
            return []
        try:
            db = self.n.database(dashed(database_id))
        except HTTPError as e:
            self.snap["missing"].append(
                {
                    "kind": "database",
                    "id": norm(database_id),
                    "why": "linked view or not shared" if e.status in (400, 404) else f"HTTP {e.status}",
                }
            )
            return []
        ids = []
        for ds in db.get("data_sources") or []:
            ids.append(norm(ds["id"]))
            self.export_data_source(ds["id"], database=db)
        return ids

    def export_data_source(self, ds_id: str, database: Optional[dict] = None):
        key = norm(ds_id)
        if key in self.snap["data_sources"] or self._excluded("data_source", ds_id):
            return
        try:
            ds = self.n.data_source(dashed(ds_id))
        except HTTPError as e:
            self.snap["missing"].append({"kind": "data_source", "id": key, "why": f"HTTP {e.status}"})
            return
        self.log(f"database: {_title(ds.get('title'))}")
        entry = {
            k: ds.get(k)
            for k in (
                "id",
                "title",
                "description",
                "properties",
                "parent",
                "database_parent",
                "icon",
                "cover",
                "is_inline",
                "created_time",
                "last_edited_time",
                "created_by",
                "last_edited_by",
                "public_url",
                "url",
            )
        }
        entry["rows"] = []
        entry["templates"] = []
        entry["views"] = self.n.views(dashed(ds_id))
        self.snap["data_sources"][key] = entry
        for t in self.n.templates(dashed(ds_id)):
            tid = norm(t.get("id", ""))
            entry["templates"].append({"id": tid, "name": t.get("name") or "", "is_default": bool(t.get("is_default"))})
            if tid:
                self.export_page(tid, template_of=key)
        for row in self.n.query(dashed(ds_id)):
            if row.get("in_trash") or row.get("archived"):
                continue
            entry["rows"].append(norm(row["id"]))
            self.export_page(row["id"], page_obj=row)

    # -- pages -------------------------------------------------------------
    def export_page(self, page_id: str, page_obj: Optional[dict] = None, template_of: Optional[str] = None):
        key = norm(page_id)
        if key in self._seen_pages:
            return
        if self._excluded("page", page_id):
            self._seen_pages.add(key)
            return
        if self.max_pages is not None and len(self._seen_pages) >= self.max_pages:
            return
        self._seen_pages.add(key)
        if page_obj is None:
            try:
                page_obj = self.n.page(dashed(page_id))
            except HTTPError as e:
                self.snap["missing"].append({"kind": "page", "id": key, "why": f"HTTP {e.status}"})
                return
        page = {
            k: page_obj.get(k)
            for k in (
                "id",
                "parent",
                "properties",
                "icon",
                "cover",
                "url",
                "public_url",
                "created_time",
                "last_edited_time",
                "created_by",
                "last_edited_by",
                "is_locked",
            )
        }
        if template_of:
            page["template_of"] = template_of
        self._fill_long_properties(page)
        self._page_files(page)
        page["blocks"] = self._blocks(page_id)
        page["comments"] = self._comments(page_id)
        self.snap["pages"][key] = page
        # sub-pages and inline databases found in the body
        for child in _walk(page["blocks"]):
            t = child.get("type")
            if t in ("child_page", "child_database") and norm(child["id"]) in self.exclude:
                child["excluded"] = True
            if t == "child_page":
                self.export_page(child["id"])
            elif t == "child_database":
                child["database_data_sources"] = self.export_database(child["id"])

    def _fill_long_properties(self, page: dict):
        """Relations/people over 25 items come back truncated; fetch the rest."""
        for name, prop in (page.get("properties") or {}).items():
            if prop.get("has_more") and prop.get("id"):
                items = list(self.n.page_property(dashed(page["id"]), prop["id"]))
                t = prop.get("type")
                if t == "relation":
                    prop["relation"] = [i.get("relation") for i in items if i.get("relation")]
                elif t == "people":
                    prop["people"] = [i.get("people") for i in items if i.get("people")]
                elif t in ("rich_text", "title"):
                    prop[t] = [i.get(t) for i in items if i.get(t)]
                prop["has_more"] = False

    def _comments(self, block_id: str) -> list:
        if not self.snap["comments_readable"]:
            return []
        got = self.n.comments(dashed(block_id))
        if got is None:
            self.snap["comments_readable"] = False
            self.snap["notes"].append(
                "Comments were not read: the Notion integration does not have the 'Read comments' capability."
            )
            return []
        return [
            {
                "id": c.get("id"),
                "rich_text": c.get("rich_text"),
                "created_by": norm((c.get("created_by") or {}).get("id")),
                "created_time": c.get("created_time"),
                "discussion_id": c.get("discussion_id"),
            }
            for c in got
        ]

    def _blocks(self, block_id: str, depth: int = 0) -> list:
        out = []
        try:
            children = list(self.n.children(dashed(block_id)))
        except HTTPError as e:
            self.snap["missing"].append({"kind": "blocks", "id": norm(block_id), "why": f"HTTP {e.status}"})
            return out
        for b in children:
            t = b.get("type")
            if t in FILE_BLOCKS:
                self._block_file(b)
            if b.get("has_children") and t not in ("child_page", "child_database") and depth < 30:
                b["children"] = self._blocks(b["id"], depth + 1)
            if self.block_comments and self.snap["comments_readable"]:
                b["comments"] = self._comments(b["id"])
            out.append(b)
        return out

    # -- files -------------------------------------------------------------
    def _block_file(self, b: dict):
        data = b.get(b["type"]) or {}
        self._file_obj(data, name=data.get("name"), where=f"{b['type']} block")

    def _page_files(self, page: dict):
        for slot in ("cover", "icon"):
            obj = page.get(slot)
            if obj and obj.get("type") == "file":
                self._file_obj(obj, where=f"page {slot}")
        for prop in (page.get("properties") or {}).values():
            if prop.get("type") == "files":
                for f in prop.get("files") or []:
                    self._file_obj(f, name=f.get("name"), where="files property")

    def _file_obj(self, obj: dict, name: Optional[str] = None, where: str = ""):
        """Download a Notion-hosted file and record it in obj['_file'] (a files key)."""
        if obj.get("type") != "file":
            return  # external link: kept as a link, never re-hosted
        url = (obj.get("file") or {}).get("url")
        if not url:
            return
        name = safe_name(name or file_name_from_url(url))
        fkey = hashlib.sha256(url.split("?")[0].encode("utf-8")).hexdigest()[:32]
        obj["_file"] = fkey
        if fkey in self.snap["files"]:
            return
        rec = {"name": name, "where": where, "status": "pending", "size": None, "path": None}
        self.snap["files"][fkey] = rec
        if not self.download_files:
            rec["status"] = "not downloaded (dry run)"
            size = self.n.file_size(url) if hasattr(self.n, "file_size") else None
            if size is not None:
                rec["size"] = size
                if size > self.max_file_bytes:
                    rec["status"] = "too big"
            return
        try:
            data = self.n.download(url, max_bytes=self.max_file_bytes)
        except Exception as e:  # network or expired link
            rec["status"] = f"download failed: {e}"
            return
        if data is None:
            rec["status"] = "too big"
            rec["size"] = f">{self.max_file_bytes}"
            return
        sha = hashlib.sha256(data).hexdigest()
        path = os.path.join(self.files_dir, sha)
        if not os.path.exists(path):
            with open(path, "wb") as fh:
                fh.write(data)
        rec.update(status="ok", size=len(data), path=f"files/{sha}", sha256=sha)


def _title(rich) -> str:
    return "".join((r.get("plain_text") or "") for r in rich or []) or "Untitled"


def _walk(blocks: list):
    for b in blocks or []:
        yield b
        yield from _walk(b.get("children") or [])


def load_snapshot(path: str) -> dict:
    if os.path.isdir(path):
        path = os.path.join(path, "snapshot.json")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
