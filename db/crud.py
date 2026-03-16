# db/crud.py
"""
Database CRUD operations.
"""

from sqlalchemy.orm import Session
from datetime import datetime
from db.models import User, Poster, ModerationStatus
from typing import Optional, List

# ============ USER OPERATIONS ============

def get_or_create_user(session: Session, telegram_id: int, **kwargs) -> User:
    """Get existing user or create new one"""
    user = session.query(User).filter(User.telegram_id == telegram_id).first()
    
    if not user:
        user = User(
            telegram_id=telegram_id,
            username=kwargs.get("username"),
            first_name=kwargs.get("first_name", "Unknown"),
            last_name=kwargs.get("last_name"),
            language_code=kwargs.get("language_code"),
            is_premium=kwargs.get("is_premium", False)
        )
        session.add(user)
        session.commit()
        session.refresh(user)
    
    return user

def get_user(session: Session, telegram_id: int) -> Optional[User]:
    """Get user by Telegram ID"""
    return session.query(User).filter(User.telegram_id == telegram_id).first()

def get_user_stats(session: Session, telegram_id: int) -> dict:
    """Get user's poster statistics"""
    posters = session.query(Poster).filter(Poster.user_id == telegram_id).all()
    
    return {
        "total": len(posters),
        "approved": sum(1 for p in posters if p.status == ModerationStatus.APPROVED),
        "declined": sum(1 for p in posters if p.status == ModerationStatus.DECLINED),
        "pending": sum(1 for p in posters if p.status == ModerationStatus.PENDING)
    }

# ============ POSTER OPERATIONS ============

def create_poster(
    session: Session,
    user_id: int,
    photo_file_id: str,
    caption: str,
    event_date: datetime,
    is_anonymous: bool
) -> Poster:
    """Create new poster submission"""
    poster = Poster(
        user_id=user_id,
        photo_file_id=photo_file_id,
        caption=caption,
        event_date=event_date,
        is_anonymous=is_anonymous,
        status=ModerationStatus.PENDING
    )
    session.add(poster)
    session.commit()
    session.refresh(poster)
    return poster

def get_poster(session: Session, poster_id: int) -> Optional[Poster]:
    """Get poster by ID"""
    return session.query(Poster).filter(Poster.id == poster_id).first()

def update_poster_status(
    session: Session,
    poster_id: int,
    status: str,
    moderator_id: int = None,
    channel_message_id: int = None,
    channel_chat_id: int = None
) -> Optional[Poster]:
    """Update poster moderation status"""
    poster = session.query(Poster).filter(Poster.id == poster_id).first()
    
    if poster:
        poster.status = ModerationStatus(status)
        poster.moderated_by = moderator_id
        poster.moderated_at = datetime.now()
        poster.channel_message_id = channel_message_id
        poster.channel_chat_id = channel_chat_id
        session.commit()
        session.refresh(poster)
    
    return poster

def get_pending_posters(session: Session) -> List[Poster]:
    """Get all pending posters for moderation"""
    return session.query(Poster).filter(
        Poster.status == ModerationStatus.PENDING
    ).order_by(Poster.created_at.asc()).all()

def get_posters_by_week(
    session: Session,
    start_date: datetime,
    end_date: datetime,
    status: ModerationStatus = ModerationStatus.APPROVED
) -> List[Poster]:
    """Get posters approved within date range (for weekly summary)"""
    return session.query(Poster).filter(
        Poster.status == status,
        Poster.moderated_at >= start_date,
        Poster.moderated_at <= end_date
    ).order_by(Poster.event_date.asc()).all()

def update_poster_status(
    session: Session,
    poster_id: int,
    status: str,
    moderator_id: int = None,
    channel_message_id: int = None,
    channel_chat_id: int = None,
    decline_reason: str = None  # ← ADD THIS
) -> Optional[Poster]:
    """Update poster moderation status"""
    poster = session.query(Poster).filter(Poster.id == poster_id).first()
    
    if poster:
        poster.status = ModerationStatus(status)
        poster.moderated_by = moderator_id
        poster.moderated_at = datetime.now()
        poster.channel_message_id = channel_message_id
        poster.channel_chat_id = channel_chat_id
        if decline_reason:
            poster.decline_reason = decline_reason  # ← ADD THIS
        session.commit()
        session.refresh(poster)
    
    return poster