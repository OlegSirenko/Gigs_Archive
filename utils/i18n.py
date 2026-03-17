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
    def get_user_language(cls, language_code: str) -> str:
        """
        Get best matching language from user's language_code.
        
        Telegram sends codes like: 'ru', 'en', 'en-US', 'pt-BR'
        We match to available locales: 'ru', 'en'
        """
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
        
        # Fallback to default
        return cls._default_language
    
    @classmethod
    def project_name(cls) -> str:
        """Get project name"""
        return cls.PROJECT_NAME


# Convenience function for shorter imports
def t(key: str, language: str = None, **kwargs) -> str:
    """Shortcut for i18n.t()"""
    return i18n.t(key, language, **kwargs)