# web/helpers.py
"""Slug + tiny markdown helpers shared by routes."""

import re
import unicodedata
import requests
from markupsafe import Markup

# ОГРОМНЫЙ ПРИНТ, ЧТОБЫ УБЕДИТЬСЯ, ЧТО ФАЙЛ ЧИТАЕТСЯ
print("=" * 60)
print("!!! ФАЙЛ web/helpers.py БЫЛ ПРОЧИТАН PYTHON ПРИ ЗАПУСКЕ !!!")
print("=" * 60)


def poster_image_url(poster) -> str | None:
    """Возвращает URL нашего прокси-эндпоинта для картинки."""
    if not poster or not hasattr(poster, 'photo_file_id') or not poster.photo_file_id:
        return None
    
    # Просто возвращаем ссылку на наш прокси, который использует Bot API
    return f"/api/poster-image/{poster.id}"


def slugify(text: str, max_len: int = 180) -> str:
    """URL-safe slug; supports Cyrillic transliteration."""
    text = (text or "").strip().lower()
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
    """Преобразует текст с переносами строк из Telegram в HTML-абзацы."""
    if not text:
        return ""
    paragraphs = re.split(r'\n\s*\n', text)
    formatted = []
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        if p.startswith('<'):
            formatted.append(p)
        else:
            p_with_br = p.replace('\n', '<br>')
            formatted.append(f'<p>{p_with_br}</p>')
    return Markup('\n'.join(formatted))


def first_line(caption: str | None, fallback: str = "Event") -> str:
    if not caption:
        return fallback
    for line in caption.splitlines():
        line = line.strip()
        if line:
            return line[:120]
    return fallback