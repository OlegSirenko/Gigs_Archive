"""
HTML caption extraction helper for aiogram 3.x
"""
from aiogram.types import Message


def get_html_caption(message: Message) -> str:
    """
    Get message caption with HTML formatting preserved.

    In aiogram 3.x, we use HtmlDecoration.unparse(text, caption_entities)
    to convert caption + caption_entities to HTML.

    Works for: photos, videos, documents, audio with captions.
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
    """
    if message.text:
        from aiogram.utils.text_decorations import HtmlDecoration
        html_decoration = HtmlDecoration()
        return html_decoration.unparse(message.text, message.entities)
    
    # Fallback to empty string if no text
    return ""

