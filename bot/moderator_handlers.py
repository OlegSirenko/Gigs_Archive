# bot/moderator_handlers.py
"""
Moderator handlers for approval workflow and DM finalization.
Separated from user handlers for clarity.
"""

import re
import asyncio
import logging
import json
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, InputMediaPhoto
from sqlalchemy import and_, func
from sqlalchemy.orm import joinedload
from db.crud import get_moderator_stats

# ✅ ADD i18n IMPORT
from utils.i18n import i18n, t

from bot.moderator_states import ModeratorEdit
from bot.keyboards import (
    moderation_keyboard,
    decline_reason_keyboard,
    moderator_skip_keyboard,
    moderator_confirmation_keyboard
)
from db.models import get_session, Poster, User
from db.crud import get_poster, update_poster_status, ModerationStatus, get_pending_posters_count, get_user_stats
from utils.helpers import format_public_caption, format_moderation_caption
from config import config
from datetime import datetime

logger = logging.getLogger(__name__)

# ============ ROUTERS ============
moderation_router = Router(name="moderation")         # Moderation chat handlers
moderator_edit_router = Router(name="moderator_edit") # Moderator DM handlers


async def safe_edit_moderation_message(bot, chat_id: int, message, status_text: str):
    """
    Safely edit moderation message, handling InaccessibleMessage after group migration.
    Returns True if edit succeeded, False if message was inaccessible.
    """
    try:
        if message.photo:
            await message.edit_caption(
                caption=(message.caption or "") + status_text,
                parse_mode="HTML",
                reply_markup=None
            )
        else:
            await message.edit_text(
                text=(message.text or "") + status_text,
                parse_mode="HTML",
                reply_markup=None
            )
        return True
    except Exception as e:
        # Message is inaccessible (e.g., group migrated to supergroup)
        logger.warning(f"Could not edit moderation message (likely migrated): {e}")
        # Send status as a new message using bot object (not message.bot which may not exist)
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=status_text.replace("\n\n━━━━━━━━━━━━━━━━━━━━", ""),
                parse_mode="HTML"
            )
        except Exception:
            pass  # If even this fails, just log and continue
        return False


async def safe_edit_keyboard(bot, chat_id: int, message, keyboard):
    """Safely edit keyboard on moderation message, handling InaccessibleMessage."""
    try:
        if message.photo:
            await message.edit_caption(
                caption=message.caption or "📝 Poster Submission",
                reply_markup=keyboard.as_markup()
            )
        else:
            await message.edit_text(
                text=message.text or "📝 Poster Submission",
                reply_markup=keyboard.as_markup()
            )
        return True
    except Exception as e:
        logger.warning(f"Could not edit keyboard (likely migrated): {e}")
        # Send as new message with keyboard
        try:
            await bot.send_message(
                chat_id=chat_id,
                text="📝 Poster Submission",
                reply_markup=keyboard.as_markup()
            )
        except Exception:
            pass
        return False

# =============================================================================
# ============ MODERATION CHAT HANDLERS =======================================
# =============================================================================

@moderation_router.callback_query(F.data.regexp(r"^(approve|decline):(\d+):([01]):(\d+)$"))
async def handle_moderation_decision(callback: types.CallbackQuery, state: FSMContext):
    """Process moderator approve/decline decision"""
    
    language = i18n.get_user_language(callback.from_user.language_code, callback.from_user.id)  # ← ADDED
    
    if callback.from_user.id not in config.admin_ids:
        await callback.answer(t("common.not_authorized", language), show_alert=True)  # ← CHANGED
        return
    
    action, user_id_str, anon_flag, poster_id_str = callback.data.split(":")
    user_id = int(user_id_str)
    poster_id = int(poster_id_str)
    moderator_id = callback.from_user.id
    moderator_username = callback.from_user.username or "no_username"
    
    try:
        with get_session() as session:
            poster = get_poster(session, poster_id)
            
            if not poster:
                await callback.answer(t("common.not_found", language), show_alert=True)  # ← CHANGED
                return
            
            # bot/moderator_handlers.py - In handle_moderation_decision, approve section

            if action == "approve":
                language = i18n.get_user_language(callback.from_user.language_code, callback.from_user.id)

                with get_session() as session:
                    poster = get_poster(session, poster_id)

                    if not poster:
                        await callback.answer(t("common.not_found", language), show_alert=True)
                        return

                    # ✅ IDEMPOTENCY CHECK: Prevent duplicate processing
                    # NOTE: poster.status is Enum object, not string!
                    if poster.status != ModerationStatus.PENDING:
                        # Show status-specific message
                        status_messages = {
                            ModerationStatus.PENDING_FINAL: t("moderation.action.already_in_progress", language),
                            ModerationStatus.APPROVED: t("moderation.action.already_approved", language),
                            ModerationStatus.DECLINED: t("moderation.action.already_declined", language),
                        }
                        error_msg = status_messages.get(poster.status, t("moderation.action.already_processed", language))
                        await callback.answer(error_msg, show_alert=True)
                        return

                    # ✅ EARLY CALLBACK ANSWER: Acknowledge immediately
                    await callback.answer(t("moderation.action.sent_to_dm", language), show_alert=False)

                    # Update DB to PENDING_FINAL
                    update_poster_status(
                        session=session,
                        poster_id=poster_id,
                        status=ModerationStatus.PENDING_FINAL.value,
                        moderator_id=moderator_id
                    )
                    
                    # ✅ Send instruction message and store its ID
                    instruction_text = (
                        f"{t('moderation.moderation_finalize.title', language)}"
                        f"{t('moderation.moderation_finalize.id', language, id=poster_id)}\n"
                        f"{t('moderation.moderation_finalize.userlink', language, userlink=poster.caption)}\n\n"
                        f"{t('moderation.moderation_finalize.description', language)}"
                        f"{t('moderation.moderation_finalize.footer', language)}\n\n"
                        f"💡 <i>Вы можете использовать HTML-форматирование: "
                        f"&lt;a href=\"https://example.com\"&gt;ссылка&lt;/a&gt;, "
                        f"&lt;b&gt;жирный&lt;/b&gt;, "
                        f"&lt;i&gt;курсив&lt;/i&gt;, "
                        f"&lt;code&gt;код&lt;/code&gt;</i>"
                    )
                    
                    skip_builder = InlineKeyboardBuilder()
                    skip_builder.row(
                        InlineKeyboardButton(
                            text=t("keyboards.moderator.start_editing", language),
                            callback_data=f"moderator:start_edit:{poster_id}"
                        )
                    )
                    skip_builder.row(
                        InlineKeyboardButton(
                            text=t("keyboards.moderator.skip", language),
                            callback_data=f"moderator:skip:{poster_id}"
                        )
                    )

                    # ✅ Send instruction message and get its ID
                    instruction_message = await callback.bot.send_message(
                        chat_id=moderator_id,
                        text=instruction_text,
                        parse_mode="HTML",
                        reply_markup=skip_builder.as_markup()
                    )

                    # ✅ Store instruction message info in FSM state (WITHOUT setting active state)
                    await state.update_data(
                        poster_id=poster_id,
                        user_id=poster.user_id,
                        is_anonymous=poster.is_anonymous,
                        photo_file_id=poster.photo_file_id,
                        original_caption=poster.caption,
                        event_date=poster.event_date.isoformat() if poster.event_date else None,
                        first_name=poster.user.first_name if poster.user else None,
                        username=poster.user.username if poster.user else None,
                        instruction_message_id=instruction_message.message_id,  # ← STORE THIS
                        instruction_chat_id=moderator_id,  # ← STORE THIS
                    )
                    
                    # Edit moderation message (same as before)
                    status_text = (
                        f"\n\n━━━━━━━━━━━━━━━━━━━━\n"
                        f"{t('moderation.status.pending_final', language)}\n"
                        f"👤 Moderator: @{moderator_username}\n"
                        f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
                        f"<i>{t('moderation.status.pending_final_hint', language)}</i>"
                    )

                    await safe_edit_moderation_message(callback.bot, callback.message.chat.id, callback.message, status_text)

            elif action == "decline":
                # Show decline reason keyboard (stateless)
                keyboard = decline_reason_keyboard(user_id, anon_flag, poster_id, language)

                if not await safe_edit_keyboard(callback.bot, callback.message.chat.id, callback.message, keyboard):
                    # If message is inaccessible, send decline as new message
                    await callback.bot.send_message(
                        chat_id=callback.message.chat.id,
                        text=t("moderation.action.decline_selected", language),
                        reply_markup=keyboard.as_markup()
                    )

                await callback.answer(t("moderation.action.decline_selected", language), show_alert=False)  # ← CHANGED
            
            logger.info(f"Moderation {action} for poster {poster_id} by @{moderator_username}")
            
    except Exception as e:
        logger.error(f"Moderation error: {e}")
        await callback.answer(t("common.error", language), show_alert=True)  # ← CHANGED


@moderation_router.callback_query(F.data.regexp(r"^decline_reason:(\w+):(\d+):([01]):(\d+)$"))
async def handle_decline_reason(callback: types.CallbackQuery):
    """Handle decline reason selection"""
    
    language = i18n.get_user_language(callback.from_user.language_code, callback.from_user.id)  # ← ADDED
    
    # Check if moderator is admin
    if callback.from_user.id not in config.admin_ids:
        await callback.answer(t("common.not_authorized", language), show_alert=True)  # ← CHANGED
        return
    
    # Parse callback  decline_reason:reason_code:user_id:anon_flag:poster_id
    parts = callback.data.split(":")
    
    if len(parts) != 5:
        await callback.answer("⚠️ Invalid callback data!", show_alert=True)
        return
    
    reason_code = parts[1]
    user_id = int(parts[2])
    anon_flag = parts[3]
    poster_id = int(parts[4])
    moderator_id = callback.from_user.id
    moderator_username = callback.from_user.username or "no_username"
    
    # ✅ Map reason codes to translations
    reason_text = t(f"notifications.decline_reasons.{reason_code}", language)
    
    try:
        with get_session() as session:
            # Get poster to verify it exists
            poster = get_poster(session, poster_id)
            if not poster:
                await callback.answer(t("common.not_found", language), show_alert=True)  # ← CHANGED
                return
            
            # Update database
            update_poster_status(
                session=session,
                poster_id=poster_id,
                status=ModerationStatus.DECLINED.value,
                moderator_id=moderator_id,
                decline_reason=reason_code
            )
            
            # ✅ Notify user with reason (in Russian)
            await callback.bot.send_message(
                chat_id=user_id,
                text=(
                    f"{t('notifications.declined.title', language)}\n\n"
                    f"{t('notifications.declined.reason', language)} {reason_text}\n\n"
                    f"{t('notifications.declined.moderator', language)} @{moderator_username}\n\n"
                    f"{t('notifications.declined.hint', language)}"
                ),
                parse_mode="HTML"
            )
            
            # EDIT moderation message to show result
            status_text = (
                f"\n\n━━━━━━━━━━━━━━━━━━━━\n"
                f"{t('moderation.status.declined', language)}\n"
                f"👤 Moderator: @{moderator_username}\n"
                f"📋 Reason: {reason_code}\n"
                f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            )

            await safe_edit_moderation_message(callback.bot, callback.message.chat.id, callback.message, status_text)

            await callback.answer(t("moderation.action.poster_declined", language), show_alert=False)
            logger.info(f"Poster {poster_id} declined by @{moderator_username} - Reason: {reason_code}")

    except Exception as e:
        logger.error(f"Decline error: {e}")
        await callback.answer(t("common.error", language), show_alert=True)  # ← CHANGED


@moderation_router.callback_query(F.data.regexp(r"^moderation:cancel_decline:(\d+):([01]):(\d+)$"))
async def cancel_decline(callback: types.CallbackQuery):
    """Cancel decline action and restore original keyboard"""

    language = i18n.get_user_language(callback.from_user.language_code, callback.from_user.id)  # ← ADDED

    # Check if moderator is admin
    if callback.from_user.id not in config.admin_ids:
        await callback.answer(t("common.not_authorized", language), show_alert=True)  # ← CHANGED
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
                await callback.answer(t("common.not_found", language), show_alert=True)  # ← CHANGED
                return

            # Restore original moderation keyboard
            keyboard = moderation_keyboard(
                user_id=poster.user_id,
                is_anonymous=poster.is_anonymous,
                poster_id=poster.id,
                language=language
            ).as_markup()

            # Get original caption (remove any status text)
            original_caption = callback.message.caption or "📝 Poster Submission"
            clean_caption = re.sub(
                r"\n\n━━━━━━━━━━━━━━━━━━━━.*",
                "",
                original_caption,
                flags=re.DOTALL
            )

            # Edit message — handle InaccessibleMessage gracefully
            try:
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
            except Exception as msg_error:
                logger.warning(f"Could not restore keyboard (likely migrated): {msg_error}")
                await callback.answer(t("moderation.action.decline_cancelled", language) + " (message inaccessible)", show_alert=True)
                return

        await callback.answer(t("moderation.action.decline_cancelled", language), show_alert=True)  # ← CHANGED
        logger.info(f"Decline cancelled for poster {poster_id}")
        
    except Exception as e:
        logger.error(f"Cancel decline error: {e}")
        await callback.answer(t("common.error", language), show_alert=True)  # ← CHANGED


@moderation_router.callback_query(F.data.regexp(r"^userinfo:(\d+)$"))
async def handle_userinfo(callback: types.CallbackQuery):
    """Show information about the user who submitted the poster"""
    
    language = i18n.get_user_language(callback.from_user.language_code, callback.from_user.id)  # ← ADDED
    
    # Check if moderator is admin
    if callback.from_user.id not in config.admin_ids:
        await callback.answer(t("common.not_authorized", language), show_alert=True)  # ← CHANGED
        return
    
    # Parse callback  userinfo:user_id
    user_id = int(callback.data.split(":")[1])
    
    try:
        with get_session() as session:
            user = session.query(User).filter(User.telegram_id == user_id).first()
            
            if not user:
                await callback.answer(t("common.not_found", language), show_alert=True)  # ← CHANGED
                return
            
            # Get user's poster statistics
            stats = get_user_stats(session, user_id)
            
            # ✅ Build user info text using translations
            userinfo_text = f"{t('moderation.userinfo.title', language)}\n\n"
            userinfo_text += f"{t('moderation.userinfo.id', language)} <code>{user.telegram_id}</code>\n"
            userinfo_text += f"{t('moderation.userinfo.name', language)} {user.first_name}"
            
            if user.last_name:
                userinfo_text += f" {user.last_name}"
            
            if user.username:
                userinfo_text += f"\n{t('moderation.userinfo.username', language)} @{user.username}"
            else:
                userinfo_text += f"\n{t('moderation.userinfo.username', language)} {t('moderation.userinfo.username_none', language)}"
            
            if user.language_code:
                userinfo_text += f"\n{t('moderation.userinfo.language', language)} {user.language_code.upper()}"
            
            if user.is_premium:
                userinfo_text += f"\n{t('moderation.userinfo.premium', language)} {t('moderation.userinfo.premium_yes', language)}"
            
            userinfo_text += f"\n\n{t('moderation.userinfo.stats_title', language)}\n"
            userinfo_text += f"{t('moderation.userinfo.stats_total', language)}: <b>{stats['total']}</b>\n"
            userinfo_text += f"{t('moderation.userinfo.stats_approved', language)}: <b>{stats['approved']}</b>\n"
            userinfo_text += f"{t('moderation.userinfo.stats_declined', language)}: <b>{stats['declined']}</b>\n"
            userinfo_text += f"{t('moderation.userinfo.stats_pending', language)}: <b>{stats['pending']}</b>\n\n"
            userinfo_text += f"{t('moderation.userinfo.registered', language)} {user.created_at.strftime('%d.%m.%Y %H:%M') if user.created_at else 'Н/Д'}"
            
            # Build keyboard with actions
            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(text=t("moderation.userinfo.write_button", language), url=f"tg://user?id={user_id}")
            )
            builder.row(
                InlineKeyboardButton(text=t("moderation.userinfo.close_button", language), callback_data="userinfo:close")
            )
            
            # Send as new message
            await callback.message.answer(
                userinfo_text,
                parse_mode="HTML",
                reply_markup=builder.as_markup()
            )
            
            await callback.answer()
            logger.info(f"User info requested for {user_id} by moderator {callback.from_user.id}")
            
    except Exception as e:
        logger.error(f"User info error: {e}")
        await callback.answer(t("common.error", language), show_alert=True)  # ← CHANGED


@moderation_router.callback_query(F.data == "userinfo:close")
async def close_userinfo(callback: types.CallbackQuery):
    """Close the user info message"""

    language = i18n.get_user_language(callback.from_user.language_code, callback.from_user.id)

    try:
        # Delete the user info message
        await callback.message.delete()
        await callback.answer()
    except:
        # If can't delete, just answer
        await callback.answer(t("common.close", language))


# =============================================================================
# ============ MODERATOR DM HANDLERS (Two-Stage Moderation) ===================
# =============================================================================

@moderator_edit_router.callback_query(F.data.startswith("moderator:start_edit:"))
async def start_editing(callback: types.CallbackQuery, state: FSMContext):
    """Handle 'Start Editing' button - sets FSM state in DM context"""

    language = i18n.get_user_language(callback.from_user.language_code, callback.from_user.id)
    poster_id = int(callback.data.split(":")[2])

    with get_session() as session:
        poster = get_poster(session, poster_id)
        if not poster:
            await callback.answer(t("common.not_found", language), show_alert=True)
            return

        # ✅ SET FSM STATE HERE (in DM context!)
        await state.set_state(ModeratorEdit.waiting_for_description)
        await state.update_data(
            poster_id=poster_id,
            user_id=poster.user_id,
            is_anonymous=poster.is_anonymous,
            photo_file_id=poster.photo_file_id,
            original_caption=poster.caption,  # Store for display/cancel
            event_date=poster.event_date.isoformat() if poster.event_date else None,
            first_name=poster.user.first_name if poster.user else None,
            username=poster.user.username if poster.user else None,
        )

        # ✅ Escape original caption for safe display in <code> block
        import html
        safe_original = html.escape(poster.caption or t("common.no_caption", language), quote=True)
        
        # ✅ Build keyboard with Cancel button
        cancel_builder = InlineKeyboardBuilder()
        cancel_builder.row(
            InlineKeyboardButton(
                text=t("keyboards.moderator.cancel_editing", language),
                callback_data=f"moderator:cancel_edit:{poster_id}"
            )
        )

        # ✅ EDIT instruction message to show input prompt + original caption
        await callback.message.edit_text(
            f"{t('moderation.start_editing.title', language)}\n\n"
            f"{t('moderation.start_editing.description', language)}\n\n"
            f"{t('moderation.start_editing.original_label', language)}\n"
            f"<code>{safe_original}</code>",  # ← Copiable original caption
            parse_mode="HTML",
            reply_markup=cancel_builder.as_markup()
        )
        
        await callback.answer()



@moderator_edit_router.callback_query(F.data.startswith("moderator:start_edit:"))
async def start_editing(callback: types.CallbackQuery, state: FSMContext):
    """Handle 'Start Editing' button - sets FSM state in DM context"""

    language = i18n.get_user_language(callback.from_user.language_code, callback.from_user.id)
    poster_id = int(callback.data.split(":")[2])

    with get_session() as session:
        poster = get_poster(session, poster_id)
        if not poster:
            await callback.answer(t("common.not_found", language), show_alert=True)
            return

        # ✅ SET FSM STATE HERE (in DM context!)
        await state.set_state(ModeratorEdit.waiting_for_description)
        await state.update_data(
            poster_id=poster_id,
            user_id=poster.user_id,
            is_anonymous=poster.is_anonymous,
            photo_file_id=poster.photo_file_id,
            original_caption=poster.caption,  # Store for display/cancel
            event_date=poster.event_date.isoformat() if poster.event_date else None,
            first_name=poster.user.first_name if poster.user else None,
            username=poster.user.username if poster.user else None,
        )

        # ✅ Escape original caption for safe display in <code> block
        import html
        safe_original = html.escape(poster.caption or t("common.no_caption", language), quote=True)
        
        # ✅ Build keyboard with Cancel button
        cancel_builder = InlineKeyboardBuilder()
        cancel_builder.row(
            InlineKeyboardButton(
                text=t("keyboards.moderator.cancel_editing", language),
                callback_data=f"moderator:cancel_edit:{poster_id}"
            )
        )

        # ✅ EDIT instruction message to show input prompt + original caption
        await callback.message.edit_text(
            f"{t('moderation.start_editing.title', language)}\n\n"
            f"{t('moderation.start_editing.description', language)}\n\n"
            f"{t('moderation.start_editing.original_label', language)}\n"
            f"<code>{safe_original}</code>",  # ← Copiable original caption
            parse_mode="HTML",
            reply_markup=cancel_builder.as_markup()
        )
        
        await callback.answer()

@moderator_edit_router.callback_query(F.data.startswith("moderator:skip:"))
async def skip_description(callback: types.CallbackQuery, state: FSMContext):
    """Handle skip button - FIRST response in DM (sets FSM state)"""
    
    language = i18n.get_user_language(callback.from_user.language_code, callback.from_user.id)
    poster_id = int(callback.data.split(":")[2])
    
    with get_session() as session:
        poster = get_poster(session, poster_id)
        if not poster:
            await callback.answer(t("common.not_found", language), show_alert=True)
            return
        
        # ✅ SET FSM STATE HERE (in DM context!)
        await state.set_state(ModeratorEdit.waiting_for_confirmation)
        await state.update_data(
            poster_id=poster_id,
            user_id=poster.user_id,
            is_anonymous=poster.is_anonymous,
            photo_file_id=poster.photo_file_id,
            final_caption=poster.caption,
            event_date=poster.event_date.isoformat() if poster.event_date else None,
            first_name=poster.user.first_name if poster.user else None,
            username=poster.user.username if poster.user else None,
        )
        
        # Build preview
        preview_caption = format_public_caption(
            data={
                "caption": poster.caption,
                "event_date": poster.event_date.isoformat() if poster.event_date else None,
                "is_anonymous": poster.is_anonymous
            },
            user_info=None if poster.is_anonymous else {
                "first_name": poster.user.first_name if poster.user else None,
                "username": poster.user.username if poster.user else None
            },
            language=language
        )
        
        # ✅ Build keyboard inline with poster_id
        confirm_builder = InlineKeyboardBuilder()
        confirm_builder.row(
            InlineKeyboardButton(text=t("keyboards.moderator.publish", language), callback_data=f"moderator:confirm:{poster_id}"),
            InlineKeyboardButton(text=t("keyboards.moderator.edit_again", language), callback_data=f"moderator:edit:{poster_id}")
        )
        confirm_builder.row(
            InlineKeyboardButton(text=t("common.cancel", language), callback_data=f"moderator:cancel:{poster_id}")
        )

        # ✅ EDIT THE ORIGINAL MESSAGE instead of sending new one
        await callback.message.edit_text(
            f"{t('moderation.skip_preview.title', language)}\n\n"
            f"{preview_caption}\n\n"
            f"{t('moderation.skip_preview.ready_hint', language)}",
            parse_mode="HTML",
            reply_markup=confirm_builder.as_markup()
        )
        await callback.answer()


@moderator_edit_router.callback_query(F.data.startswith("moderator:cancel_edit:"))
async def cancel_during_editing(callback: types.CallbackQuery, state: FSMContext):
    """Cancel editing and return poster to moderation queue"""
    
    language = i18n.get_user_language(callback.from_user.language_code, callback.from_user.id)
    poster_id = int(callback.data.split(":")[2])
    moderator_id = callback.from_user.id
    
    with get_session() as session:
        poster = get_poster(session, poster_id)
        if not poster:
            await callback.answer(t("common.not_found", language), show_alert=True)
            return
        
        # ✅ Reset to PENDING (back to queue)
        update_poster_status(
            session=session,
            poster_id=poster_id,
            status=ModerationStatus.PENDING.value,
            moderator_id=None
        )
        
        # ✅ Restore original keyboard on the moderation message
        try:
            if poster.moderation_message_id and poster.moderation_chat_id:
                from bot.keyboards import moderation_keyboard
                
                keyboard = moderation_keyboard(
                    user_id=poster.user_id,
                    is_anonymous=poster.is_anonymous,
                    poster_id=poster.id,
                    language=language
                ).as_markup()
                
                await callback.bot.edit_message_reply_markup(
                    chat_id=poster.moderation_chat_id,
                    message_id=poster.moderation_message_id,
                    reply_markup=keyboard
                )
                
                # Optional: notify moderation chat
                await callback.bot.send_message(
                    chat_id=config.moderation_chat_id,
                    text=t(
                        "moderation.action.returned_to_queue",
                        language,
                        poster_id=poster_id,
                        username=callback.from_user.username or "no_username"
                    ),
                    parse_mode="HTML"
                )
        except Exception as e:
            logger.error(f"Could not restore keyboard for poster {poster_id}: {e}")
    
    # ✅ Clear FSM state
    await state.clear()
    
    # ✅ Notify moderator in DM
    await callback.message.edit_text(
        t("moderation.action.edit_cancelled_dm", language, poster_id=poster_id),
        parse_mode="HTML"
    )
    
    await callback.answer()
    logger.info(f"✏️ Editing cancelled for poster {poster_id} by moderator {moderator_id}")

@moderator_edit_router.message(ModeratorEdit.waiting_for_description, F.text, F.from_user.id.in_(config.admin_ids))
async def process_moderator_description(message: types.Message, state: FSMContext):
    """Handle moderator typing description - supports plain text AND HTML formatting"""

    language = i18n.get_user_language(message.from_user.language_code, message.from_user.id)
    moderator_id = message.from_user.id

    # ✅ Get caption with HTML formatting if available
    # Use HtmlDecoration.unparse for both captions and text messages
    from aiogram.utils.text_decorations import HtmlDecoration
    html_decoration = HtmlDecoration()
    
    if message.caption:
        # Photo/video/document with caption
        final_caption = html_decoration.unparse(message.caption, message.caption_entities)
    elif message.text:
        # Plain text message (moderator typing in DM)
        final_caption = html_decoration.unparse(message.text, message.entities)
    else:
        final_caption = ""

    with get_session() as session:
        poster = session.query(Poster).filter(
            and_(
                Poster.status == ModerationStatus.PENDING_FINAL,
                Poster.moderated_by == moderator_id
            )
        ).order_by(Poster.moderated_at.desc()).first()

        if not poster:
            await message.answer(
                t("moderation.no_posters_pending", language)
            )
            return

        poster_id = poster.id

        # ✅ GET CURRENT STATE DATA (should have instruction_message_id)
        current_data = await state.get_data()
        instruction_message_id = current_data.get('instruction_message_id')
        instruction_chat_id = current_data.get('instruction_chat_id')

        # ✅ SET FSM STATE
        await state.set_state(ModeratorEdit.waiting_for_confirmation)
        await state.update_data(
            poster_id=poster_id,
            user_id=poster.user_id,
            is_anonymous=poster.is_anonymous,
            photo_file_id=poster.photo_file_id,
            final_caption=final_caption,
            event_date=poster.event_date.isoformat() if poster.event_date else None,
            first_name=poster.user.first_name if poster.user else None,
            username=poster.user.username if poster.user else None,
            # Keep instruction message info
            instruction_message_id=instruction_message_id,
            instruction_chat_id=instruction_chat_id,
        )

        # Build preview — use HTML caption if available
        preview_caption = format_public_caption(
            data={
                "caption": final_caption,
                "event_date": poster.event_date.isoformat() if poster.event_date else None,
                "is_anonymous": poster.is_anonymous
            },
            user_info=None if poster.is_anonymous else {
                "first_name": poster.user.first_name if poster.user else None,
                "username": poster.user.username if poster.user else None
            },
            language=language
        )
        
        # Build keyboard
        confirm_builder = InlineKeyboardBuilder()
        confirm_builder.row(
            InlineKeyboardButton(text=t("keyboards.moderator.publish", language), callback_data=f"moderator:confirm:{poster_id}"),
            InlineKeyboardButton(text=t("keyboards.moderator.edit_again", language), callback_data=f"moderator:edit:{poster_id}")
        )
        confirm_builder.row(
            InlineKeyboardButton(text=t("common.cancel", language), callback_data=f"moderator:cancel:{poster_id}")
        )

        # ✅ TRY TO EDIT THE STORED INSTRUCTION MESSAGE
        if instruction_message_id and instruction_chat_id:
            try:
                await message.bot.edit_message_text(
                    chat_id=instruction_chat_id,
                    message_id=instruction_message_id,
                    text=(
                        f"{t('moderation.edit_preview.title', language)}\n\n"
                        f"{preview_caption}\n\n"
                        f"{t('moderation.edit_preview.check_hint', language)}"
                    ),
                    parse_mode="HTML",
                    reply_markup=confirm_builder.as_markup()
                )

                # ✅ Delete the user's text message to keep chat clean
                try:
                    await message.delete()
                except:
                    pass

            except Exception as e:
                logger.error(f"Could not edit instruction message: {e}")
                # Fallback: send new message
                await message.answer(
                    f"{t('moderation.edit_preview.title', language)}\n\n"
                    f"{preview_caption}\n\n"
                    f"{t('moderation.edit_preview.check_hint', language)}",
                    parse_mode="HTML",
                    reply_markup=confirm_builder.as_markup()
                )
        else:
            # Fallback if no instruction message ID stored
            logger.warning(f"No instruction_message_id in state for poster {poster_id}")
            await message.answer(
                f"{t('moderation.edit_preview.title', language)}\n\n"
                f"{preview_caption}\n\n"
                f"{t('moderation.edit_preview.check_hint', language)}",
                parse_mode="HTML",
                reply_markup=confirm_builder.as_markup()
            )


@moderator_edit_router.callback_query(ModeratorEdit.waiting_for_confirmation, F.data.startswith("moderator:confirm:"))
async def final_confirm(callback: types.CallbackQuery, state: FSMContext):
    """Final confirmation - publish to channel"""

    language = i18n.get_user_language(callback.from_user.language_code, callback.from_user.id)
    poster_id = int(callback.data.split(":")[2])
    data = await state.get_data()

    with get_session() as session:
        poster = get_poster(session, poster_id)
        user_id = poster.user_id

        target_channel_id = config.test_channel_id if config.debug_mode else config.main_channel_id

        # ✅ SAVE MODERATOR'S FINAL CAPTION TO DATABASE
        poster.caption = data.get("final_caption")

        final_caption = format_public_caption(
            data={
                "caption": data.get("final_caption"),
                "event_date": data.get("event_date"),
                "is_anonymous": data.get("is_anonymous")
            },
            user_info=None if data.get("is_anonymous") else {
                "first_name": data.get("first_name"),
                "username": data.get("username")
            },
            language=language
        )

        if config.debug_mode:
            final_caption += t("moderation.action.test_mode_caption", language)

        # ✅ Check if this is a media group (album)
        photos_json = poster.photos_json or data.get("photos_json")
        
        if photos_json:
            # Send album to channel
            try:
                photos_list = json.loads(photos_json)
                
                # Create media group for channel
                media_group = []
                for i, photo_data in enumerate(photos_list):
                    if i == 0:
                        # First photo gets the full caption
                        media_group.append(
                            InputMediaPhoto(
                                media=photo_data['file_id'],
                                caption=final_caption,
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
                
                # Send media group to channel
                sent_messages = await callback.bot.send_media_group(
                    chat_id=target_channel_id,
                    media=media_group
                )
                
                # Store first message ID
                sent_message = sent_messages[0]
                
            except Exception as e:
                logger.error(f"Error sending media group to channel: {e}")
                # Fallback to single photo
                sent_message = await callback.bot.send_photo(
                    chat_id=target_channel_id,
                    photo=data.get("photo_file_id") or poster.photo_file_id,
                    caption=final_caption,
                    parse_mode="HTML"
                )
        else:
            # Send single photo to channel
            sent_message = await callback.bot.send_photo(
                chat_id=target_channel_id,
                photo=data.get("photo_file_id") or poster.photo_file_id,
                caption=final_caption,
                parse_mode="HTML"
            )
        
        # Update database to APPROVED (final) - this will commit the caption change too!
        update_poster_status(
            session=session,
            poster_id=poster_id,
            status=ModerationStatus.APPROVED.value,
            moderator_id=callback.from_user.id,
            channel_message_id=sent_message.message_id,
            channel_chat_id=target_channel_id
        )
        
        # ✅ UPDATE THE ORIGINAL MODERATION MESSAGE
        if poster.moderation_message_id and poster.moderation_chat_id:
            try:
                # Build the final status text
                channel_link = f"https://t.me/c/{str(target_channel_id)[4:]}/{sent_message.message_id}" if str(target_channel_id).startswith("-100") else f"https://t.me/{target_channel_id}/{sent_message.message_id}"
                
                final_status_text = (
                    f"\n\n━━━━━━━━━━━━━━━━━━━━\n"
                    f"{t('moderation.status.approved', language)}\n"
                    f"👤 Moderator: @{callback.from_user.username or 'no_username'}\n"
                    f"{t('moderation.action.published_channel', language, channel_link=channel_link)}\n"
                    f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
                )
                
                # Get original caption and append status
                original_caption = poster.caption or "📨 New Poster Submission"
                
                # Try to edit the original moderation message
                await callback.bot.edit_message_caption(
                    chat_id=poster.moderation_chat_id,
                    message_id=poster.moderation_message_id,
                    caption=original_caption + final_status_text,
                    parse_mode="HTML",
                    reply_markup=None  # Remove buttons since it's approved
                )
            except Exception as e:
                logger.error(f"Could not update moderation message for poster {poster_id}: {e}")
                # Fallback: send a new message with the status
                try:
                    await callback.bot.send_message(
                        chat_id=config.moderation_chat_id,
                        text=(
                            t("moderation.action.poster_published", language, poster_id=poster_id) + "\n" +
                            f"🔗 {channel_link}\n" +
                            f"👤 @{callback.from_user.username or 'no_username'}"
                        ),
                        parse_mode="HTML"
                    )
                except:
                    pass
    
    # Notify moderator in DM
    await callback.message.edit_text(
        t("moderation.action.published_success", language, poster_id=poster_id),
        parse_mode="HTML"
    )
    
    # Notify user (in Russian)
    anon_text = t("notifications.approved.anon_yes", language) if data.get("is_anonymous") else t("notifications.approved.anon_no", language)
    
    if config.debug_mode:
        notify_text = t("notifications.approved.debug", language, anon_text=anon_text)
    else:
        notify_text = t("notifications.approved.production", language, anon_text=anon_text)
    
    await callback.bot.send_message(
        chat_id=user_id,
        text=notify_text,
        parse_mode="HTML"
    )
    
    await state.clear()
    logger.info(f"Poster {poster_id} finally published by moderator {callback.from_user.id}")


@moderator_edit_router.callback_query(ModeratorEdit.waiting_for_confirmation, F.data.startswith("moderator:edit:"))
async def edit_again(callback: types.CallbackQuery, state: FSMContext):
    """Let moderator edit description again"""

    language = i18n.get_user_language(callback.from_user.language_code, callback.from_user.id)

    await state.set_state(ModeratorEdit.waiting_for_description)

    await callback.message.edit_text(
        t("moderation.edit_again.title", language) + "\n\n" +
        t("moderation.edit_again.description", language),
        parse_mode="HTML"
    )
    await callback.answer()


@moderator_edit_router.callback_query(ModeratorEdit.waiting_for_confirmation, F.data.startswith("moderator:cancel:"))
async def final_cancel(callback: types.CallbackQuery, state: FSMContext):
    """Cancel final publishing - return to pending and restore keyboard"""
    
    language = i18n.get_user_language(callback.from_user.language_code, callback.from_user.id)
    poster_id = int(callback.data.split(":")[2])
    data = await state.get_data()
    moderator_id = callback.from_user.id
    
    with get_session() as session:
        # ✅ Get poster with moderation message info
        poster = get_poster(session, poster_id)
        
        # ✅ Get user info from DB (to get username)
        from db.models import User
        user = session.query(User).filter(User.telegram_id == poster.user_id).first()
        username = user.username if user and user.username else "no_username"
        
        # ✅ Reset to PENDING (back to queue)
        update_poster_status(
            session=session,
            poster_id=poster_id,
            status=ModerationStatus.PENDING.value
        )
        
        # ✅ Restore original keyboard on the moderation message
        try:
            if poster.moderation_message_id and poster.moderation_chat_id:
                from bot.keyboards import moderation_keyboard
                
                keyboard = moderation_keyboard(
                    user_id=poster.user_id,
                    is_anonymous=poster.is_anonymous,
                    poster_id=poster.id,
                    language=language
                ).as_markup()
                
                # ✅ Restore keyboard on original message
                await callback.bot.edit_message_reply_markup(
                    chat_id=poster.moderation_chat_id,
                    message_id=poster.moderation_message_id,
                    reply_markup=keyboard
                )
                
                # ✅ Send small notification (optional)
                await callback.bot.send_message(
                    chat_id=config.moderation_chat_id,
                    text=t("moderation.action.returned_to_queue", language, poster_id=poster_id, username=callback.from_user.username or "no_username"),
                    parse_mode="HTML"
                )
            else:
                logger.warning(f"Poster {poster_id} has no moderation_message_id stored")
        except Exception as e:
            logger.error(f"Could not restore keyboard for poster {poster_id}: {e}")
    
    # ✅ Notify moderator in DM
    await callback.message.edit_text(
        t("moderation.action.cancel_returned", language, operation_cancelled=t("common.operation_cancelled", language), poster_id=poster_id),
        parse_mode="HTML"
    )
    
    await state.clear()
    await callback.answer()
    logger.info(f"Poster {poster_id} cancelled by moderator {moderator_id} - keyboard restored")


# =============================================================================
# ============ ADMIN COMMANDS (Optional) ======================================
# =============================================================================

@moderation_router.message(Command("pending"), F.from_user.id.in_(config.admin_ids))
async def cmd_pending(message: types.Message):
    """Show pending posters with moderation message IDs"""

    language = i18n.get_user_language(message.from_user.language_code, message.from_user.id)

    with get_session() as session:
        # ✅ Use joinedload to eagerly load user relationship
        pending_posters = session.query(Poster).options(
            joinedload(Poster.user)  # ← PRELOAD USER DATA
        ).filter(
            Poster.status == ModerationStatus.PENDING
        ).order_by(Poster.created_at.asc()).limit(15).all()

        total_count = session.query(func.count(Poster.id)).filter(
            Poster.status == ModerationStatus.PENDING
        ).scalar() or 0

    if not pending_posters:
        await message.answer(
            t("moderation.pending.no_posters", language),
            parse_mode="HTML"
        )
        return

    # Build message text
    text = f"{t('moderation.pending.title', language)} <code>{total_count}</code>\n\n"
    
    if total_count > 15:
        text += f"<i>{t('moderation.pending.showing_first', language, count=15, total=total_count)}</i>\n\n"

    for i, poster in enumerate(pending_posters, 1):
        # Extract short caption preview
        caption_preview = poster.caption[:40] + "..." if len(poster.caption) > 40 else poster.caption

        # Get moderation message ID
        mod_message_id = poster.moderation_message_id if poster.moderation_message_id else t("moderation.pending.not_available", language)

        # ✅ Get username (with fallback)
        username = poster.user.username if poster.user and poster.user.username else t("moderation.pending.user_id_format", language, user_id=poster.user_id)

        # Add to list
        text += f"{i}. <b>{t('moderation.pending.id', language)}</b> <code>{poster.id}</code> — {caption_preview}\n"
        text += f"   👤 @{username} | 📅 {poster.event_date.strftime('%d.%m') if poster.event_date else t('moderation.pending.na', language)}\n\n"


    if total_count > 15:
        text += f"<i>... {t('moderation.pending.more_in_queue', language, count=total_count - 15)}</i>\n\n"

    # Add hint about how to find messages
    text += f"<i>💡 {t('moderation.pending.how_to_find_title', language)}</i>\n"
    text += f"<i>1. {t('moderation.pending.how_to_find_step1', language)}</i>\n"
    text += f"<i>2. {t('moderation.pending.how_to_find_step2', language)}</i>\n"
    text += f"<i>3. {t('moderation.pending.how_to_find_step3', language)}</i>"
    
    await message.answer(
        text,
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    
    logger.info(f"/pending command used by admin {message.from_user.username} — {total_count} pending")


@moderation_router.message(Command("mystats"), F.from_user.id.in_(config.admin_ids))
async def cmd_moderator_stats(message: types.Message):
    """Show moderator's personal statistics"""
    
    language = i18n.get_user_language(message.from_user.language_code, message.from_user.id)  # ← ADDED
    moderator_id = message.from_user.id
    
    with get_session() as session:
        stats = get_moderator_stats(session, moderator_id)
    
    await message.answer(
        f"{t('moderation.moderator_stats.title', language)}\n\n"
        f"{t('moderation.moderator_stats.total', language)}: <b>{stats['total']}</b>\n"
        f"{t('moderation.moderator_stats.approved', language)}: <b>{stats['approved']}</b>\n"
        f"{t('moderation.moderator_stats.declined', language)}: <b>{stats['declined']}</b>\n"
        f"{t('moderation.moderator_stats.pending_final', language)}: <b>{stats['pending_final']}</b>",
        parse_mode="HTML"
    )
