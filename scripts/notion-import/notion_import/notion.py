"""Read-only Notion API client (Notion-Version 2025-09-03).

This client can only read. Every request goes through `_guard`, which allows
GET requests plus the two read-only POST endpoints (search and data source
query). Anything else raises before a request is sent, so the importer can
never write, update or delete anything in Notion.
"""

from __future__ import annotations

import re
from typing import Any, Iterator, Optional

from .http import JSONClient, Transport, urllib_transport

NOTION_VERSION = "2025-09-03"
NOTION_RATE = 3.0  # requests per second, Notion's published average limit

_READ_ONLY_POSTS = (
    re.compile(r"^/?v1/search/?$"),
    re.compile(r"^/?v1/data_sources/[0-9a-fA-F-]+/query/?$"),
)


class WriteBlocked(Exception):
    pass


def _guard(method: str, path: str) -> None:
    if method == "GET":
        return
    if method == "POST" and any(p.match(path.split("?")[0]) for p in _READ_ONLY_POSTS):
        return
    raise WriteBlocked(f"refusing {method} {path}: the Notion client is read-only")


class Notion:
    def __init__(
        self,
        token: str,
        transport: Transport = urllib_transport,
        base_url: str = "https://api.notion.com",
        rate: float = NOTION_RATE,
        sleep=None,
        clock=None,
    ):
        kw = {}
        if sleep is not None:
            kw["sleep"] = sleep
        if clock is not None:
            kw["clock"] = clock
        self.http = JSONClient(
            base_url,
            {"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION},
            rate=rate,
            transport=transport,
            **kw,
        )

    # -- raw ---------------------------------------------------------------
    def _req(self, method: str, path: str, payload: Any = None) -> Any:
        _guard(method, path)
        return self.http.request(method, path, payload=payload)

    def _paginate_get(self, path: str) -> Iterator[dict]:
        cursor: Optional[str] = None
        while True:
            sep = "&" if "?" in path else "?"
            url = f"{path}{sep}page_size=100" + (f"&start_cursor={cursor}" if cursor else "")
            data = self._req("GET", url)
            yield from data.get("results", [])
            if not data.get("has_more"):
                return
            cursor = data.get("next_cursor")

    def _paginate_post(self, path: str, body: dict) -> Iterator[dict]:
        cursor: Optional[str] = None
        while True:
            payload = dict(body, page_size=100)
            if cursor:
                payload["start_cursor"] = cursor
            data = self._req("POST", path, payload)
            yield from data.get("results", [])
            if not data.get("has_more"):
                return
            cursor = data.get("next_cursor")

    # -- objects -----------------------------------------------------------
    def search(self, object_type: Optional[str] = None) -> Iterator[dict]:
        body: dict = {}
        if object_type:
            body["filter"] = {"property": "object", "value": object_type}
        return self._paginate_post("/v1/search", body)

    def page(self, page_id: str) -> dict:
        return self._req("GET", f"/v1/pages/{page_id}")

    def page_property(self, page_id: str, prop_id: str) -> Iterator[dict]:
        """Paginated property item (relations/people/rich text over 25 items)."""
        cursor = None
        while True:
            url = f"/v1/pages/{page_id}/properties/{prop_id}?page_size=100"
            if cursor:
                url += f"&start_cursor={cursor}"
            data = self._req("GET", url)
            if data.get("object") != "list":
                yield data
                return
            yield from data.get("results", [])
            if not data.get("has_more"):
                return
            cursor = data.get("next_cursor")

    def database(self, database_id: str) -> dict:
        return self._req("GET", f"/v1/databases/{database_id}")

    def data_source(self, data_source_id: str) -> dict:
        return self._req("GET", f"/v1/data_sources/{data_source_id}")

    def query(self, data_source_id: str) -> Iterator[dict]:
        return self._paginate_post(f"/v1/data_sources/{data_source_id}/query", {})

    def templates(self, data_source_id: str) -> list:
        """Database templates (empty list if the API does not offer them)."""
        try:
            data = self._req("GET", f"/v1/data_sources/{data_source_id}/templates")
        except Exception:  # endpoint missing or not allowed for this integration
            return []
        return data.get("templates") or data.get("results") or []

    def children(self, block_id: str) -> Iterator[dict]:
        return self._paginate_get(f"/v1/blocks/{block_id}/children")

    def comments(self, block_id: str) -> Optional[list]:
        """Open comments on a page or block; None if the integration lacks the right."""
        from .http import HTTPError

        try:
            return list(self._paginate_get(f"/v1/comments?block_id={block_id}"))
        except HTTPError as e:
            if e.status in (401, 403):
                return None
            raise

    def users(self) -> list:
        try:
            return list(self._paginate_get("/v1/users"))
        except Exception:
            return []

    def views(self, data_source_id: str) -> Optional[list]:
        """Saved views of a data source, or None when the API does not offer them."""
        try:
            return list(self._paginate_get(f"/v1/views?data_source_id={data_source_id}"))
        except Exception:
            return None

    def download(self, url: str, max_bytes: Optional[int] = None) -> Optional[bytes]:
        """Download a Notion-hosted file (signed URL, no auth header).

        Returns None when the file is larger than `max_bytes`.
        """
        if self.downloader is not None:
            return self.downloader(url, max_bytes)
        return stream_download(url, max_bytes)

    downloader = None  # tests replace this with a fake

    def file_size(self, url: str) -> Optional[int]:
        """Size of a Notion-hosted file without downloading it (one-byte range request)."""
        import urllib.request

        req = urllib.request.Request(url, headers={"Range": "bytes=0-0", "User-Agent": "notion-import"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                total = (resp.headers.get("Content-Range") or "").rpartition("/")[2]
                if total.isdigit():
                    return int(total)
                length = resp.headers.get("Content-Length")
                return int(length) if length and resp.status == 200 else None
        except Exception:
            return None


def stream_download(url: str, max_bytes: Optional[int]) -> Optional[bytes]:
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": "notion-import"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        length = resp.headers.get("Content-Length")
        if max_bytes is not None and length and int(length) > max_bytes:
            return None
        chunks, total = [], 0
        while True:
            chunk = resp.read(1 << 16)
            if not chunk:
                break
            total += len(chunk)
            if max_bytes is not None and total > max_bytes:
                return None
            chunks.append(chunk)
        return b"".join(chunks)
