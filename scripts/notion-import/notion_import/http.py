"""Small HTTP helper with rate limiting and 429 retry (stdlib only)."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Optional


class HTTPError(Exception):
    def __init__(self, status: int, body: str, url: str):
        super().__init__(f"HTTP {status} for {url}: {body[:500]}")
        self.status = status
        self.body = body
        self.url = url

    def json(self) -> Any:
        try:
            return json.loads(self.body)
        except ValueError:
            return None


class RateLimiter:
    """Allow at most `rate` calls per second (simple spacing)."""

    def __init__(
        self, rate: float, clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep
    ):
        self.interval = 1.0 / rate if rate > 0 else 0.0
        self.clock = clock
        self.sleep = sleep
        self._next = 0.0

    def wait(self) -> None:
        now = self.clock()
        if now < self._next:
            self.sleep(self._next - now)
            now = self._next
        self._next = now + self.interval


Transport = Callable[[str, str, dict, Optional[bytes]], "tuple[int, dict, bytes]"]


def urllib_transport(method: str, url: str, headers: dict, body: Optional[bytes]):
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read() or b""
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
        # Network trouble: report as 599 so the client retries with a wait.
        return 599, {}, str(e).encode("utf-8")


class JSONClient:
    """JSON API client: spacing between calls, retries on 429 and 5xx."""

    def __init__(
        self,
        base_url: str,
        headers: dict,
        rate: float,
        transport: Transport = urllib_transport,
        max_retries: int = 6,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.base_url = base_url.rstrip("/")
        self.headers = headers
        self.limiter = RateLimiter(rate, clock=clock, sleep=sleep)
        self.transport = transport
        self.max_retries = max_retries
        self.sleep = sleep
        self.calls = 0
        self.retries = 0

    def url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return self.base_url + "/" + path.lstrip("/")

    def request(
        self,
        method: str,
        path: str,
        payload: Any = None,
        raw_body: Optional[bytes] = None,
        extra_headers: Optional[dict] = None,
        expect_json: bool = True,
    ) -> Any:
        url = self.url(path)
        headers = dict(self.headers)
        if extra_headers:
            headers.update(extra_headers)
        body = raw_body
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        attempt = 0
        while True:
            self.limiter.wait()
            self.calls += 1
            status, resp_headers, data = self.transport(method, url, headers, body)
            # 429 is always safe to retry. A 5xx is retried for reads, and for writes only when
            # the request most likely never reached the app (gateway errors, network errors):
            # a 500 on a POST may have half-done the work, so it is reported, not repeated.
            retry_5xx = status >= 500 and status != 501 and (method == "GET" or status in (502, 503, 504, 599))
            if status == 429 or retry_5xx:
                if attempt >= self.max_retries:
                    raise HTTPError(status, data.decode("utf-8", "replace"), url)
                attempt += 1
                self.retries += 1
                self.sleep(retry_delay(resp_headers, attempt))
                continue
            if status >= 400:
                raise HTTPError(status, data.decode("utf-8", "replace"), url)
            if not expect_json:
                return data
            if not data:
                return None
            return json.loads(data.decode("utf-8"))

    def get(self, path: str, **kw) -> Any:
        return self.request("GET", path, **kw)

    def post(self, path: str, payload: Any = None, **kw) -> Any:
        return self.request("POST", path, payload=payload, **kw)

    def patch(self, path: str, payload: Any = None, **kw) -> Any:
        return self.request("PATCH", path, payload=payload, **kw)


def retry_delay(headers: dict, attempt: int) -> float:
    """Seconds to wait before retry: Retry-After if given, else backoff."""
    lower = {k.lower(): v for k, v in (headers or {}).items()}
    value = lower.get("retry-after")
    if value is not None:
        try:
            return max(0.5, min(float(value), 120.0))
        except ValueError:
            pass
    return min(2.0**attempt, 60.0)
