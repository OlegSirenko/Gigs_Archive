# config.py
from pydantic_settings import BaseSettings, NoDecode
from pydantic import field_validator
from functools import lru_cache
from typing import Annotated, List

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
    # NoDecode: parse the raw env string with the validator below instead of
    # letting pydantic-settings JSON-decode complex fields like "123,456".
    admin_ids: Annotated[List[int], NoDecode]

    # Privacy policy version (update to force re-acceptance)
    privacy_policy_version: str = "1.0"

    # Public website origin (SITE_URL in .env), used to deep-link the bot to the
    # full privacy policy page on the site (e.g. https://GigsArchive.at.by).
    site_url: str = ""

    # Bot username (set after bot starts)
    bot_username: str | None = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        # The shared .env also contains variables used only by the web app
        # (WEB_SYNC_MIN_INTERVAL, SITE_NAME, SITE_URL, ...). Ignore unknown
        # keys instead of crashing with extra_forbidden.
        extra = "ignore"

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, value):
        """Convert comma-separated string to list of integers.

        Accepts both plain ("123,456") and JSON-style ("[123, 456]") values.
        Note: pydantic-settings pre-decodes complex fields (List[...]) as
        JSON, so we also declare a NoDecode annotation below.
        """
        if isinstance(value, str):
            return [int(x) for x in value.strip().strip("[]").split(",") if x.strip()]
        if isinstance(value, (list, tuple)):
            return [int(x) for x in value]
        return value

@lru_cache()
def get_config() -> Settings:
    """Get cached config instance"""
    return Settings()

config = get_config()