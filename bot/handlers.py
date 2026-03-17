# handlers.py
"""
Bot handlers for commands, poster submission flow, and moderation.
"""
import asyncio
import re
from aiogram import Router, F, types, html
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.exceptions import TelegramAPIError
from bot.states import PosterSubmission
from bot.keyboards import (
    anonymous_choice_keyboard,
    confirmation_keyboard,
    cancel_keyboard,
    moderation_keyboard
)
from db.models import get_session
from db.crud import (
    get_or_create_user,
    create_poster,
    update_poster_status,
    get_poster,
    get_user_stats
)
from utils.helpers import format_preview_text, format_moderation_caption, format_public_caption
from config import config
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# ============ ROUTERS ============
# Each router handles a different feature area

commands_router = Router(name="commands")      # /start, /poster, /stats, /cancel
poster_router = Router(name="poster")          # Poster submission FSM flow
moderation_router = Router(name="moderation")  # Moderator approve/decline callbacks

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
            # Message content didn't change - ignore
            logger.debug("Message not modified (no changes)")
        elif "message to edit not found" in str(e).lower():
            # Message was deleted - send new one instead
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
    
    # ✅ Initialize both tracking keys
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

@commands_router.message(Command("testchat"))
async def cmd_testchat(message: types.Message):
    """Test if bot can access moderation chat (admin only)"""
    if message.from_user.id not in config.admin_ids:
        await message.answer("❌ Admins only!")
        return
    
    try:
        # Try to send a test message to moderation chat
        test_msg = await message.bot.send_message(
            chat_id=config.moderation_chat_id,
            text="🧪 <b>Test Message</b>\n\nIf you see this, the bot can access the moderation chat!"
        )
        await message.answer(
            f"✅ <b>Success!</b>\n\n"
            f"Test message sent to moderation chat.\n"
            f"Message ID: <code>{test_msg.message_id}</code>"
        )
    except Exception as e:
        await message.answer(
            f"❌ <b>Failed!</b>\n\n"
            f"Error: <code>{str(e)}</code>\n\n"
            f"Make sure:\n"
            f"1. Bot is added to the moderation chat\n"
            f"2. Bot is an admin in that chat\n"
            f"3. MODERATION_CHAT_ID in .env is correct"
        )

# ============ POSTER FLOW - STEP 1: PHOTO ============

@poster_router.message(PosterSubmission.waiting_for_photo, F.photo)
async def process_photo(message: types.Message, state: FSMContext):
    """Handle photo submission with link validation"""
    
    caption = message.caption or ""
    
    # ✅ Validate caption (just check for link)
    from utils.helpers import validate_caption
    is_valid, error_message = validate_caption(caption)
    
    if not is_valid:
        # ✅ Delete ALL previous bot messages (even on error)
        data = await state.get_data()
        
        # Delete first instruction message
        first_message_id = data.get("first_message_id")
        if first_message_id:
            try:
                await message.bot.delete_message(
                    chat_id=message.chat.id,
                    message_id=first_message_id
                )
                logger.debug(f"Deleted first message {first_message_id}")
            except Exception as e:
                logger.debug(f"Could not delete first message: {e}")
        
        # ✅ Delete previous bot message (with keyboard)
        prev_message_id = data.get("prev_bot_message_id")
        if prev_message_id:
            try:
                await message.bot.delete_message(
                    chat_id=message.chat.id,
                    message_id=prev_message_id
                )
                logger.debug(f"Deleted previous bot message {prev_message_id}")
            except Exception as e:
                logger.debug(f"Could not delete previous bot message: {e}")
        
        # ✅ Send error message WITH RETRY BUTTON
        from bot.keyboards import retry_keyboard
        
        await message.answer(
            f"{error_message}\n\n"
            "<i>Click the button below to try again.</i>",
            parse_mode="HTML",
            reply_markup=retry_keyboard().as_markup()  # ← ADD RETRY BUTTON
        )
        
        # ✅ Delete ONLY the user's photo so they can resend with link
        try:
            await message.delete()
        except Exception as e:
            logger.debug(f"Could not delete user photo: {e}")
        
        return  # Don't proceed to next step
    
    # ✅ Caption has link - proceed with flow
    await state.update_data(
        photo_file_id=message.photo[-1].file_id,
        caption=caption,
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name
    )
    await state.set_state(PosterSubmission.waiting_for_anonymous)
    
    # ✅ Delete ALL previous bot messages from this flow
    data = await state.get_data()
    
    # Delete first instruction message
    first_message_id = data.get("first_message_id")
    if first_message_id:
        try:
            await message.bot.delete_message(
                chat_id=message.chat.id,
                message_id=first_message_id
            )
            logger.debug(f"Deleted first message {first_message_id}")
        except Exception as e:
            logger.debug(f"Could not delete first message: {e}")
    
    # Delete previous bot message (with keyboard) if exists
    prev_message_id = data.get("prev_bot_message_id")
    if prev_message_id:
        try:
            await message.bot.delete_message(
                chat_id=message.chat.id,
                message_id=prev_message_id
            )
            logger.debug(f"Deleted previous bot message {prev_message_id}")
        except Exception as e:
            logger.debug(f"Could not delete previous bot message: {e}")
    
    # Send new message and store its ID
    sent = await message.answer(
        "🔐 <b>Privacy Settings</b>\n\n"
        "Should your name be shown with this poster?",
        parse_mode="HTML",
        reply_markup=anonymous_choice_keyboard().as_markup()
    )
    
    # ✅ Store current bot message ID for deletion on next photo
    await state.update_data(prev_bot_message_id=sent.message_id)


@poster_router.message(PosterSubmission.waiting_for_photo, ~F.photo)
async def invalid_photo(message: types.Message):
    """Reject non-photo messages"""
    await message.answer(
        "⚠️ Please send a <b>photo</b> for your poster.\n"
        "You can add a caption with event details.",
        parse_mode="HTML"
    )


@poster_router.callback_query(F.data == "poster:retry_photo")
async def retry_photo(callback: types.CallbackQuery, state: FSMContext):
    """Handle retry after validation error"""
    
    # Clear any leftover data but keep user info
    data = await state.get_data()
    
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
    
    # Update message tracking
    await state.update_data(
        first_message_id=sent.message_id,
        prev_bot_message_id=sent.message_id
    )
    
    await callback.answer("Ready! Send your photo with a link.")
    logger.info(f"User {callback.from_user.id} retried photo submission")
    
# ============ POSTER FLOW - STEP 2: ANONYMOUS ============

@poster_router.callback_query(PosterSubmission.waiting_for_anonymous, F.data.startswith("anon:"))
async def process_anonymous(callback: types.CallbackQuery, state: FSMContext):
    """Handle anonymous preference"""
    is_anonymous = callback.data.split(":")[1] == "yes"
    await state.update_data(is_anonymous=is_anonymous)
    await state.set_state(PosterSubmission.waiting_for_date)
    
    from bot.keyboards import date_picker_keyboard
    
    await safe_edit_text(
        callback.message,
        text=(
            f"{'🔒 Anonymous' if is_anonymous else '👤 Public'} mode selected.\n\n"
            "📅 <b>When is the event?</b>\n"
            "<i>Select a date from the options below:</i>"
        ),
        reply_markup=date_picker_keyboard().as_markup()
    )
    
    # ✅ Update stored bot message ID
    await state.update_data(prev_bot_message_id=callback.message.message_id)
    await callback.answer()


@poster_router.callback_query(PosterSubmission.waiting_for_date, F.data == "poster:back_to_anon")
async def back_to_anonymous(callback: types.CallbackQuery, state: FSMContext):
    """Go back to anonymous selection"""
    await state.set_state(PosterSubmission.waiting_for_anonymous)
    
    data = await state.get_data()
    is_anonymous = data.get("is_anonymous", False)
    
    from bot.keyboards import anonymous_choice_keyboard
    
    await safe_edit_text(
        callback.message,
        text=(
            f"{'🔒 Anonymous' if is_anonymous else '👤 Public'} mode selected.\n\n"
            "🔐 <b>Privacy Settings</b>\n\n"
            "Should your name be shown with this poster?"
        ),
        reply_markup=anonymous_choice_keyboard().as_markup()
    )
    
    # ✅ Update stored bot message ID
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
    
    # ✅ Update stored bot message ID
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
    
    # ✅ Update stored bot message ID
    await state.update_data(prev_bot_message_id=callback.message.message_id)
    await callback.answer()



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
    
    # ✅ Update stored bot message ID
    await state.update_data(prev_bot_message_id=callback.message.message_id)
    await callback.answer()


# ============ POSTER FLOW - STEP 4: CONFIRMATION ============

@poster_router.callback_query(PosterSubmission.waiting_for_confirmation, F.data == "poster:confirm")
async def confirm_submission(callback: types.CallbackQuery, state: FSMContext):
    """Save poster to database and send to moderation"""
    data = await state.get_data()
    
    try:
        with get_session() as session:
            # Create poster record
            poster = create_poster(
                session=session,
                user_id=data['user_id'],
                photo_file_id=data['photo_file_id'],
                caption=data.get('caption', ''),
                event_date=datetime.fromisoformat(data['event_date']),
                is_anonymous=data['is_anonymous']
            )
            
            # Send to moderation chat
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


@poster_router.callback_query(F.data == "poster:cancel")
async def cancel_submission(callback: types.CallbackQuery, state: FSMContext):
    """Cancel submission from any step"""
    data = await state.get_data()
    
    # Check if user already sent a photo (past step 1)
    has_photo = "photo_file_id" in data
    
    # Delete the first instruction message if it exists
    first_message_id = data.get("first_message_id")
    if first_message_id:
        try:
            await callback.message.bot.delete_message(
                chat_id=callback.message.chat.id,
                message_id=first_message_id
            )
        except:
            pass
    
    # Delete the current bot message
    try:
        await callback.message.delete()
    except:
        pass
    
    await state.clear()
    
    # If user sent a photo, send a welcoming message so bot doesn't "disappear"
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
        # Early cancel - simple message
        await callback.message.answer("❌ Submission cancelled.")
    
    await callback.answer()
    logger.info(f"Submission cancelled by user {callback.from_user.id} (has_photo={has_photo})")

# ============ MODERATION ============

@moderation_router.callback_query(F.data.regexp(r"^(approve|decline):(\d+):([01]):(\d+)$"))
async def handle_moderation_decision(callback: types.CallbackQuery):
    """Process moderator approve/decline decision"""
    
    # Check if moderator is admin
    if callback.from_user.id not in config.admin_ids:
        await callback.answer("❌ You're not authorized to moderate!", show_alert=True)
        return
    
    # Parse callback  action:user_id:anon_flag:poster_id
    action, user_id_str, anon_flag, poster_id_str = callback.data.split(":")
    user_id = int(user_id_str)
    poster_id = int(poster_id_str)
    moderator_id = callback.from_user.id
    moderator_username = callback.from_user.username or "no_username"
    
    try:
        with get_session() as session:
            # Get poster from database
            poster = get_poster(session, poster_id)
            
            if not poster:
                await callback.answer("⚠️ Poster not found!", show_alert=True)
                return
            
            if action == "approve":
                # Determine target channel based on debug mode
                target_channel_id = config.test_channel_id if config.debug_mode else config.main_channel_id
                
                # Forward to channel (if photo exists)
                if callback.message.photo:
                    photo_file_id = callback.message.photo[-1].file_id
                    
                    # Format public caption
                    public_caption = format_public_caption(
                        data={
                            "caption": poster.caption,
                            "event_date": poster.event_date.isoformat() if poster.event_date else None,
                            "is_anonymous": poster.is_anonymous
                        },
                        user_info={
                            "first_name": poster.user.first_name if poster.user else "User",
                            "username": poster.user.username if poster.user else None
                        } if not poster.is_anonymous else None
                    )
                    
                    # Add debug watermark
                    if config.debug_mode:
                        public_caption += "\n\n⚠️ <i>TEST MODE - Not a real post</i>"
                    
                    sent_message = await callback.bot.send_photo(
                        chat_id=target_channel_id,
                        photo=photo_file_id,
                        caption=public_caption,
                        parse_mode="HTML"
                    )
                    
                    # Update database
                    update_poster_status(
                        session=session,
                        poster_id=poster_id,
                        status="approved",
                        moderator_id=moderator_id,
                        channel_message_id=sent_message.message_id,
                        channel_chat_id=target_channel_id
                    )
                
                # Notify user
                if config.debug_mode:
                    notify_text = (
                        "🧪 <b>TEST MODE - Poster Approved!</b>\n\n"
                        f"{'It was published anonymously.' if poster.is_anonymous else 'It was published with your name.'}\n"
                        f"⚠️ <i>This is a test channel. Not published to main channel.</i>"
                    )
                else:
                    notify_text = (
                        "🎉 <b>Your poster was approved!</b>\n\n"
                        f"{'It was published anonymously.' if poster.is_anonymous else 'It was published with your name.'}\n"
                        f"Check the channel!"
                    )
                
                await callback.bot.send_message(
                    chat_id=user_id,
                    text=notify_text,
                    parse_mode="HTML"
                )
                
                # EDIT moderation message to show result (DON'T DELETE)
                status_text = (
                    f"\n\n━━━━━━━━━━━━━━━━━━━━\n"
                    f"✅ <b>APPROVED</b>\n"
                    f"👤 Moderator: @{moderator_username}\n"
                    f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
                )
                
                if callback.message.photo:
                    await callback.message.edit_caption(
                        caption=(callback.message.caption or "") + status_text,
                        parse_mode="HTML",
                        reply_markup=None
                    )
                else:
                    await callback.message.edit_text(
                        text=(callback.message.text or "") + status_text,
                        parse_mode="HTML",
                        reply_markup=None
                    )
                
                await callback.answer("✅ Poster approved!", show_alert=False)
                
            elif action == "decline":
                # Show decline reason keyboard
                from bot.keyboards import decline_reason_keyboard
                
                if callback.message.photo:
                    await callback.message.edit_caption(
                        caption=callback.message.caption or "📝 Poster Submission",
                        reply_markup=decline_reason_keyboard(user_id, anon_flag, poster_id).as_markup()  # ← Correct order
                    )
                else:
                    await callback.message.edit_text(
                        text=callback.message.caption or "📝 Poster Submission",
                        reply_markup=decline_reason_keyboard(user_id, anon_flag, poster_id).as_markup()  # ← Correct order
                    )
                
                await callback.answer("Select a decline reason:")
            
            logger.info(f"Moderation {action} for poster {poster_id} by @{moderator_username}")
            
    except Exception as e:
        logger.error(f"Moderation error: {e}")
        await callback.answer("⚠️ Error processing decision.", show_alert=True)


@moderation_router.callback_query(F.data.regexp(r"^decline_reason:(\w+):(\d+):([01]):(\d+)$"))
async def handle_decline_reason(callback: types.CallbackQuery):
    """Handle decline reason selection"""
    
    # Debug log
    logger.info(f"Decline reason callback received: {callback.data}")
    
    # Check if moderator is admin
    if callback.from_user.id not in config.admin_ids:
        await callback.answer("❌ You're not authorized!", show_alert=True)
        return
    
    # Parse callback  decline_reason:reason_code:user_id:anon_flag:poster_id
    parts = callback.data.split(":")
    
    # Debug: log the parts
    logger.info(f"Callback parts: {parts}")
    
    if len(parts) != 5:
        await callback.answer("⚠️ Invalid callback data!", show_alert=True)
        return
    
    reason_code = parts[1]
    user_id = int(parts[2])
    anon_flag = parts[3]
    poster_id = int(parts[4])
    moderator_id = callback.from_user.id
    moderator_username = callback.from_user.username or "no_username"
    
    # Map reason codes to user-friendly messages
    reason_messages = {
        "low_quality": "📷 Low image quality - Please use a clearer, higher resolution image.",
        "missing_details": "📝 Missing event details - Please include date, time, and location.",
        "inappropriate": "🚫 Inappropriate content - Please ensure content follows community guidelines.",
        "wrong_date": "📅 Wrong date or past event - Please submit events that are in the future.",
        "duplicate": "🔄 Duplicate submission - This event was already submitted.",
        "custom": "⚠️ Please contact moderation for more details."
    }
    
    reason_text = reason_messages.get(reason_code, "⚠️ Poster declined by moderation.")
    
    try:
        with get_session() as session:
            # Get poster to verify it exists
            poster = get_poster(session, poster_id)
            if not poster:
                await callback.answer("⚠️ Poster not found!", show_alert=True)
                return
            
            # Update database
            update_poster_status(
                session=session,
                poster_id=poster_id,
                status="declined",
                moderator_id=moderator_id,
                decline_reason=reason_code
            )
            
            # Notify user with reason
            await callback.bot.send_message(
                chat_id=user_id,
                text=(
                    "😔 <b>Your poster was declined</b>\n\n"
                    f"<b>Reason:</b> {reason_text}\n\n"
                    f"<b>Moderator:</b> @{moderator_username}\n\n"
                    "<i>Use /poster to submit a new version.</i>"
                ),
                parse_mode="HTML"
            )
            
            # EDIT moderation message to show result
            status_text = (
                f"\n\n━━━━━━━━━━━━━━━━━━━━\n"
                f"❌ <b>DECLINED</b>\n"
                f"👤 Moderator: @{moderator_username}\n"
                f"📋 Reason: {reason_code}\n"
                f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            )
            
            if callback.message.photo:
                await callback.message.edit_caption(
                    caption=(callback.message.caption or "") + status_text,
                    parse_mode="HTML",
                    reply_markup=None
                )
            else:
                await callback.message.edit_text(
                    text=(callback.message.text or "") + status_text,
                    parse_mode="HTML",
                    reply_markup=None
                )
            
            await callback.answer("❌ Poster declined!", show_alert=False)
            
            logger.info(f"Poster {poster_id} declined by @{moderator_username} - Reason: {reason_code}")
            
    except Exception as e:
        logger.error(f"Decline error: {e}")
        await callback.answer("⚠️ Error processing decline.", show_alert=True)


@moderation_router.callback_query(F.data.regexp(r"^moderation:cancel_decline:(\d+):([01]):(\d+)$"))
async def cancel_decline(callback: types.CallbackQuery):
    """Cancel decline action and restore original keyboard"""
    
    # Check if moderator is admin
    if callback.from_user.id not in config.admin_ids:
        await callback.answer("❌ Not authorized!", show_alert=True)
        return
    
    # Parse callback  moderation:cancel_decline:user_id:anon_flag:poster_id
    parts = callback.data.split(":")
    user_id = int(parts[2])
    anon_flag = parts[3]
    poster_id = int(parts[4])
    
    logger.info(f"Cancel decline for poster {poster_id}")
    
    try:
        with get_session() as session:
            # Get poster from database
            poster = get_poster(session, poster_id)
            
            if not poster:
                await callback.answer("⚠️ Poster not found!", show_alert=True)
                return
            
            # Restore original moderation keyboard
            from bot.keyboards import moderation_keyboard
            keyboard = moderation_keyboard(
                user_id=poster.user_id,
                is_anonymous=poster.is_anonymous,
                poster_id=poster.id
            ).as_markup()
            
            # Get original caption (remove any "Select a decline reason" text)
            original_caption = callback.message.caption or "📝 Poster Submission"
            
            # Remove any status text that might have been added
            import re
            clean_caption = re.sub(
                r"\n\n━━━━━━━━━━━━━━━━━━━━.*",
                "",
                original_caption,
                flags=re.DOTALL
            )
            
            # Edit message based on type (photo or text)
            if callback.message.photo:
                await callback.message.edit_caption(
                    caption=clean_caption,
                    reply_markup=keyboard
                )
            else:
                await callback.message.edit_text(
                    text=clean_caption,
                    reply_markup=keyboard
                )
        
        await callback.answer("✅ Decline cancelled. Original options restored.")
        logger.info(f"Decline cancelled for poster {poster_id}")
        
    except Exception as e:
        logger.error(f"Cancel decline error: {e}")
        await callback.answer("⚠️ Error cancelling decline.", show_alert=True)