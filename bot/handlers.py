"""
User-facing bot handlers (commands, poster submission flow).
NO moderation logic here!
"""
import asyncio
import re
import logging
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.exceptions import TelegramAPIError
from bot.states import PosterSubmission
from bot.keyboards import (
    cancel_keyboard,
    retry_keyboard,
    start_over_keyboard,
    anonymous_choice_keyboard,
    date_picker_keyboard,
    confirmation_keyboard
)
from db.models import get_session
from db.crud import get_or_create_user, create_poster, get_user_stats
from utils.helpers import format_preview_text, validate_caption
from config import config
from datetime import datetime

logger = logging.getLogger(__name__)

# ============ ROUTERS ============
commands_router = Router(name="commands")    # /start, /poster, /stats, /cancel
poster_router = Router(name="poster")        # Poster submission FSM flow

# ============ HELPER FUNCTIONS ============

async def safe_edit_text(message: types.Message, text: str, reply_markup=None):
    """Safely edit message text with error handling"""
    try:
        await message.edit_text(
            text=text,
            parse_mode="HTML",
            reply_markup=reply_markup
        )
    except TelegramAPIError as e:
        if "message is not modified" in str(e).lower():
            logger.debug("Message not modified (no changes)")
        elif "message to edit not found" in str(e).lower():
            await message.answer(
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
        else:
            logger.error(f"Edit error: {e}")
            raise

# ============ COMMANDS ============

@commands_router.message(Command("start"))
async def cmd_start(message: types.Message):
    """Handle /start command"""
    await message.answer(
        "👋 <b>Welcome to Poster Bot!</b>\n\n"
        "I help you submit event posters for moderation and publication.\n\n"
        "📸 <b>How to submit a poster:</b>\n"
        "1. Use /poster command\n"
        "2. Send a photo with event details\n"
        "3. Choose anonymous or public\n"
        "4. Select event date\n"
        "5. Confirm and submit!\n\n"
        "All submissions are moderated before publishing to the channel.\n\n"
        "Use /help for more commands."
    )

@commands_router.message(Command("help"))
async def cmd_help(message: types.Message):
    """Show all available commands"""
    help_text = (
        "📚 <b>Available Commands</b>\n\n"
        "🔹 <b>General</b>\n"
        "  /start - Start the bot\n"
        "  /help - Show this help message\n"
        "  /ping - Check if bot is alive\n\n"
        "🔹 <b>Info</b>\n"
        "  /me - Get your Telegram ID\n"
        "  /chat - Get chat information & ID\n"
        "  /admin - Check admin status\n\n"
        "🔹 <b>Posters</b>\n"
        "  /poster - Submit a new poster\n"
        "  /stats - Your submission statistics\n"
        "  /cancel - Cancel current operation\n\n"
        "<i>All posters are moderated before publication.</i>"
    )
    await message.answer(help_text, parse_mode="HTML")

@commands_router.message(Command("poster"))
async def cmd_poster(message: types.Message, state: FSMContext):
    """Start poster submission wizard"""
    await state.clear()
    await state.set_state(PosterSubmission.waiting_for_photo)
    
    # Register/update user in database
    with get_session() as session:
        get_or_create_user(
            session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
            language_code=message.from_user.language_code,
            is_premium=message.from_user.is_premium or False
        )
    
    sent = await message.answer(
        "📸 <b>Send Your Poster</b>\n\n"
        "Attach a photo and add a caption with event details.\n"
        "You can edit everything before publishing!",
        parse_mode="HTML",
        reply_markup=cancel_keyboard().as_markup()
    )
    
    # Store message IDs for cleanup
    await state.update_data(
        first_message_id=sent.message_id,
        prev_bot_message_id=sent.message_id
    )
    logger.info(f"User {message.from_user.id} started poster submission")

@commands_router.message(Command("stats"))
async def cmd_stats(message: types.Message):
    """Show user statistics"""
    with get_session() as session:
        stats = get_user_stats(session, message.from_user.id)
    
    await message.answer(
        "📊 <b>Your Statistics</b>\n\n"
        f"Total submissions: <b>{stats['total']}</b>\n"
        f"✅ Approved: <b>{stats['approved']}</b>\n"
        f"❌ Declined: <b>{stats['declined']}</b>\n"
        f"⏳ Pending: <b>{stats['pending']}</b>",
        parse_mode="HTML"
    )

@commands_router.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    """Cancel current operation"""
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("✅ No active operation to cancel.")
        return
    
    await state.clear()
    await message.answer("❌ Operation cancelled.")
    logger.info(f"Submission cancelled by user {message.from_user.id}")

# ============ POSTER FLOW - STEP 1: PHOTO ============

@poster_router.message(PosterSubmission.waiting_for_photo, F.photo)
async def process_photo(message: types.Message, state: FSMContext):
    """Handle photo submission with caption validation"""
    caption = message.caption or ""
    
    # Validate caption (just check for link)
    is_valid, error_message = validate_caption(caption)
    
    if not is_valid:
        # Delete ALL previous bot messages
        data = await state.get_data()
        
        first_message_id = data.get("first_message_id")
        if first_message_id:
            try:
                await message.bot.delete_message(
                    chat_id=message.chat.id,
                    message_id=first_message_id
                )
            except Exception as e:
                logger.debug(f"Could not delete first message: {e}")
        
        prev_message_id = data.get("prev_bot_message_id")
        if prev_message_id:
            try:
                await message.bot.delete_message(
                    chat_id=message.chat.id,
                    message_id=prev_message_id
                )
            except Exception as e:
                logger.debug(f"Could not delete previous bot message: {e}")
        
        # Send error message with retry button
        await message.answer(
            f"{error_message}\n\n"
            "<i>Click the button below to try again.</i>",
            parse_mode="HTML",
            reply_markup=retry_keyboard().as_markup()
        )
        
        # Delete user's photo
        try:
            await message.delete()
        except Exception as e:
            logger.debug(f"Could not delete user photo: {e}")
        
        return
    
    # Caption is valid - proceed with flow
    await state.update_data(
        photo_file_id=message.photo[-1].file_id,
        caption=caption,
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name
    )
    await state.set_state(PosterSubmission.waiting_for_anonymous)
    
    # Delete previous bot messages
    data = await state.get_data()
    
    first_message_id = data.get("first_message_id")
    if first_message_id:
        try:
            await message.bot.delete_message(
                chat_id=message.chat.id,
                message_id=first_message_id
            )
        except Exception as e:
            logger.debug(f"Could not delete first message: {e}")
    
    prev_message_id = data.get("prev_bot_message_id")
    if prev_message_id:
        try:
            await message.bot.delete_message(
                chat_id=message.chat.id,
                message_id=prev_message_id
            )
        except Exception as e:
            logger.debug(f"Could not delete previous bot message: {e}")
    
    # Send next step
    sent = await message.answer(
        "🔐 <b>Privacy Settings</b>\n\n"
        "Should your name be shown with this poster?",
        parse_mode="HTML",
        reply_markup=anonymous_choice_keyboard().as_markup()
    )
    
    await state.update_data(prev_bot_message_id=sent.message_id)

@poster_router.message(PosterSubmission.waiting_for_photo, ~F.photo)
async def invalid_photo(message: types.Message):
    """Reject non-photo messages"""
    await message.answer(
        "⚠️ Please send a <b>photo</b> for your poster.\n"
        "You can add a caption with event details.",
        parse_mode="HTML"
    )

# ============ POSTER FLOW - STEP 2: ANONYMOUS ============

@poster_router.callback_query(PosterSubmission.waiting_for_anonymous, F.data.startswith("anon:"))
async def process_anonymous(callback: types.CallbackQuery, state: FSMContext):
    """Handle anonymous preference"""
    is_anonymous = callback.data.split(":")[1] == "yes"
    await state.update_data(is_anonymous=is_anonymous)
    await state.set_state(PosterSubmission.waiting_for_date)
    
    await safe_edit_text(
        callback.message,
        text=(
            f"{'🔒 Anonymous' if is_anonymous else '👤 Public'} mode selected.\n\n"
            "📅 <b>When is the event?</b>\n"
            "<i>Select a date from the options below:</i>"
        ),
        reply_markup=date_picker_keyboard().as_markup()
    )
    
    await state.update_data(prev_bot_message_id=callback.message.message_id)
    await callback.answer()

@poster_router.callback_query(PosterSubmission.waiting_for_anonymous, F.data == "poster:back_to_photo")
async def back_to_photo(callback: types.CallbackQuery, state: FSMContext):
    """Go back to photo step"""
    await state.set_state(PosterSubmission.waiting_for_photo)
    
    await safe_edit_text(
        callback.message,
        text=(
            "📸 <b>Send Your Poster</b>\n\n"
            "Attach a photo and add a caption with event details."
        ),
        reply_markup=cancel_keyboard().as_markup()
    )
    
    await state.update_data(prev_bot_message_id=callback.message.message_id)
    await callback.answer()

# ============ POSTER FLOW - STEP 3: DATE ============

@poster_router.callback_query(PosterSubmission.waiting_for_date, F.data.startswith("date:"))
async def process_date_selection(callback: types.CallbackQuery, state: FSMContext):
    """Handle date selection from custom picker"""
    date_str = callback.data.split(":")[1]
    
    await state.update_data(event_date=date_str)
    await state.set_state(PosterSubmission.waiting_for_confirmation)
    
    data = await state.get_data()
    preview_text = format_preview_text(data)
    
    await safe_edit_text(
        callback.message,
        text=preview_text,
        reply_markup=confirmation_keyboard().as_markup()
    )
    
    await state.update_data(prev_bot_message_id=callback.message.message_id)
    await callback.answer()

@poster_router.callback_query(PosterSubmission.waiting_for_date, F.data == "poster:back_to_anon")
async def back_to_anonymous(callback: types.CallbackQuery, state: FSMContext):
    """Go back to anonymous selection"""
    await state.set_state(PosterSubmission.waiting_for_anonymous)
    
    data = await state.get_data()
    is_anonymous = data.get("is_anonymous", False)
    
    await safe_edit_text(
        callback.message,
        text=(
            f"{'🔒 Anonymous' if is_anonymous else '👤 Public'} mode selected.\n\n"
            "🔐 <b>Privacy Settings</b>\n\n"
            "Should your name be shown with this poster?"
        ),
        reply_markup=anonymous_choice_keyboard().as_markup()
    )
    
    await state.update_data(prev_bot_message_id=callback.message.message_id)
    await callback.answer()

# ============ POSTER FLOW - STEP 4: CONFIRMATION ============

@poster_router.callback_query(PosterSubmission.waiting_for_confirmation, F.data == "poster:confirm")
async def confirm_submission(callback: types.CallbackQuery, state: FSMContext):
    """Save poster to database and send to moderation"""
    data = await state.get_data()
    
    try:
        with get_session() as session:
            poster = create_poster(
                session=session,
                user_id=data['user_id'],
                photo_file_id=data['photo_file_id'],
                caption=data.get('caption', ''),
                event_date=datetime.fromisoformat(data['event_date']),
                is_anonymous=data['is_anonymous']
            )
            
            # Send to moderation chat (moderator_handlers.py will handle the rest)
            from bot.keyboards import moderation_keyboard
            from utils.helpers import format_moderation_caption
            
            mod_caption = format_moderation_caption(data, poster.id)
            keyboard = moderation_keyboard(
                user_id=data['user_id'],
                is_anonymous=data['is_anonymous'],
                poster_id=poster.id
            ).as_markup()
            
            await callback.bot.send_photo(
                chat_id=config.moderation_chat_id,
                photo=data['photo_file_id'],
                caption=mod_caption,
                parse_mode="HTML",
                reply_markup=keyboard
            )
        
        await safe_edit_text(
            callback.message,
            text=(
                "✅ <b>Poster Submitted!</b>\n\n"
                "Your poster is now in the moderation queue.\n"
                "You'll be notified once it's reviewed."
            ),
            reply_markup=None
        )
        
        await state.clear()
        logger.info(f"Poster {poster.id} submitted by user {data['user_id']}")
        
    except Exception as e:
        logger.error(f"Submission failed: {e}")
        await callback.answer("⚠️ Error submitting poster. Try again.", show_alert=True)

@poster_router.callback_query(PosterSubmission.waiting_for_confirmation, F.data == "poster:edit")
async def edit_submission(callback: types.CallbackQuery, state: FSMContext):
    """Return to photo step for editing"""
    await state.set_state(PosterSubmission.waiting_for_photo)
    
    data = await state.get_data()
    
    await safe_edit_text(
        callback.message,
        text=(
            "✏️ <b>Edit Your Poster</b>\n\n"
            "Send a new photo to replace the current one.\n\n"
            f"<i>Previous caption:</i>\n"
            f"<code>{data.get('caption', 'None')[:100]}{'...' if len(data.get('caption', '')) > 100 else ''}</code>"
        ),
        reply_markup=cancel_keyboard().as_markup()
    )
    
    await state.update_data(prev_bot_message_id=callback.message.message_id)
    await callback.answer()

@poster_router.callback_query(F.data == "poster:cancel")
async def cancel_submission(callback: types.CallbackQuery, state: FSMContext):
    """Cancel submission from any step"""
    data = await state.get_data()
    has_photo = "photo_file_id" in data
    
    # Delete first instruction message
    first_message_id = data.get("first_message_id")
    if first_message_id:
        try:
            await callback.message.bot.delete_message(
                chat_id=callback.message.chat.id,
                message_id=first_message_id
            )
        except:
            pass
    
    # Delete current bot message
    try:
        await callback.message.delete()
    except:
        pass
    
    await state.clear()
    
    # Send appropriate cancel message
    if has_photo:
        await callback.message.answer(
            "👋 <b>Welcome to Poster Bot!</b>\n\n"
            "I help you submit event posters for moderation and publication.\n\n"
            "📸 <b>How to submit a poster:</b>\n"
            "1. Use /poster command\n"
            "2. Send a photo with event details\n"
            "3. Choose anonymous or public\n"
            "4. Select event date\n"
            "5. Confirm and submit!\n\n"
            "All submissions are moderated before publishing to the channel.\n\n"
            "Use /help for more commands.",
            parse_mode="HTML"
        )
    else:
        await callback.message.answer("❌ Submission cancelled.")
    
    await callback.answer()
    logger.info(f"Submission cancelled by user {callback.from_user.id} (has_photo={has_photo})")

@poster_router.callback_query(F.data == "poster:retry_photo")
async def retry_photo(callback: types.CallbackQuery, state: FSMContext):
    """Handle retry after validation error"""
    # Delete the error message
    try:
        await callback.message.delete()
    except Exception as e:
        logger.debug(f"Could not delete error message: {e}")
    
    # Send fresh instruction
    sent = await callback.message.answer(
        "📸 <b>Send Your Poster</b>\n\n"
        "Attach a photo and add a caption with event details.\n"
        "<b>Don't forget to add at least one link!</b>\n\n"
        "<i>Examples:</i>\n"
        "• example.com\n"
        "• https://tickets.com\n"
        "• t.me/myevent",
        parse_mode="HTML",
        reply_markup=cancel_keyboard().as_markup()
    )
    
    await state.update_data(
        first_message_id=sent.message_id,
        prev_bot_message_id=sent.message_id
    )
    
    await callback.answer("Ready! Send your photo with a link.")
    logger.info(f"User {callback.from_user.id} retried photo submission")

@poster_router.callback_query(F.data == "poster:start_over")
async def start_over(callback: types.CallbackQuery, state: FSMContext):
    """Restart poster submission after cancellation"""
    await state.clear()
    await state.set_state(PosterSubmission.waiting_for_photo)
    
    # Register user if needed
    with get_session() as session:
        get_or_create_user(
            session,
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
            language_code=callback.from_user.language_code,
            is_premium=callback.from_user.is_premium or False
        )
    
    sent = await callback.message.edit_text(
        "📸 <b>Send Your Poster</b>\n\n"
        "Attach a photo and add a caption with event details.\n"
        "You can edit everything before publishing!",
        parse_mode="HTML",
        reply_markup=cancel_keyboard().as_markup()
    )
    
    await state.update_data(
        first_message_id=sent.message_id,
        prev_bot_message_id=sent.message_id
    )
    
    await callback.answer()
    logger.info(f"User {callback.from_user.id} restarted poster submission")