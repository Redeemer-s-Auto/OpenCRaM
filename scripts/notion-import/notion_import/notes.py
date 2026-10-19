"""Notes (Plane-based) public API v1 client: the calls the importer needs."""

from __future__ import annotations

import time
import uuid
from urllib.parse import urlparse
from typing import Any, Optional

from .http import HTTPError, JSONClient, Transport, urllib_transport

NOTES_RATE = 0.9  # requests per second; the v1 default limit is 60 per minute per key


def notes_retry_delay(headers: dict, attempt: int, now: float) -> Optional[float]:
    lower = {k.lower(): v for k, v in (headers or {}).items()}
    reset = lower.get("x-ratelimit-reset")
    if reset:
        try:
            return max(1.0, min(float(reset) - now + 1, 90.0))
        except ValueError:
            return None
    return None


class Notes:
    def __init__(self, base_url: str, api_key: str, workspace: str,
                 transport: Transport = urllib_transport, rate: float = NOTES_RATE,
                 sleep=time.sleep, clock=time.monotonic, upload_transport: Optional[Transport] = None):
        self.base = base_url.rstrip("/")
        self.ws = workspace
        self.http = JSONClient(self.base + "/api/v1", {"X-API-Key": api_key, "Accept": "application/json"},
                               rate=rate, transport=self._wrap(transport), sleep=sleep, clock=clock)
        self.upload_transport = upload_transport or urllib_transport

    @staticmethod
    def _wrap(transport: Transport) -> Transport:
        """Turn X-RateLimit-Reset into Retry-After so the shared retry loop waits right."""
        def t(method, url, headers, body):
            status, h, data = transport(method, url, headers, body)
            if status == 429:
                lower = {k.lower(): v for k, v in (h or {}).items()}
                if "retry-after" not in lower:
                    wait = notes_retry_delay(h, 0, time.time())
                    if wait:
                        h = dict(h or {})
                        h["Retry-After"] = str(wait)
            return status, h, data
        return t

    def _p(self, path: str) -> str:
        return f"/workspaces/{self.ws}/{path.lstrip('/')}"

    # -- generic -----------------------------------------------------------
    def get(self, path, **kw):
        return self.http.get(self._p(path), **kw)

    def post(self, path, payload=None, **kw):
        return self.http.post(self._p(path), payload, **kw)

    def patch(self, path, payload=None, **kw):
        return self.http.patch(self._p(path), payload, **kw)

    def _all(self, path: str) -> list:
        """Follow Plane's cursor pagination (or accept a plain list)."""
        out, cursor = [], None
        while True:
            sep = "&" if "?" in path else "?"
            url = f"{path}{sep}per_page=100" + (f"&cursor={cursor}" if cursor else "")
            data = self.get(url)
            if isinstance(data, list):
                return data
            out.extend(data.get("results") or [])
            if not data.get("next_page_results"):
                return out
            cursor = data.get("next_cursor")

    # -- workspace ---------------------------------------------------------
    def members(self) -> list:
        return self.get("members/")

    def me(self) -> dict:
        return self.http.get("/users/me/")

    def projects(self) -> list:
        return self._all("projects/")

    def create_project(self, payload: dict) -> dict:
        return self.post("projects/", payload)

    def update_project(self, project_id: str, payload: dict) -> dict:
        return self.patch(f"projects/{project_id}/", payload)

    # -- states ------------------------------------------------------------
    def states(self, project_id: str) -> list:
        return self._all(f"projects/{project_id}/states/")

    def create_state(self, project_id: str, payload: dict) -> dict:
        return self.post(f"projects/{project_id}/states/", payload)

    # -- custom fields -----------------------------------------------------
    def fields(self, project_id: str) -> list:
        data = self.get(f"projects/{project_id}/custom-fields/?archived=all")
        return data if isinstance(data, list) else data.get("results", [])

    def create_field(self, project_id: str, payload: dict) -> dict:
        return self.post(f"projects/{project_id}/custom-fields/", payload)

    def update_field(self, project_id: str, field_id: str, payload: dict) -> dict:
        return self.patch(f"projects/{project_id}/custom-fields/{field_id}/", payload)

    # -- cards -------------------------------------------------------------
    def find_card(self, project_id: str, ext_source: str, ext_id: str) -> Optional[dict]:
        from urllib.parse import quote
        try:
            return self.get(f"projects/{project_id}/work-items/?external_source={quote(ext_source)}"
                            f"&external_id={quote(ext_id)}")
        except HTTPError as e:
            if e.status == 404:
                return None
            raise

    def create_card(self, project_id: str, payload: dict) -> dict:
        return self.post(f"projects/{project_id}/work-items/", payload)

    def update_card(self, project_id: str, card_id: str, payload: dict) -> dict:
        return self.patch(f"projects/{project_id}/work-items/{card_id}/", payload)

    def get_card(self, project_id: str, card_id: str) -> dict:
        return self.get(f"projects/{project_id}/work-items/{card_id}/")

    def add_comment(self, project_id: str, card_id: str, payload: dict) -> dict:
        return self.post(f"projects/{project_id}/work-items/{card_id}/comments/", payload)

    def update_comment(self, project_id: str, card_id: str, comment_id: str, payload: dict) -> dict:
        return self.patch(f"projects/{project_id}/work-items/{card_id}/comments/{comment_id}/", payload)

    # -- templates (fork addition) -----------------------------------------
    def templates(self, project_id: str) -> list:
        return self.get(f"projects/{project_id}/work-item-templates/")

    def create_template(self, project_id: str, payload: dict) -> dict:
        return self.post(f"projects/{project_id}/work-item-templates/", payload)

    def update_template(self, project_id: str, template_id: str, payload: dict) -> dict:
        return self.patch(f"projects/{project_id}/work-item-templates/{template_id}/", payload)

    # -- files -------------------------------------------------------------
    def upload_image(self, project_id: str, name: str, mime: str, data: bytes, ext_id: str) -> str:
        """Upload an image for a card body. Returns the asset id (re-used on re-run)."""
        payload = {"name": name, "type": mime, "size": len(data), "project_id": project_id,
                   "external_source": "notion", "external_id": ext_id}
        try:
            res = self.post("assets/", payload)
        except HTTPError as e:
            if e.status == 409 and (e.json() or {}).get("asset_id"):
                return (e.json() or {})["asset_id"]
            raise
        self._s3(res["upload_data"], name, mime, data)
        self.patch(f"assets/{res['asset_id']}/", {"is_uploaded": True})
        return res["asset_id"]

    def attach(self, project_id: str, card_id: str, name: str, mime: str, data: bytes, ext_id: str) -> dict:
        """Attach a file to a card. Returns {"id", "asset_url"?}; re-used on re-run."""
        payload = {"name": name, "type": mime, "size": len(data), "external_source": "notion", "external_id": ext_id}
        base = f"projects/{project_id}/work-items/{card_id}/attachments/"
        try:
            res = self.post(base, payload)
        except HTTPError as e:
            if e.status == 409 and (e.json() or {}).get("id"):
                return {"id": (e.json() or {})["id"], "existing": True}
            raise
        self._s3(res["upload_data"], name, mime, data)
        self.patch(f"{base}{res['asset_id']}/", {"is_uploaded": True})
        return {"id": res["asset_id"], "asset_url": res.get("asset_url")}

    def _s3(self, upload: dict, name: str, mime: str, data: bytes):
        boundary = "----notionimport" + uuid.uuid4().hex
        parts = []
        for k, v in (upload.get("fields") or {}).items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        safe = name.replace('"', "_")
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{safe}"\r\n'
                     f"Content-Type: {mime}\r\n\r\n".encode() + data + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        body = b"".join(parts)
        url = upload["url"]
        # A bucket URL without the trailing slash ("https://host/uploads") misses reverse-proxy
        # rules written for "/uploads/"; the slash form is valid for S3 and MinIO alike.
        if not urlparse(url).path.endswith("/"):
            url += "/"
        status, _h, resp = self.upload_transport(
            "POST", url, {"Content-Type": f"multipart/form-data; boundary={boundary}"}, body)
        if status >= 300:
            raise HTTPError(status, resp.decode("utf-8", "replace"), url)
