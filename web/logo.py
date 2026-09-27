"""
Download the Telegram channel's profile photo and use it as the site logo.

Telegram exposes public channel photos without any login through its preview
endpoint:  https://t.me/s/<channel-username>  ->  <meta property="og:image" ...>

Usage:
    python -m web.logo                 # download into web_static/img/logo.png
    python -m web.logo --force         # re-download even if the file exists

The site header automatically picks up web_static/img/logo.png once it is
there (no restart needed — only an image refresh). If the file is missing,
the header falls back to a built-in SVG badge.
"""

import argparse
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web.config import settings

_OG_IMAGE_RE = re.compile(
    r'<meta\s+property="og:image"\s+content="([^"]+)"', re.I
)

_EXT_BY_MAGIC = [
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"GIF8", ".gif"),
    (b"RIFF", ".webp"),   # double-check WEBP below
]


def _detect_ext(data: bytes) -> str:
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    for magic, ext in _EXT_BY_MAGIC:
        if data.startswith(magic):
            if ext == ".webp" and data[8:12] != b"WEBP":
                continue
            return ext
    return ".jpg"


def fetch_channel_photo_url(channel: str) -> str | None:
    """Return the og:image URL of the public t.me preview page, or None."""
    url = f"https://t.me/s/{channel}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; GigsArchiveLogo/1.0)",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except OSError as e:
        print(f"ERROR: could not fetch {url}: {e}")
        return None
    m = _OG_IMAGE_RE.search(html)
    if not m:
        print("ERROR: no og:image found on the channel preview page "
              "(is the channel public and does it have a photo?)")
        return None
    return m.group(1).strip()


def download(url: str, dest_base: str) -> tuple[str, bytes]:
    """Download the photo and save it as <dest_base><real-ext>. Returns the path."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; GigsArchiveLogo/1.0)",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
    except OSError as e:
        print(f"ERROR: could not download {url}: {e}")
        return None
    if len(data) < 100:
        print("ERROR: downloaded file looks too small — aborting.")
        return None
    os.makedirs(os.path.dirname(dest_base), exist_ok=True)
    # remove any previous logo.* so only one variant is present
    folder = os.path.dirname(dest_base)
    stem = os.path.basename(dest_base)          # "logo"
    for fn in os.listdir(folder):
        if fn.startswith(stem + ".") and fn != os.path.basename(dest_base):
            try:
                os.remove(os.path.join(folder, fn))
            except OSError:
                pass
    dest = dest_base + _detect_ext(data)
    with open(dest, "wb") as f:
        f.write(data)
    return dest


def main():
    ap = argparse.ArgumentParser(description="Fetch the Telegram channel photo as site logo")
    ap.add_argument("--channel", default=settings.telegram_channel,
                    help="Telegram channel username (default: from TELEGRAM_CHANNEL)")
    ap.add_argument("--force", action="store_true", help="overwrite existing logo")
    args = ap.parse_args()

    dest_base = os.path.splitext(settings.logo_path)[0]
    if settings.logo_url and not args.force:
        print(f"Logo already exists at {settings.logo_path} — use --force to re-download.")
        return

    photo_url = fetch_channel_photo_url(args.channel)
    if not photo_url:
        sys.exit(1)
    print(f"Channel photo URL: {photo_url}")
    saved = download(photo_url, dest_base)
    if saved:
        print(f"Saved -> {saved}  (the site header picks it up automatically)")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
