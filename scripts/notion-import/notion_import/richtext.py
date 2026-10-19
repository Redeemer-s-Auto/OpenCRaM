"""Notion rich text -> plain text and HTML."""

from __future__ import annotations

import html
from typing import Callable, Optional

LinkResolver = Callable[[str], Optional[str]]  # notion page id -> Notes URL or None


def plain(rich: list) -> str:
    return "".join((r.get("plain_text") or "") for r in rich or [])


def esc(text: str) -> str:
    return html.escape(text or "", quote=True)


def _notion_page_id_from_url(url: str) -> Optional[str]:
    """Pull a 32-hex page id out of a notion.so / notion.site / app.notion.com link."""
    import re
    if not url or "notion." not in url:
        return None
    path = url.split("?")[0].split("#")[0].lower()
    m = re.findall(r"(?<![0-9a-f])([0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12})(?![0-9a-f])", path)
    return m[-1].replace("-", "") if m else None


def to_html(rich: list, resolve: Optional[LinkResolver] = None, notes: Optional[list] = None,
            user_name: Optional[Callable[[str], str]] = None) -> str:
    """Convert rich text to inline HTML.

    `resolve` maps a Notion page id to a Notes card URL (link rewriting).
    `notes` collects warnings (e.g. a link to a page that was not imported).
    """
    out = []
    for r in rich or []:
        kind = r.get("type")
        text = r.get("plain_text") or ""
        href = r.get("href")
        if kind == "mention":
            m = r.get("mention") or {}
            mtype = m.get("type")
            if mtype in ("page", "database"):
                target = (m.get(mtype) or {}).get("id", "")
                url = resolve(target.replace("-", "").lower()) if resolve else None
                if url:
                    href = url
                else:
                    href = None
                    if notes is not None:
                        notes.append(f"link to a page that was not imported: {text}")
                    text = text or "(page)"
            elif mtype == "user":
                uid = (m.get("user") or {}).get("id", "")
                name = text.lstrip("@") or (user_name(uid) if user_name else "") or "someone"
                text = "@" + name
                href = None
            elif mtype == "date":
                href = None
            elif mtype in ("link_preview", "link_mention"):
                href = href or (m.get(mtype) or {}).get("url") or (m.get(mtype) or {}).get("href")
            else:
                href = None
        elif kind == "equation":
            expr = (r.get("equation") or {}).get("expression") or text
            out.append(f"<code>{esc(expr)}</code>")
            continue
        piece = esc(text).replace("\n", "<br>")
        a = r.get("annotations") or {}
        if a.get("code"):
            piece = f"<code>{piece}</code>"
        if a.get("bold"):
            piece = f"<strong>{piece}</strong>"
        if a.get("italic"):
            piece = f"<em>{piece}</em>"
        if a.get("strikethrough"):
            piece = f"<s>{piece}</s>"
        if a.get("underline"):
            piece = f"<u>{piece}</u>"
        if href:
            if resolve and kind != "mention":
                pid = _notion_page_id_from_url(href)
                if pid:
                    new = resolve(pid)
                    if new:
                        href = new
                    elif notes is not None:
                        notes.append(f"link to a Notion page that was not imported: {text}")
            piece = f'<a href="{esc(href)}" target="_blank" rel="noopener noreferrer nofollow">{piece}</a>'
        out.append(piece)
    return "".join(out)
