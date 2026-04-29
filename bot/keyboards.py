# bot/keyboards.py
"""
All inline keyboards for Гиги Архив bot.
Separated into User and Moderator sections for clarity.
"""

from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from datetime import datetime, timedelta
from utils.i18n import i18n, t

# =============================================================================
# ============ USER KEYBOARDS (Poster Submission Flow) ========================
# =============================================================================

def cancel_keyboard(language: str = "ru") -> InlineKeyboardBuilder:
    """Cancel submission keyboard (shown at every step)"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=t("common.cancel", language), callback_data="poster:cancel")
    )
    return builder


def retry_keyboard(language: str = "ru") -> InlineKeyboardBuilder:
    """Keyboard shown after validation error"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=t("poster_flow.retry.button", language), callback_data="poster:retry_photo")
    )
    return builder


def start_over_keyboard(language: str = "ru") -> InlineKeyboardBuilder:
    """Keyboard shown after cancellation (if photo was sent)"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=t("poster_flow.start_over.button", language), callback_data="poster:start_over")
    )
    return builder


def anonymous_choice_keyboard(language: str = "ru") -> InlineKeyboardBuilder:
    """Choose anonymous or public posting"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=t("poster_flow.anonymous.show_name", language), callback_data="anon:no"),
        InlineKeyboardButton(text=t("poster_flow.anonymous.anonymous", language), callback_data="anon:yes")
    )
    builder.row(
        InlineKeyboardButton(text=t("common.back", language), callback_data="poster:back_to_photo")
    )
    return builder


def date_picker_keyboard(language: str = "ru") -> InlineKeyboardBuilder:
    """Simple date picker with next 14 days (3 buttons per row for bigger size)"""
    builder = InlineKeyboardBuilder()
    
    today = datetime.now().date()
    
    row_buttons = []
    for i in range(14):
        date = today + timedelta(days=i)
        
        # ✅ Use localized day name
        day_name = i18n.get_day_name(date, language)
        day_num = date.strftime("%d.%m")  # Keep numeric date format
        
        row_buttons.append(
            InlineKeyboardButton(
                text=f"{day_name}\n{day_num}", 
                callback_data=f"date:{date.isoformat()}"
            )
        )
        
        if len(row_buttons) == 3:
            builder.row(*row_buttons)
            row_buttons = []
    
    if row_buttons:
        builder.row(*row_buttons)
    
    builder.row(
        InlineKeyboardButton(text=t("common.back", language), callback_data="poster:back_to_anon")
    )
    
    return builder


def confirmation_keyboard(language: str = "ru") -> InlineKeyboardBuilder:
    """Final confirmation before submission"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=t("poster_flow.confirmation.publish", language), callback_data="poster:confirm"),
        InlineKeyboardButton(text=t("poster_flow.confirmation.edit", language), callback_data="poster:edit")
    )
    builder.row(
        InlineKeyboardButton(text=t("common.cancel", language), callback_data="poster:cancel")
    )
    return builder


def language_selection_keyboard(language: str) -> InlineKeyboardBuilder:
    """Language selection keyboard (shown after /start on first start)"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
        InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en")
    )
    return builder


def privacy_policy_keyboard(language: str):
    """Main keyboard for /start command (returning users)"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=f"{i18n.t('common.privacy_policy', language)}", callback_data="privacy:show")
    )
    return builder


def privacy_acceptance_keyboard(language: str):
    """Keyboard for users who haven't accepted privacy policy"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=f"{i18n.t('common.privacy_accept', language)}", callback_data="privacy:accept")
    )
    return builder

# =============================================================================
# ============ MODERATOR KEYBOARDS (Moderation Flow) ==========================
# =============================================================================

def moderation_keyboard(user_id: int, is_anonymous: bool, poster_id: int, language: str = "ru") -> InlineKeyboardBuilder:
    """Keyboard for moderators (approve/decline)"""
    builder = InlineKeyboardBuilder()
    anon_flag = "1" if is_anonymous else "0"
    
    builder.row(
        InlineKeyboardButton(
            text=t("keyboards.moderation.approve", language),
            callback_data=f"approve:{user_id}:{anon_flag}:{poster_id}"
        ),
        InlineKeyboardButton(
            text=t("keyboards.moderation.decline", language),
            callback_data=f"decline:{user_id}:{anon_flag}:{poster_id}"
        )
    )
    

    builder.row(
        InlineKeyboardButton(
            text=t("keyboards.moderation.view_user", language),
            callback_data=f"userinfo:{user_id}"
        )
    )
    
    return builder


def decline_reason_keyboard(user_id: int, anon_flag: str, poster_id: int, language: str = "ru") -> InlineKeyboardBuilder:
    """Keyboard for selecting decline reason"""
    builder = InlineKeyboardBuilder()
    
    reasons = [
        (t("keyboards.decline_reasons.low_quality", language), "low_quality"),
        (t("keyboards.decline_reasons.missing_details", language), "missing_details"),
        (t("keyboards.decline_reasons.inappropriate", language), "inappropriate"),
        (t("keyboards.decline_reasons.wrong_date", language), "wrong_date"),
        (t("keyboards.decline_reasons.duplicate", language), "duplicate"),
        (t("keyboards.decline_reasons.custom", language), "custom")
    ]
    
    for text, reason_code in reasons:
        builder.row(
            InlineKeyboardButton(
                text=text,
                callback_data=f"decline_reason:{reason_code}:{user_id}:{anon_flag}:{poster_id}"
            )
        )
    
    builder.row(
        InlineKeyboardButton(
            text=t("common.cancel", language), 
            callback_data=f"moderation:cancel_decline:{user_id}:{anon_flag}:{poster_id}"
        )
    )
    
    return builder


def moderator_skip_keyboard(language: str = "ru") -> InlineKeyboardBuilder:
    """Keyboard for moderator to skip description editing"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=t("keyboards.moderator.skip", language),
            callback_data="moderator:skip_description"
        )
    )
    return builder


def moderator_confirmation_keyboard(poster_id: int, language: str = "ru") -> InlineKeyboardBuilder:
    """Keyboard for moderator final confirmation in DM"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=t("keyboards.moderator.publish", language),
            callback_data=f"moderator:confirm:{poster_id}"
        ),
        InlineKeyboardButton(
            text=t("keyboards.moderator.edit_again", language),
            callback_data=f"moderator:edit:{poster_id}"
        )
    )
    builder.row(
        InlineKeyboardButton(text=t("common.cancel", language), callback_data=f"moderator:cancel:{poster_id}")
    )
    return builder
