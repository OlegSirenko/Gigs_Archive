"""Server-side storage for images uploaded from the admin article editor.

Images can be pasted (clipboard) or picked from disk directly in the article
form; they are saved under web_static/uploads/<article_id>/ and referenced
from the article body as ``![alt](/static/uploads/<article_id>/<file>.jpg)``.

To keep the disk usage tiny (the site publishes ~1 article per 1-2 weeks with
4-5 pictures each), every upload is:
  * verified by magic bytes (we only accept real JPEG / PNG / WebP / GIF);
  * downscaled so its longest side fits MAX_DIMENSION px;
  * re-encoded to JPEG at a moderate quality (alpha is flattened onto white,
    animated GIFs keep their first frame).

Typical result: a phone screenshot pastes in at 300-800 KB and lands on disk
at well under 200 KB.
"""

import io
import os
import re
import secrets
from datetime import datetime, timedelta

from PIL import Image, ImageOps

from web.config import STATIC_ROOT_DIR, settings

# Folder inside web_static — automatically served via the existing
# StaticFiles mount: <uploads_dir> -> /static/uploads
UPLOADS_SUBDIR = "uploads"
UPLOADS_DIR = os.path.join(STATIC_ROOT_DIR, UPLOADS_SUBDIR)
UPLOADS_URL_PREFIX = f"{settings.static_url_path}/{UPLOADS_SUBDIR}"

MAX_UPLOAD_BYTES = 10 * 1024 * 1024   # hard cap on what we read from the request
MAX_DIMENSION = 1600                  # longest side after downscale
JPEG_QUALITY = 82                     # visual quality of the re-encoded file

PREVIEW_DIMENSION = 320               # longest side of editor thumbnails
PREVIEW_QUALITY = 70                  # quality of editor thumbnails

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}

# Fallback when the browser sends no/misleading Content-Type (paste events do
# sometimes): sniff the first bytes instead.
_MAGIC_SIGNATURES = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)


class ImageValidationError(ValueError):
    """Raised when the uploaded blob is not an acceptable image."""


def _sniff_content_type(data: bytes) -> str | None:
    for magic, mime in _MAGIC_SIGNATURES:
        if data.startswith(magic):
            return mime
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def ensure_uploads_dir() -> str:
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    return UPLOADS_DIR


def save_upload(data: bytes, content_type: str = "", subdir: str = "") -> str:
    """Validate, compress and store one image; returns its public URL.

    `subdir` groups files per article (e.g. "12"); pass "" for standalone
    uploads such as article covers.
    """
    if not data:
        raise ImageValidationError("Пустой файл. / Empty file.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ImageValidationError(
            f"Файл слишком большой (>{MAX_UPLOAD_BYTES // (1024 * 1024)} МБ).")

    mime = content_type.split(";")[0].strip().lower()
    if mime not in ALLOWED_CONTENT_TYPES:
        mime = _sniff_content_type(data) or ""
    if mime not in ALLOWED_CONTENT_TYPES:
        raise ImageValidationError(
            "Можно загружать только изображения JPEG / PNG / WebP / GIF.")

    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception:
        raise ImageValidationError("Не удалось прочитать изображение.")

    # Strip EXIF orientation, then apply it so output pixels are upright.
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass

    # Downscale big images (LANCZOS keeps text/posters crisp).
    w, h = img.size
    longest = max(w, h)
    if longest > MAX_DIMENSION:
        ratio = MAX_DIMENSION / longest
        img = img.resize((max(1, round(w * ratio)), max(1, round(h * ratio))),
                         Image.LANCZOS)

    # Animated formats: take the first frame; flatten transparency onto white.
    frames = getattr(img, "n_frames", 1)
    if frames > 1:
        img.seek(0)
    has_alpha = (
        img.mode in ("RGBA", "LA", "PA")
        or (img.mode == "P" and "transparency" in img.info)
    )
    if has_alpha:
        rgba = img.convert("RGBA")
        flat = Image.new("RGB", rgba.size, (255, 255, 255))
        flat.paste(rgba, mask=rgba.split()[-1])
        img = flat
    elif img.mode != "RGB":
        img = img.convert("RGB")

    out = io.BytesIO()
    img.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    encoded = out.getvalue()
    # Extremely pathological input could end up bigger than the original;
    # never store something larger than what was uploaded.
    if len(encoded) >= len(data) and len(data) <= 512 * 1024:
        encoded = data
        final_ext = {
            "image/jpeg": "jpg", "image/png": "png",
            "image/webp": "webp", "image/gif": "gif",
        }[mime]
    else:
        final_ext = "jpg"

    target_dir = os.path.join(UPLOADS_DIR, subdir) if subdir else UPLOADS_DIR
    os.makedirs(target_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"{stamp}-{secrets.token_hex(4)}.{final_ext}"
    with open(os.path.join(target_dir, name), "wb") as f:
        f.write(encoded)

    prefix = f"{UPLOADS_URL_PREFIX}/{subdir}" if subdir else UPLOADS_URL_PREFIX
    return f"{prefix}/{name}"


def save_preview(data: bytes, content_type: str = "", subdir: str = "") -> str | None:
    """Генерирует маленький превью-файл (thumbnail) для уже загруженной картинки.

    Превью сохраняется рядом с оригиналом под именем ``<оригинал>_thumb.jpg``
    и используется редактором статей как миниатюра (чтобы не тянуть
    полномерное изображение ради квадратика 160px). Возвращает URL превью или
    None, если его создать не удалось (тогда редактор покажет оригинал).
    """
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception:
        return None
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    img.thumbnail((PREVIEW_DIMENSION, PREVIEW_DIMENSION), Image.LANCZOS)
    out = io.BytesIO()
    try:
        img.save(out, "JPEG", quality=PREVIEW_QUALITY, optimize=True,
                 progressive=True)
    except Exception:
        return None

    target_dir = os.path.join(UPLOADS_DIR, subdir) if subdir else UPLOADS_DIR
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"{stamp}-{secrets.token_hex(4)}_thumb.jpg"
    try:
        with open(os.path.join(target_dir, name), "wb") as f:
            f.write(out.getvalue())
    except OSError:
        return None
    prefix = f"{UPLOADS_URL_PREFIX}/{subdir}" if subdir else UPLOADS_URL_PREFIX
    return f"{prefix}/{name}"


def delete_article_images(article_id: int) -> int:
    """Remove all uploaded images belonging to an article. Returns file count."""
    folder = os.path.join(UPLOADS_DIR, str(article_id))
    removed = 0
    if os.path.isdir(folder):
        for entry in os.listdir(folder):
            path = os.path.join(folder, entry)
            if os.path.isfile(path):
                try:
                    os.remove(path)
                    removed += 1
                except OSError:
                    pass
        try:
            os.rmdir(folder)
        except OSError:
            pass
    return removed


def prune_orphan_uploads(days: int = 7) -> int:
    """Delete uploads older than `days` that no published/draft article references.

    Protects against leftovers from abandoned paste-and-discard sessions.
    Returns the number of removed files.
    """
    from web.articles_db import Article, get_article_session

    cutoff = datetime.now() - timedelta(days=days)
    with get_article_session() as s:
        texts = [f"{a.title}\n{a.lead or ''}\n{a.body or ''}\n{a.cover_image_url or ''}"
                 for a in s.query(Article).all()]
    haystack = "\n".join(texts)

    removed = 0
    if not os.path.isdir(UPLOADS_DIR):
        return 0
    for root, _dirs, files in os.walk(UPLOADS_DIR):
        for name in files:
            path = os.path.join(root, name)
            try:
                if datetime.fromtimestamp(os.path.getmtime(path)) >= cutoff:
                    continue
                rel = os.path.relpath(path, UPLOADS_DIR).replace(os.sep, "/")
                if f"/{rel}" in haystack:  # still referenced by some article
                    continue
                # миниатюры редактора (<файл>_thumb.jpg) удаляем вместе с
                # оригиналом: на них ссылки в тексте статей нет
                if rel.endswith("_thumb.jpg"):
                    base = rel[:-len("_thumb.jpg")] + ".jpg"
                    if f"/{base}" in haystack:
                        continue
                    orig = os.path.join(root, os.path.basename(base))
                    if not os.path.isfile(orig):
                        try:
                            os.remove(path)
                            removed += 1
                        except OSError:
                            pass
                    continue
                os.remove(path)
                removed += 1
            except OSError:
                pass
    return removed
