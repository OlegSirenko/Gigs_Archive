# main.py
"""
Main entry point for the Poster Bot.
Initialize database, connect routers, and start polling.
"""

import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from config import config
from db.models import init_db
from bot.handlers import commands_router, poster_router
from bot.moderator_handlers import moderation_router, moderator_edit_router

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize bot
bot = Bot(
    token=config.bot_token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# Include all routers
dp.include_routers(commands_router, poster_router, moderation_router, moderator_edit_router)

async def main():
    """Main entry point"""
    try:
        # Initialize database
        init_db()
        logger.info("✅ Database initialized")
        
        # Get bot info
        bot_info = await bot.get_me()
        config.bot_username = bot_info.username
        logger.info(f"✅ Bot authorized: @{bot_info.username} (ID: {bot_info.id})")
        
        # Log config summary
        logger.info(f"📝 Debug mode: {config.debug_mode}")
        logger.info(f"👥 Admin IDs: {config.admin_ids}")
        logger.info(f"💾 Database: {config.database_path}")
        logger.info(f"📢 Main Channel: {config.main_channel_id}")
        logger.info(f"🔍 Moderation Chat: {config.moderation_chat_id}")
    

        # Set commands menu
        await bot.set_my_commands([
            types.BotCommand(command="start", description="🚀 Start the bot"),
            types.BotCommand(command="help", description="📚 Show all commands"),
            types.BotCommand(command="poster", description="📸 Submit a poster"),
            types.BotCommand(command="stats", description="📊 Your statistics"),
            types.BotCommand(command="cancel", description="❌ Cancel operation"),
        ])
        logger.info("✅ Bot commands menu set")
        
        # Start polling
        logger.info("🚀 Starting bot polling...")
        await dp.start_polling(bot)
        
    except Exception as e:
        logger.error(f"❌ Bot startup failed: {e}")
        raise
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")