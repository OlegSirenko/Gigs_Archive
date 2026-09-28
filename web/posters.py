"""
Helpers for displaying posters that are re-posted from Telegram.

Telegram stores photos as file_id strings — they can only be downloaded by the
bot itself (via Bot API getFile). The site therefore supports two sources:

1. LOCAL IMPORT (recommended): run `python -m web.importer` — it uses the bot
   token to download channel photos into web_static/posters/ and records the
   filename in posters.moderator_notes as JSON {"web_image": "..."}.
2. PUBLIC URL TEMPLATE: set POSTER_IMAGE_URL_TEMPLATE in .env, e.g.
   https://example.org/telegram/photos/{chat_id}_{message_id}.jpg
   (for a proxy service that resolves file_ids on the fly).

If neither is available we render a stylish placeholder with the event title —
the poster data (caption/date) still comes live from the bot's DB.
"""

import json
import os
import re

from web.config import settings

_NOTES_IMAGE_RE = re.compile(r'\{"web_image":\s*"([^"]+)"')


def _notes_image(notes: str | None) -> str | None:
    """Extract web_image recorded by the importer in moderator_notes."""
    if not notes:
        return None
    try:
        data = json.loads(notes)
        if isinstance(data, dict):
            img = data.get("web_image")
            if img and os.path.isfile(os.path.join(settings.posters_dir, os.path.basename(img))):
                return f"/static/posters/{os.path.basename(img)}"
    except (ValueError, TypeError):
        pass
    m = _NOTES_IMAGE_RE.search(notes)
    if m:
        name = os.path.basename(m.group(1))
        if os.path.isfile(os.path.join(settings.posters_dir, name)):
            return f"/static/posters/{name}"
    return None


def poster_image_url(poster) -> str | None:
    """Best-effort public URL for a Poster's image, or None (placeholder used)."""
    # 1. locally imported file
    local = _notes_image(poster.moderator_notes)
    if local:
        return local

    # 2. templated public URL (needs channel message reference)
    if settings.poster_image_url_template and poster.channel_message_id and poster.channel_chat_id:
        try:
            chat = str(poster.channel_chat_id)
            clean = chat.replace("-100", "") if chat.startswith("-100") else chat.lstrip("-")
            return settings.poster_image_url_template.format(
                chat_id=clean,
                message_id=poster.channel_message_id,
                file_id=poster.photo_file_id or "",
            )
        except (KeyError, IndexError):
            return None
    return None


def telegram_post_link(poster) -> str | None:
    """Link to the original post in the Telegram channel (t.me/c/<id>/<mid>)."""
    # https://t.me/GigsArchive/1292
    if not poster.channel_message_id:
        return None
    chat = str(poster.channel_chat_id or "")
    if chat.startswith("-100"):
        return f"https://t.me/GigsArchive/{poster.channel_message_id}"
    return None


def first_line(caption: str | None, fallback: str = "Event") -> str:
    """Poster captions usually start with the event title line."""
    if not caption:
        return fallback
    for line in caption.splitlines():
        line = line.strip()
        if line:
            return line[:120]
    return fallback
