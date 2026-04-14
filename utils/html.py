"""
HTML caption extraction helper for aiogram 3.x
"""
from aiogram.types import Message


def get_html_caption(message: Message) -> str:
    """
    Get message caption with HTML formatting preserved.
    
    In aiogram 3.x, we use HtmlDecoration.unparse(text, entities)
    to convert caption + caption_entities to HTML.
    
    Usage:
        caption = get_html_caption(message)  # Returns formatted HTML or plain text
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
    Uses message.html_text which is built into aiogram 3.x
    """
    return message.html_text if message.html_text else (message.text or "")

