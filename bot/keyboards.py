
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from datetime import datetime, timedelta



def decline_reason_keyboard(user_id: int, anon_flag: str, poster_id: int) -> InlineKeyboardBuilder:
    """Keyboard for selecting decline reason"""
    builder = InlineKeyboardBuilder()
    
    # Predefined reasons
    reasons = [
        ("📷 Low image quality", "low_quality"),
        ("📝 Missing event details", "missing_details"),
        ("🚫 Inappropriate content", "inappropriate"),
        ("📅 Wrong date/past event", "wrong_date"),
        ("🔄 Duplicate submission", "duplicate"),
        ("⚠️ Other (custom)", "custom")
    ]
    
    for text, reason_code in reasons:
        # Format: decline_reason:reason_code:user_id:anon_flag:poster_id
        builder.row(
            InlineKeyboardButton(
                text=text,
                callback_data=f"decline_reason:{reason_code}:{user_id}:{anon_flag}:{poster_id}"
            )
        )
    
    # Cancel button
    builder.row(
        InlineKeyboardButton(text="❌ Cancel", 
                             callback_data=f"moderation:cancel_decline:{user_id}:{anon_flag}:{poster_id}")
    )
    
    return builder


def moderation_keyboard(user_id: int, is_anonymous: bool, poster_id: int) -> InlineKeyboardBuilder:
    """Keyboard for moderators (approve/decline)"""
    builder = InlineKeyboardBuilder()
    anon_flag = "1" if is_anonymous else "0"
    
    builder.row(
        InlineKeyboardButton(
            text="✅ Approve",
            callback_data=f"approve:{user_id}:{anon_flag}:{poster_id}"
        ),
        InlineKeyboardButton(
            text="❌ Decline",
            callback_data=f"decline:{user_id}:{anon_flag}:{poster_id}"
        )
    )
    
    # Optional: View user info (only if not anonymous)
    if not is_anonymous:
        builder.row(
            InlineKeyboardButton(
                text="👤 View User",
                callback_data=f"userinfo:{user_id}"
            )
        )
    
    return builder

def date_picker_keyboard() -> InlineKeyboardBuilder:
    """Simple date picker with next 14 days (3 buttons per row for bigger size)"""
    builder = InlineKeyboardBuilder()
    
    today = datetime.now().date()
    
    # Add next 14 days as buttons (3 per row = bigger buttons)
    row_buttons = []
    for i in range(14):
        date = today + timedelta(days=i)
        day_name = date.strftime("%a")  # Mon, Tue, Wed...
        day_num = date.strftime("%d.%m")  # 15.03, 16.03...
        
        row_buttons.append(
            InlineKeyboardButton(
                text=f"{day_name}\n{day_num}", 
                callback_data=f"date:{date.isoformat()}"
            )
        )
        
        # Add row every 3 buttons 
        if len(row_buttons) == 3:
            builder.row(*row_buttons)
            row_buttons = []
    
    # Add remaining buttons
    if row_buttons:
        builder.row(*row_buttons)
    
    # Add back button
    builder.row(
        InlineKeyboardButton(text="⬅️ Back", callback_data="poster:back_to_anon")
    )
    
    return builder

def anonymous_choice_keyboard() -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="👤 Show my name", callback_data="anon:no"),
        InlineKeyboardButton(text="🔒 Post anonymously", callback_data="anon:yes")
    )
    builder.row(
        InlineKeyboardButton(text="⬅️ Back", callback_data="poster:back_to_photo")
    )
    return builder

def confirmation_keyboard() -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Publish", callback_data="poster:confirm"),
        InlineKeyboardButton(text="✏️ Edit", callback_data="poster:edit")
    )
    builder.row(
        InlineKeyboardButton(text="❌ Cancel", callback_data="poster:cancel")
    )
    return builder

def cancel_keyboard() -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="❌ Cancel submission", callback_data="poster:cancel")
    )
    return builder


def retry_keyboard() -> InlineKeyboardBuilder:
    """Keyboard shown after validation error"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔄 Try Again", callback_data="poster:retry_photo")
    )
    return builder