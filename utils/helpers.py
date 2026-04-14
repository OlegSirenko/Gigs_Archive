# utils/helpers.py
"""Helper functions for formatting and text processing"""
import re
import json
from aiogram.types import Message, MessageOriginUser, MessageOriginChat, MessageOriginHiddenUser, MessageOriginChannel
from datetime import datetime, date
from typing import Optional, Dict
from utils.i18n import i18n, t


def has_valid_link(text: str) -> bool:
    """Check if text contains at least one valid URL/link"""
    if not text:
        return False
    
    # Simple but effective: matches domain.tld with optional protocol/www/path
    url_pattern = r'((?:https?://)?(?:www\.)?[a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?|t\.me/[^\s]+|telegram\.me/[^\s]+)'
    
    return bool(re.search(url_pattern, text, re.IGNORECASE))


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

def format_preview_text(data: dict) -> str:
    """Format preview text for confirmation step"""

    language = data.get('language', 'ru')  # Get language from data or default to ru

    preview = f"{t('poster_flow.confirmation.title', language)}\n\n"

    # Photo info
    if data.get('photo_file_id'):
        is_media_group = data.get('is_media_group', False)
        photos_json = data.get('photos_json')
        
        if is_media_group and photos_json:
            try:
                photos_list = json.loads(photos_json)
                photo_count = len(photos_list)
                preview += f"{t('poster_flow.preview.photo_attached', language)} ({t('poster_flow.preview.photos_count', language, count=photo_count)})\n"
            except:
                preview += f"{t('poster_flow.preview.photo_attached', language)}\n"
        else:
            preview += f"{t('poster_flow.preview.photo_attached', language)}\n"

    # Caption
    caption = data.get('caption', '')
    if not caption:
        caption = t('poster_flow.preview.no_description', language)
    if len(caption) > 100:
        caption = caption[:100] + '...'
    preview += f"\n{t('poster_flow.preview.description_label', language)}\n<code>{caption}</code>\n"

    # Event date - ✅ Convert string to date object
    event_date_str = data.get('event_date')
    if event_date_str:
        try:
            # Convert ISO string to date object
            if isinstance(event_date_str, str):
                date_formatted = datetime.fromisoformat(event_date_str).date()
            else:
                date_formatted = event_date_str

            # Now get_day_name will work
            day_name = i18n.get_day_name(date_formatted, language)
            date_display = date_formatted.strftime("%d.%m.%Y")

            preview += f"\n{t('poster_flow.date.date', language)} {day_name} {date_display}\n"
        except Exception as e:
            preview += f"\n{t('poster_flow.date.date', language)} {event_date_str}\n"

    # Anonymity
    is_anonymous = data.get('is_anonymous', False)
    if is_anonymous:
        preview += f"\n{t('poster_flow.preview.anonymous_label', language)}\n"
    else:
        preview += f"\n{t('poster_flow.preview.show_name_label', language)}\n"
        if data.get('username'):
            preview += f"@{data.get('username')}\n"
        else:
            preview += f"{data.get('first_name', t('poster_flow.preview.user_default', language))}\n"

    # Forwarded info
    if data.get('is_forwarded'):
        preview += f"\n{t('poster_flow.preview.forwarded_from', language)} {data.get('forward_source', t('poster_flow.preview.unknown_source', language))}\n"
        if data.get('telegram_link'):
            preview += f"🔗 {data.get('telegram_link')}\n"

    return preview

def format_moderation_caption(data: Dict, poster_id: int, language: str = "ru") -> str:
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
        date_formatted = t("moderation.preview.not_specified", language)

    return (
        f"{t('moderation.preview.submission_title', language)}\n\n"
        f"{t('moderation.preview.poster_id', language, poster_id=poster_id)}\n"
        f"{t('moderation.preview.user_id', language, user_id=data.get('user_id'))} (@{username})\n"
        f"{t('moderation.preview.anonymous', language, anonymous=t('common.yes' if is_anon else 'common.no', language))}\n"
        f"{t('moderation.preview.event_date', language, date=date_formatted)}\n\n"
        f"{t('moderation.preview.original_caption', language)}\n"
        f"{data.get('caption', t('moderation.preview.no_description', language))}"
    )


def format_public_caption(data: dict, user_info: dict | None = None, language: str = "ru") -> str:
    """
    Format the final public caption for channel posts.

    Args:
        data: dict with caption, event_date, is_anonymous, etc.
        user_info: dict with first_name, username (if not anonymous)
        language: language code for localization

    Returns:
        Formatted caption string with HTML tags
    """

    # ✅ Initialize ALL variables upfront to avoid UnboundLocalError
    author_line = ""
    date_line = ""
    caption = data.get("caption", "").strip()

    # ============ AUTHOR LINE ============
    if data.get("is_anonymous"):
        author_line = ""  # Anonymous = no author line
    elif user_info:
        if user_info.get("username"):
            author_line = f"👤 {user_info['username']}\n"
        elif user_info.get("first_name"):
            author_line = f"👤 {user_info['first_name']}\n"
        else:
            author_line = f"👤 {t('poster_flow.preview.user_default', language)}\n"
    else:
        # Fallback if user_info is None but not anonymous
        author_line = ""

    # ============ DATE LINE ============
    event_date = data.get("event_date")
    if event_date:
        try:
            # Handle both string and datetime objects
            if isinstance(event_date, str):
                from datetime import datetime
                event_date = datetime.fromisoformat(event_date)

            # Format: "📅 29 марта 2026" with localized month names
            month_names = {
                "ru": {
                    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
                    5: "мая", 6: "июня", 7: "июля", 8: "августа",
                    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
                },
                "en": {
                    1: "January", 2: "February", 3: "March", 4: "April",
                    5: "May", 6: "June", 7: "July", 8: "August",
                    9: "September", 10: "October", 11: "November", 12: "December"
                }
            }

            day = event_date.day
            month_ru = month_names.get("ru", {}).get(event_date.month, "месяца")
            month_en = month_names.get("en", {}).get(event_date.month, "Month")
            year = event_date.year

            # Use English month name if language is English, otherwise Russian
            if language == "en":
                date_line = f"📅 {month_en} {day}, {year}\n"
            else:
                date_line = f"📅 {day} {month_ru} {year}\n"
        except Exception as e:
            logger.warning(f"Could not format event date: {e}")
            date_line = f"📅 {event_date}\n"
    else:
        date_line = ""

    # ============ BUILD FINAL CAPTION ============

    # Add source link if forwarded from Telegram
    if data.get("telegram_link"):
        caption += f"\n\n🔗 Источник: {data['telegram_link']}"

    # Add attribution for forwarded posts
    if data.get("is_forwarded") and data.get("forward_source"):
        caption += f"\n<i>{t('poster_flow.forwarded.attribution', language, source=data['forward_source'])}</i>"

    # Combine all parts
    result = f"{author_line}{date_line}\n{caption}"

    return result.strip()


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


def extract_forwarded_info(message: Message) -> dict:
    """
    Extract relevant info from a forwarded message.
    
    Returns dict with:
    - caption: str
    - photo_file_id: str or None
    - source_name: str (channel/user name)
    - source_username: str or None
    - telegram_link: str or None
    - is_channel_forward: bool ← NEW: True if from channel/group
    """
    info = {
        'caption': None,
        'photo_file_id': None,
        'source_name': None,
        'source_username': None,
        'telegram_link': None,
        'is_channel_forward': False 
    }
    
    if message.forward_origin:
        origin = message.forward_origin
        
        if isinstance(origin, MessageOriginUser):
            info['source_name'] = origin.sender_user.first_name
            if origin.sender_user.username:
                info['source_username'] = f"@{origin.sender_user.username}"
            # ❌ Not a channel forward
            info['is_channel_forward'] = False
            
        elif isinstance(origin, MessageOriginChat):
            info['source_name'] = origin.sender_chat.title
            if origin.sender_chat.username:
                info['source_username'] = f"@{origin.sender_chat.username}"
                info['telegram_link'] = f"https://t.me/{origin.sender_chat.username}/{origin.message_id}"
            elif origin.sender_chat.id:
                chat_id = str(origin.sender_chat.id)
                if chat_id.startswith('-100'):
                    chat_id = chat_id[4:]
                info['telegram_link'] = f"https://t.me/c/{chat_id}/{origin.message_id}"
            # ✅ Channel/group forward
            info['is_channel_forward'] = True
            
        elif isinstance(origin, MessageOriginHiddenUser):
            info['source_name'] = origin.sender_user_name
            info['source_username'] = None
            info['is_channel_forward'] = False
            
        elif isinstance(origin, MessageOriginChannel):
            info['source_name'] = origin.chat.title if origin.chat else "Канал"
            if origin.chat and origin.chat.username:
                info['source_username'] = f"@{origin.chat.username}"
                info['telegram_link'] = f"https://t.me/{origin.chat.username}/{origin.message_id}"
            elif origin.chat and origin.chat.id:
                chat_id = str(origin.chat.id)
                if chat_id.startswith('-100'):
                    chat_id = chat_id[4:]
                info['telegram_link'] = f"https://t.me/c/{chat_id}/{origin.message_id}"
            # ✅ Channel forward
            info['is_channel_forward'] = True
    
    # Get message content — use html_text for text messages
    from utils.html import get_html_caption, get_html_text
    
    text = get_html_text(message) if message.text else (message.caption or "")

    if text:
        info['caption'] = text

    if message.photo:
        info['photo_file_id'] = message.photo[-1].file_id
        if not info['caption']:
            info['caption'] = get_html_caption(message)

    elif message.video:
        if message.video.thumbnails:
            info['photo_file_id'] = message.video.thumbnails[-1].file_id
        if not info['caption']:
            info['caption'] = get_html_caption(message)

    elif message.document:
        if message.document.thumbnails:
            info['photo_file_id'] = message.document.thumbnails[-1].file_id
        if not info['caption']:
            info['caption'] = get_html_caption(message)
    
    return info


def format_channel_post_link(poster) -> str | None:
    """
    Build Telegram link to published channel post.
    
    Args:
        poster: Poster object with channel_message_id and channel_chat_id
    
    Returns:
        str: Link like 'https://t.me/channelname/123' or None if not published
    """
    if not poster.channel_message_id or not poster.channel_chat_id:
        return None
    
    chat_id = str(poster.channel_chat_id)
    message_id = poster.channel_message_id
    
    # Format link based on chat type
    if chat_id.startswith('-100'):
        # Supergroup/channel
        chat_id_clean = chat_id[4:]
        return f"https://t.me/c/{chat_id_clean}/{message_id}"
    elif chat_id.startswith('-'):
        # Private group (may not work, but try)
        chat_id_clean = chat_id[1:]
        return f"https://t.me/c/{chat_id_clean}/{message_id}"
    else:
        # Public username
        return f"https://t.me/{chat_id}/{message_id}"