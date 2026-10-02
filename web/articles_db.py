"""
Separate SQLite database for articles (Статьи).

Articles no longer live in the bot's shared DB (gigs_archive.db) — they have
their own file so the web content can be backed up / moved independently.

Path resolution:
  * ARTICLES_DB_PATH env var — absolute, or relative to the project root;
  * default: <PROJECT_ROOT>/articles.db

Cross-database note: Article.poster_id is a logical link to posters.id in the
bot DB only. SQLite does NOT enforce it (no real FK constraint), and routes
that need poster data join them manually per-database.
"""

import enum
from contextlib import contextmanager
from datetime import datetime
import os

from sqlalchemy import (Boolean, Column, DateTime, Integer, String, Text,
                        create_engine)
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.sql import func

from web.config import PROJECT_ROOT, settings


def _resolve_articles_db_path() -> str:
    p = os.environ.get("ARTICLES_DB_PATH", "articles.db")
    if not os.path.isabs(p):
        p = os.path.join(PROJECT_ROOT, p)
    return p


ArticleBase = declarative_base()


class ArticleKind(enum.Enum):
    article = "article"
    interview = "interview"
    review = "review"


class Article(ArticleBase):
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
    poster_id = Column(Integer, nullable=True)       # logical link to posters.id (bot DB)

    is_published = Column(Boolean, default=False, index=True)
    published_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<Article {self.id} '{self.title}'>"


# ============ Engine / session (dedicated SQLite file for articles) ============

articles_db_path = _resolve_articles_db_path()
articles_engine = create_engine(
    f"sqlite:///{articles_db_path}",
    connect_args={"check_same_thread": False},
)
ArticleSessionLocal = sessionmaker(bind=articles_engine, autocommit=False,
                                   autoflush=False, expire_on_commit=False)


def init_articles_db():
    """Create the web_articles table in the separate articles DB (idempotent)."""
    ArticleBase.metadata.create_all(bind=articles_engine)


@contextmanager
def get_article_session():
    """Yield an articles-DB session; detach objects at exit so templates can
    still read plain attributes afterwards (no lazy DB access)."""
    session = ArticleSessionLocal()
    try:
        yield session
    finally:
        session.expunge_all()
        session.close()


def migrate_articles_from_shared_db(drop_old: bool = True) -> int:
    """One-time copy of web_articles from the shared bot DB into the separate
    articles DB. Returns the number of migrated rows. Existing rows with the
    same id are skipped, so re-running is safe."""
    from web.database import engine as shared_engine  # local import: avoid cycles

    init_articles_db()

    # Nothing to do if the old table doesn't exist (fresh install).
    from sqlalchemy import inspect as sa_inspect, text
    if "web_articles" not in sa_inspect(shared_engine).get_table_names():
        print("No web_articles table in the shared DB — nothing to migrate.")
        return 0

    with shared_engine.connect() as src, articles_engine.begin() as dst:
        rows = src.execute(text("SELECT * FROM web_articles")).mappings().all()
        existing_ids = {r[0] for r in dst.execute(
            text("SELECT id FROM web_articles"))}

        migrated = 0
        for row in rows:
            if row["id"] in existing_ids:
                continue
            cols = ", ".join(row.keys())
            placeholders = ", ".join(f":{k}" for k in row.keys())
            dst.execute(text(f"INSERT INTO web_articles ({cols}) "
                             f"VALUES ({placeholders})"), dict(row))
            migrated += 1

        if migrated and drop_old:
            # Copy succeeded — remove the now-redundant table from the shared DB.
            src.execute(text("DROP TABLE web_articles"))

    return migrated
