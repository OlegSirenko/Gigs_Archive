"""
Web-layer database models & session factory.

Reuses the existing SQLAlchemy Base (db.models) so that `init_db()` creates
BOTH the bot tables (users, posters) and the new web tables (articles) in the
SAME SQLite file the bot already uses. No data duplication — the site reads
approved posters straight from the bot's DB.

NOTE: we do NOT import db.models (it pulls in the bot's pydantic config which
requires BOT_TOKEN etc.). Instead we re-declare the two shared tables here with
identical schema. The ORM only needs to know the columns it queries.
"""

import enum
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import (declarative_base, lazyload, relationship,
                            sessionmaker)
from sqlalchemy.sql import func

from web.config import settings

Base = declarative_base()


# ============ SHARED (BOT) TABLES — read-only mapping ============

class ModerationStatus(enum.Enum):
    PENDING = "pending"
    PENDING_FINAL = "pending_final"
    APPROVED = "approved"
    DECLINED = "declined"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String, nullable=True, index=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=True)
    language_code = Column(String, nullable=True)
    is_premium = Column(Boolean, default=False)
    privacy_accepted = Column(Boolean, default=False)
    privacy_version_accepted = Column(String, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    subscribe_weekly = Column(Boolean, default=False)

    def __repr__(self):
        return f"<User {self.telegram_id} @{self.username}>"


class Poster(Base):
    __tablename__ = "posters"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.telegram_id"), nullable=False, index=True)

    photo_file_id = Column(String, nullable=False)
    photos_json = Column(Text, nullable=True)
    caption = Column(Text, nullable=True)
    event_date = Column(DateTime, nullable=True, index=True)
    is_anonymous = Column(Boolean, default=False, index=True)

    status = Column(Enum(ModerationStatus), default=ModerationStatus.PENDING, index=True)
    moderated_by = Column(Integer, nullable=True, index=True)
    moderated_at = Column(DateTime, nullable=True, index=True)
    decline_reason = Column(String, nullable=True)
    moderator_notes = Column(Text, nullable=True)

    moderation_message_id = Column(Integer, nullable=True)
    moderation_chat_id = Column(Integer, nullable=True)

    channel_message_id = Column(Integer, nullable=True)
    channel_chat_id = Column(Integer, nullable=True, index=True)

    view_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now(), index=True)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # lazy="raise_on_sql": templates must never trigger hidden queries;
    # routes that need the poster author load it explicitly with .options(lazyload(...))
    user = relationship("User", foreign_keys=[user_id], lazy="raise_on_sql")

    __table_args__ = (
        Index('ix_posters_status_moderated_at', 'status', 'moderated_at'),
        Index('ix_posters_user_id_status', 'user_id', 'status'),
        Index('ix_posters_event_date_status', 'event_date', 'status'),
    )

    def __repr__(self):
        return f"<Poster {self.id} by User {self.user_id}>"


# ============ NEW WEB TABLE: Articles (admin interviews / reviews) ============

class Article(Base):
    """Long-form admin content: musician interviews, event reviews, criticism."""

    __tablename__ = "web_articles"

    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    slug = Column(String(220), nullable=False, unique=True, index=True)
    lead = Column(Text, nullable=True)          # short intro shown in lists
    body = Column(Text, nullable=False)         # the "big text" (markdown-ish plain text)
    cover_image_url = Column(String, nullable=True)

    kind = Column(String(30), default="article")  # article | interview | review
    author_username = Column(String, nullable=True)  # admin who wrote it
    poster_id = Column(Integer, ForeignKey("posters.id"), nullable=True)  # link to event

    is_published = Column(Boolean, default=False, index=True)
    published_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    poster = relationship("Poster", foreign_keys=[poster_id], lazy="raise_on_sql")

    __table_args__ = (
        Index('ix_web_articles_pub_kind', 'is_published', 'kind'),
    )

    def __repr__(self):
        return f"<Article {self.id} '{self.title}'>"


# ============ Engine / session (same SQLite file as the bot) ============

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False,
                            expire_on_commit=False)


def init_web_db():
    """Create web tables (+ bot tables if DB is empty) in the shared SQLite file."""
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_session():
    """Yield a session; detaches all loaded objects at exit so templates can
    still read their plain attributes afterwards (no lazy DB access)."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.expunge_all()
        session.close()
