"""
Middleware to check privacy policy acceptance
"""
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, Update
from db.models import get_session, User
from utils.i18n import i18n, t
from utils.privacy import user_needs_to_accept_privacy, get_current_privacy_version
from bot.keyboards import privacy_acceptance_keyboard
from config import config
import logging
from typing import Callable, Dict, Any

logger = logging.getLogger(__name__)


class PrivacyPolicyMiddleware(BaseMiddleware):
    """Middleware to check if user accepted privacy policy"""

    async def __call__(
        self,
        handler: Callable,
        event: Message | CallbackQuery | Update,
        data: Dict[str, Any]
    ) -> Any:
        # Extract real event from Update if needed
        real_event = event
        if isinstance(event, Update):
            if event.message:
                real_event = event.message
            elif event.callback_query:
                real_event = event.callback_query
            else:
                # No message or callback_query, skip
                return await handler(event, data)

        # Skip for moderators/admins - they don't need privacy acceptance
        if real_event.from_user.id in config.admin_ids:
            return await handler(event, data)

        # Skip for callback queries related to privacy policy
        if isinstance(real_event, CallbackQuery):
            if real_event.data and real_event.data.startswith("privacy:"):
                return await handler(event, data)
            if real_event.data and real_event.data.startswith("lang:"):
                return await handler(event, data)
            if real_event.data and real_event.data.startswith("delete:"):
                return await handler(event, data)

        # Skip for /start command (it handles privacy policy display)
        if isinstance(real_event, Message) and real_event.text:
            if real_event.text.startswith("/start"):
                return await handler(event, data)

        # Get user from database
        user_id = real_event.from_user.id

        with get_session() as session:
            user = session.query(User).filter(User.telegram_id == user_id).first()

            # If user doesn't exist or needs to accept privacy policy
            if not user or user_needs_to_accept_privacy(user):
                language = i18n.get_user_language(
                    getattr(real_event.from_user, 'language_code', None),
                    user_id
                )

                # Show privacy policy acceptance message
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

                if isinstance(real_event, Message):
                    await real_event.answer(
                        privacy_text,
                        parse_mode="HTML",
                        reply_markup=privacy_acceptance_keyboard(language).as_markup()
                    )
                elif isinstance(real_event, CallbackQuery):
                    await real_event.message.answer(
                        privacy_text,
                        parse_mode="HTML",
                        reply_markup=privacy_acceptance_keyboard(language).as_markup()
                    )
                    await real_event.answer()

                return  # Block the handler

        # User accepted privacy policy - proceed
        return await handler(event, data)
