# bot/moderator_handlers.py
"""
Moderator handlers for approval workflow and DM finalization.
Separated from user handlers for clarity.
"""

import re
import asyncio
import logging
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from sqlalchemy import and_
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

# =============================================================================
# ============ MODERATION CHAT HANDLERS =======================================
# =============================================================================

@moderation_router.callback_query(F.data.regexp(r"^(approve|decline):(\d+):([01]):(\d+)$"))
async def handle_moderation_decision(callback: types.CallbackQuery):
    """Process moderator approve/decline decision"""
    
    language = i18n.get_user_language(callback.from_user.language_code)  # ← ADDED
    
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
            
            if action == "approve":
                # Update DB to PENDING_FINAL
                update_poster_status(
                    session=session,
                    poster_id=poster_id,
                    status=ModerationStatus.PENDING_FINAL.value,
                    moderator_id=moderator_id
                )
                
                # ✅ Send DM - but DON'T set FSM state yet!
                # State will be set when moderator responds IN DM
                await callback.bot.send_message(
                    chat_id=moderator_id,
                    text=(
                        "✏️ <b>Создайте финальное описание</b>\n\n"
                        f"ID афиши: <code>{poster_id}</code>\n"
                        f"Ссылка пользователя: <code>{poster.caption}</code>\n\n"
                        "Отправьте финальное описание для этой публикации.\n"
                        "Включите:\n"
                        "• Детали события\n"
                        "• Дата/время\n"
                        "• Место проведения\n"
                        "• Ссылки на билеты\n"
                        "• Хештеги\n\n"
                        "Или нажмите «Пропустить», чтобы использовать оригинальное описание."
                    ),
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardBuilder().row(
                        InlineKeyboardButton(
                            text="⏭️ Пропустить — использовать оригинал", 
                            callback_data=f"moderator:skip:{poster_id}"  # ← Includes poster_id!
                        )
                    ).as_markup()
                )
                
                # Edit moderation message
                status_text = (
                    f"\n\n━━━━━━━━━━━━━━━━━━━━\n"
                    f"{t('moderation.status.pending_final', language)}\n"
                    f"👤 Moderator: @{moderator_username}\n"
                    f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
                    f"<i>{t('moderation.status.pending_final_hint', language)}</i>"
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
                
                await callback.answer("✅ Отправлено в ЛС для финализации!", show_alert=False)  # ← CHANGED
                
            elif action == "decline":
                # Show decline reason keyboard (stateless)
                keyboard = decline_reason_keyboard(user_id, anon_flag, poster_id, language)  # ← ADDED language param
                
                if callback.message.photo:
                    await callback.message.edit_caption(
                        caption=callback.message.caption or "📝 Poster Submission",
                        reply_markup=keyboard.as_markup()
                    )
                else:
                    await callback.message.edit_text(
                        text=callback.message.caption or "📝 Poster Submission",
                        reply_markup=keyboard.as_markup()
                    )
                
                await callback.answer("Выберите причину отклонения:")  # ← CHANGED
            
            logger.info(f"Moderation {action} for poster {poster_id} by @{moderator_username}")
            
    except Exception as e:
        logger.error(f"Moderation error: {e}")
        await callback.answer(t("common.error", language), show_alert=True)  # ← CHANGED


@moderation_router.callback_query(F.data.regexp(r"^decline_reason:(\w+):(\d+):([01]):(\d+)$"))
async def handle_decline_reason(callback: types.CallbackQuery):
    """Handle decline reason selection"""
    
    language = i18n.get_user_language(callback.from_user.language_code)  # ← ADDED
    
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
            
            await callback.answer("❌ Афиша отклонена!", show_alert=False)  # ← CHANGED
            logger.info(f"Poster {poster_id} declined by @{moderator_username} - Reason: {reason_code}")
            
    except Exception as e:
        logger.error(f"Decline error: {e}")
        await callback.answer(t("common.error", language), show_alert=True)  # ← CHANGED


@moderation_router.callback_query(F.data.regexp(r"^moderation:cancel_decline:(\d+):([01]):(\d+)$"))
async def cancel_decline(callback: types.CallbackQuery):
    """Cancel decline action and restore original keyboard"""
    
    language = i18n.get_user_language(callback.from_user.language_code)  # ← ADDED
    
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
                language=language  # ← ADDED language param
            ).as_markup()
            
            # Get original caption (remove any status text)
            original_caption = callback.message.caption or "📝 Poster Submission"
            
            # Remove any status text that might have been added
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
        
        await callback.answer("✅ Отклонение отменено. Варианты восстановлены.", show_alert=True)  # ← CHANGED
        logger.info(f"Decline cancelled for poster {poster_id}")
        
    except Exception as e:
        logger.error(f"Cancel decline error: {e}")
        await callback.answer(t("common.error", language), show_alert=True)  # ← CHANGED


@moderation_router.callback_query(F.data.regexp(r"^userinfo:(\d+)$"))
async def handle_userinfo(callback: types.CallbackQuery):
    """Show information about the user who submitted the poster"""
    
    language = i18n.get_user_language(callback.from_user.language_code)  # ← ADDED
    
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
    
    try:
        # Delete the user info message
        await callback.message.delete()
        await callback.answer()
    except:
        # If can't delete, just answer
        await callback.answer(t("common.close", language))  # ← CHANGED


# =============================================================================
# ============ MODERATOR DM HANDLERS (Two-Stage Moderation) ===================
# =============================================================================

@moderator_edit_router.callback_query(F.data.startswith("moderator:skip:"))
async def skip_description(callback: types.CallbackQuery, state: FSMContext):
    """Handle skip button - FIRST response in DM (sets FSM state)"""
    
    language = i18n.get_user_language(callback.from_user.language_code)
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
            }
        )
        
        # ✅ Build keyboard inline with poster_id
        confirm_builder = InlineKeyboardBuilder()
        confirm_builder.row(
            InlineKeyboardButton(text="✅ Опубликовать в канале", callback_data=f"moderator:confirm:{poster_id}"),
            InlineKeyboardButton(text="✏️ Редактировать ещё раз", callback_data=f"moderator:edit:{poster_id}")
        )
        confirm_builder.row(
            InlineKeyboardButton(text=t("common.cancel", language), callback_data=f"moderator:cancel:{poster_id}")
        )
        
        await callback.message.answer(
            f"👁️ <b>Предпросмотр (оригинальное описание)</b>\n\n"
            f"{preview_caption}\n\n"
            f"<i>Готовы опубликовать?</i>",
            parse_mode="HTML",
            reply_markup=confirm_builder.as_markup()
        )
        await callback.answer()


@moderator_edit_router.message(F.text)
async def process_moderator_description(message: types.Message, state: FSMContext):
    """Handle moderator typing description - FIRST response in DM (sets FSM state)"""
    
    language = i18n.get_user_language(message.from_user.language_code)
    moderator_id = message.from_user.id
    
    with get_session() as session:
        poster = session.query(Poster).filter(
            and_(
                Poster.status == ModerationStatus.PENDING_FINAL,
                Poster.moderated_by == moderator_id
            )
        ).order_by(Poster.moderated_at.desc()).first()
        
        if not poster:
            await message.answer(
                "ℹ️ Нет афиш, ожидающих финализации.\n"
                "Сначала одобрите афишу в чате модерации!"
            )
            return
        
        poster_id = poster.id
        
        # ✅ SET FSM STATE HERE (in DM context!)
        await state.set_state(ModeratorEdit.waiting_for_confirmation)
        await state.update_data(
            poster_id=poster_id,
            user_id=poster.user_id,
            is_anonymous=poster.is_anonymous,
            photo_file_id=poster.photo_file_id,
            final_caption=message.text,
            event_date=poster.event_date.isoformat() if poster.event_date else None,
            first_name=poster.user.first_name if poster.user else None,
            username=poster.user.username if poster.user else None,
        )
        
        # Build preview with moderator's description
        preview_caption = format_public_caption(
            data={
                "caption": message.text,
                "event_date": poster.event_date.isoformat() if poster.event_date else None,
                "is_anonymous": poster.is_anonymous
            },
            user_info=None if poster.is_anonymous else {
                "first_name": poster.user.first_name if poster.user else None,
                "username": poster.user.username if poster.user else None
            }
        )
        
        # ✅ Build keyboard inline with poster_id
        confirm_builder = InlineKeyboardBuilder()
        confirm_builder.row(
            InlineKeyboardButton(text="✅ Опубликовать в канале", callback_data=f"moderator:confirm:{poster_id}"),
            InlineKeyboardButton(text="✏️ Редактировать ещё раз", callback_data=f"moderator:edit:{poster_id}")
        )
        confirm_builder.row(
            InlineKeyboardButton(text=t("common.cancel", language), callback_data=f"moderator:cancel:{poster_id}")
        )
        
        await message.answer(
            f"👁️ <b>Предпросмотр перед публикацией</b>\n\n"
            f"{preview_caption}\n\n"
            f"<i>Проверьте перед публикацией!</i>",
            parse_mode="HTML",
            reply_markup=confirm_builder.as_markup()
        )


@moderator_edit_router.callback_query(ModeratorEdit.waiting_for_confirmation, F.data.startswith("moderator:confirm:"))
async def final_confirm(callback: types.CallbackQuery, state: FSMContext):
    """Final confirmation - publish to channel"""
    
    language = i18n.get_user_language(callback.from_user.language_code)
    poster_id = int(callback.data.split(":")[2])
    data = await state.get_data()
    
    with get_session() as session:
        poster = get_poster(session, poster_id)
        user_id = poster.user_id
        
        target_channel_id = config.test_channel_id if config.debug_mode else config.main_channel_id
        
        final_caption = format_public_caption(
            data={
                "caption": data.get("final_caption"),
                "event_date": data.get("event_date"),
                "is_anonymous": data.get("is_anonymous")
            },
            user_info=None if data.get("is_anonymous") else {
                "first_name": data.get("first_name"),
                "username": data.get("username")
            }
        )
        
        if config.debug_mode:
            final_caption += "\n\n⚠️ <i>ТЕСТОВЫЙ РЕЖИМ — не реальная публикация</i>"
        
        sent_message = await callback.bot.send_photo(
            chat_id=target_channel_id,
            photo=data.get("photo_file_id"),
            caption=final_caption,
            parse_mode="HTML"
        )
        
        update_poster_status(
            session=session,
            poster_id=poster_id,
            status=ModerationStatus.APPROVED.value,
            moderator_id=callback.from_user.id,
            channel_message_id=sent_message.message_id,
            channel_chat_id=target_channel_id
        )
    
    # Notify moderator (in Russian)
    await callback.message.edit_text(
        "✅ <b>Опубликовано успешно!</b>\n\n"
        f"Афиша #{poster_id} теперь в канале.",
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
    
    language = i18n.get_user_language(callback.from_user.language_code)
    
    await state.set_state(ModeratorEdit.waiting_for_description)
    
    await callback.message.edit_text(
        "✏️ <b>Редактировать финальное описание</b>\n\n"
        "Отправьте финальный текст для этой публикации.",
        parse_mode="HTML"
    )
    await callback.answer()


@moderator_edit_router.callback_query(ModeratorEdit.waiting_for_confirmation, F.data.startswith("moderator:cancel:"))
async def final_cancel(callback: types.CallbackQuery, state: FSMContext):
    """Cancel final publishing - return to pending"""
    
    language = i18n.get_user_language(callback.from_user.language_code)
    poster_id = int(callback.data.split(":")[2])
    data = await state.get_data()
    moderator_id = callback.from_user.id
    
    with get_session() as session:
        # Get poster info
        poster = get_poster(session, poster_id)
        
        # ✅ Reset to PENDING
        update_poster_status(
            session=session,
            poster_id=poster_id,
            status=ModerationStatus.PENDING.value
        )
        
        # ✅ Re-send poster to moderation chat with original keyboard
        try:
            from bot.keyboards import moderation_keyboard
            from utils.helpers import format_moderation_caption
            
            mod_caption = format_moderation_caption({
                "caption": poster.caption,
                "user_id": poster.user_id,
                "is_anonymous": poster.is_anonymous,
                "event_date": poster.event_date.isoformat() if poster.event_date else None
            }, poster.id)
            
            keyboard = moderation_keyboard(
                user_id=poster.user_id,
                is_anonymous=poster.is_anonymous,
                poster_id=poster.id,
                language=language
            ).as_markup()
            
            # Send new message to moderation chat
            await callback.bot.send_photo(
                chat_id=config.moderation_chat_id,
                photo=poster.photo_file_id,
                caption=(
                    f"{mod_caption}\n\n"
                    f"⬅️ <i>Возвращено в очередь после отмены финализации</i>\n"
                    f"👤 Предыдущий модератор: @{callback.from_user.username or 'no_username'}"
                ),
                parse_mode="HTML",
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Could not re-send poster to moderation chat: {e}")
    
    # ✅ Notify moderator in DM
    await callback.message.edit_text(
        f"{t('common.operation_cancelled', language)}\n\n"
        f"Афиша #{poster_id} возвращена в очередь модерации.",
        parse_mode="HTML"
    )
    
    await state.clear()
    await callback.answer()
    logger.info(f"Poster {poster_id} cancelled by moderator {moderator_id} - returned to queue")

# =============================================================================
# ============ ADMIN COMMANDS (Optional) ======================================
# =============================================================================

@moderation_router.message(Command("pending"), F.from_user.id.in_(config.admin_ids))
async def cmd_pending(message: types.Message):
    """Show pending posters count"""
    
    language = i18n.get_user_language(message.from_user.language_code)  # ← ADDED
    
    with get_session() as session:
        count = get_pending_posters_count(session)
    
    await message.answer(
        f"{t('moderation.pending.title', language)} {t('moderation.pending.count', language, count=count)}",
        parse_mode="HTML"
    )


@moderation_router.message(Command("mystats"), F.from_user.id.in_(config.admin_ids))
async def cmd_moderator_stats(message: types.Message):
    """Show moderator's personal statistics"""
    
    language = i18n.get_user_language(message.from_user.language_code)  # ← ADDED
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