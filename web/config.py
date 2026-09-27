"""
Web-specific configuration.

Loaded from environment variables / .env (same file the bot uses).
All values have safe defaults so the site can boot without extra setup:
  - ADMIN_USERNAMES falls back to an empty list -> use `python -m web.manage add-admin ...`
    which writes web/admins.json.
  - SECRET_KEY is auto-generated and persisted to web/.secret_key on first run.
"""

import json
import os
import secrets

WEB_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(WEB_DIR)


def _parse_env_file(path: str) -> dict:
    result = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip().strip("'\"")
    return result


def _load_dotenv_once():
    """Load project .env into os.environ (without overriding real env vars)."""
    env_path = os.path.join(PROJECT_ROOT, ".env")
    if not os.path.isfile(env_path):
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path, override=False)
        return
    except ImportError:
        pass
    for key, value in _parse_env_file(env_path).items():
        os.environ.setdefault(key, value)


_load_dotenv_once()


def _get_secret_key() -> str:
    """SECRET_KEY env var > persisted web/.secret_key > newly generated one."""
    env_key = os.environ.get("SECRET_KEY")
    if env_key:
        return env_key
    key_file = os.path.join(WEB_DIR, ".secret_key")
    if os.path.isfile(key_file):
        with open(key_file) as f:
            key = f.read().strip()
        if key:
            return key
    key = secrets.token_hex(32)
    try:
        with open(key_file, "w") as f:
            f.write(key)
    except OSError:
        pass
    return key


class WebSettings:
    def __init__(self):
        # --- Database (shared with the Telegram bot) ---
        # If .env sets DATABASE_PATH but the file doesn't exist yet, fall back
        # to the project's conventional DB name so both apps point at one file.
        db_path = os.environ.get("DATABASE_PATH", "gigs_archive.db")
        if not os.path.isabs(db_path) and not os.path.isfile(db_path):
            alt = os.path.join(PROJECT_ROOT, "gigs_archive.db")
            if os.path.isfile(alt):
                db_path = alt
        if not os.path.isabs(db_path):
            db_path = os.path.join(PROJECT_ROOT, db_path)
        self.database_path = db_path
        self.database_url = f"sqlite:///{db_path}"

        # --- Auth ---
        self.secret_key = _get_secret_key()
        # Comma-separated usernames allowed to log in as admin
        # (Telegram usernames, case-insensitive). Also see web/admins.json.
        self.admin_usernames = {
            u.strip().lstrip("@").lower()
            for u in os.environ.get("ADMIN_USERNAMES", "").split(",")
            if u.strip()
        }
        self.admins_json_path = os.path.join(WEB_DIR, "admins.json")

        # --- Session cookie ---
        self.session_cookie_name = "gigs_session"
        self.session_max_age = 60 * 60 * 24 * 7  # 1 week

        # --- Site meta ---
        self.site_title = os.environ.get("SITE_TITLE", "Gigs Archive")
        self.telegram_channel = os.environ.get("TELEGRAM_CHANNEL", "Gigs_archive")

        # --- Telegram poster images (re-posted from the bot/channel) ---
        # Public Bot API endpoint that serves channel photos, e.g.
        # https://raw.gigs-archive.example.org/photos/{chat_id}_{message_id}.jpg
        self.poster_image_url_template = os.environ.get(
            "POSTER_IMAGE_URL_TEMPLATE", ""
        )
        # Local folder used by the telegram importer to download photos into
        self.posters_dir = os.environ.get(
            "POSTERS_DIR",
            os.path.join(os.path.dirname(WEB_DIR), "web_static", "posters"),
        )
        # Static mount point served by the app
        self.static_url_path = "/static"

        # --- Telegram API (used only by the importer script) ---
        self.bot_token = os.environ.get("BOT_TOKEN", "")
        self.main_channel_id = os.environ.get("MAIN_CHANNEL_ID", "")

    def admins_file_usernames(self) -> set:
        """Extra admin usernames stored in web/admins.json."""
        try:
            with open(self.admins_json_path, encoding="utf-8") as f:
                data = json.load(f)
            return {str(u).lstrip("@").lower() for u in data.get("admins", [])}
        except (OSError, ValueError):
            return set()

    def is_admin_username(self, username: str | None) -> bool:
        if not username:
            return False
        return username.lstrip("@").lower() in self.all_admin_usernames()

    def all_admin_usernames(self) -> set:
        return self.admin_usernames | self.admins_file_usernames()

    def add_admin_username(self, username: str):
        username = username.lstrip("@").lower()
        current = sorted(self.all_admin_usernames())
        if username not in current:
            current.append(username)
        with open(self.admins_json_path, "w", encoding="utf-8") as f:
            json.dump({"admins": current}, f, indent=2, ensure_ascii=False)

    @property
    def poster_image_base(self) -> str:
        """Directory of locally imported poster images (served under /static/posters)."""
        return self.posters_dir


settings = WebSettings()
