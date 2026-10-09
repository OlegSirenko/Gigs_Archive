"""
Web-layer database models & session factories.

Three separate SQLite files, three engines/sessions:

  1. gigs_archive.db  (BOT database, READ-ONLY for the web app)
     tables: users, posters. Written by the Telegram bot only; the site just
     reads it (moderation status, author names, telegram file ids).

  2. articles.db      (WEB database) table: web_articles. See web/articles_db.py.

  3. posters_web.db   (WEB database, WRITABLE by the web app only)
     table: web_posters — the lightweight mirror of the events that are shown
     on the site. Deliberately minimal columns:
        id            poster index (same value as posters.id in the bot DB)
        caption       poster text
        event_date    date of the event
        is_cancelled  boolean, default False
     The bot never touches this file; the admin panel marks events cancelled
     here, and the watermark renderer reads it from here.

NOTE: we do NOT import db.models (it pulls in the bot's pydantic config which
requires BOT_TOKEN etc.). Instead we re-declare the needed tables here.
The ORM only needs to know the columns it queries.
"""

import enum
from contextlib import contextmanager

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


# ============ WEB-ONLY TABLES — posters_web.db (writable by the site) ============


class WebPoster(Base):
    """Lightweight copy of an approved event, stored in the WEB database.

    Only the columns the site actually needs. `is_cancelled` is the single
    piece of state the admin panel can toggle for an event; everything else
    about the event itself still comes from the bot's read-only DB.
    """

    __tablename__ = "web_posters"

    # Poster index — deliberately the SAME id as posters.id in the bot DB so
    # links (/posters/<id>, /api/poster-image/<id>) keep working unchanged.
    id = Column(Integer, primary_key=True, autoincrement=False)
    photo_file_id = Column(String, nullable=True)         # telegram file id
    channel_chat_id = Column(Integer, nullable=True)      # where the photo is
    channel_message_id = Column(Integer, nullable=True)
    caption = Column(Text, nullable=True)                 # poster text
    event_date = Column(DateTime, nullable=True, index=True)  # date of event
    is_cancelled = Column(Boolean, nullable=False, default=False, index=True)
    cancelled_at = Column(DateTime, nullable=True)        # when it was marked

    # --- convenience attributes for the watermark renderer & templates ---

    @property
    def image_url(self) -> str | None:
        """URL of the poster picture. Cancelled events get the pre-rendered
        watermarked static file when it already exists, otherwise the normal
        Telegram proxy URL (which stamps the watermark on the fly)."""
        if self.is_cancelled:
            try:
                from web.cancelled_images import cancelled_image_url
                url = cancelled_image_url(self)
                if url:
                    return url
            except Exception:
                pass
        if self.photo_file_id:
            return f"/api/poster-image/{self.id}"
        return None

    # Templates read `is_cancelled` as a plain attribute; keep an explicit
    # boolean property so Jinja never sees an int from raw SQL rows.
    @property
    def cancelled(self) -> bool:
        return bool(self.is_cancelled)

    def __repr__(self):
        return f"<WebPoster {self.id} cancelled={self.is_cancelled}>"


# ============ Engine / session (bot's shared SQLite file) ============

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False,
                            expire_on_commit=False)


# ---- Engine / session for the WEB posters database (posters_web.db) ----

web_engine = create_engine(
    settings.web_database_url,
    connect_args={"check_same_thread": False},
)
WebSessionLocal = sessionmaker(bind=web_engine, autocommit=False,
                               autoflush=False, expire_on_commit=False)


def init_web_db():
    """Create the bot tables (users, posters) in the bot's SQLite file if they
    are missing, and the web tables (web_posters) in posters_web.db.
    create_all() is idempotent: existing tables/rows are left untouched.
    Articles live in their own DB — see web/articles_db.init_articles_db()."""
    Base.metadata.create_all(bind=engine)
    WebPoster.__table__.create(bind=web_engine)


@contextmanager
def get_web_session():
    """Session for the WEB database (posters_web.db) — writable by the site."""
    session = WebSessionLocal()
    try:
        yield session
    finally:
        session.expunge_all()
        session.close()


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


def sync_web_posters() -> int:
    """Copy newly APPROVED events from the bot DB into the web DB.

    Only approved posters are mirrored, and only with the columns the site
    needs (id / photo refs / caption / event_date). New rows always get
    is_cancelled = False; rows that already exist keep their cancel state.
    Returns the number of rows added. Called on app startup and from the
    admin panel ("Синхронизировать" button); safe to call as often as you like.
    """
    import sqlite3

    from web.cancelled_images import SETTINGS_TABLE_DDL, _lock

    added = 0
    with _lock, sqlite3.connect(settings.web_database_path) as wconn:
        wconn.execute(SETTINGS_TABLE_DDL)
        known = {r[0] for r in wconn.execute("SELECT id FROM web_posters")}
        with get_session() as s:
            rows = (
                s.query(Poster.id, Poster.photo_file_id, Poster.channel_chat_id,
                        Poster.channel_message_id, Poster.caption,
                        Poster.event_date)
                .filter(Poster.status == ModerationStatus.APPROVED)
                .all()
            )
        for pid, file_id, chat_id, msg_id, caption, event_date in rows:
            if pid in known:
                # Keep the mirrored text/date fresh, but NEVER touch
                # is_cancelled — that flag belongs to the web DB alone.
                wconn.execute(
                    "UPDATE web_posters SET photo_file_id = ?,"
                    " channel_chat_id = ?, channel_message_id = ?, caption = ?,"
                    " event_date = ? WHERE id = ?",
                    (file_id, chat_id, msg_id, caption, event_date, pid),
                )
                continue
            wconn.execute(
                "INSERT INTO web_posters (id, photo_file_id, channel_chat_id,"
                " channel_message_id, caption, event_date, is_cancelled,"
                " cancelled_at) VALUES (?, ?, ?, ?, ?, ?, 0, NULL)",
                (pid, file_id, chat_id, msg_id, caption, event_date),
            )
            added += 1
        wconn.commit()
    return added


def set_poster_cancelled(poster_id: int, cancelled: bool):
    """Toggle the cancel flag in the WEB database (the bot DB is never written)."""
    now = func.now()
    with get_web_session() as s:
        row = s.get(WebPoster, int(poster_id))
        if row is None:
            # The event may not be synced yet — create a minimal row so the
            # admin action never fails; it will be filled by sync_web_posters().
            row = WebPoster(id=int(poster_id))
            s.add(row)
        row.is_cancelled = bool(cancelled)
        row.cancelled_at = now if cancelled else None
        s.commit()
    # Force browsers/CDN to fetch a fresh render when the state changes.
    try:
        from web.cancelled_images import delete_cached_render
        delete_cached_render(int(poster_id))
    except Exception:
        pass
