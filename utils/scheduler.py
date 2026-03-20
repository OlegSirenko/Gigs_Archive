# helpers/scheduler.py
"""
Async scheduler for automated tasks (Friday summary, etc.)
"""

import asyncio
import logging
from datetime import datetime, time, timedelta

from bot.summary_handlers import send_friday_summary_to_users
from config import config

logger = logging.getLogger(__name__)


async def friday_summary_task(bot):
    """
    Send weekly summary to subscribed users every Friday at 18:00.
    Runs in background loop.
    """
    
    while True:
        now = datetime.now()
        
        # 📅 Calculate next Friday at 14:30
        # Friday = weekday 4
        days_until_friday = (4 - now.weekday()) % 7
        if days_until_friday == 0 and now.time() >= time(14,28):
            # Already passed 18:00 today, wait for next Friday
            days_until_friday = 7
        
        next_friday = now.date() + timedelta(days=days_until_friday)
        next_run = datetime.combine(next_friday, time(14, 28))
        
        sleep_seconds = (next_run - now).total_seconds()
        
        logger.info(f"🕐 Friday summary scheduled for {next_run} (in {sleep_seconds/3600:.4f} hours)")
        
        # ⏳ Wait until next Friday 18:00
        await asyncio.sleep(sleep_seconds)
        
        # 📤 Send summaries
        try:
            await send_friday_summary_to_users(bot, config)
        except Exception as e:
            logger.error(f"❌ Friday summary task failed: {e}")
        
        # Small delay to avoid double-run on edge cases
        await asyncio.sleep(60)


async def start_scheduler(bot):
    """Start all background scheduler tasks"""
    
    logger.info("🕐 Starting scheduler...")
    
    # 🎯 Start Friday summary task (runs in background)
    asyncio.create_task(friday_summary_task(bot))
    
    logger.info("✅ Scheduler started — Friday summaries at 14:30")