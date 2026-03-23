# main.py
"""
Main entry point for the Poster Bot.
Initialize database, connect routers, and start polling.
"""

import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommandScopeDefault, BotCommandScopeChat
from config import config
from db.models import init_db
from bot.handlers import commands_router, poster_router
from bot.moderator_handlers import moderation_router, moderator_edit_router
from bot.summary_handlers import summary_router
from utils.scheduler import start_scheduler
from utils.i18n import i18n, t

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
dp.include_routers(commands_router, summary_router, poster_router, moderation_router, moderator_edit_router)


async def setup_bot_commands(bot: Bot):
    """Set up bot commands for different scopes and languages"""

    # Default commands for all users (Russian - default)
    default_commands_ru = [
        types.BotCommand(command="start", description=t("commands.menu.start", "ru")),
        types.BotCommand(command="help", description=t("commands.menu.help", "ru")),
        types.BotCommand(command="language", description=t("commands.menu.language", "ru")),
        types.BotCommand(command="poster", description=t("commands.menu.poster", "ru")),
        types.BotCommand(command="stats", description=t("commands.menu.stats", "ru")),
        types.BotCommand(command="summary", description=t("commands.menu.summary", "ru")),
        types.BotCommand(command="sub_on", description=t("commands.menu.sub_on", "ru")),
        types.BotCommand(command="sub_off", description=t("commands.menu.sub_off", "ru")),
        types.BotCommand(command="cancel", description=t("commands.menu.cancel", "ru")),
    ]

    # English commands
    default_commands_en = [
        types.BotCommand(command="start", description=t("commands.menu.start", "en")),
        types.BotCommand(command="help", description=t("commands.menu.help", "en")),
        types.BotCommand(command="language", description=t("commands.menu.language", "en")),
        types.BotCommand(command="poster", description=t("commands.menu.poster", "en")),
        types.BotCommand(command="stats", description=t("commands.menu.stats", "en")),
        types.BotCommand(command="summary", description=t("commands.menu.summary", "en")),
        types.BotCommand(command="sub_on", description=t("commands.menu.sub_on", "en")),
        types.BotCommand(command="sub_off", description=t("commands.menu.sub_off", "en")),
        types.BotCommand(command="cancel", description=t("commands.menu.cancel", "en")),
    ]

    # Admin-only commands (Russian)
    admin_commands_ru = default_commands_ru + [
        types.BotCommand(command="pending", description=t("commands.menu.pending", "ru")),
        types.BotCommand(command="mystats", description=t("commands.menu.mystats", "ru")),
    ]

    # Admin-only commands (English)
    admin_commands_en = default_commands_en + [
        types.BotCommand(command="pending", description=t("commands.menu.pending", "en")),
        types.BotCommand(command="mystats", description=t("commands.menu.mystats", "en")),
    ]

    try:
        # 1. Set default commands for everyone (private chats + groups) - Russian
        await bot.set_my_commands(
            commands=default_commands_ru,
            scope=types.BotCommandScopeDefault()
        )

        # 3. Set admin commands for each admin in their DM
        for admin_id in config.admin_ids:
            await bot.set_my_commands(
                commands=admin_commands_ru,
                scope=types.BotCommandScopeChat(chat_id=admin_id)
            )

        # 4. Set admin commands for moderation chat (if configured)
        if config.moderation_chat_id:
            await bot.set_my_commands(
                commands=admin_commands_ru,
                scope=types.BotCommandScopeChat(chat_id=config.moderation_chat_id)
            )

        logger.info("✅ Bot commands configured for all scopes")

    except Exception as e:
        logger.error(f"❌ Failed to set bot commands: {e}")


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
        logger.info(f"📢 Test Channel Channel: {config.test_channel_id}")
        logger.info(f"🔍 Moderation Chat: {config.moderation_chat_id}")
    
        await setup_bot_commands(bot=bot)

        logger.info("✅ Bot commands menu set")
        
        await start_scheduler(bot)

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