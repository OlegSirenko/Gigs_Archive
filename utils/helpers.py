# utils/helpers.py
"""Helper functions for formatting and text processing"""
import logging
import re
import json
import html
from aiogram.types import Message, MessageOriginUser, MessageOriginChat, MessageOriginHiddenUser, MessageOriginChannel
from datetime import datetime, date
from typing import Optional, Dict
from utils.i18n import i18n, t

logger = logging.getLogger(__name__)

# Диапазоны кодовых точек эмодзи и декоративных пиктограмм
# (синхронизировано с web/helpers.py — тот же паттерн используется на сайте)
_EMOJI_RE = re.compile(
    "["
    "\U0001F1E6-\U0001F1FF"   # флаги-символы
    "\U0001F300-\U0001FAFF"   # основной блок эмодзи (включая 🎸, 🔥 и т.п.)
    "\U00002600-\U000027BF"   # misc symbols и дингбаты (☀–➿, ✔, ✨)
    "\U0001F000-\U0001F0FF"   # маджонг/домино/карты
    "\U00002B00-\U00002BFF"   # стрелки и прочие символы (⬆–⭐)
    "\U0000FE00-\U0000FE0F"   # variation selectors
    "\U0000200D"              # zero-width joiner
    "\U00002049\U0000203C"    # ⁉ ‼
    "\U00002122\U00002139"    # ™ ℹ
    "\U00002194-\U000021AA"   # ↔ … ↪ стрелки
    "\U0000231A-\U0000231B"   # ⌚ ⌛
    "\U00002328"              # ⌨
    "\U000023CF-\U000023FA"   # ⏏ – ⏺
    "\U000024C2"              # Ⓜ
    "\U000025AA-\U000025FE"   # геометрические фигуры ▪ – ◾
    "\U00002934-\U00002935"   # ⤴ ⤵
    "\U00003030\U0000303D"    # 〰 〽
    "\U00003297\U00003299"    # ㊗ ㊙
    "]+",
    flags=re.UNICODE,
)

# Остатки telegram-разметки: <a href="...">...</a>, голые URL, markdown-ссылки
_TG_LINK_TAG_RE = re.compile(r'<a\b[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
_TG_HTML_TAG_RE = re.compile(
    r'</?\s*(?:a|u|s|strong|ins|del|b|i|em|span|pre|code|blockquote)\b[^>]*>',
    re.IGNORECASE,
)
_MD_LINK_RE = re.compile(r'\[([^\]]*)\]\((?:https?://)?[^\s)]+\)')
_BARE_URL_RE = re.compile(
    r'(?:https?://|www\.)[^\s<>"]+|t\.me/[^\s<>"]+|telegram\.me/[^\s<>"]+',
    re.IGNORECASE,
)
_MD_MARKERS_RE = re.compile(r'\*\*|__|~~|\|\||`')


def strip_emoji(text: str | None) -> str:
    """Удаляет все эмодзи и декоративные пиктограммы из текста."""
    if not text:
        return ""
    cleaned = _EMOJI_RE.sub("", text)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()


def strip_telegram_markup(text: str | None) -> str:
    """Полностью убирает разметку Telegram, оставляя только чистый текст.

    Ссылки <a href="...">текст</a> и [текст](url) превращаются просто в «текст»,
    голые URL вырезаются, теги <b>/<i> и символы **/__ удаляются.
    Синхронизировано с web/helpers.py — так бот показывает заголовки событий
    так же, как сайт.
    """
    if not text:
        return ""
    text = _TG_LINK_TAG_RE.sub(lambda m: m.group(1), text)
    text = _MD_LINK_RE.sub(lambda m: m.group(1), text)
    text = _TG_HTML_TAG_RE.sub("", text)
    text = _BARE_URL_RE.sub("", text)
    text = re.sub(r'(?:\*\*|__)((?!\s).+?(?<!\s))(?:\*\*|__)', r'\1', text)
    text = _MD_MARKERS_RE.sub("", text)
    return text


def first_line(caption: str | None, fallback: str = "Event") -> str:
    """Первая непустая строка описания — как карточки на сайте.

    Без эмодзи и без какой-либо разметки: ссылки не допускаются,
    остаётся только чистый текст.
    """
    if not caption:
        return fallback
    for line in caption.splitlines():
        line = strip_telegram_markup(strip_emoji(line)).strip()
        if line:
            return line[:120]
    return fallback


def has_valid_link(text: str) -> bool:
    """
    Check if text contains at least one valid URL/link.
    Handles plain URLs, HTML-encoded URLs, and href attributes.
    """
    if not text:
        return False
    
    # ✅ Step 1: Decode HTML entities (&amp; → &, &lt; → <, etc.)
    # This ensures encoded URLs are detectable
    decoded = html.unescape(text)
    
    # ✅ Step 2: Check for URLs inside href attributes (HTML-formatted links)
    # Matches: href="https://...", href='https://...', href=https://...
    href_pattern = r'href\s*=\s*["\']?((?:https?://)?[a-zA-Z0-9-]+\.[a-zA-Z]{2,}[^\s<>"\']*)'
    if re.search(href_pattern, decoded, re.IGNORECASE):
        return True
    
    # ✅ Step 3: Your original pattern (now runs on decoded text)
    # Matches: https://example.com, example.com/path, t.me/user, etc.
    url_pattern = r'((?:https?://)?(?:www\.)?[a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?|t\.me/[^\s]+|telegram\.me/[^\s]+)'
    
    return bool(re.search(url_pattern, decoded, re.IGNORECASE))


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
    
    # Escape HTML inside <code> block to prevent parsing errors
    # (forwarded messages may contain HTML like <a href="...">)
    caption_for_code = html.escape(caption)
    
    if len(caption_for_code) > 100:
        caption_for_code = caption_for_code[:100] + '...'
    
    preview += f"\n{t('poster_flow.preview.description_label', language)}\n<code>{caption_for_code}</code>\n"

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


# Telegram photo caption hard limit (in characters). Captions longer than this
# are rejected by the Bot API with error "TOO_LONG".
TG_CAPTION_LIMIT = 1024


def plain_text_length(html_text: str) -> int:
    """Return the length of the text as Telegram will see it after parsing HTML.

    Telegram counts <b>/<i>/<a href="...">visible text</a> tags by their inner
    text only (the markup itself is not counted), so we strip tags and decode
    entities before measuring. This lets us warn users *before* hitting the
    "message caption TOO_LONG" API error.
    """
    if not html_text:
        return 0
    without_links = _TG_LINK_TAG_RE.sub(r"\1", html_text)
    without_tags = _TG_HTML_TAG_RE.sub("", without_links)
    return len(html.unescape(without_tags))


def validate_caption(caption: str, language: str = "ru") -> tuple[bool, str]:
    """
    Validate poster caption:
      1. must not be empty;
      2. must not exceed Telegram's photo-caption length limit (1024 chars);
      3. must contain at least one valid link.

    Returns: (is_valid, error_message) - error_message is an HTML-formatted,
    localized explanation that tells the user exactly what is wrong and how to
    fix it.
    """
    stripped = (caption or "").strip()

    # ---- Empty caption ---------------------------------------------------
    if not stripped:
        return False, (
            f"{t('poster_flow.validation_error.empty', language)}\n\n"
            f"{t('poster_flow.validation_error.examples_title', language)}\n"
            f"{t('poster_flow.validation_error.examples', language)}\n\n"
            f"{t('poster_flow.validation_error.retry_hint', language)}"
        )

    # ---- Too long ("too many chars") -------------------------------------
    actual_len = plain_text_length(stripped)
    if actual_len > TG_CAPTION_LIMIT:
        return False, (
            t(
                "poster_flow.validation_error.too_long",
                language,
                current=actual_len,
                limit=TG_CAPTION_LIMIT,
                excess=actual_len - TG_CAPTION_LIMIT,
            )
            + "\n\n"
            + t("poster_flow.validation_error.too_long_hint", language)
            + "\n\n"
            + t("poster_flow.validation_error.retry_hint", language)
        )

    # ---- Missing link ----------------------------------------------------
    if not has_valid_link(stripped):
        return False, (
            f"{t('poster_flow.validation_error.no_link', language)}\n\n"
            f"{t('poster_flow.validation_error.examples_title', language)}\n"
            f"{t('poster_flow.validation_error.examples', language)}\n\n"
            f"{t('poster_flow.validation_error.retry_hint', language)}"
        )

    return True, ""


def describe_telegram_error(error: Exception, language: str = "ru") -> str:
    """Translate a raw aiogram/Telegram API exception into a friendly,
    human-readable explanation the user can act on.

    Falls back to a generic message with the original error text so nothing
    is ever silently swallowed.
    """
    status_code = getattr(error, "status_code", None) or getattr(error, "code", None)
    raw = str(error)
    lowered = raw.lower()

    # Message/caption exceeds Telegram limits (HTTP 400, "TOO_LONG")
    if "too_long" in lowered or "too long" in lowered:
        return t("common.errors.too_long", language)

    # Bad entity offsets / unbalanced HTML tags (HTTP 400, "can't parse entities")
    if ("can't parse entities" in lowered
            or "unsupported start offset" in lowered
            or "invalid entity" in lowered):
        return t("common.errors.bad_html", language)

    # File problems
    if "file_reference_expired" in lowered or "file id expired" in lowered:
        return t("common.errors.file_expired", language)
    if "file_too_big" in lowered:
        return t("common.errors.file_too_big", language)

    # Permissions
    if "chat not found" in lowered:
        return t("common.errors.chat_not_found", language)
    if "bot was blocked" in lowered or "user is deactivated" in lowered:
        return t("common.errors.bot_blocked", language)

    generic = t("common.error", language)
    if status_code:
        return f"{generic}\n\n<code>HTTP {status_code}: {html.escape(raw[:200])}</code>"
    return f"{generic}\n\n<code>{html.escape(raw[:200])}</code>"


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
    
    # Get message content — use HTML helpers to preserve formatting
    from utils.html import get_html_caption, get_html_text

    if message.text:
        # Text message with possible HTML entities
        info['caption'] = get_html_text(message)
    elif message.caption:
        # Photo/video/document with caption - preserve HTML
        info['caption'] = get_html_caption(message)

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