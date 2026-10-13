"""
Middleware to check privacy policy acceptance
"""
import logging
from typing import Callable, Dict, Any

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, Update

from db.models import get_session, User
from utils.i18n import i18n
from utils.privacy import (
    user_needs_to_accept_privacy,
    get_current_privacy_version,
    build_privacy_text,
)
from bot.keyboards import privacy_acceptance_keyboard
from config import config

logger = logging.getLogger(__name__)

# Callback prefixes that must be allowed through even before the privacy
# policy is accepted (resolving the pending prompt, language choice, etc.)
ALLOWED_CALLBACK_PREFIXES = (
    "privacy:",   # accept / show / back - needed to resolve the prompt
    "lang:",      # language selection shown right after acceptance
    "delete:",    # account deletion must always remain reachable
    "cancel",     # allow aborting an in-progress flow
)


class PrivacyPolicyMiddleware(BaseMiddleware):
    """Middleware to check if user accepted privacy policy.

    Every non-admin user must accept the current privacy policy version
    before any bot functionality becomes available. The check happens on
    every update (messages *and* callback queries), so there is no way to
    "skip" the prompt: all entry points are either blocked by this
    middleware or explicitly handle the policy themselves (/start).
    """

    async def __call__(
        self,
        handler: Callable,
        event: Message | CallbackQuery | Update,
        data: Dict[str, Any]
    ) -> Any:
        try:
            return await self._process(handler, event, data)
        except Exception:
            # Never let a middleware crash silently open the gate:
            # log loudly and fail closed (block the action).
            logger.exception("Privacy middleware failed while processing update")
            return await self._fail_closed(event)

    async def _process(
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
                # No message or callback_query (edited_*, poll answers, etc.)
                # These events carry no user-facing action to gate; the next
                # real message/callback will be checked again.
                return await handler(event, data)

        if not getattr(real_event, "from_user", None):
            return await handler(event, data)

        # ⚠️ SKIP FOR ADMINS/MODS first - they need full access everywhere (including mod group)
        if real_event.from_user.id in config.admin_ids:
            return await handler(event, data)

        # ⚠️ Skip privacy check for forwarded messages.
        # We only want to enforce privacy policy when a user interacts directly
        # with the bot in DMs. Messages forwarded from external channels/groups
        # should pass through freely to be processed by the poster flow.
        if getattr(real_event, 'forward_from_chat', None):
            return await handler(event, data)

        # ⚠️ STRICT DM-ONLY POLICY FOR USERS.
        # Non-admin users can ONLY interact with the bot in Direct Messages.
        # All group/channel/forum updates are dropped silently (no crash, no error).
        chat_type = getattr(real_event.chat, 'type', None)
        if chat_type != 'private':
            return await handler(event, data)

        # Allow callbacks that are part of resolving the privacy prompt
        if isinstance(real_event, CallbackQuery):
            cb_data = real_event.data or ""
            if any(cb_data.startswith(p) for p in ALLOWED_CALLBACK_PREFIXES):
                return await handler(event, data)

        # Skip for /start command (it handles privacy policy display itself)
        if isinstance(real_event, Message) and real_event.text:
            if real_event.text.startswith("/start"):
                return await handler(event, data)

        user_id = real_event.from_user.id

        with get_session() as session:
            user = session.query(User).filter(User.telegram_id == user_id).first()

            needs_acceptance = user is None or user_needs_to_accept_privacy(user)

            # If user doesn't exist or needs to accept privacy policy -
            # block the handler and re-show the acceptance prompt.
            if needs_acceptance:
                language = i18n.get_user_language(
                    getattr(real_event.from_user, 'language_code', None),
                    user_id
                )

                privacy_text = build_privacy_text(language)

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
                    await real_event.answer(
                        i18n.t('common.privacy_required_alert', language)
                    )

                logger.info(
                    f"Blocked update for user {user_id}: "
                    f"privacy policy v{get_current_privacy_version()} not accepted"
                )
                return  # Block the handler

        # User accepted privacy policy - proceed
        return await handler(event, data)

    async def _fail_closed(self, event) -> Any:
        """If the DB/policy check itself fails, do NOT execute the handler."""
        try:
            real_event = event
            if isinstance(event, Update):
                real_event = event.message or event.callback_query or event
            if isinstance(real_event, CallbackQuery):
                await real_event.answer("⚠️ Temporarily unavailable, please try again.")
            elif isinstance(real_event, Message):
                await real_event.answer("⚠️ Temporarily unavailable, please try again later.")
        except Exception:
            logger.exception("Failed to notify user about privacy middleware error")
        return None
