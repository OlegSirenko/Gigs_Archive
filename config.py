# config.py
from pydantic_settings import BaseSettings
from pydantic import field_validator
from functools import lru_cache
from typing import List

class Settings(BaseSettings):
    """Bot configuration from .env file"""
    
    # Bot
    bot_token: str
    
    # Database
    database_path: str = "poster_bot.db"
    debug_mode: bool = False
    
    # Chat IDs
    main_channel_id: int
    moderation_chat_id: int
    summary_channel_id: int
    test_channel_id: int | None = None
    
    # Admin IDs (comma-separated string → List[int])
    admin_ids: List[int]

    # Privacy policy version (update to force re-acceptance)
    privacy_policy_version: str = "1.0"

    # Bot username (set after bot starts)
    bot_username: str | None = None
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
    
    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, value):
        """Convert comma-separated string to list of integers"""
        if isinstance(value, str):
            # Split by comma, strip whitespace, convert to int
            return [int(x.strip()) for x in value.split(",")]
        return value

@lru_cache()
def get_config() -> Settings:
    """Get cached config instance"""
    return Settings()

config = get_config()