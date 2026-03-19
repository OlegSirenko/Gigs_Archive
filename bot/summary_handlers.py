# bot/summary_handlers.py
"""
Weekly summary handlers for Гиги Архив bot.
"""

import logging
from datetime import datetime, timedelta
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from db.models import get_session
from db.crud import get_posters_by_date_range
from utils.i18n import i18n, t

logger = logging.getLogger(__name__)

summary_router = Router(name="summary")

# ============ COMMANDS ============

@summary_router.message(Command("summary"))
async def cmd_summary(message: types.Message):
    """Show weekly summary of approved events"""
    
    language = i18n.get_user_language(message.from_user.language_code)
    
    # Calculate current week range (Monday to Sunday)
    today = datetime.now().date()
    start_of_week = today - timedelta(days=today.weekday())  # Monday
    end_of_week = start_of_week + timedelta(days=6)  # Sunday
    
    start_datetime = datetime.combine(start_of_week, datetime.min.time())
    end_datetime = datetime.combine(end_of_week, datetime.max.time())
    
    with get_session() as session:
        posters = get_posters_by_date_range(
            session,
            start_date=start_datetime,
            end_date=end_datetime,
            limit=100
        )
    
    if not posters:
        await message.answer(
            t("weekly_summary.no_events", language),
            parse_mode="HTML"
        )
        return
    
    # Group posters by event date
    posters_by_date = {}
    for poster in posters:
        date_key = poster.event_date.strftime("%d.%m.%Y")
        if date_key not in posters_by_date:
            posters_by_date[date_key] = []
        posters_by_date[date_key].append(poster)
    
    # Build summary text
    # Build summary text
    summary_text = f"{t('weekly_summary.title', language)}\n\n"
    summary_text += f"{t('weekly_summary.period', language, start_date=start_of_week.strftime('%d.%m'), end_date=end_of_week.strftime('%d.%m'))}\n"
    summary_text += f"{t('weekly_summary.total', language, count=len(posters))}\n"
    
    # Group by event date
    for date_str, date_posters in sorted(posters_by_date.items()):
        summary_text += f"\n🗓️ <b>{date_str}</b> ({len(date_posters)} событий)\n"
        
        for i, poster in enumerate(date_posters[:10], 1):  # Limit 10 per date
            # Extract short caption
            caption = poster.caption[:60] + "..." if len(poster.caption) > 60 else poster.caption
            
            # Extract first link from caption
            import re
            links = re.findall(r'https?://[^\s]+', caption)
            if links:
                summary_text += f"  {i}. {caption}\n      🔗 {links[0]}\n"
            else:
                summary_text += f"  {i}. {caption}\n"
        
        if len(date_posters) > 10:
            summary_text += f"  ... и ещё {len(date_posters) - 10}\n"
    
    summary_text += f"\n{t('weekly_summary.footer', language)}"
    
    await message.answer(summary_text, parse_mode="HTML")
    logger.info(f"Weekly summary requested by user {message.from_user.id}")


# ============ AUTO WEEKLY POST TO CHANNEL ============

async def send_weekly_summary_to_channel(bot, config):
    """
    Send weekly summary to channel (called from scheduler).
    Posts every Monday at 10:00 with last week's events.
    """
    
    language = "ru"  # Channel language
    
    # Calculate last week range (Monday to Sunday)
    today = datetime.now().date()
    last_week_start = today - timedelta(days=today.weekday() + 7)  # Last Monday
    last_week_end = last_week_start + timedelta(days=6)  # Last Sunday
    
    start_datetime = datetime.combine(last_week_start, datetime.min.time())
    end_datetime = datetime.combine(last_week_end, datetime.max.time())
    
    target_channel_id = config.test_channel_id if config.debug_mode else config.main_channel_id
    
    with get_session() as session:
        posters = get_posters_by_date_range(
            session,
            start_date=start_datetime,
            end_date=end_datetime,
            limit=100
        )
    
    if not posters:
        logger.info(f"No posters to summarize for week {last_week_start} - {last_week_end}")
        return
    
    # Group posters by event date
    posters_by_date = {}
    for poster in posters:
        date_key = poster.event_date.strftime("%d.%m.%Y")
        if date_key not in posters_by_date:
            posters_by_date[date_key] = []
        posters_by_date[date_key].append(poster)
    
    # Build summary text
    summary_text = f"{t('weekly_summary.title', language)}\n\n"
    summary_text += f"📅 Период: {last_week_start.strftime('%d.%m')} — {last_week_end.strftime('%d.%m')}\n"
    summary_text += f"✅ Всего одобрено: {len(posters)} событий\n"
    
    # Group by event date
    for date_str, date_posters in sorted(posters_by_date.items()):
        summary_text += f"\n🗓️ <b>{date_str}</b> ({len(date_posters)} событий)\n"
        
        for i, poster in enumerate(date_posters, 1):
            # Create short caption
            caption = poster.caption[:80] + "..." if len(poster.caption) > 80 else poster.caption
            
            # Extract first link from caption
            import re
            links = re.findall(r'https?://[^\s]+', caption)
            link_text = links[0] if links else "Нет ссылки"
            
            summary_text += f"\n{i}. {caption}"
            summary_text += f"\n   🔗 {link_text}"
            
            if not poster.is_anonymous and poster.user and poster.user.username:
                summary_text += f"\n   👤 @{poster.user.username}"
    
    summary_text += f"\n\n{t('weekly_summary.footer', language)}"
    
    try:
        # Use first poster's photo if available
        if posters and posters[0].photo_file_id:
            await bot.send_photo(
                chat_id=target_channel_id,
                photo=posters[0].photo_file_id,
                caption=summary_text,
                parse_mode="HTML"
            )
        else:
            await bot.send_message(
                chat_id=target_channel_id,
                text=summary_text,
                parse_mode="HTML"
            )
        
        logger.info(f"Weekly summary sent to channel {target_channel_id} ({len(posters)} posters)")
        
    except Exception as e:
        logger.error(f"Failed to send weekly summary: {e}")