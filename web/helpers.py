"""Slug + tiny markdown helpers shared by routes."""

import re
import unicodedata


def slugify(text: str, max_len: int = 180) -> str:
    """URL-safe slug; supports Cyrillic transliteration."""

    text = (text or "").strip().lower()

    # Basic cyrillic -> latin transliteration (event/interview titles are RU)
    _TRANSLIT = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
        "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
        "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    }
    text = "".join(_TRANSLIT.get(ch, ch) for ch in text)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:max_len] or "untitled"


def unique_slug(session, model, base_slug: str, exclude_id: int | None = None) -> str:
    """Append -2, -3... until the slug is free in `model`."""
    slug = base_slug
    n = 1
    while True:
        q = session.query(model).filter(model.slug == slug)
        if exclude_id is not None:
            q = q.filter(model.id != exclude_id)
        if q.first() is None:
            return slug
        n += 1
        slug = f"{base_slug}-{n}"


def render_body(text: str) -> str:
    """Very small safe subset of markdown -> HTML for article bodies.

    Supports: **bold**, *italic*, paragraphs, line breaks, --- horizontal rule.
    Everything is HTML-escaped first, so admin content can never inject markup.
    """
    import html as _html

    escaped = _html.escape(text or "")
    blocks = []
    for block in re.split(r"\n\s*\n", escaped):
        block = block.strip()
        if not block:
            continue
        if re.fullmatch(r"-{3,}", block.replace("\n", "").strip()):
            blocks.append("<hr>")
            continue
        inner = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", block, flags=re.S)
        inner = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", inner)
        inner = re.sub(
            r"(https?://[^\s<]+)",
            r'<a href="\1" target="_blank" rel="noopener">\1</a>',
            inner,
        )
        inner = inner.replace("\n", "<br>\n")
        blocks.append(f"<p>{inner}</p>")
    return "\n".join(blocks)
