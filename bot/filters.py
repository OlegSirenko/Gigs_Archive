"""
Filters for checking user privacy policy acceptance
"""
from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery
from db.models import get_session, User


class PrivacyAcceptedFilter(BaseFilter):
    """Check if user has accepted privacy policy"""

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        """Return True if user accepted privacy policy"""
        user_id = event.from_user.id

        with get_session() as session:
            user = session.query(User).filter(User.telegram_id == user_id).first()

            # If user doesn't exist, they haven't accepted
            if not user:
                return False

            return user.privacy_accepted is True


class PrivacyNotAcceptedFilter(BaseFilter):
    """Check if user has NOT accepted privacy policy"""

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        """Return True if user has NOT accepted privacy policy"""
        user_id = event.from_user.id

        with get_session() as session:
            user = session.query(User).filter(User.telegram_id == user_id).first()

            # If user doesn't exist, they haven't accepted
            if not user:
                return True

            return user.privacy_accepted is not True
