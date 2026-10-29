"""Notion page blocks -> Notes card body HTML.

The output uses placeholders that the apply step fills in once the target
exists in Notes:

    @@CARD:<notion page id>@@    link to the imported card (or plain text)
    @@BOARD:<notion db id>@@     link to the board made from a database
    @@ASSET:<file key>@@         id of an image uploaded to Notes
    @@FILE:<file key>@@          link to a file attached to the card

Every block that has no Notes equivalent becomes a visible placeholder line,
never silently dropped, and is counted in `losses`.
"""

from __future__ import annotations

from collections import Counter
from typing import Optional

from .richtext import esc, plain, to_html

CALLOUT_BG = {
    "gray": "gray",
    "brown": "peach",
    "orange": "orange",
    "yellow": "orange",
    "green": "green",
    "blue": "light-blue",
    "purple": "purple",
    "pink": "pink",
    "red": "pink",
    "default": "gray",
}
LIST_TYPES = ("bulleted_list_item", "numbered_list_item", "to_do")


def card_link(page_id: str) -> str:
    return f"@@CARD:{page_id.replace('-', '').lower()}@@"


def _resolve(page_id: str) -> str:
    return card_link(page_id)


class Renderer:
    def __init__(self, files: Optional[dict] = None):
        self.files = files or {}  # snapshot["files"]
        self.losses = Counter()  # what changed or was not brought over
        self.changed = Counter()  # came over, but changed
        self.attachments = []  # file keys to attach to the card
        self.child_pages = []  # notion page ids of sub-pages, in order
        self.child_databases = []  # notion database ids
        self.mentions_people = 0
        self.mentions_dates = 0

    # -- helpers -----------------------------------------------------------
    def rt(self, rich) -> str:
        for r in rich or []:
            if r.get("type") == "mention":
                t = (r.get("mention") or {}).get("type")
                if t == "user":
                    self.changed["@mention of a person (kept as plain text)"] += 1
                elif t == "date":
                    d = (r.get("mention") or {}).get("date") or {}
                    if d.get("end"):
                        self.changed["@date range mention (kept as plain text)"] += 1
                    else:
                        self.changed["@date mention (became a date chip, no reminder)"] += 1
                elif t == "template_mention":
                    self.changed["template mention (kept as plain text)"] += 1
            elif r.get("type") == "equation":
                self.changed["inline equation (kept as code text)"] += 1
        return to_html(rich, resolve=_resolve)

    def placeholder(self, what: str) -> str:
        self.losses[what] += 1
        return f"<p><em>[From Notion: {esc(what)} - not brought over]</em></p>"

    # -- entry -------------------------------------------------------------
    def render(self, blocks: list) -> str:
        out = []
        i = 0
        blocks = blocks or []
        while i < len(blocks):
            b = blocks[i]
            t = b.get("type")
            if t in LIST_TYPES:
                j = i
                while j < len(blocks) and blocks[j].get("type") == t:
                    j += 1
                out.append(self.list_group(t, blocks[i:j]))
                i = j
                continue
            out.append(self.block(b))
            i += 1
        return "".join(out)

    def children(self, b: dict) -> str:
        return self.render(b.get("children") or [])

    def list_group(self, t: str, items: list) -> str:
        if t == "to_do":
            lis = []
            for b in items:
                d = b.get("to_do") or {}
                checked = bool(d.get("checked"))
                box = '<input type="checkbox" checked>' if checked else '<input type="checkbox">'
                lis.append(
                    f'<li data-type="taskItem" data-checked="{"true" if checked else "false"}">'
                    f"<label>{box}<span></span></label><div><p>{self.rt(d.get('rich_text'))}</p>"
                    f"{self.children(b)}</div></li>"
                )
            return '<ul data-type="taskList">' + "".join(lis) + "</ul>"
        tag = "ul" if t == "bulleted_list_item" else "ol"
        lis = [f"<li><p>{self.rt((b.get(t) or {}).get('rich_text'))}</p>{self.children(b)}</li>" for b in items]
        return f"<{tag}>" + "".join(lis) + f"</{tag}>"

    def block(self, b: dict) -> str:
        t = b.get("type")
        d = b.get(t) or {}
        if t == "paragraph":
            return f"<p>{self.rt(d.get('rich_text'))}</p>" + self.children(b)
        if t in ("heading_1", "heading_2", "heading_3", "heading_4"):
            level = int(t[-1])
            text = self.rt(d.get("rich_text"))
            if d.get("is_toggleable"):
                self.changed["toggle heading (became a toggle block)"] += 1
                return self.toggle(f"<strong>{text}</strong>", self.children(b))
            return f"<h{level}>{text}</h{level}>" + self.children(b)
        if t == "quote":
            return f"<blockquote><p>{self.rt(d.get('rich_text'))}</p>{self.children(b)}</blockquote>"
        if t == "callout":
            return self.callout(b, d)
        if t == "code":
            lang = esc((d.get("language") or "plain text").replace(" ", "-"))
            code = esc(plain(d.get("rich_text")))
            cap = plain(d.get("caption"))
            return f'<pre><code class="language-{lang}">{code}</code></pre>' + (
                f"<p><em>{esc(cap)}</em></p>" if cap else ""
            )
        if t == "divider":
            return "<hr>"
        if t == "toggle":
            return self.toggle(self.rt(d.get("rich_text")), self.children(b))
        if t == "column_list":
            return self.columns(b)
        if t == "column":
            return self.children(b)
        if t == "table":
            return self.table(b, d)
        if t in ("image", "file", "pdf", "video", "audio"):
            return self.file_block(t, d)
        if t in ("bookmark", "embed", "link_preview"):
            url = d.get("url") or ""
            cap = plain(d.get("caption")) or url
            if t == "embed":
                self.changed["embed (shown as a link)"] += 1
            elif t == "link_preview":
                self.changed["link preview (shown as a link)"] += 1
            if not url:
                return self.placeholder(f"{t} without a link")
            return (
                f'<p>{"🔗 " if t != "embed" else "🧩 "}<a href="{esc(url)}" target="_blank" '
                f'rel="noopener noreferrer nofollow">{esc(cap)}</a></p>'
            )
        if t in ("child_page", "child_database") and b.get("excluded"):
            what = "sub-page" if t == "child_page" else "inline database"
            self.changed[f"{what} left out on purpose (excluded)"] += 1
            return f'<p><em>[From Notion: {what} "{esc(d.get("title") or "Untitled")}" was left out of this import]</em></p>'
        if t == "child_page":
            self.child_pages.append(b["id"].replace("-", "").lower())
            title = d.get("title") or "Untitled"
            return f'<p>📄 <a href="{card_link(b["id"])}">{esc(title)}</a></p>'
        if t == "child_database":
            title = d.get("title") or "Untitled database"
            if b.get("database_data_sources") is not None and not b.get("database_data_sources"):
                return self.placeholder(f'linked database view "{title}" (the API cannot read linked views)')
            self.child_databases.append(b["id"].replace("-", "").lower())
            self.changed["inline database (became its own board, linked here)"] += 1
            dbid = b["id"].replace("-", "").lower()
            return f'<p>🗂️ <a href="@@BOARD:{dbid}@@">{esc(title)}</a></p>'
        if t == "link_to_page":
            target = d.get("page_id") or d.get("database_id") or ""
            if d.get("type") == "database_id":
                return f'<p>↗ <a href="@@BOARD:{target.replace("-", "").lower()}@@">linked database</a></p>'
            return f'<p>↗ <a href="{card_link(target)}">linked page</a></p>'
        if t == "synced_block":
            if d.get("synced_from"):
                self.changed["synced block copy (content copied, no longer syncs)"] += 1
            elif b.get("children"):
                self.changed["synced block original (content copied, no longer syncs)"] += 1
            return self.children(b)
        if t == "equation":
            self.changed["equation block (kept as code text)"] += 1
            return f"<pre><code>{esc(d.get('expression') or '')}</code></pre>"
        if t == "table_of_contents":
            return self.placeholder("table of contents block")
        if t == "breadcrumb":
            return self.placeholder("breadcrumb block")
        if t == "template":
            return self.placeholder("template button block")
        if t in ("meeting_notes", "transcription"):
            return self.placeholder("AI meeting notes block")
        if t == "tab":
            return self.children(b)
        if t == "unsupported":
            kind = (d or {}).get("block_type") or "block type the Notion API does not return"
            return self.placeholder(f"{kind.replace('_', ' ')}")
        return self.placeholder(f"{(t or 'unknown').replace('_', ' ')} block")

    def toggle(self, title_html: str, inner: str) -> str:
        return (
            '<details data-block-type="toggle" data-open="false">'
            f'<summary data-block-type="toggle-title">{title_html}</summary>'
            f'<div data-block-type="toggle-content">{inner or "<p></p>"}</div></details>'
        )

    def callout(self, b: dict, d: dict) -> str:
        icon = d.get("icon") or {}
        color = (d.get("color") or "default").replace("_background", "")
        bg = CALLOUT_BG.get(color, "gray")
        attrs = f'data-block-type="callout-component" data-background="{bg}"'
        if icon.get("type") == "emoji" and icon.get("emoji"):
            attrs += f' data-logo-in-use="emoji" data-emoji-unicode="{ord(icon["emoji"][0])}"'
        else:
            attrs += ' data-logo-in-use="emoji"'
            if icon:
                self.changed["callout with a custom icon (icon replaced)"] += 1
        return f"<div {attrs}><p>{self.rt(d.get('rich_text'))}</p>{self.children(b)}</div>"

    def columns(self, b: dict) -> str:
        cols = [c for c in (b.get("children") or []) if c.get("type") == "column"]
        if 2 <= len(cols) <= 3:
            inner = "".join(f'<div data-block-type="column">{self.children(c) or "<p></p>"}</div>' for c in cols)
            return f'<div data-block-type="column-list" data-columns="{len(cols)}">{inner}</div>'
        if len(cols) > 3:
            self.changed[f"{len(cols)}-column layout (Notes has 2 or 3 columns; stacked instead)"] += 1
        return "".join(self.children(c) for c in cols)

    def table(self, b: dict, d: dict) -> str:
        rows = [r for r in (b.get("children") or []) if r.get("type") == "table_row"]
        head_row = d.get("has_column_header")
        head_col = d.get("has_row_header")
        out = []
        for ri, r in enumerate(rows):
            cells = (r.get("table_row") or {}).get("cells") or []
            tds = []
            for ci, cell in enumerate(cells):
                tag = "th" if (head_row and ri == 0) or (head_col and ci == 0) else "td"
                tds.append(f"<{tag}><p>{self.rt(cell)}</p></{tag}>")
            out.append("<tr>" + "".join(tds) + "</tr>")
        return "<table><tbody>" + "".join(out) + "</tbody></table>"

    def file_block(self, t: str, d: dict) -> str:
        cap = plain(d.get("caption"))
        cap_html = f"<p><em>{esc(cap)}</em></p>" if cap else ""
        kind = d.get("type")
        if kind == "external":
            url = (d.get("external") or {}).get("url") or ""
            if t == "image":
                self.changed["image from an outside link (still loads from that link)"] += 1
                return (
                    f'<image-component src="{esc(url)}" width="35%" height="auto" alignment="left" '
                    f'status="uploaded"></image-component>' + cap_html
                )
            self.changed[f"{t} from an outside link (kept as a link)"] += 1
            return f'<p>📎 <a href="{esc(url)}" target="_blank" rel="noopener noreferrer nofollow">{esc(cap or url)}</a></p>'
        key = d.get("_file")
        if not key:
            return self.placeholder(f"{t} stored in Notion that could not be read")
        rec = self.files.get(key)
        name = (rec or {}).get("name") or d.get("name") or t
        if not rec or rec.get("status") != "ok":
            status = (rec or {}).get("status") or "not downloaded"
            if status == "too big":
                return self.placeholder(f'{t} "{name}" is over the Notes file size limit')
            if status.startswith("not downloaded"):
                # dry run: count what would come over, show the planned line
                self.changed[f"{t} (re-uploaded to Notes)"] += 1
                if t == "image":
                    return (
                        f'<image-component src="@@ASSET:{key}@@" width="35%" height="auto" alignment="left" status="uploaded"></image-component>'
                        + cap_html
                    )
                self.attachments.append(key)
                return f'<p>📎 <a href="@@FILE:{key}@@">{esc(name)}</a></p>' + cap_html
            return self.placeholder(f'{t} "{name}" ({status})')
        if t == "image":
            return (
                f'<image-component src="@@ASSET:{key}@@" width="35%" height="auto" alignment="left" '
                f'status="uploaded"></image-component>' + cap_html
            )
        self.attachments.append(key)
        return f'<p>📎 <a href="@@FILE:{key}@@">{esc(name)}</a></p>' + cap_html
