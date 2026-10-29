"""Inventory of a Notion workspace: databases (data sources) and top-level pages.

Built from /v1/search results only (titles, counts, dates, parents). No row
contents are written out.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Iterable, Optional

from .richtext import plain


def page_title(page: dict) -> str:
    for prop in (page.get("properties") or {}).values():
        if prop.get("type") == "title":
            return plain(prop.get("title") or []) or "Untitled"
    return "Untitled"


def ds_title(ds: dict) -> str:
    return plain(ds.get("title") or []) or "Untitled database"


def norm(i: Optional[str]) -> str:
    return (i or "").replace("-", "").lower()


def parent_ref(obj: dict) -> tuple:
    """(kind, id) of an object's parent. For data sources, the database's parent."""
    parent = obj.get("database_parent") if obj.get("object") == "data_source" else obj.get("parent")
    parent = parent or {}
    kind = parent.get("type")
    return kind, norm(parent.get(kind)) if kind and kind != "workspace" else ""


class Inventory:
    def __init__(self, data_sources: Iterable[dict], pages: Iterable[dict]):
        self.data_sources = [d for d in data_sources if not d.get("in_trash") and not d.get("archived")]
        self.pages = [p for p in pages if not p.get("in_trash") and not p.get("archived")]
        self.page_by_id = {norm(p["id"]): p for p in self.pages}
        self.ds_by_id = {norm(d["id"]): d for d in self.data_sources}
        self.db_to_ds = defaultdict(list)
        for d in self.data_sources:
            self.db_to_ds[norm((d.get("parent") or {}).get("database_id"))].append(d)
        self.rows = Counter()
        self.rows_last_edit = {}
        for p in self.pages:
            par = p.get("parent") or {}
            if par.get("type") == "data_source_id":
                key = norm(par.get("data_source_id"))
                self.rows[key] += 1
                t = p.get("last_edited_time") or ""
                if t > self.rows_last_edit.get(key, ""):
                    self.rows_last_edit[key] = t
        self.child_pages = Counter()
        for p in self.pages:
            kind, pid = parent_ref(p)
            if kind == "page_id":
                self.child_pages[pid] += 1

    def parent_title(self, obj: dict) -> str:
        kind, pid = parent_ref(obj)
        if kind == "workspace":
            return "(workspace top level)"
        if kind == "page_id":
            p = self.page_by_id.get(pid)
            return page_title(p) if p else "(page not shared with the integration)"
        if kind == "block_id":
            return "(inside a block of a page)"
        if kind in ("database_id", "data_source_id"):
            ds = self.ds_by_id.get(pid) or (self.db_to_ds.get(pid) or [None])[0]
            return ds_title(ds) if ds else "(database not shared)"
        return f"({kind or 'unknown'})"

    def path(self, obj: dict, depth: int = 6) -> str:
        """Title path from the top, e.g. 'HR Homepage / Payroll'."""
        parts = []
        cur = obj
        for _ in range(depth):
            kind, pid = parent_ref(cur)
            if kind == "page_id" and pid in self.page_by_id:
                cur = self.page_by_id[pid]
                parts.append(page_title(cur))
                continue
            if kind == "data_source_id" and pid in self.ds_by_id:
                cur = self.ds_by_id[pid]
                parts.append(ds_title(cur))
                continue
            if kind == "database_id" and self.db_to_ds.get(pid):
                cur = self.db_to_ds[pid][0]
                parts.append(ds_title(cur))
                continue
            break
        return " / ".join(reversed(parts))

    def top_level_pages(self) -> list:
        """Pages whose parent is the workspace or is not visible to the integration."""
        out = []
        for p in self.pages:
            kind, pid = parent_ref(p)
            if kind == "workspace":
                out.append(p)
            elif kind == "page_id" and pid not in self.page_by_id:
                out.append(p)
            elif kind == "block_id":
                # inside a block: keep only if the containing page is unknown to us
                continue
        return out

    def schema_counts(self, ds: dict) -> Counter:
        return Counter(p.get("type") for p in (ds.get("properties") or {}).values())
