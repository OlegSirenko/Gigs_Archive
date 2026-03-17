"""
Moderator handlers for approval workflow and DM finalization.
Separated from user handlers for clarity.
"""

import re
import asyncio
import logging
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from bot.moderator_states import ModeratorEdit  
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from bot.keyboards import (
    moderation_keyboard,
    decline_reason_keyboard,
    moderator_skip_keyboard,
    moderator_confirmation_keyboard
)
from db.models import get_session, Poster
from db.crud import get_poster, update_poster_status, ModerationStatus, get_pending_posters_count
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
async def handle_moderation_decision(callback: types.CallbackQuery):  # No FSMContext!
    """Process moderator approve/decline decision"""
    
    if callback.from_user.id not in config.admin_ids:
        await callback.answer("❌ You're not authorized to moderate!", show_alert=True)
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
                await callback.answer("⚠️ Poster not found!", show_alert=True)
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
                skip_builder = InlineKeyboardBuilder()
                skip_builder.row(
                    InlineKeyboardButton(
                        text="⏭️ Skip - Use Original", 
                        callback_data=f"moderator:skip:{poster_id}"
                    )
                )
                
                await callback.bot.send_message(
                    chat_id=moderator_id,
                    text=(
                        "✏️ <b>Create Final Description</b>\n\n"
                        f"Poster ID: <code>{poster_id}</code>\n"
                        f"User's link: <code>{poster.caption}</code>\n\n"
                        "Send the final description for this post.\n\n"
                        "Or click 'Skip' to use the original caption."
                    ),
                    parse_mode="HTML",
                    reply_markup=skip_builder.as_markup()
                )
                
                # Edit moderation message
                status_text = (
                    f"\n\n━━━━━━━━━━━━━━━━━━━━\n"
                    f"⏳ <b>PENDING FINAL</b>\n"
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
                
                await callback.answer("✅ Sent to your DM for finalization!", show_alert=False)
                
            elif action == "decline":
                # Show decline reason keyboard (stateless)
                if callback.message.photo:
                    await callback.message.edit_caption(
                        caption=callback.message.caption or "📝 Poster Submission",
                        reply_markup=decline_reason_keyboard(user_id, anon_flag, poster_id).as_markup()
                    )
                else:
                    await callback.message.edit_text(
                        text=callback.message.caption or "📝 Poster Submission",
                        reply_markup=decline_reason_keyboard(user_id, anon_flag, poster_id).as_markup()
                    )
                
                await callback.answer("Select a decline reason:")
            
            logger.info(f"Moderation {action} for poster {poster_id} by @{moderator_username}")
            
    except Exception as e:
        logger.error(f"Moderation error: {e}")
        await callback.answer("⚠️ Error processing decision.", show_alert=True)

@moderation_router.callback_query(F.data.regexp(r"^decline_reason:(\w+):(\d+):([01]):(\d+)$"))
async def handle_decline_reason(callback: types.CallbackQuery):
    """Handle decline reason selection"""
    
    # Check if moderator is admin
    if callback.from_user.id not in config.admin_ids:
        await callback.answer("❌ You're not authorized!", show_alert=True)
        return
    
    # Parse callback data: decline_reason:reason_code:user_id:anon_flag:poster_id
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
                status=ModerationStatus.DECLINED.value,
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
    
    # Parse callback data: moderation:cancel_decline:user_id:anon_flag:poster_id
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
            keyboard = moderation_keyboard(
                user_id=poster.user_id,
                is_anonymous=poster.is_anonymous,
                poster_id=poster.id
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
        
        await callback.answer("✅ Decline cancelled. Original options restored.")
        logger.info(f"Decline cancelled for poster {poster_id}")
        
    except Exception as e:
        logger.error(f"Cancel decline error: {e}")
        await callback.answer("⚠️ Error cancelling decline.", show_alert=True)


# bot/moderator_handlers.py - Add this after cancel_decline handler

@moderation_router.callback_query(F.data.regexp(r"^userinfo:(\d+)$"))
async def handle_userinfo(callback: types.CallbackQuery):
    """Show information about the user who submitted the poster"""
    
    # Check if moderator is admin
    if callback.from_user.id not in config.admin_ids:
        await callback.answer("❌ You're not authorized!", show_alert=True)
        return
    
    # Parse callback data: userinfo:user_id
    user_id = int(callback.data.split(":")[1])
    
    try:
        with get_session() as session:
            # Get user from database
            from db.crud import get_user_stats
            from db.models import User
            
            user = session.query(User).filter(User.telegram_id == user_id).first()
            
            if not user:
                await callback.answer("⚠️ User not found!", show_alert=True)
                return
            
            # Get user's poster statistics
            stats = get_user_stats(session, user_id)
            
            # Build user info text (in Russian)
            userinfo_text = (
                f"👤 <b>Информация о пользователе</b>\n\n"
                f"<b>ID:</b> <code>{user.telegram_id}</code>\n"
                f"<b>Имя:</b> {user.first_name}"
            )
            
            if user.last_name:
                userinfo_text += f" {user.last_name}"
            
            if user.username:
                userinfo_text += f"\n<b>Username:</b> @{user.username}"
            else:
                userinfo_text += "\n<b>Username:</b> <i>не указан</i>"
            
            if user.language_code:
                userinfo_text += f"\n<b>Язык:</b> {user.language_code.upper()}"
            
            if user.is_premium:
                userinfo_text += "\n<b>Telegram Premium:</b> ✅"
            
            userinfo_text += (
                f"\n\n📊 <b>Статистика публикаций:</b>\n"
                f"Всего отправлено: <b>{stats['total']}</b>\n"
                f"✅ Одобрено: <b>{stats['approved']}</b>\n"
                f"❌ Отклонено: <b>{stats['declined']}</b>\n"
                f"⏳ В ожидании: <b>{stats['pending']}</b>\n\n"
                f"<i>Зарегистрирован:</i> {user.created_at.strftime('%d.%m.%Y %H:%M') if user.created_at else 'Н/Д'}"
            )
            
            # Build keyboard with actions
            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(text="📨 Написать пользователю", url=f"tg://user?id={user_id}")
            )
            builder.row(
                InlineKeyboardButton(text="❌ Закрыть", callback_data="userinfo:close")
            )
            
            # Send as new message (or edit existing)
            await callback.message.answer(
                userinfo_text,
                parse_mode="HTML",
                reply_markup=builder.as_markup()
            )
            
            await callback.answer()
            logger.info(f"User info requested for {user_id} by moderator {callback.from_user.id}")
            
    except Exception as e:
        logger.error(f"User info error: {e}")
        await callback.answer("⚠️ Error getting user info.", show_alert=True)


@moderation_router.callback_query(F.data == "userinfo:close")
async def close_userinfo(callback: types.CallbackQuery):
    """Close the user info message"""
    
    try:
        # Delete the user info message
        await callback.message.delete()
        await callback.answer()
    except:
        # If can't delete, just answer
        await callback.answer("ℹ️ Закройте сообщение вручную")


# =============================================================================
# ============ MODERATOR DM HANDLERS (Two-Stage Moderation) ===================
# =============================================================================

# bot/moderator_handlers.py

# ============ MODERATOR DM: SKIP BUTTON (First Response - SETS STATE) ============

@moderator_edit_router.callback_query(F.data.startswith("moderator:skip:"))
async def skip_description(callback: types.CallbackQuery, state: FSMContext):
    """Handle skip button - FIRST response in DM (sets FSM state)"""
    
    poster_id = int(callback.data.split(":")[2])
    
    with get_session() as session:
        poster = get_poster(session, poster_id)
        if not poster:
            await callback.answer("⚠️ Poster not found!", show_alert=True)
            return
        
        # ✅ SET FSM STATE HERE (in DM context!)
        await state.set_state(ModeratorEdit.waiting_for_confirmation)
        await state.update_data(
            poster_id=poster_id,
            user_id=poster.user_id,  # ← Store for later notification
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
        
        confirm_builder = InlineKeyboardBuilder()
        confirm_builder.row(
            InlineKeyboardButton(text="✅ Publish to Channel", callback_data=f"moderator:confirm:{poster_id}"),
            InlineKeyboardButton(text="✏️ Edit Anyway", callback_data=f"moderator:edit:{poster_id}")
        )
        confirm_builder.row(
            InlineKeyboardButton(text="❌ Cancel", callback_data=f"moderator:cancel:{poster_id}")
        )
        
        await callback.message.answer(
            "👁️ <b>Preview (Original Caption)</b>\n\n"
            f"{preview_caption}\n\n"
            "<i>Ready to publish?</i>",
            parse_mode="HTML",
            reply_markup=confirm_builder.as_markup()
        )
        await callback.answer()

# ============ MODERATOR DM: TEXT DESCRIPTION (First Response - SETS STATE) ============

@moderator_edit_router.message(F.text)
async def process_moderator_description(message: types.Message, state: FSMContext):
    """Handle moderator typing description - FIRST response in DM (sets FSM state)"""
    
    moderator_id = message.from_user.id
    
    with get_session() as session:
        from sqlalchemy import and_
        poster = session.query(Poster).filter(
            and_(
                Poster.status == ModerationStatus.PENDING_FINAL,
                Poster.moderated_by == moderator_id
            )
        ).order_by(Poster.moderated_at.desc()).first()
        
        if not poster:
            await message.answer(
                    "ℹ️ No poster waiting for finalization.\n"
                    "Approve one in the moderation chat first!"
                )
            return
        
        poster_id = poster.id
        
        # ✅ SET FSM STATE HERE (in DM context!)
        await state.set_state(ModeratorEdit.waiting_for_confirmation)
        await state.update_data(
            poster_id=poster_id,
            user_id=poster.user_id,  # ← Store for later notification
            is_anonymous=poster.is_anonymous,
            photo_file_id=poster.photo_file_id,
            final_caption=message.text,  # ← Moderator's new description
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
        
        confirm_builder = InlineKeyboardBuilder()
        confirm_builder.row(
            InlineKeyboardButton(text="✅ Publish to Channel", callback_data=f"moderator:confirm:{poster_id}"),
            InlineKeyboardButton(text="✏️ Edit Again", callback_data=f"moderator:edit:{poster_id}")
        )
        confirm_builder.row(
            InlineKeyboardButton(text="❌ Cancel", callback_data=f"moderator:cancel:{poster_id}")
        )
        
        await message.answer(
            "👁️ <b>Preview Before Publishing</b>\n\n"
            f"{preview_caption}\n\n"
            "<i>Review before it goes live!</i>",
            parse_mode="HTML",
            reply_markup=confirm_builder.as_markup()
        )

# ============ MODERATOR DM: CONFIRMATION (Uses FSM State + DB for Notification) ============

@moderator_edit_router.callback_query(ModeratorEdit.waiting_for_confirmation, F.data.startswith("moderator:confirm:"))
async def final_confirm(callback: types.CallbackQuery, state: FSMContext):
    """Final confirmation - publish to channel"""
    
    data = await state.get_data()
    poster_id = data.get("poster_id")
    user_id = data.get("user_id")  # ← From FSM (or fetch from DB)
    
    with get_session() as session:
        # ✅ Could also fetch from DB to be extra safe
        poster = get_poster(session, poster_id)
        user_id = poster.user_id  # ← Use DB as source of truth
        
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
            final_caption += "\n\n⚠️ <i>TEST MODE - Not a real post</i>"
        
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
    
    # Notify moderator
    await callback.message.edit_text(
        "✅ <b>Published Successfully!</b>\n\n"
        f"Poster #{poster_id} is now live in the channel.",
        parse_mode="HTML"
    )
    
    # ✅ Notify user (fetch from DB, not FSM)
    notify_text = (
        "🎉 <b>Your poster was approved!</b>\n\n"
        f"{'It was published anonymously.' if data.get('is_anonymous') else 'It was published with your name.'}\n"
        f"Check the channel!"
    )
    
    await callback.bot.send_message(
        chat_id=user_id,  # ← From DB
        text=notify_text,
        parse_mode="HTML"
    )
    
    await state.clear()  # ✅ Moderator DM FSM ends here
    logger.info(f"Poster {poster_id} finally published by moderator {callback.from_user.id}")


@moderator_edit_router.callback_query(ModeratorEdit.waiting_for_confirmation, F.data.startswith("moderator:edit:"))
async def edit_again(callback: types.CallbackQuery, state: FSMContext):
    """Let moderator edit description again"""
    await state.set_state(ModeratorEdit.waiting_for_description)
    
    await callback.message.edit_text(
        "✏️ <b>Edit Final Description</b>\n\n"
        "Send the final text for this post.",
        parse_mode="HTML"
    )
    await callback.answer()


@moderator_edit_router.callback_query(ModeratorEdit.waiting_for_confirmation, F.data.startswith("moderator:cancel:"))
async def final_cancel(callback: types.CallbackQuery, state: FSMContext):
    """Cancel final publishing - return to pending"""
    data = await state.get_data()
    poster_id = data.get("poster_id")
    
    with get_session() as session:
        update_poster_status(
            session=session,
            poster_id=poster_id,
            status=ModerationStatus.PENDING.value
        )
    
    await callback.message.edit_text(
        "❌ <b>Cancelled</b>\n\n"
        f"Poster #{poster_id} returned to moderation queue.",
        parse_mode="HTML"
    )
    
    await state.clear()  # ✅ Moderator DM FSM ends here
    await callback.answer()
    logger.info(f"Poster {poster_id} cancelled by moderator {callback.from_user.id}")


# =============================================================================
# ============ ADMIN COMMANDS (Optional) ======================================
# =============================================================================

@moderation_router.message(Command("pending"), F.from_user.id.in_(config.admin_ids))
async def cmd_pending(message: types.Message):
    """Show pending posters count"""
    with get_session() as session:
        count = get_pending_posters_count(session)
    
    await message.answer(
        f"⏳ <b>Pending posters:</b> <code>{count}</code>",
        parse_mode="HTML"
    )


@moderation_router.message(Command("mystats"), F.from_user.id.in_(config.admin_ids))
async def cmd_moderator_stats(message: types.Message):
    """Show moderator's personal statistics"""
    moderator_id = message.from_user.id
    
    with get_session() as session:
        from db.crud import get_moderator_stats
        stats = get_moderator_stats(session, moderator_id)
    
    await message.answer(
        "📊 <b>Your Moderation Stats</b>\n\n"
        f"Total reviewed: <b>{stats['total']}</b>\n"
        f"✅ Approved: <b>{stats['approved']}</b>\n"
        f"❌ Declined: <b>{stats['declined']}</b>\n"
        f"⏳ Pending Final: <b>{stats['pending_final']}</b>",
        parse_mode="HTML"
    )