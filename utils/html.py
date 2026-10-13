"""
HTML caption extraction helper for aiogram 3.x

IMPORTANT: Custom-emoji (<tg-emoji>) tags are preserved as-is.
We no longer strip them because Telegram Bot API supports publishing
them directly to channels/groups (they render correctly in TG clients).
Stripping would downgrade a Premium emoji <tg-emoji emoji-id="...">🔥</tg-emoji>
to a plain Unicode flame 🔥, losing its animated/custom appearance.
"""
import re

from aiogram.types import Message

# <tg-emoji emoji-id="...">😀</tg-emoji> — Telegram's custom (premium) emoji
# markup produced by HtmlDecoration.unparse(). We NOW KEEP these tags instead of
# stripping them, so custom-premium emojis render correctly in channel posts.
_TG_EMOJI_TAG_RE = re.compile(r'<tg-emoji\b[^>]*>(.*?)</tg-emoji>', re.IGNORECASE | re.DOTALL)


def _keep_tg_emoji(match: re.Match) -> str:
    """Replace <tg-emoji ...>EMOJI</tg-emoji> → EMOJI (just unwrap, preserve content)."""
    if not match:
        return ""
    return match.group(1)


def get_html_caption(message: Message) -> str:
    """
    Get message caption with HTML formatting preserved.

    In aiogram 3.x, we use HtmlDecoration.unparse(text, caption_entities)
    to convert caption + caption_entities to HTML.

    Works for: photos, videos, documents, audio with captions.
    Custom-emoji (<tg-emoji>) wrappers are PRESERVED — they must be kept
    so Premium emojis render correctly when published to channels.
    """
    if message.caption:
        from aiogram.utils.text_decorations import HtmlDecoration
        html_decoration = HtmlDecoration()
        return html_decoration.unparse(message.caption, message.caption_entities)

    # Fallback to empty string if no caption
    return ""


def get_html_text(message: Message) -> str:
    """
    Get message text with HTML formatting preserved.

    Works for: regular text messages, forwarded messages, replies.
    Uses HtmlDecoration.unparse(text, entities) for consistent HTML extraction.
    Custom-emoji (<tg-emoji>) wrappers are PRESERVED — see module docstring.
    """
    if message.text:
        from aiogram.utils.text_decorations import HtmlDecoration
        html_decoration = HtmlDecoration()
        return html_decoration.unparse(message.text, message.entities)

    # Fallback to empty string if no text
    return ""
