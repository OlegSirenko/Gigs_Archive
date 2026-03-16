# utils/helpers.py
"""Helper functions for formatting and text processing"""
import re
from datetime import datetime, date
from typing import Optional, Dict

def format_date(d: date | datetime) -> str:
    """Format date as 'Monday, 15 March 2026'"""
    if isinstance(d, datetime):
        d = d.date()
    return d.strftime("%A, %d %B %Y")

def format_date_short(d: date | datetime) -> str:
    """Format date as '15 Mar 2026'"""
    if isinstance(d, datetime):
        d = d.date()
    return d.strftime("%d %b %Y")

def truncate_text(text: str, max_length: int = 100) -> str:
    """Truncate text with ellipsis"""
    if not text:
        return "No description"
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."

def format_preview_text(data: Dict) -> str:
    """Format poster preview for user confirmation"""
    is_anon = data.get("is_anonymous", False)
    author = "🔒 Anonymous" if is_anon else f"👤 {data.get('first_name', 'User')}"
    
    event_date = data.get("event_date")
    if event_date:
        try:
            date_obj = datetime.fromisoformat(event_date).date()
            date_formatted = format_date(date_obj)
        except:
            date_formatted = event_date
    else:
        date_formatted = "Not specified"
    
    caption = truncate_text(data.get("caption", "No description"), 200)
    
    return (
        f"👁️ <b>Preview Your Poster</b>\n\n"
        f"{author}\n"
        f"📅 <b>Date:</b> {date_formatted}\n\n"
        f"📝 <b>Description:</b>\n"
        f"<code>{caption}</code>\n\n"
        f"<i>Everything looks good? Confirm to submit for moderation!</i>"
    )

def format_moderation_caption(data: Dict, poster_id: int) -> str:
    """Format caption for moderation chat"""
    is_anon = data.get("is_anonymous", False)
    username = data.get("username", "no_username")
    
    event_date = data.get("event_date")
    if event_date:
        try:
            date_obj = datetime.fromisoformat(event_date).date()
            date_formatted = format_date_short(date_obj)
        except:
            date_formatted = event_date
    else:
        date_formatted = "Not specified"
    
    return (
        f"📨 <b>New Poster Submission</b>\n\n"
        f"🆔 Poster ID: <code>{poster_id}</code>\n"
        f"👤 User: <code>{data.get('user_id')}</code> (@{username})\n"
        f"🔒 Anonymous: {'Yes' if is_anon else 'No'}\n"
        f"📅 Event Date: {date_formatted}\n\n"
        f"📝 <b>Original Caption:</b>\n"
        f"{data.get('caption', 'No description')}"
    )

def format_public_caption(data: dict, user_info: Optional[dict] = None) -> str:
    """Format final caption for public channel"""
    is_anon = data.get("is_anonymous", False)
    
    # Author line
    if is_anon:
        author_line = "🔒 <b>Anonymous submission</b>"
    else:
        # Non-anonymous: show user info
        if user_info:
            name = user_info.get("first_name", "User")
            username = user_info.get("username")
            if username:
                author_line = f"👤 <b>Submitted by @{username}</b>"
            else:
                author_line = f"👤 <b>Submitted by {name}</b>"
        else:
            author_line = "👤 <b>Submitted by User</b>"
    
    # Event date line
    event_date = data.get("event_date")
    date_line = ""
    if event_date:
        try:
            date_obj = datetime.fromisoformat(event_date).date()
            date_formatted = format_date(date_obj)
            date_line = f"\n📅 <b>Date:</b> {date_formatted}"
        except:
            pass
    
    # Caption with hashtag
    caption = data.get("caption", "No description")
    if "#афиша" not in caption.lower():
        caption += "\n\n#афиша"
    
    return f"{author_line}{date_line}\n\n{caption}"


def has_valid_link(text: str) -> bool:
    """Check if text contains at least one valid URL/link"""
    if not text:
        return False
    
    # Simple but effective: matches domain.tld with optional protocol/www/path
    url_pattern = r'((?:https?://)?(?:www\.)?[a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?|t\.me/[^\s]+|telegram\.me/[^\s]+)'
    
    return bool(re.search(url_pattern, text, re.IGNORECASE))


def validate_caption(caption: str) -> tuple[bool, str]:
    """
    Validate poster caption - just check for at least one link.
    Returns: (is_valid, error_message)
    """
    if not caption or len(caption.strip()) == 0:
        return False, "⚠️ Please add at least one link to the event."
    
    if not has_valid_link(caption):
        return False, (
            "⚠️ Please add at least one link to the event.\n\n"
            "<i>Examples:</i>\n"
            "• example.com\n"
            "• https://tickets.com\n"
            "• t.me/myevent"
        )
    return True, ""