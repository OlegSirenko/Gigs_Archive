from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text, Enum, ForeignKey, Index
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy.sql import func
from sqlalchemy.pool import StaticPool
from datetime import datetime
from contextlib import contextmanager
import enum
from config import config

Base = declarative_base()

class ModerationStatus(enum.Enum):
    PENDING = "pending"
    PENDING_FINAL = "pending_final"  # ← For two-stage moderation
    APPROVED = "approved"
    DECLINED = "declined"

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String, nullable=True, index=True)  # ← INDEX ADDED
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=True)
    language_code = Column(String, nullable=True)
    is_premium = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    posters = relationship("Poster", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User {self.telegram_id} @{self.username}>"

class Poster(Base):
    __tablename__ = "posters"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.telegram_id"), nullable=False, index=True)
    
    # Content
    photo_file_id = Column(String, nullable=False)
    caption = Column(Text, nullable=True)
    event_date = Column(DateTime, nullable=True, index=True)  #  INDEX ADDED
    is_anonymous = Column(Boolean, default=False, index=True)  #  INDEX ADDED
    
    # Moderation
    status = Column(Enum(ModerationStatus), default=ModerationStatus.PENDING, index=True)  #  INDEX ADDED
    moderated_by = Column(Integer, nullable=True, index=True)  #  INDEX ADDED
    moderated_at = Column(DateTime, nullable=True, index=True)  #  INDEX ADDED
    decline_reason = Column(String, nullable=True)
    moderator_notes = Column(Text, nullable=True)  #  NEW FIELD
    
    moderation_message_id = Column(Integer, nullable=True)  # ← NEW FIELD
    moderation_chat_id = Column(Integer, nullable=True)     # ← NEW FIELD
    

    # Published message reference
    channel_message_id = Column(Integer, nullable=True)
    channel_chat_id = Column(Integer, nullable=True, index=True)  # ← INDEX ADDED
    
    # Analytics (future use)
    view_count = Column(Integer, default=0)  #  NEW FIELD
    
    created_at = Column(DateTime, default=func.now(), index=True)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    user = relationship("User", back_populates="posters")
    
    # ← COMPOSITE INDEXES ADDED
    __table_args__ = (
        Index('ix_posters_status_moderated_at', 'status', 'moderated_at'),
        Index('ix_posters_user_id_status', 'user_id', 'status'),
        Index('ix_posters_event_date_status', 'event_date', 'status'),
    )
    
    def __repr__(self):
        return f"<Poster {self.id} by User {self.user_id}>"

# Database setup
DATABASE_URL = f"sqlite:///{config.database_path}"
engine = create_engine(
    DATABASE_URL,
    echo=config.debug_mode,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool  # ← Better connection handling
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

def init_db():
    """Create all database tables"""
    Base.metadata.create_all(bind=engine)

@contextmanager
def get_session():
    """Get database session (context manager)"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()