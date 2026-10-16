"""Privacy-policy page: renders locales/privacy_{ru,en}.md as site HTML.

The same ``privacy_ru.md`` / ``privacy_en.md`` files the Telegram bot shows are
the single source of truth. This module implements the small markdown subset
those files use — headings, bold/italic, links, lists, blockquotes, horizontal
rules and pipe tables — and turns it into HTML that the site styles with its
ransom-note article skin (see templates/privacy.html + ransom.css).
"""

from __future__ import annotations

import os
import re
from html import escape

from markupsafe import Markup

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES_DIR = os.path.join(PROJECT_ROOT, "locales")

DEFAULT_LANG = "ru"
AVAILABLE_LANGS = ("ru", "en")


def load_markdown(lang: str) -> str:
    """Return the raw markdown of privacy_<lang>.md (empty string if missing)."""
    lang = lang if lang in AVAILABLE_LANGS else DEFAULT_LANG
    path = os.path.join(LOCALES_DIR, f"privacy_{lang}.md")
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


# --------------------------------------------------------------------------
# Inline markdown (emphasis, links, bare urls/emails)
# --------------------------------------------------------------------------
_MD_LINK_RE = re.compile(
    r'\[([^\]]+)\]\((https?://[^)\s]+|tg://[^)\s]+|mailto:[^)\s]+)\)')
_EMAIL_RE = re.compile(r'(?<![\w./@-])[\w.+-]+@[\w-]+\.[\w.-]+\b')
_URL_RE = re.compile(r'(?<![\w/])(https?://[^\s<>()"\']+|t\.me/[^\s<>()"\']+)')
_TOKEN = "\x00L{}\x00"


def _inline(text: str) -> str:
    """Escape + apply inline markdown. Generated <a> are stashed in tokens so
    the bare-url pass can never re-link them."""
    text = escape(str(text), quote=False)
    store: list[str] = []

    def _keep(html: str) -> str:
        store.append(html)
        return _TOKEN.format(len(store) - 1)

    # [text](url)
    text = _MD_LINK_RE.sub(
        lambda m: _keep(
            f'<a href="{m.group(2)}" target="_blank" rel="noopener noreferrer">'
            f'{m.group(1)}</a>'),
        text)
    # bare emails -> mailto
    text = _EMAIL_RE.sub(
        lambda m: _keep(f'<a href="mailto:{m.group(0)}">{m.group(0)}</a>'),
        text)
    # bare urls / t.me
    text = _URL_RE.sub(
        lambda m: _keep(
            f'<a href="{m.group(0) if m.group(0).startswith("http") else "https://" + m.group(0)}"'
            f' target="_blank" rel="noopener noreferrer">{m.group(0)}</a>'),
        text)
    # **bold** / __bold__
    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'(?<!\w)__([^_]+)__(?!\w)', r'<strong>\1</strong>', text)
    # *italic* / _italic_
    text = re.sub(r'(?<!\*)\*([^*\n]+)\*(?!\*)', r'<em>\1</em>', text)
    text = re.sub(r'(?<!\w)_([^_\n]+)_(?!\w)', r'<em>\1</em>', text)

    for i, html in enumerate(store):
        text = text.replace(_TOKEN.format(i), html)
    return text


# --------------------------------------------------------------------------
# Block markdown
# --------------------------------------------------------------------------
_TABLE_SEP_RE = re.compile(r'^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$')
_HR_RE = re.compile(r'^\s*(?:-{3,}|\*{3,}|_{3,})\s*$')
_H_RE = re.compile(r'^\s*(#{1,6})\s+(.*?)\s*$')
_UL_RE = re.compile(r'^\s*[-*+]\s+(.*)$')
_OL_RE = re.compile(r'^\s*\d+[.)]\s+(.*)$')


def _split_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def _cell(tag: str, cells: list[str], aligns: list[str]) -> str:
    out = []
    for idx, c in enumerate(cells):
        al = aligns[idx] if idx < len(aligns) else ""
        style = f' style="text-align:{al}"' if al else ""
        out.append(f"<{tag}{style}>{_inline(c)}</{tag}>")
    return "".join(out)


def _render_table(lines: list[str], i: int, n: int):
    header = _split_row(lines[i])
    aligns = []
    for c in _split_row(lines[i + 1]):
        if c.startswith(":") and c.endswith(":"):
            aligns.append("center")
        elif c.endswith(":"):
            aligns.append("right")
        elif c.startswith(":"):
            aligns.append("left")
        else:
            aligns.append("")
    i += 2
    rows = []
    while i < n and lines[i].strip() and "|" in lines[i] \
            and not _TABLE_SEP_RE.match(lines[i]):
        rows.append(_split_row(lines[i]))
        i += 1
    html = ['<div class="privacy-table-wrap"><table class="privacy-table">']
    html.append("<thead><tr>" + _cell("th", header, aligns) + "</tr></thead>")
    html.append("<tbody>")
    for r in rows:
        html.append("<tr>" + _cell("td", r, aligns) + "</tr>")
    html.append("</tbody></table></div>")
    return i, "".join(html)


def _starts_block(lines: list[str], i: int) -> bool:
    s = lines[i].strip()
    if not s:
        return True
    if _H_RE.match(s) or _HR_RE.match(s) or s.startswith(">"):
        return True
    if _UL_RE.match(lines[i]) or _OL_RE.match(lines[i]):
        return True
    if "|" in s and i + 1 < len(lines) and _TABLE_SEP_RE.match(lines[i + 1]):
        return True
    return False


def md_to_html(md: str) -> Markup:
    lines = md.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    i, n = 0, len(lines)
    while i < n:
        s = lines[i].strip()
        if not s:
            i += 1
            continue
        # pipe table
        if "|" in s and i + 1 < n and _TABLE_SEP_RE.match(lines[i + 1]):
            i, table = _render_table(lines, i, n)
            out.append(table)
            continue
        # horizontal rule
        if _HR_RE.match(s):
            out.append('<hr class="article-sep">')
            i += 1
            continue
        # heading
        m = _H_RE.match(s)
        if m:
            lvl = len(m.group(1))
            body = _inline(m.group(2))
            if lvl == 1:
                out.append(f'<h1 class="privacy-title">{body}</h1>')
            else:
                tag = min(lvl, 6)
                out.append(
                    f'<h{tag} class="article-subhead">{body}</h{tag}>')
            i += 1
            continue
        # blockquote
        if s.startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip()[1:].lstrip())
                i += 1
            out.append("<blockquote>"
                       + "<br>".join(_inline(x) for x in buf)
                       + "</blockquote>")
            continue
        # bullet list
        if _UL_RE.match(lines[i]):
            items = []
            while i < n and _UL_RE.match(lines[i]):
                items.append(_inline(_UL_RE.match(lines[i]).group(1)))
                i += 1
            out.append('<ul class="article-list">'
                       + "".join(f"<li>{x}</li>" for x in items)
                       + "</ul>")
            continue
        # ordered list
        if _OL_RE.match(lines[i]):
            items = []
            while i < n and _OL_RE.match(lines[i]):
                items.append(_inline(_OL_RE.match(lines[i]).group(1)))
                i += 1
            out.append('<ol class="article-list">'
                       + "".join(f"<li>{x}</li>" for x in items)
                       + "</ol>")
            continue
        # paragraph (consecutive non-blank, non-block lines)
        buf = [s]
        i += 1
        while i < n and not _starts_block(lines, i):
            buf.append(lines[i].strip())
            i += 1
        para = _inline("\n".join(buf)).replace("\n", "<br>")
        out.append(f"<p>{para}</p>")

    return Markup("\n".join(out))


def render(lang: str = DEFAULT_LANG) -> Markup:
    """Full HTML body of the privacy page for the given language."""
    return md_to_html(load_markdown(lang))
