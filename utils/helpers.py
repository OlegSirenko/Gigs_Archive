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
        # Moderation chat shows the submission as a *photo caption* (1024-char
        # hard limit). The user's caption was validated against 874 chars, but
        # this header adds ~150 more — trim defensively so the API never
        # rejects the moderation post with an opaque "TOO_LONG".
        f"{_trim_caption(data.get('caption') or t('moderation.preview.no_description', language))}"
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

    # Final safety net: Telegram rejects photo captions longer than 1024 chars
    # with an opaque "TOO_LONG" API error. The user caption was validated
    # against a smaller effective limit, but attribution/source links appended
    # here could still push it over — trim defensively instead of failing.
    return _trim_caption(result.strip())


# Telegram photo caption hard limit (in characters). Captions longer than this
# are rejected by the Bot API with error "TOO_LONG".
TG_CAPTION_LIMIT = 1024

# Hard limit for a plain text message sent by a bot (Telegram Bot API):
# 4,096 UTF-8 characters. Longer texts must be split into several messages.
TG_TEXT_LIMIT = 4096

# Safety margin so attribution/links appended after validation still fit.
TG_CAPTION_SAFETY_MARGIN = 150

# Effective limit used when validating user captions: the real API limit minus
# the safety margin (author line, date line, source link etc. are added later).
TG_CAPTION_EFFECTIVE_LIMIT = TG_CAPTION_LIMIT - TG_CAPTION_SAFETY_MARGIN


def split_message(text: str, limit: int = TG_TEXT_LIMIT) -> list[str]:
    """Split a long text into chunks that each fit within ``limit`` characters.

    Tries to keep HTML formatting valid across chunk boundaries: any tags that
    are opened inside a chunk but not closed there are closed at the end of the
    chunk and re-opened at the start of the next one. Chunks are broken at
    paragraph or word boundaries whenever possible.
    """
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    tag_re = re.compile(r"<(/?)(b|i|u|s|a|code|pre|blockquote)(\s[^>]*)?>", re.IGNORECASE)

    def _visible_len(s: str) -> int:
        return len(tag_re.sub("", s))

    def _open_tags(s: str) -> list[str]:
        """Return stack of currently-open simple tags after scanning ``s``."""
        stack: list[str] = []
        for m in tag_re.finditer(s):
            closing, name = m.group(1) == "/", m.group(2).lower()
            if closing:
                # pop matching tag (tolerate stray closers)
                for i in range(len(stack) - 1, -1, -1):
                    if stack[i].startswith(f"</{name}") is False and stack[i][1:].split(" ")[0].rstrip(">") == name:
                        del stack[i]
                        break
            else:
                stack.append(m.group(0))
        return stack

    chunks: list[str] = []
    remaining = text
    while remaining:
        if _visible_len(remaining) <= limit:
            piece, remaining = remaining, ""
        else:
            # Walk char-by-char until visible length hits the limit.
            cut = 0
            visible = 0
            i = 0
            n = len(remaining)
            while i < n:
                m = tag_re.match(remaining, i)
                if m:
                    cut = m.end()
                    i = m.end()
                    continue
                visible += 1
                if visible > limit - 10:  # leave room to close open tags
                    break
                i += 1
            cut = i if i else cut

            # Prefer a paragraph / word boundary near the cut.
            head = remaining[:cut]
            for sep in ("\n\n", "\n", " "):
                boundary = head.rfind(sep)
                if boundary > cut * 0.5:
                    cut = boundary + (len(sep) if sep != " " else 0)
                    break

            piece, remaining = remaining[:cut], remaining[cut:]

            # Keep HTML balanced across the boundary.
            opens = _open_tags(piece)
            closes = "".join(f"</{m.group(2).lower()}>" for m in
                             (re.finditer(r"<(b|i|u|s|a|code|pre|blockquote)(\s[^>]*)?>", p, re.IGNORECASE)
                              for p in opens))
            if closes:
                piece += closes
                remaining = closes.replace("</", "<") + remaining

        chunks.append(piece.strip())

    return [c for c in chunks if c]


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
    # Validate against the *effective* limit (1024 minus a safety margin),
    # because author line / date / source link are appended later in the flow
    # and would otherwise push the final caption over the API limit.
    actual_len = plain_text_length(stripped)
    if actual_len > TG_CAPTION_EFFECTIVE_LIMIT:
        return False, (
            t(
                "poster_flow.validation_error.too_long",
                language,
                current=actual_len,
                limit=TG_CAPTION_EFFECTIVE_LIMIT,
                excess=actual_len - TG_CAPTION_EFFECTIVE_LIMIT,
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


def _trim_caption(caption: str, limit: int = TG_CAPTION_LIMIT) -> str:
    """Trim an HTML caption so its *visible* length fits Telegram's 1024-char
    photo-caption limit. Cuts at paragraph/word boundaries and re-balances any
    HTML tag left open by the cut, so the result is always valid HTML."""
    if not caption or plain_text_length(caption) <= limit:
        return caption

    tag_re = re.compile(r"<(/?)(b|i|u|s|a|code|pre|blockquote)(\s[^>]*)?>", re.IGNORECASE)
    cut = 0
    visible = 0
    i = 0
    n = len(caption)
    while i < n:
        m = tag_re.match(caption, i)
        if m:
            i = m.end()
            continue
        visible += 1
        if visible > limit - 30:  # room for ellipsis + closing tags
            break
        i += 1
    trimmed = caption[:i]

    # Prefer a cleaner boundary near the end.
    for sep in ("\n\n", "\n", " "):
        b = trimmed.rfind(sep)
        if b > len(trimmed) * 0.7:
            trimmed = trimmed[:b]
            break

    # Close any tags left open by the cut (simple LIFO over known tags).
    opens: list[str] = []
    for m in tag_re.finditer(trimmed):
        if m.group(1) == "/":
            for j in range(len(opens) - 1, -1, -1):
                if tag_re.fullmatch(opens[j]).group(2).lower() == m.group(2).lower():
                    del opens[j]
                    break
        else:
            opens.append(m.group(0))
    closers = "".join(f"</{tag_re.fullmatch(p).group(2).lower()}>" for p in reversed(opens))

    return trimmed.rstrip() + "…" + closers


async def send_long_message(
    bot,
    chat_id: int,
    text: str,
    parse_mode: str = "HTML",
    reply_markup=None,
    disable_web_page_preview: bool = True,
):
    """Send a text message, automatically splitting it into several messages if
    it exceeds Telegram's 4096-character limit (the Bot API rejects longer
    texts with HTTP 400 'TOO_LONG').

    Returns the first sent Message (or None when the text was empty).
    Only the last chunk carries the reply keyboard.
    """
    if not text:
        return None
    chunks = split_message(text, TG_TEXT_LIMIT)
    first = None
    for idx, chunk in enumerate(chunks):
        sent = await bot.send_message(
            chat_id=chat_id,
            text=chunk,
            parse_mode=parse_mode,
            reply_markup=reply_markup if idx == len(chunks) - 1 else None,
            disable_web_page_preview=disable_web_page_preview,
        )
        if first is None:
            first = sent
    if len(chunks) > 1:
        logger.info(f"Split long message ({len(text)} chars) into {len(chunks)} parts for chat {chat_id}")
    return first


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