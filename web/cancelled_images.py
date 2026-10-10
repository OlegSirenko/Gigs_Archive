"""The "Canceled" watermark drawn over poster pictures of cancelled events.

How it works
------------
* Cancel state lives in the WEB database (posters_web.db, table web_posters:
  id / caption / event_date / is_cancelled) — see web/database.WebPoster.
* When an image is requested for a cancelled poster, we take the original
  picture (locally imported file, or the bytes served by the Telegram Bot API
  proxy), stamp a big red diagonal word ("Отменено"/"Canceled", editable in
  the admin panel) across the TOP part of the image with Pillow, and cache the
  result under web_static/img/watermarks/<id>.jpg (served as a static file).
* Uncancelling an event simply deletes the cached render, so the next request
  returns the clean original again.

Public helpers used by the templates/routes:
    is_cancelled(poster_id)          -> bool
    get_cancelled_label()            -> str   (admin-editable, per language)
    cancelled_image_url(poster)      -> str|None  (static URL if already rendered)
    ensure_cancelled_image(poster)   -> bytes|None (render + cache on demand)
"""

from __future__ import annotations

import io
import os
import sqlite3
import threading
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont, ImageOps

from web.config import STATIC_ROOT_DIR, settings

# ---------------------------------------------------------------------------
# Settings stored in posters_web.db (web-only DB; never touched by the bot)
# ---------------------------------------------------------------------------

SETTINGS_TABLE_DDL = (
    "CREATE TABLE IF NOT EXISTS web_settings ("
    " key TEXT PRIMARY KEY,"
    " value TEXT NOT NULL,"
    " updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
)

LABEL_KEY_RU = "cancelled_label_ru"
LABEL_KEY_EN = "cancelled_label_en"

_lock = threading.RLock()


def _sqlite_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.web_database_path)
    conn.execute(SETTINGS_TABLE_DDL)
    return conn


def init_web_settings():
    """Create the settings table inside posters_web.db (idempotent)."""
    with _lock:
        with _sqlite_conn() as conn:
            conn.execute(SETTINGS_TABLE_DDL)
            conn.commit()


def get_setting(key: str, default: str | None = None) -> str | None:
    try:
        with _lock, _sqlite_conn() as conn:
            row = conn.execute(
                "SELECT value FROM web_settings WHERE key = ?", (key,)
            ).fetchone()
    except sqlite3.Error:
        return default
    if row is None or not str(row[0]).strip():
        return default
    return str(row[0]).strip()


def set_setting(key: str, value: str):
    with _lock, _sqlite_conn() as conn:
        conn.execute(SETTINGS_TABLE_DDL)
        conn.execute(
            "INSERT INTO web_settings (key, value, updated_at) VALUES (?, ?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value,"
            " updated_at = excluded.updated_at",
            (key, value.strip(), datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()


def get_cancelled_label(language: str | None = None) -> str:
    """Word stamped on cancelled posters. Admin value > env default.

    `language` ("ru"/"en" or None) picks the variant; None returns the Russian
    one because the site UI is Russian.
    """
    if language and language.lower().startswith("en"):
        return get_setting(LABEL_KEY_EN, settings.cancelled_label_en)
    return get_setting(LABEL_KEY_RU, settings.cancelled_label_ru)


# ---------------------------------------------------------------------------
# Sync of APPROVED events from the bot DB into the web DB (web-side mirror)
# ---------------------------------------------------------------------------

# NOTE: the actual "copy APPROVED events into posters_web.db" routine lives in
# web.database.sync_web_posters() — it is defined there because it needs the
# ORM models; importing it here would create a circular import.


# ---------------------------------------------------------------------------
# Cancel state
# ---------------------------------------------------------------------------

def is_cancelled(poster_id: int) -> bool:
    """True if the event is marked cancelled in the web DB."""
    try:
        with _lock, _sqlite_conn() as conn:
            row = conn.execute(
                "SELECT is_cancelled FROM web_posters WHERE id = ?",
                (int(poster_id),),
            ).fetchone()
    except sqlite3.Error:
        return False
    return bool(row and row[0])


def set_cancelled(poster_id: int, cancelled: bool):
    """Mark/unmark an event as cancelled (creates the web row if missing)."""
    with _lock, _sqlite_conn() as conn:
        conn.execute(SETTINGS_TABLE_DDL)
        now = datetime.now().isoformat(timespec="seconds")
        exists = conn.execute(
            "SELECT 1 FROM web_posters WHERE id = ?", (int(poster_id),)
        ).fetchone()
        if exists:
            conn.execute(
                "UPDATE web_posters SET is_cancelled = ?, cancelled_at = ?"
                " WHERE id = ?",
                (1 if cancelled else 0, now if cancelled else None,
                 int(poster_id)),
            )
        else:
            conn.execute(
                "INSERT INTO web_posters (id, caption, event_date,"
                " is_cancelled, cancelled_at) VALUES (?, NULL, NULL, ?, ?)",
                (int(poster_id), 1 if cancelled else 0,
                 now if cancelled else None),
            )
        conn.commit()
    if not cancelled:
        delete_cached_render(poster_id)


def cancelled_ids() -> set[int]:
    """All cancelled poster ids (used to annotate lists in one query)."""
    try:
        with _lock, _sqlite_conn() as conn:
            return {int(r[0]) for r in conn.execute(
                "SELECT id FROM web_posters WHERE is_cancelled = 1")}
    except sqlite3.Error:
        return set()


def get_web_poster_for_render(poster_id: int):
    """Load the minimal web row needed to render a watermark.

    The web DB is self-sufficient for rendering: it has the poster index,
    telegram file id and channel coordinates of every APPROVED event.
    Returns None when the event was never synced into posters_web.db.
    """
    from web.database import WebPoster, get_web_session

    try:
        with get_web_session() as s:
            return s.get(WebPoster, int(poster_id))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Watermark rendering (Pillow)
# ---------------------------------------------------------------------------

_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    os.path.join(STATIC_ROOT_DIR, "fonts", "DejaVuSans-Bold.ttf"),
    "C:/Windows/Fonts/arialbd.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
)

RED = (220, 20, 40)
WHITE_EDGE = (255, 255, 255, 235)
CACHE_VERSION = "v1"


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in _FONT_CANDIDATES:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _cache_path(poster_id: int) -> str:
    return os.path.join(settings.watermarks_dir, f"{int(poster_id)}-{CACHE_VERSION}.jpg")


def delete_cached_render(poster_id: int):
    p = _cache_path(poster_id)
    try:
        if os.path.isfile(p):
            os.remove(p)
    except OSError:
        pass


def ensure_uploads_dirs():
    """Make sure the watermark cache dir exists (kept out of /uploads)."""
    os.makedirs(settings.watermarks_dir, exist_ok=True)


def _original_bytes(poster) -> bytes | None:
    """Source image bytes for a poster: local import first, Telegram after."""
    pid = getattr(poster, "id", None)
    if pid is None:
        return None

    # 1. Locally imported photo (web/importer.py downloads them to
    #    web_static/posters as <chat_id>_<message_id>.jpg)
    chat_id = getattr(poster, "channel_chat_id", None)
    msg_id = getattr(poster, "channel_message_id", None)
    if chat_id and msg_id:
        for name in (f"{chat_id}_{msg_id}.jpg", f"{chat_id}_{msg_id}.png"):
            p = os.path.join(settings.posters_dir, name)
            if os.path.isfile(p):
                try:
                    with open(p, "rb") as f:
                        return f.read()
                except OSError:
                    pass

    # 2. Ask the Telegram Bot API directly (same endpoint the image proxy uses).
    file_id = getattr(poster, "photo_file_id", None)
    token = settings.bot_token
    if not file_id or not token:
        return None
    try:
        import httpx
        with httpx.Client(timeout=20.0) as client:
            info = client.get(
                f"https://api.telegram.org/bot{token}/getFile",
                params={"file_id": file_id},
            ).json()
            if not info.get("ok"):
                return None
            path = info["result"]["file_path"]
            img = client.get(
                f"https://api.telegram.org/file/bot{token}/{path}")
            if img.status_code != 200:
                return None
            return img.content
    except Exception:
        return None


def draw_cancelled_watermark(image_bytes: bytes, label: str | None = None,
                             language: str | None = None) -> bytes:
    """Stamp a big RED DIAGONAL word across the TOP of the image. Returns JPEG."""
    text = (label or get_cancelled_label(language)).upper()
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    # Respect EXIF orientation so the stamp matches what browsers show.
    img = ImageOps.exif_transpose(img)

    w, h = img.size
    scale = max(w, h) / 1000.0
    target_w = w * 0.92                      # text spans ~92% of the width
    font_size = max(24, int(h * 0.16))       # start from ~16% of the height
    font = _load_font(font_size)

    # Shrink until the rotated text fits nicely inside the canvas.
    measure = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    def text_size(f):
        box = measure.textbbox((0, 0), text, font=f)
        return box[2] - box[0], box[3] - box[1]

    tw, th = text_size(font)
    while tw > target_w * 1.05 and font_size > 20:
        font_size = int(font_size * 0.92)
        font = _load_font(font_size)
        tw, th = text_size(font)

    angle = -20                              # diagonal, rising to the right
    pad = max(6, int(th * 0.35))
    layer = Image.new("RGBA", (tw + pad * 2, th + pad * 2), (0, 0, 0, 0))
    ldraw = ImageDraw.Draw(layer)
    stroke = max(2, int(th * 0.06))
    # white outline first, then the red fill on top -> readable on any poster
    ldraw.text((pad, pad), text, font=font, fill=RED + (255,),
               stroke_width=stroke, stroke_fill=WHITE_EDGE)
    layer = layer.rotate(angle, expand=True, resample=Image.BICUBIC)

    # Position: horizontally centred, near the TOP of the poster.
    lw, lh = layer.size
    x = int((w - lw) / 2)
    y = int(h * 0.02)
    # Keep the whole stamp visible even on narrow/tall images.
    x = max(-lw // 4, min(x, w - lw * 3 // 4))
    if y + lh > h:
        y = max(0, h - lh)

    img.paste(layer, (x, y), layer)

    out = io.BytesIO()
    img.save(out, "JPEG", quality=85)
    return out.getvalue()


def ensure_cancelled_image(poster) -> bytes | None:
    """Render (and cache) the watermarked image; returns JPEG bytes or None."""
    if poster is None or not is_cancelled(poster.id):
        return None
    # If the caller gave us an object without the photo columns (deferred
    # loading), take the values straight from the web DB instead.
    if getattr(poster, "photo_file_id", None) is None and \
            getattr(poster, "channel_message_id", None) is None:
        web_row = get_web_poster_for_render(poster.id)
        if web_row is not None:
            poster = web_row
    path = _cache_path(poster.id)
    if os.path.isfile(path):
        try:
            with open(path, "rb") as f:
                return f.read()
        except OSError:
            pass
    original = _original_bytes(poster)
    if not original:
        return None
    try:
        data = draw_cancelled_watermark(original)
    except Exception:
        return None
    try:
        ensure_uploads_dirs()
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except OSError:
        pass
    return data


def render_and_cache(poster_id: int, image_bytes: bytes) -> bytes | None:
    """Stamp `image_bytes` and save the result into the on-disk cache."""
    try:
        data = draw_cancelled_watermark(image_bytes)
    except Exception:
        return None
    try:
        ensure_uploads_dirs()
        path = _cache_path(poster_id)
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except OSError:
        pass
    return data


def cancelled_image_url(poster) -> str | None:
    """Static URL of the already-rendered watermarked image, if it exists."""
    if poster is None or not is_cancelled(poster.id):
        return None
    if os.path.isfile(_cache_path(poster.id)):
        return f"/static/img/watermarks/{os.path.basename(_cache_path(poster.id))}"
    return None
