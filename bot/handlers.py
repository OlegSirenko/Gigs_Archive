# bot/handlers.py
"""
User-facing bot handlers (commands, poster submission flow).
NO moderation logic here!
"""
import asyncio
import re
import logging
import json
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InputMediaPhoto
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.states import PosterSubmission
from bot.keyboards import (
    cancel_keyboard,
    retry_keyboard,
    start_over_keyboard,
    anonymous_choice_keyboard,
    date_picker_keyboard,
    confirmation_keyboard,
    language_selection_keyboard,
    privacy_policy_keyboard,
    privacy_acceptance_keyboard
)
from bot.filters import PrivacyNotAcceptedFilter
from db.models import get_session, User, Poster
from db.crud import get_or_create_user, create_poster, get_user_stats
from utils.helpers import format_preview_text, validate_caption, extract_forwarded_info
from utils.i18n import i18n, t
from utils.privacy import user_needs_to_accept_privacy, get_current_privacy_version, update_user_privacy_acceptance
from config import config
from datetime import datetime
from sqlalchemy import delete as sql_delete

logger = logging.getLogger(__name__)

# ============ GLOBAL: Media groups tracking ============
# Store pending media groups: {media_group_id: {'photos': [...], 'timer_task': asyncio.Task}}
pending_media_groups: dict[str, dict] = {}
MEDIA_GROUP_TIMEOUT = 1.5  # seconds to wait for all photos

# ============ ROUTERS ============
commands_router = Router(name="commands")    # /start, /poster, /stats, /cancel
poster_router = Router(name="poster")        # Poster submission FSM flow

# ============ HELPER FUNCTIONS ============

async def process_media_group_complete(message: types.Message, state: FSMContext, photos: list, language: str, forwarded_data: dict = None):
    """
    Process completed media group (all photos received).
    This is called after timeout when we assume all photos are collected.
    """
    try:
        # Get caption from first photo or forwarded data
        if forwarded_data:
            caption = forwarded_data.get('caption', '')
            telegram_link = forwarded_data.get('telegram_link')
            
            # Add attribution for forwarded channels
            if forwarded_data.get('is_channel_forward') and forwarded_data.get('source_name'):
                if telegram_link:
                    attribution_source = f"{forwarded_data['source_name']} — {telegram_link}"
                    caption = f"{caption}\n\n{t('poster_flow.forwarded.attribution', language, source=attribution_source)}"
                else:
                    caption = f"{caption}\n\n{t('poster_flow.forwarded.attribution', language, source=forwarded_data['source_name'])}"
            
            # Validate caption if no Telegram link
            is_valid = True
            error_message = ""
            if not telegram_link:
                is_valid, error_message = validate_caption(caption)
            
            if not is_valid:
                await handle_validation_error(message, state, error_message, language)
                return
            
            # Store forwarded data
            await state.update_data(
                photos_json=json.dumps(photos),
                photo_file_id=photos[0]['file_id'],
                caption=caption,
                user_id=message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                is_forwarded=True,
                is_media_group=True,
                forward_source=forwarded_data.get('source_name'),
                telegram_link=telegram_link,
                language=language
            )
        else:
            # Direct photo upload (not forwarded)
            caption = photos[0].get('caption', '')
            
            is_valid, error_message = validate_caption(caption)
            
            if not is_valid:
                await handle_validation_error(message, state, error_message, language)
                return
            
            await state.update_data(
                photos_json=json.dumps(photos),
                photo_file_id=photos[0]['file_id'],
                caption=caption,
                user_id=message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                is_forwarded=False,
                is_media_group=True,
                language=language
            )
        
        # Proceed to next step
        await state.set_state(PosterSubmission.waiting_for_anonymous)
        
        sent = await message.answer(
            f"{t('poster_flow.anonymous.title', language)}\n\n"
            f"{t('poster_flow.anonymous.description', language)}",
            parse_mode="HTML",
            reply_markup=anonymous_choice_keyboard(language).as_markup()
        )
        
        await state.update_data(
            first_message_id=sent.message_id,
            prev_bot_message_id=sent.message_id
        )
        
        logger.info(f"Media group processed: {len(photos)} photos from user {message.from_user.id}")
        
    except Exception as e:
        logger.error(f"Error processing media group: {e}")
        await message.answer(t('common.error', language))


async def handle_media_group_message(message: types.Message, state: FSMContext, forwarded_data: dict = None):
    """
    Handle individual message that is part of a media group.
    Collects photos and processes them after timeout.
    """
    media_group_id = message.media_group_id

    if not media_group_id:
        return False  # Not a media group

    language = i18n.get_user_language(message.from_user.language_code, message.from_user.id)

    # Initialize group if first photo
    if media_group_id not in pending_media_groups:
        pending_media_groups[media_group_id] = {
            'photos': [],
            'timer_task': None,
            'message': message,
            'state': state,
            'language': language,
            'forwarded_data': forwarded_data
        }

    group = pending_media_groups[media_group_id]

    # Extract photo file_id
    if message.photo:
        photo_info = {
            'file_id': message.photo[-1].file_id,
            'caption': message.caption or ''
        }
        group['photos'].append(photo_info)

    # Cancel existing timer
    if group['timer_task'] and not group['timer_task'].done():
        group['timer_task'].cancel()
        try:
            await group['timer_task']
        except asyncio.CancelledError:
            pass

    # Start new timer to process group after timeout
    async def process_after_timeout():
        try:
            await asyncio.sleep(MEDIA_GROUP_TIMEOUT)
            if media_group_id in pending_media_groups:
                group_data = pending_media_groups.pop(media_group_id)
                if group_data['photos']:
                    await process_media_group_complete(
                        message=group_data['message'],
                        state=group_data['state'],
                        photos=group_data['photos'],
                        language=group_data['language'],
                        forwarded_data=group_data.get('forwarded_data')
                    )
        except asyncio.CancelledError:
            # Timer was cancelled, which is expected when new photo arrives
            pass

    group['timer_task'] = asyncio.create_task(process_after_timeout())

    return True  # Is a media group

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


async def handle_validation_error(message: types.Message, state: FSMContext, error_message: str, language: str):
    """Handle validation error with cleanup and retry option"""
    
    # Delete ALL previous bot messages
    data = await state.get_data()
    
    first_message_id = data.get("first_message_id")
    if first_message_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=first_message_id)
        except:
            pass
    
    prev_message_id = data.get("prev_bot_message_id")
    if prev_message_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=prev_message_id)
        except:
            pass
    
    # Send error message with retry button
    await message.answer(
        f"{t('poster_flow.validation_error.no_link', language)}\n\n"
        f"{t('poster_flow.validation_error.examples_title', language)}\n"
        f"{t('poster_flow.validation_error.examples', language)}\n\n"
        f"{t('poster_flow.validation_error.retry_hint', language)}",
        parse_mode="HTML",
        reply_markup=retry_keyboard(language).as_markup()
    )
    
    # Delete user's message
    try:
        await message.delete()
    except:
        pass


async def cleanup_previous_messages(message: types.Message, state: FSMContext):
    """Delete previous bot messages before showing next step"""
    data = await state.get_data()
    
    for key in ["first_message_id", "prev_bot_message_id"]:
        msg_id = data.get(key)
        if msg_id:
            try:
                await message.bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
            except:
                pass

# ============ COMMANDS ============

@commands_router.message(Command("start"))
async def cmd_start(message: types.Message):
    """Handle /start command"""
    language = i18n.get_user_language(message.from_user.language_code, message.from_user.id)

    # Check if this is the first time user starts the bot
    with get_session() as session:
        user = session.query(User).filter(User.telegram_id == message.from_user.id).first()
        is_first_start = user is None

        # Register user if not exists
        if is_first_start:
            user = get_or_create_user(
                session,
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name,
                language_code=message.from_user.language_code,
                is_premium=message.from_user.is_premium or False,
                subscribe_weekly=True  # Auto-subscribe new users to weekly digest
            )

    steps_list = i18n.t('commands.start.steps', language)
    if isinstance(steps_list, list):
        steps = "\n".join([f"{i}. {step}" for i, step in enumerate(steps_list, 1)])
    else:
        steps = steps_list

    # Determine which keyboard to show
    reply_markup = None
    needs_privacy_acceptance = user_needs_to_accept_privacy(user) if user else True

    if is_first_start:
        # First start: show language selection
        reply_markup = language_selection_keyboard(language).as_markup()
    elif needs_privacy_acceptance:
        # Privacy not accepted or old version: NO keyboard in welcome message
        # (privacy policy message below has the accept button)
        reply_markup = None
    else:
        # Privacy accepted: show privacy policy button only
        reply_markup = privacy_policy_keyboard(language).as_markup()

    # Send welcome message
    await message.answer(
        f"{t('commands.start.title', language)}\n\n"
        f"{t('commands.start.description', language)}\n\n"
        f"{t('commands.start.how_to', language)}\n"
        f"{steps}\n\n"
        f"{t('commands.start.footer', language)}\n\n"
        f"{t('commands.start.auto_subscribe_note', language)}",
        parse_mode="HTML",
        reply_markup=reply_markup
    )

    # Send privacy policy message immediately after /start if needed
    if needs_privacy_acceptance:
        privacy_text = (
            f"{i18n.t('common.privacy_policy', language)}\n\n"
            f"{i18n.t('common.privacy_policy_text.collect', language)}"
            f"{i18n.t('common.privacy_policy_text.use', language)}"
            f"{i18n.t('common.privacy_policy_text.storage', language)}"
            f"{i18n.t('common.privacy_policy_text.rights', language)}"
            f"{i18n.t('common.privacy_policy_text.mailing', language)}"
            f"{i18n.t('common.privacy_policy_text.questions', language)}"
            f"{i18n.t('common.privacy_policy_text.acception', language)}"
        )

        await message.answer(
            privacy_text,
            parse_mode="HTML",
            reply_markup=privacy_acceptance_keyboard(language).as_markup()
        )


@commands_router.callback_query(F.data == "privacy:show")
async def show_privacy_policy(callback: types.CallbackQuery):
    """Show privacy policy"""

    language = i18n.get_user_language(callback.from_user.language_code, callback.from_user.id)

    privacy_text = (
        f"{i18n.t('common.privacy_policy', language)}\n\n"
        f"{i18n.t('common.privacy_policy_text.collect', language)}"
        f"{i18n.t('common.privacy_policy_text.use', language)}"
        f"{i18n.t('common.privacy_policy_text.storage', language)}"
        f"{i18n.t('common.privacy_policy_text.rights', language)}"
        f"{i18n.t('common.privacy_policy_text.mailing', language)}"
        f"{i18n.t('common.privacy_policy_text.questions', language)}"
        f"{i18n.t('common.privacy_policy_text.acception', language)}"
    )

    # Check if user needs to accept (new user or old version)
    with get_session() as session:
        user = session.query(User).filter(User.telegram_id == callback.from_user.id).first()
        needs_acceptance = user_needs_to_accept_privacy(user) if user else True

    # ✅ Simple back button
    builder = InlineKeyboardBuilder()
    
    if needs_acceptance:
        # Show accept button for users who haven't accepted
        builder.row(
            types.InlineKeyboardButton(
                text=i18n.t('common.privacy_accept', language),
                callback_data="privacy:accept"
            )
        )
    
    builder.row(
        types.InlineKeyboardButton(text=i18n.t('common.back', language), callback_data="privacy:back")
    )

    builder.row(
        types.InlineKeyboardButton(text=i18n.t('common.delete_data', language), callback_data="delete:confirm")
    )

    await callback.message.answer(
        privacy_text,
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )

    await callback.answer()


@commands_router.callback_query(F.data == "privacy:accept")
async def accept_privacy_policy(callback: types.CallbackQuery):
    """Handle privacy policy acceptance"""

    language = i18n.get_user_language(callback.from_user.language_code, callback.from_user.id)
    user_id = callback.from_user.id

    # Update user's privacy acceptance status with current version
    with get_session() as session:
        user = session.query(User).filter(User.telegram_id == user_id).first()
        if user:
            update_user_privacy_acceptance(user)
            session.commit()

    # Delete the privacy policy message
    try:
        await callback.message.delete()
    except:
        pass

    # Send confirmation
    await callback.message.answer(
        f"{t('commands.start.title', language)}\n\n"
        f"{t('commands.start.description', language)}\n\n"
        f"{t('commands.start.how_to', language)}\n"
        f"{t('commands.start.footer', language)}",
        parse_mode="HTML",
        reply_markup=privacy_policy_keyboard(language).as_markup()
    )

    await callback.answer()


@commands_router.callback_query(F.data == "delete:confirm")
async def confirm_delete_account(callback: types.CallbackQuery):
    """Show delete confirmation dialog"""
    
    language = i18n.get_user_language(callback.from_user.language_code, callback.from_user.id)
    user_id = callback.from_user.id
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(
            text=i18n.t('common.delete_account.confirm_button', language),
            callback_data=f"delete:execute:{user_id}"
        ),
        types.InlineKeyboardButton(
            text=i18n.t('common.delete_account.cancel_button', language),
            callback_data="delete:cancel"
        )
    )
    
    await callback.message.answer(
        f"{i18n.t('common.delete_account.warning', language)}\n\n"
        f"{i18n.t('common.delete_account.confirm_text', language)}\n\n"
        f"{i18n.t('common.delete_account.posters_note', language)}",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    
    await callback.answer()


@commands_router.callback_query(F.data == "delete:cancel")
async def delete_back(callback: types.CallbackQuery):
    """Go back from privacy policy"""
    
    # Just delete the privacy message
    try:
        await callback.message.delete()
    except:
        pass
    
    await callback.answer()

@commands_router.callback_query(F.data.startswith("delete:execute:"))
async def execute_delete_account(callback: types.CallbackQuery):
    """Execute account deletion"""
    
    user_id = int(callback.data.split(":")[2])
    language = i18n.get_user_language(callback.from_user.language_code, callback.from_user.id)
    
    # ✅ Verify it's the same user
    if user_id != callback.from_user.id:
        await callback.answer(
            i18n.t('common.delete_account.not_your_account', language),
            show_alert=True
        )
        return
    
    try:
        with get_session() as session:
            # ✅ Delete user's posters first (foreign key constraint)
            session.execute(
                sql_delete(Poster).where(Poster.user_id == user_id)
            )
            
            # ✅ Delete user
            session.execute(
                sql_delete(User).where(User.telegram_id == user_id)
            )
            
            session.commit()
        
        # ✅ Update message to show success
        await callback.message.answer(
            f"{i18n.t('common.delete_account.success_title', language)}\n\n"
            f"{i18n.t('common.delete_account.success_text', language)}",
            parse_mode="HTML"
        )
        
        await callback.answer()
        logger.info(f"✅ User {user_id} deleted their account")
        
    except Exception as e:
        logger.error(f"❌ Error deleting user {user_id}: {e}")
        
        await callback.message.answer(
            i18n.t('common.delete_account.error', language),
            parse_mode="HTML"
        )
        
        await callback.answer()




@commands_router.callback_query(F.data == "privacy:back")
async def privacy_back(callback: types.CallbackQuery):
    """Go back from privacy policy"""
    
    # Just delete the privacy message
    try:
        await callback.message.delete()
    except:
        pass
    
    await callback.answer()


@commands_router.message(Command("help"))
async def cmd_help(message: types.Message):
    """Show all available commands"""
    language = i18n.get_user_language(message.from_user.language_code, message.from_user.id)

    # Check if user is admin (moderator)
    is_admin = message.from_user.id in config.admin_ids

    help_text = (
        f"{t('commands.help.title', language)}\n\n"
        f"{t('commands.help.general_title', language)}\n"
        f"{t('commands.help.general_commands', language)}\n\n"
        f"{t('commands.help.posters_title', language)}\n"
        f"{t('commands.help.posters_commands', language)}\n\n"
        f"{t('commands.help.subscription_title', language)}\n"
        f"{t('commands.help.subscription_commands', language)}"
    )

    # Show moderator commands only for admins
    if is_admin:
        help_text += f"\n\n{t('commands.help.moderator_title', language)}\n"
        help_text += f"{t('commands.help.moderator_commands', language)}"

    help_text += f"\n\n{t('commands.help.footer', language)}"

    await message.answer(help_text, parse_mode="HTML")


@commands_router.message(Command("language"))
async def cmd_language(message: types.Message):
    """Show language selection keyboard"""
    language = i18n.get_user_language(message.from_user.language_code, message.from_user.id)

    await message.answer(
        f"{t('common.language', language)}\n\n"
        f"🇷🇺 Русский | 🇬🇧 English",
        reply_markup=language_selection_keyboard(language).as_markup()
    )

@commands_router.callback_query(F.data.startswith("lang:"))
async def handle_language_selection(callback: types.CallbackQuery):
    """Handle user's language selection"""
    selected_lang = callback.data.split(":")[1]  # "ru" or "en"

    # Get language name in selected language
    lang_name = t(f"common.language_{selected_lang}", selected_lang)

    # Save user's language preference to database
    with get_session() as session:
        user = get_or_create_user(
            session,
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
            language_code=selected_lang,
            is_premium=callback.from_user.is_premium or False
        )
        # Update language preference
        user.language_code = selected_lang
        session.commit()

    # ✅ Load steps array and format with numbers in selected language
    steps_list = i18n.t('commands.start.steps', selected_lang)
    if isinstance(steps_list, list):
        steps = "\n".join([f"{i}. {step}" for i, step in enumerate(steps_list, 1)])
    else:
        steps = steps_list

    # Send full /start message in selected language with confirmation at top
    await callback.message.edit_text(
        f"✅ {t('common.language_selected', selected_lang, language_name=lang_name)}\n"
        f"{t('common.language_hint', selected_lang)}\n\n"
        f"{t('commands.start.title', selected_lang)}\n\n"
        f"{t('commands.start.description', selected_lang)}\n\n"
        f"{t('commands.start.how_to', selected_lang)}\n"
        f"{steps}\n\n"
        f"{t('commands.start.footer', selected_lang)}",
        parse_mode="HTML",
        reply_markup=None  # Hide keyboard after selection
    )

    await callback.answer()
    logger.info(f"User {callback.from_user.id} selected language: {selected_lang}")

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

    language = i18n.get_user_language(message.from_user.language_code, message.from_user.id)
    
    sent = await message.answer(
        f"{t('poster_flow.start.title', language)}\n\n"
        f"{t('poster_flow.start.description', language)}\n"
        f"{t('poster_flow.start.edit_hint', language)}\n"
        f"{t('poster_flow.start.cancel_hint', language)}\n\n"
        f"{t('poster_flow.start.examples_title', language)}\n"
        f"{t('poster_flow.start.examples', language)}",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(language).as_markup()
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
    language = i18n.get_user_language(message.from_user.language_code, message.from_user.id)
    
    with get_session() as session:
        stats = get_user_stats(session, message.from_user.id)
    
    await message.answer(
        f"{t('commands.stats.title', language)}\n\n"
        f"{t('commands.stats.total', language)}: <b>{stats['total']}</b>\n"
        f"{t('commands.stats.approved', language)}: <b>{stats['approved']}</b>\n"
        f"{t('commands.stats.declined', language)}: <b>{stats['declined']}</b>\n"
        f"{t('commands.stats.pending', language)}: <b>{stats['pending']}</b>",
        parse_mode="HTML"
    )

@commands_router.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    """Cancel current operation"""
    language = i18n.get_user_language(message.from_user.language_code, message.from_user.id)
    
    current_state = await state.get_state()
    if current_state is None:
        await message.answer(t('common.no_active_operation', language))
        return
    
    await state.clear()
    await message.answer(t('common.operation_cancelled', language))
    logger.info(f"Submission cancelled by user {message.from_user.id}")

# =============================================================================
# ============ AUTO-START ON FORWARD OR PHOTO (No /poster command needed) =====
# =============================================================================
# ⚠️ THIS HANDLER MUST COME FIRST - catches ANY photo/forward before state filters

@poster_router.message(F.photo | F.forward_origin)
async def process_photo_without_command(message: types.Message, state: FSMContext):
    """Auto-start poster flow when user sends photo or forwards message (without /poster)"""

    language = i18n.get_user_language(message.from_user.language_code, message.from_user.id)

    # ✅ Clear any existing state and start fresh
    await state.clear()
    await state.set_state(PosterSubmission.waiting_for_photo)

    # ✅ Register/update user in database
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

    # ============ HANDLE FORWARDED MESSAGE ============
    if message.forward_origin:
        # Extract info from forwarded message
        forwarded_data = extract_forwarded_info(message)

        # Validate: forwarded message must have text or media
        if not forwarded_data.get('caption') and not forwarded_data.get('photo_file_id'):
            await message.answer(
                t('poster_flow.forwarded.no_content', language),
                parse_mode="HTML"
            )
            await state.clear()
            return

        # Check if this is part of a forwarded media group (album)
        if message.media_group_id:
            # Handle as media group - collect all photos with timeout
            await handle_media_group_message(message, state, forwarded_data)
            return  # Don't proceed yet - waiting for more photos
        
        # Single forwarded message (not album)
        caption = forwarded_data.get('caption', '')
        photo_file_id = forwarded_data.get('photo_file_id')
        telegram_link = forwarded_data.get('telegram_link')

        # Add attribution note WITH link
        if forwarded_data.get('is_channel_forward') and forwarded_data.get('source_name'):
            if telegram_link:
                attribution_source = f"{forwarded_data['source_name']} — {telegram_link}"
                caption = f"{caption}\n\n{t('poster_flow.forwarded.attribution', language, source=attribution_source)}"
            else:
                caption = f"{caption}\n\n{t('poster_flow.forwarded.attribution', language, source=forwarded_data['source_name'])}"

        # Validate caption if no Telegram link
        is_valid = True
        error_message = ""
        if not telegram_link:
            is_valid, error_message = validate_caption(caption)

        if not is_valid:
            await handle_validation_error(message, state, error_message, language)
            return

        # Proceed with flow using forwarded data
        await state.update_data(
            photo_file_id=photo_file_id,
            caption=caption,
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            is_forwarded=True,
            forward_source=forwarded_data.get('source_name'),
            telegram_link=telegram_link,
            language=language
        )

    # ============ HANDLE PHOTO (INCLUDING MEDIA GROUPS) ============
    elif message.photo:
        # Check if this is part of a media group (album)
        if message.media_group_id:
            # Handle as media group - collect all photos with timeout
            is_group = await handle_media_group_message(message, state)
            if is_group:
                return  # Don't proceed yet - waiting for more photos
        
        # Single photo (not part of album)
        caption = message.caption or ""

        is_valid, error_message = validate_caption(caption)

        if not is_valid:
            await handle_validation_error(message, state, error_message, language)
            return

        await state.update_data(
            photo_file_id=message.photo[-1].file_id,
            caption=caption,
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            is_forwarded=False,
            language=language
        )

    # ============ INVALID INPUT ============
    else:
        await message.answer(
            t('poster_flow.invalid_photo.text', language),
            parse_mode="HTML"
        )
        await state.clear()
        return

    # ============ COMMON: Proceed to Next Step ============
    await state.set_state(PosterSubmission.waiting_for_anonymous)

    # Send next step (anonymous choice) - this is the "initial instruction" for auto-start
    sent = await message.answer(
        f"{t('poster_flow.anonymous.title', language)}\n\n"
        f"{t('poster_flow.anonymous.description', language)}",
        parse_mode="HTML",
        reply_markup=anonymous_choice_keyboard(language).as_markup()
    )

    await state.update_data(
        first_message_id=sent.message_id,
        prev_bot_message_id=sent.message_id
    )

    logger.info(f"Auto-started poster flow for user {message.from_user.id}")

# =============================================================================
# ============ POSTER FLOW - STEP 1: PHOTO (After /poster command) ===========
# =============================================================================
# ⚠️ This handler ONLY runs when user is already in waiting_for_photo state

@poster_router.message(PosterSubmission.waiting_for_photo, F.photo)
async def process_photo(message: types.Message, state: FSMContext):
    """Handle photo submission with caption validation (after /poster command)"""

    language = i18n.get_user_language(message.from_user.language_code, message.from_user.id)

    # Check if this is part of a media group (album)
    if message.media_group_id:
        # Handle as media group - collect all photos with timeout
        is_group = await handle_media_group_message(message, state)
        if is_group:
            return  # Don't proceed yet - waiting for more photos
    
    # Single photo (not part of album)
    caption = message.caption or ""

    # Validate caption (just check for link)
    is_valid, error_message = validate_caption(caption)

    if not is_valid:
        await handle_validation_error(message, state, error_message, language)
        return

    # Caption is valid - proceed with flow
    await state.update_data(
        photo_file_id=message.photo[-1].file_id,
        caption=caption,
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        is_forwarded=False,
        language=language
    )

    await state.set_state(PosterSubmission.waiting_for_anonymous)

    # Delete previous bot messages
    await cleanup_previous_messages(message, state)

    # Send next step
    sent = await message.answer(
        f"{t('poster_flow.anonymous.title', language)}\n\n"
        f"{t('poster_flow.anonymous.description', language)}",
        parse_mode="HTML",
        reply_markup=anonymous_choice_keyboard(language).as_markup()
    )

    await state.update_data(prev_bot_message_id=sent.message_id)

# =============================================================================
# ============ INVALID INPUT HANDLER =========================================
# =============================================================================

@poster_router.message(PosterSubmission.waiting_for_photo, ~F.photo & ~F.forward_origin)
async def invalid_photo(message: types.Message):
    """Reject non-photo, non-forwarded messages"""
    language = i18n.get_user_language(message.from_user.language_code, message.from_user.id)
    await message.answer(
        t('poster_flow.invalid_photo.text', language),
        parse_mode="HTML"
    )

# =============================================================================
# ============ POSTER FLOW - STEP 2: ANONYMOUS ===============================
# =============================================================================

@poster_router.callback_query(PosterSubmission.waiting_for_anonymous, F.data.startswith("anon:"))
async def process_anonymous(callback: types.CallbackQuery, state: FSMContext):
    """Handle anonymous preference"""
    language = i18n.get_user_language(callback.from_user.language_code, callback.from_user.id)
    
    is_anonymous = callback.data.split(":")[1] == "yes"
    await state.update_data(is_anonymous=is_anonymous)
    await state.set_state(PosterSubmission.waiting_for_date)
    
    selected_text = t('poster_flow.anonymous.selected_anon', language) if is_anonymous else t('poster_flow.anonymous.selected_public', language)
    
    await safe_edit_text(
        callback.message,
        text=(
            f"{selected_text}\n\n"
            f"{t('poster_flow.date.title', language)}\n"
            f"{t('poster_flow.date.description', language)}"
        ),
        reply_markup=date_picker_keyboard(language).as_markup()
    )
    
    await state.update_data(prev_bot_message_id=callback.message.message_id)
    await callback.answer()

@poster_router.callback_query(PosterSubmission.waiting_for_anonymous, F.data == "poster:back_to_photo")
async def back_to_photo(callback: types.CallbackQuery, state: FSMContext):
    """Go back to photo step"""
    language = i18n.get_user_language(callback.from_user.language_code, callback.from_user.id)
    
    await state.set_state(PosterSubmission.waiting_for_photo)
    
    await safe_edit_text(
        callback.message,
        text=(
            f"{t('poster_flow.start.title', language)}\n\n"
            f"{t('poster_flow.start.description', language)}"
        ),
        reply_markup=cancel_keyboard(language).as_markup()
    )
    
    await state.update_data(prev_bot_message_id=callback.message.message_id)
    await callback.answer()

# =============================================================================
# ============ POSTER FLOW - STEP 3: DATE ====================================
# =============================================================================

@poster_router.callback_query(PosterSubmission.waiting_for_date, F.data.startswith("date:"))
async def process_date_selection(callback: types.CallbackQuery, state: FSMContext):
    """Handle date selection from custom picker"""
    language = i18n.get_user_language(callback.from_user.language_code, callback.from_user.id)
    
    date_str = callback.data.split(":")[1]
    
    await state.update_data(event_date=date_str)
    await state.set_state(PosterSubmission.waiting_for_confirmation)
    
    data = await state.get_data()
    preview_text = format_preview_text(data)
    
    await safe_edit_text(
        callback.message,
        text=(
            f"{preview_text}\n\n"
            f"{t('poster_flow.confirmation.preview_hint', language)}"
        ),
        reply_markup=confirmation_keyboard(language).as_markup()
    )
    await state.update_data(prev_bot_message_id=callback.message.message_id)
    await callback.answer()


@poster_router.callback_query(PosterSubmission.waiting_for_date, F.data == "poster:back_to_anon")
async def back_to_anonymous(callback: types.CallbackQuery, state: FSMContext):
    """Go back to anonymous selection"""
    language = i18n.get_user_language(callback.from_user.language_code, callback.from_user.id)
    
    await state.set_state(PosterSubmission.waiting_for_anonymous)
    
    data = await state.get_data()
    is_anonymous = data.get("is_anonymous", False)
    
    selected_text = t('poster_flow.anonymous.selected_anon', language) if is_anonymous else t('poster_flow.anonymous.selected_public', language)
    
    await safe_edit_text(
        callback.message,
        text=(
            f"{selected_text}\n\n"
            f"{t('poster_flow.anonymous.title', language)}\n\n"
            f"{t('poster_flow.anonymous.description', language)}"
        ),
        reply_markup=anonymous_choice_keyboard(language).as_markup()
    )
    
    await state.update_data(prev_bot_message_id=callback.message.message_id)
    await callback.answer()

# =============================================================================
# ============ POSTER FLOW - STEP 4: CONFIRMATION ============================
# =============================================================================

@poster_router.callback_query(PosterSubmission.waiting_for_confirmation, F.data == "poster:confirm")
async def confirm_submission(callback: types.CallbackQuery, state: FSMContext):
    """Save poster to database and send to moderation"""
    language = i18n.get_user_language(callback.from_user.language_code, callback.from_user.id)
    data = await state.get_data()

    try:
        with get_session() as session:
            poster = create_poster(
                session=session,
                user_id=data['user_id'],
                photo_file_id=data['photo_file_id'],
                caption=data.get('caption', ''),
                event_date=datetime.fromisoformat(data['event_date']),
                is_anonymous=data['is_anonymous'],
                photos_json=data.get('photos_json')  # ← NEW: Store media group photos
            )

            # Send to moderation chat
            from bot.keyboards import moderation_keyboard
            from utils.helpers import format_moderation_caption
            from db.crud import update_moderation_message_info

            mod_data = {
                "caption": data.get('caption', ''),
                "user_id": data['user_id'],
                "username": data.get('username'),
                "is_anonymous": data['is_anonymous'],
                "event_date": data.get('event_date')
            }

            mod_caption = format_moderation_caption(mod_data, poster.id, language)

            keyboard = moderation_keyboard(
                user_id=data['user_id'],
                is_anonymous=data['is_anonymous'],
                poster_id=poster.id,
                language=language
            ).as_markup()

            # ✅ Check if this is a media group (album)
            is_media_group = data.get('is_media_group', False)
            
            if is_media_group:
                # Send album to moderation
                photos_json = data.get('photos_json')
                if photos_json:
                    photos_list = json.loads(photos_json)
                    
                    # Create media group for moderation
                    media_group = []
                    for i, photo_data in enumerate(photos_list):
                        if i == 0:
                            # First photo gets the full caption
                            media_group.append(
                                InputMediaPhoto(
                                    media=photo_data['file_id'],
                                    caption=mod_caption,
                                    parse_mode="HTML"
                                )
                            )
                        else:
                            # Subsequent photos without caption
                            media_group.append(
                                InputMediaPhoto(
                                    media=photo_data['file_id']
                                )
                            )
                    
                    # Send media group (no reply_markup - send separately)
                    sent_messages = await callback.bot.send_media_group(
                        chat_id=config.moderation_chat_id,
                        media=media_group
                    )
                    
                    # Store first message ID for moderation
                    sent_message = sent_messages[0]
                    
                    # Send keyboard as separate message below the album
                    await callback.bot.send_message(
                        chat_id=config.moderation_chat_id,
                        text=t('moderation.actions', language),
                        reply_markup=keyboard
                    )
                else:
                    # Fallback to single photo if something went wrong
                    sent_message = await callback.bot.send_photo(
                        chat_id=config.moderation_chat_id,
                        photo=data['photo_file_id'],
                        caption=mod_caption,
                        parse_mode="HTML",
                        reply_markup=keyboard
                    )
            else:
                # Send single photo
                sent_message = await callback.bot.send_photo(
                    chat_id=config.moderation_chat_id,
                    photo=data['photo_file_id'],
                    caption=mod_caption,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )

            # ✅ Store moderation message info in DB
            update_moderation_message_info(
                session=session,
                poster_id=poster.id,
                moderation_message_id=sent_message.message_id,
                moderation_chat_id=config.moderation_chat_id
            )

        await safe_edit_text(
            callback.message,
            text=(
                f"{t('poster_flow.success.title', language)}\n\n"
                f"{t('poster_flow.success.description', language)}"
            ),
            reply_markup=None
        )

        await state.clear()
        logger.info(f"Poster {poster.id} submitted by user {data['user_id']} (media_group={is_media_group})")

    except Exception as e:
        logger.error(f"Submission failed: {e}")
        await callback.answer(t('common.error', language), show_alert=True)

@poster_router.callback_query(PosterSubmission.waiting_for_confirmation, F.data == "poster:edit")
async def edit_submission(callback: types.CallbackQuery, state: FSMContext):
    """Return to photo step for editing"""
    language = i18n.get_user_language(callback.from_user.language_code, callback.from_user.id)
    
    await state.set_state(PosterSubmission.waiting_for_photo)
    
    data = await state.get_data()
    
    await safe_edit_text(
        callback.message,
        text=(
            f"{t('poster_flow.edit.title', language)}\n\n"
            f"{t('poster_flow.edit.description', language)}\n\n"
            f"{t('poster_flow.edit.previous_caption', language)}\n"
            f"<code>{data.get('caption', 'None')[:100]}{'...' if len(data.get('caption', '')) > 100 else ''}</code>"
        ),
        reply_markup=cancel_keyboard(language).as_markup()
    )
    
    await state.update_data(prev_bot_message_id=callback.message.message_id)
    await callback.answer()

@poster_router.callback_query(F.data == "poster:cancel")
async def cancel_submission(callback: types.CallbackQuery, state: FSMContext):
    """Cancel submission from any step"""
    language = i18n.get_user_language(callback.from_user.language_code, callback.from_user.id)
    
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
            t('poster_flow.cancelled.with_photo', language),
            parse_mode="HTML"
        )
    else:
        await callback.message.answer(t('poster_flow.cancelled.without_photo', language))
    
    await callback.answer()
    logger.info(f"Submission cancelled by user {callback.from_user.id} (has_photo={has_photo})")

@poster_router.callback_query(F.data == "poster:retry_photo")
async def retry_photo(callback: types.CallbackQuery, state: FSMContext):
    """Handle retry after validation error"""
    language = i18n.get_user_language(callback.from_user.language_code, callback.from_user.id)
    
    # Delete the error message
    try:
        await callback.message.delete()
    except Exception as e:
        logger.debug(f"Could not delete error message: {e}")
    
    # Send fresh instruction
    sent = await callback.message.answer(
        f"{t('poster_flow.retry.title', language)}\n\n"
        f"{t('poster_flow.retry.description', language)}\n\n"
        f"{t('poster_flow.retry.examples_title', language)}\n"
        f"{t('poster_flow.retry.examples', language)}",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(language).as_markup()
    )
    
    await state.update_data(
        first_message_id=sent.message_id,
        prev_bot_message_id=sent.message_id
    )
    
    await callback.answer(t('poster_flow.retry.button', language))
    logger.info(f"User {callback.from_user.id} retried photo submission")

@poster_router.callback_query(F.data == "poster:start_over")
async def start_over(callback: types.CallbackQuery, state: FSMContext):
    """Restart poster submission after cancellation"""
    language = i18n.get_user_language(callback.from_user.language_code, callback.from_user.id)
    
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
        f"{t('poster_flow.start.title', language)}\n\n"
        f"{t('poster_flow.start.description', language)}\n"
        f"{t('poster_flow.start.edit_hint', language)}",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(language).as_markup()
    )
    
    await state.update_data(
        first_message_id=sent.message_id,
        prev_bot_message_id=sent.message_id
    )
    
    await callback.answer()
    logger.info(f"User {callback.from_user.id} restarted poster submission")