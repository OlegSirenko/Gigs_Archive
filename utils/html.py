"""
HTML caption extraction helper for aiogram 3.x
"""
import re

from aiogram.types import Message

# <tg-emoji emoji-id="...">😀</tg-emoji> — Telegram's custom (premium) emoji
# markup produced by HtmlDecoration.unparse(). Bots are NOT allowed to send
# this tag, and its ~30-char markup inflates the message length against the
# 4096-char / 1024-caption limits. We keep the inner emoji character and drop
# the wrapper immediately at extraction time so it never reaches storage,
# validation or sending code.
_TG_EMOJI_TAG_RE = re.compile(r'<tg-emoji\b[^>]*>(.*?)</tg-emoji>', re.IGNORECASE | re.DOTALL)


def _strip_tg_emoji(text: str) -> str:
    """Remove <tg-emoji ...> wrappers, keeping the emoji characters inside."""
    if not text:
        return text
    return _TG_EMOJI_TAG_RE.sub(r"\1", text)


def get_html_caption(message: Message) -> str:
    """
    Get message caption with HTML formatting preserved.

    In aiogram 3.x, we use HtmlDecoration.unparse(text, caption_entities)
    to convert caption + caption_entities to HTML.

    Works for: photos, videos, documents, audio with captions.
    Custom-emoji (<tg-emoji>) wrappers are stripped (see module docstring).
    """
    if message.caption:
        from aiogram.utils.text_decorations import HtmlDecoration
        html_decoration = HtmlDecoration()
        return _strip_tg_emoji(html_decoration.unparse(message.caption, message.caption_entities))

    # Fallback to empty string if no caption
    return ""


def get_html_text(message: Message) -> str:
    """
    Get message text with HTML formatting preserved.

    Works for: regular text messages, forwarded messages, replies.
    Uses HtmlDecoration.unparse(text, entities) for consistent HTML extraction.
    Custom-emoji (<tg-emoji>) wrappers are stripped (see module docstring).
    """
    if message.text:
        from aiogram.utils.text_decorations import HtmlDecoration
        html_decoration = HtmlDecoration()
        return _strip_tg_emoji(html_decoration.unparse(message.text, message.entities))

    # Fallback to empty string if no text
    return ""
