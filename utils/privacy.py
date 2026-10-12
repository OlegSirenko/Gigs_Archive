"""
Privacy policy version checker
"""
import logging

from db.models import get_session, User
from config import config

logger = logging.getLogger(__name__)


def get_current_privacy_version() -> str:
    """Get current privacy policy version from config.

    Falls back to "1.0" if the value is missing/empty in the environment,
    so that users are never prompted for (and never silently accepted into)
    a policy with an undefined version.
    """
    version = (config.privacy_policy_version or "").strip()
    if not version:
        logger.warning("PRIVACY_POLICY_VERSION is empty; falling back to '1.0'")
        return "1.0"
    return version


def user_needs_to_accept_privacy(user: User) -> bool:
    """
    Check if user needs to accept privacy policy.
    
    Returns True if:
    - User hasn't accepted privacy policy at all
    - User accepted old version and new version is available
    """
    if not user.privacy_accepted:
        return True
    
    # Check version
    current_version = get_current_privacy_version()
    accepted_version = user.privacy_version_accepted
    
    # If user accepted old version, they need to accept new one
    if accepted_version != current_version:
        return True
    
    return False


def update_user_privacy_acceptance(user: User, version: str = None) -> bool:
    """Update user's privacy policy acceptance.

    Returns True on success, False if the user object is missing.
    NOTE: the caller is responsible for committing the session.
    """
    if user is None:
        logger.error("Cannot update privacy: user is None")
        return False

    if version is None:
        version = get_current_privacy_version()

    user.privacy_accepted = True
    user.privacy_version_accepted = version
    return True


def build_privacy_text(language: str) -> str:
    """Build the full privacy policy text (single source of truth).

    Used by the /start handler, the middleware and the privacy:show handler
    so the displayed policy can never drift out of sync between them.
    """
    from utils.i18n import i18n

    version = get_current_privacy_version()
    return (
        f"{i18n.t('common.privacy_policy', language)} ({version})\n\n"
        f"{i18n.t('common.privacy_policy_text.collect', language)}"
        f"{i18n.t('common.privacy_policy_text.use', language)}"
        f"{i18n.t('common.privacy_policy_text.storage', language)}"
        f"{i18n.t('common.privacy_policy_text.rights', language)}"
        f"{i18n.t('common.privacy_policy_text.mailing', language)}"
        f"{i18n.t('common.privacy_policy_text.questions', language)}"
        f"{i18n.t('common.privacy_policy_text.acception', language)}"
    )
