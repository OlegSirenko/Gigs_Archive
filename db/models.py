# db/models.py
"""
Database models for Users and Posters.
"""

from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text, Enum, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy.sql import func
from datetime import datetime
from contextlib import contextmanager
import enum
from config import config

# ============ BASE ============
Base = declarative_base()

# ============ ENUMS ============

class ModerationStatus(enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DECLINED = "declined"

# ============ MODELS ============

class User(Base):
    """Telegram user information"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=True)
    language_code = Column(String, nullable=True)
    is_premium = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationship
    posters = relationship("Poster", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User {self.telegram_id} @{self.username}>"

# db/models.py - Poster model

class Poster(Base):
    __tablename__ = "posters"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.telegram_id"), nullable=False)
    
    # Content
    photo_file_id = Column(String, nullable=False)
    caption = Column(Text, nullable=True)
    event_date = Column(DateTime, nullable=True)
    is_anonymous = Column(Boolean, default=False)
    
    # Moderation
    status = Column(Enum(ModerationStatus), default=ModerationStatus.PENDING)
    moderated_by = Column(Integer, nullable=True)
    moderated_at = Column(DateTime, nullable=True)
    decline_reason = Column(String, nullable=True) 
    
    # Published message reference
    channel_message_id = Column(Integer, nullable=True)
    channel_chat_id = Column(Integer, nullable=True)
    
    created_at = Column(DateTime, default=func.now(), index=True)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    user = relationship("User", back_populates="posters")


# ============ DATABASE SETUP ============

DATABASE_URL = f"sqlite:///{config.database_path}"
engine = create_engine(DATABASE_URL, echo=config.debug_mode, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

# ============ FUNCTIONS ============

def init_db():
    """Create all database tables"""
    Base.metadata.create_all(bind=engine)

@contextmanager  # ← ADD THIS DECORATOR
def get_session():
    """Get database session (context manager)"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()