"""
Privacy policy version checker
"""
from db.models import get_session, User
from config import config


def get_current_privacy_version() -> str:
    """Get current privacy policy version from config"""
    return config.privacy_policy_version


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


def update_user_privacy_acceptance(user: User, version: str = None):
    """Update user's privacy policy acceptance"""
    if version is None:
        version = get_current_privacy_version()
    
    user.privacy_accepted = True
    user.privacy_version_accepted = version
