# utils/i18n.py
"""
i18n (internationalization) manager for Гиги Архив bot.
Loads translations from JSON files and provides easy access.
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

class i18n:
    """Translation manager with language fallback"""
    
    _translations = {}
    _default_language = "ru"
    _locales_path = Path(__file__).parent.parent / "locales"
    
    # Project name (can be changed in one place)
    PROJECT_NAME = "Гиги Архив"
    
    @classmethod
    def load(cls, language: str = None):
        """Load translations for a language"""
        if language is None:
            language = cls._default_language
        
        if language in cls._translations:
            return cls._translations[language]
        
        locale_file = cls._locales_path / f"{language}.json"
        
        if not locale_file.exists():
            logger.warning(f"Locale file not found: {locale_file}")
            if language != cls._default_language:
                return cls.load(cls._default_language)
            return {}
        
        try:
            with open(locale_file, "r", encoding="utf-8") as f:
                cls._translations[language] = json.load(f)
                logger.info(f"Loaded translations for: {language}")
                return cls._translations[language]
        except Exception as e:
            logger.error(f"Error loading locale {language}: {e}")
            if language != cls._default_language:
                return cls.load(cls._default_language)
            return {}
    
    @classmethod
    def t(cls, key: str, language: str = None, **kwargs) -> str:
        """
        Get translation by key with optional formatting.

        Usage:
            i18n.t("commands.start.title")
            i18n.t("notifications.approved.production", anon_text="...")
            i18n.t("commands.start.title", language="en")
        """
        if language is None:
            language = cls._default_language

        translations = cls.load(language)

        # Navigate nested keys (e.g., "commands.start.title")
        parts = key.split(".")
        value = translations

        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                # Key not found - try fallback language
                if language != cls._default_language:
                    return cls.t(key, cls._default_language, **kwargs)
                return f"[[MISSING: {key}]]"

        # Handle pluralization format: "{count}|singular|plural|..."
        if isinstance(value, str) and "|" in value and kwargs.get('count') is not None:
            try:
                count = int(kwargs.get('count', 1))
                parts = value.split("|")
                # Remove {count} prefix from first part
                format_string = parts[0].replace("{count}", "").strip()
                
                if count == 1:
                    # Singular form (first after format string)
                    result = parts[1] if len(parts) > 1 else parts[0]
                else:
                    # Plural form (use last available or second part)
                    result = parts[-1] if len(parts) > 2 else (parts[1] if len(parts) > 1 else parts[0])
                
                return result.format(count=count, **kwargs)
            except Exception as e:
                logger.warning(f"Error formatting pluralization for {key}: {e}")
                return value

        # Format with kwargs if value is a string
        if isinstance(value, str) and kwargs:
            try:
                return value.format(**kwargs)
            except KeyError as e:
                logger.warning(f"Missing format key {e} in translation {key}")
                return value

        return value
    
    @classmethod
    def set_default(cls, language: str):
        """Set default language"""
        cls._default_language = language
        logger.info(f"Default language set to: {language}")
    
    @classmethod
    def get_user_language(cls, language_code: str = None, telegram_id: int = None) -> str:
        """
        Get best matching language from user's language_code or database.

        Priority:
        1. Database preference (if telegram_id provided)
        2. Telegram's language_code
        3. Default language

        Telegram sends codes like: 'ru', 'en', 'en-US', 'pt-BR'
        We match to available locales: 'ru', 'en'
        """
        # 1. Try database first if telegram_id provided
        if telegram_id:
            try:
                from db.models import get_session, User
                with get_session() as session:
                    user = session.query(User).filter(User.telegram_id == telegram_id).first()
                    if user and user.language_code:
                        # Check if we have this language
                        try:
                            available_locales = [f.stem for f in cls._locales_path.glob("*.json")]
                        except:
                            available_locales = [cls._default_language]

                        if user.language_code in available_locales:
                            return user.language_code
            except Exception as e:
                # Silently fail and continue with language_code
                pass

        # 2. Try Telegram's language_code
        if not language_code:
            return cls._default_language

        # Normalize: 'en-US' -> 'en'
        lang = language_code.split("-")[0].lower()

        # Check if we have this language
        try:
            available_locales = [f.stem for f in cls._locales_path.glob("*.json")]
        except:
            available_locales = [cls._default_language]

        if lang in available_locales:
            return lang

        # 3. Fallback to default
        return cls._default_language
    
    @classmethod
    def project_name(cls) -> str:
        """Get project name"""
        return cls.PROJECT_NAME


    @classmethod
    def get_day_name(cls, date, language: str = "ru") -> str:
        """Get localized day name abbreviation (Mon, Tue, etc.)"""
        day_names = {
            "ru": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"],
            "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
            # Add more languages as needed
        }
        
        # Get list for language, fallback to English
        names = day_names.get(language, day_names["en"])
        
        # strftime weekday: Monday=0, Sunday=6
        return names[date.weekday()]
    
    @classmethod
    def get_month_name(cls, date, language: str = "ru") -> str:
        """Get localized month name abbreviation (Jan, Feb, etc.)"""
        month_names = {
            "ru": ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"],
            "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
        }
        
        names = month_names.get(language, month_names["en"])
        return names[date.month - 1]
    
def t(key: str, language: str = None, **kwargs) -> str:
    """
    Shortcut for i18n.t()

    Usage:
    from utils.i18n import t
    t("commands.start.title")
    t("notifications.approved.production", anon_text="...")
        """
    return i18n.t(key, language, **kwargs)