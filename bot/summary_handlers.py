# bot/summary_handlers.py
"""
Weekly summary handlers for Гиги Архив bot.
✨ Pretty output, prime-time highlighting, auto Friday DMs
"""

import logging
import re
import asyncio
from datetime import datetime, timedelta, date
from typing import List, Dict

from aiogram import Router, F, types
from aiogram.filters import Command

from db.models import get_session, Poster
from db.crud import get_posters_by_date_range, get_user
from utils.i18n import i18n, t
from utils.helpers import format_channel_post_link

logger = logging.getLogger(__name__)

summary_router = Router(name="summary")

# 🗓️ Russian day names (Mon=0 ... Sun=6)
RU_DAY_NAMES = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

# 🎯 Prime-time days: always show individually (Fri=4, Sat=5, Sun=6)
PRIME_DAYS = [4, 5, 6]


# =============================================================================
# ✨ HELPER FUNCTIONS
# =============================================================================

def get_short_description(caption: str, max_length: int = 120, language: str = "ru") -> str:
    """Extract a short, clean description from caption"""
    if not caption:
        return t("weekly_summary.no_description", language)

    # Remove URLs for cleaner preview
    clean = re.sub(r'https?://[^\s]+', '', caption)
    clean = ' '.join(clean.split())  # Normalize whitespace

    # Truncate with word boundary
    if len(clean) > max_length:
        return clean[:max_length].rsplit(' ', 1)[0] + "..."

    return clean.strip() or t("weekly_summary.no_description", language)


def _group_posters_by_date(posters: List[Poster]) -> Dict[date, List[Poster]]:
    """Group posters by their event date (date object as key)"""
    grouped: Dict[date, List[Poster]] = {}
    
    for poster in posters:
        event_date = poster.event_date
        if isinstance(event_date, datetime):
            event_date = event_date.date()
        
        if event_date not in grouped:
            grouped[event_date] = []
        grouped[event_date].append(poster)
    
    return grouped


def _format_date_header(date_obj: date) -> str:
    """Format date as bold header: <b>19.03|Пт</b>"""
    date_str = date_obj.strftime("%d.%m")
    day_name = RU_DAY_NAMES[date_obj.weekday()]
    return f"<b>{date_str}|{day_name}</b>"


def _format_collapsed_header(start: date, end: date) -> str:
    """Format collapsed range: <b>16.03|Пн - 19.03|Чт</b>"""
    start_str = start.strftime("%d.%m")
    start_day = RU_DAY_NAMES[start.weekday()]
    end_str = end.strftime("%d.%m")
    end_day = RU_DAY_NAMES[end.weekday()]
    return f"<b>{start_str}|{start_day} - {end_str}|{end_day}</b>"


def _render_date_block(date_obj: date, posters: List[Poster], language: str = "ru") -> List[str]:
    """Render a single date block with posters (returns list of lines)"""
    lines = ["", _format_date_header(date_obj)]

    for poster in posters:
        link = format_channel_post_link(poster)
        desc = get_short_description(poster.caption, language=language)

        if link:
            lines.append(f"• <a href=\"{link}\">{desc}</a>")
        else:
            lines.append(f"• {desc}")

    return lines


def _build_manual_summary(
    posters_by_date: Dict[date, List[Poster]],
    week_start: date,
    week_end: date,
    language: str
) -> str:
    """Build detailed summary for manual /summary command"""

    lines = []

    # 📋 Header
    lines.append(t('weekly_summary.title', language))
    lines.append("")
    lines.append(t('weekly_summary.period', language,
                   start_date=week_start.strftime('%d.%m'),
                   end_date=week_end.strftime('%d.%m')))
    lines.append(t('weekly_summary.total', language,
                   count=sum(len(p) for p in posters_by_date.values())))

    # 🗓️ Weekdays (Mon–Thu): collapse if empty, show individually if not
    weekday_dates = [d for d in posters_by_date if d.weekday() not in PRIME_DAYS]

    if weekday_dates:
        # Show each weekday with events
        for date_obj in sorted(d for d in posters_by_date if d.weekday() not in PRIME_DAYS):
            lines.extend(_render_date_block(date_obj, posters_by_date[date_obj], language))
    else:
        # Collapse empty Mon–Thu into one line
        mon = week_start
        thu = week_start + timedelta(days=3)
        lines.append("")
        lines.append(_format_collapsed_header(mon, thu))
        lines.append(t("weekly_summary.empty_weekdays", language))
    
    # 🎉 Prime-time days (Fri–Sun): always show individually
    for day_offset in PRIME_DAYS:
        prime_date = week_start + timedelta(days=day_offset)
        if prime_date > week_end:
            continue
            
        lines.append("")
        lines.append(_format_date_header(prime_date))
        
        if prime_date in posters_by_date:
            for poster in posters_by_date[prime_date]:
                link = format_channel_post_link(poster)
                desc = get_short_description(poster.caption)
                
                if link:
                    lines.append(f"• <a href=\"{link}\">{desc}</a>")
                else:
                    lines.append(f"• {desc}")
        else:
            lines.append(t("weekly_summary.empty_day", language))
    
    # 🔚 Footer
    lines.append("")
    lines.append(t('weekly_summary.footer', language))
    
    return "\n".join(lines)


def format_auto_friday_summary(
    posters_by_date: Dict[date, List[Poster]],
    week_start: date,
    week_end: date,
    language: str = "ru"
) -> str:
    """
    Friendly, casual summary for auto Friday DM.
    Less technical, more engaging ✨
    """
    lines = []

    lines.append(t("subscription.friday_message.title", language))
    lines.append("")

    # Count total events
    total = sum(len(p) for p in posters_by_date.values())

    if total == 0:
        lines.append(t("subscription.friday_message.no_events", language))
        lines.append("")
        lines.append(t("subscription.friday_message.hint", language))
        return "\n".join(lines)

    lines.append(t("subscription.friday_message.found_events", language, count=total))
    
    # Show only Fri–Sun (prime time)
    for day_offset in PRIME_DAYS:
        prime_date = week_start + timedelta(days=day_offset)
        if prime_date > week_end:
            continue
            
        day_name = RU_DAY_NAMES[prime_date.weekday()]
        date_str = prime_date.strftime("%d.%m")
        
        if prime_date in posters_by_date:
            lines.append("")
            lines.append(f"🗓️ <b>{date_str} {day_name}</b>")
            
            for poster in posters_by_date[prime_date][:5]:  # Limit 5 per day
                link = format_channel_post_link(poster)
                desc = get_short_description(poster.caption, max_length=80)
                
                if link:
                    lines.append(f"• <a href=\"{link}\">{desc}</a>")
                else:
                    lines.append(f"• {desc}")
    
    lines.append("")
    lines.append(t("subscription.friday_message.footer", language))

    return "\n".join(lines)


# =============================================================================
# 📊 USER COMMANDS
# =============================================================================

@summary_router.message(Command("summary"))
async def cmd_summary(message: types.Message):
    """📊 Show weekly summary with prime-time highlighting"""
    
    language = i18n.get_user_language(message.from_user.language_code)
    
    # 📅 Calculate week boundaries (Mon–Sun)
    today = datetime.now().date()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    
    # 🔍 Fetch approved posters for this week
    with get_session() as session:
        posters = get_posters_by_date_range(
            session,
            start_date=datetime.combine(week_start, datetime.min.time()),
            end_date=datetime.combine(week_end, datetime.max.time()),
            limit=100
        )
    
    # 📭 Handle empty week
    if not posters:
        await message.answer(
            t("weekly_summary.no_events", language),
            parse_mode="HTML"
        )
        return
    
    # 🗂️ Group posters by event date
    posters_by_date = _group_posters_by_date(posters)
    
    # ✨ Build the summary
    summary_text = _build_manual_summary(
        posters_by_date=posters_by_date,
        week_start=week_start,
        week_end=week_end,
        language=language
    )
    
    # 📤 Send to user
    await message.answer(
        summary_text,
        parse_mode="HTML",
        disable_web_page_preview=False
    )
    
    logger.info(f"📊 Weekly summary requested by user {message.from_user.id}")


@summary_router.message(Command("sub_on"))
async def cmd_subscribe_on(message: types.Message):
    """✅ Enable weekly Friday summary"""

    language = i18n.get_user_language(message.from_user.language_code)

    with get_session() as session:
        user = get_user(session, message.from_user.id)
        if user:
            user.subscribe_weekly = True
            session.commit()

    await message.answer(
        t("subscription.sub_on.title", language) + "\n\n" +
        t("subscription.sub_on.description", language) + "\n\n" +
        t("subscription.sub_on.unsubscribe_hint", language),
        parse_mode="HTML"
    )


@summary_router.message(Command("sub_off"))
async def cmd_subscribe_off(message: types.Message):
    """❌ Disable weekly Friday summary"""

    language = i18n.get_user_language(message.from_user.language_code)

    with get_session() as session:
        user = get_user(session, message.from_user.id)
        if user:
            user.subscribe_weekly = False
            session.commit()

    await message.answer(
        t("subscription.sub_off.title", language) + "\n\n" +
        t("subscription.sub_off.resubscribe_hint", language),
        parse_mode="HTML"
    )


# =============================================================================
# 🤖 AUTO FRIDAY SUMMARY (Called from scheduler)
# =============================================================================

async def send_friday_summary_to_users(bot, config):
    """
    Send friendly Friday summary to all subscribed users.
    Called by scheduler every Friday at 18:00.
    """
    
    # 📅 Calculate current week (Mon–Sun)
    today = datetime.now().date()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    
    start_dt = datetime.combine(week_start, datetime.min.time())
    end_dt = datetime.combine(week_end, datetime.max.time())
    
    # 🔍 Fetch approved posters
    with get_session() as session:
        posters = get_posters_by_date_range(session, start_dt, end_dt, limit=200)
    
    if not posters:
        logger.info("📭 No posters for this week's Friday summary")
        return
    
    # 🗂️ Group by date
    posters_by_date = _group_posters_by_date(posters)
    
    # 👥 Get subscribed users
    with get_session() as session:
        from db.models import User
        subscribed = session.query(User).filter(User.subscribe_weekly == True).all()
    
    if not subscribed:
        logger.info("👥 No users subscribed to Friday summaries")
        return
    
    # 📤 Send to each user
    sent_count = 0
    for user in subscribed:
        try:
            # Get user's language preference
            user_language = i18n.get_user_language(user.language_code)

            summary_text = format_auto_friday_summary(
                posters_by_date=posters_by_date,
                week_start=week_start,
                week_end=week_end,
                language=user_language
            )
            
            await bot.send_message(
                chat_id=user.telegram_id,
                text=summary_text,
                parse_mode="HTML",
                disable_web_page_preview=False
            )
            sent_count += 1
            
            # Small delay to avoid rate limits
            await asyncio.sleep(0.3)
            
        except Exception as e:
            logger.warning(f"⚠️ Could not send Friday summary to user {user.telegram_id}: {e}")
    
    logger.info(f"🎉 Friday summary sent to {sent_count}/{len(subscribed)} users")
