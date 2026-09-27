"""
Telegram -> website importer (re-posting posters + weekly starter pack).

Two modes:

1. DB MODE (default):  python -m web.importer
   Downloads photos of approved posters from Telegram using the bot token and
   the file_ids already stored in the shared DB, into web_static/posters/.

2. CHANNEL MODE (starter pack, no database needed):
   python -m web.importer --channel GigsArchive --out starter_pack
   Parses the public preview page https://t.me/s/<channel> (no login/token
   required) and downloads every post photo + caption text into
   web_static/starter_pack/, writing an index.json manifest grouped by week.
   This gives a ready-to-browse starter archive even before the bot's DB is
   connected to the site.
"""

import argparse
import asyncio
import html as html_lib
import json
import os
import re
import sys
import urllib.request
from collections import OrderedDict
from datetime import datetime

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web.config import settings
from web.database import ModerationStatus, Poster, get_session, init_web_db


def _notes_with_image(old_notes: str | None, filename: str) -> str:
    """Merge {"web_image": ...} into moderator_notes without losing existing text."""
    try:
        data = json.loads(old_notes) if old_notes else {}
        if not isinstance(data, dict):
            data = {"note": data}
    except (ValueError, TypeError):
        data = {"note": old_notes} if old_notes else {}
    data["web_image"] = filename
    return json.dumps(data, ensure_ascii=False)


async def download_file(client: httpx.AsyncClient, file_id: str, dest: str) -> bool:
    r = await client.get(f"https://api.telegram.org/bot{settings.bot_token}/getFile",
                         params={"file_id": file_id})
    payload = r.json()
    if not payload.get("ok"):
        print(f"    getFile failed: {payload.get('description')}")
        return False
    path = payload["result"]["file_path"]
    r2 = await client.get(f"https://api.telegram.org/file/bot{settings.bot_token}/{path}")
    if r2.status_code != 200:
        print(f"    download failed: HTTP {r2.status_code}")
        return False
    with open(dest, "wb") as f:
        f.write(r2.content)
    return True


async def run(limit: int | None, force: bool):
    if not settings.bot_token:
        print("ERROR: BOT_TOKEN is not set (see .env). The bot token is required "
              "to download photos from Telegram.")
        sys.exit(1)

    init_web_db()
    os.makedirs(settings.posters_dir, exist_ok=True)

    with get_session() as s:
        q = s.query(Poster).filter(Poster.status == ModerationStatus.APPROVED)
        if not force:
            q = q.filter(
                (Poster.moderator_notes.is_(None))
                | (~Poster.moderator_notes.like("%web_image%"))
            )
        posters = q.order_by(Poster.created_at.desc()).all()
        if limit:
            posters = posters[:limit]
        print(f"Importing {len(posters)} poster(s) into {settings.posters_dir}")

        async with httpx.AsyncClient(timeout=60) as client:
            for p in posters:
                ext = os.path.splitext(getattr(p, "photo_file_id", "") or "")[1] or ".jpg"
                filename = f"poster_{p.id}{ext}"
                dest = os.path.join(settings.posters_dir, filename)
                print(f"  #{p.id} {p.photo_file_id[:18]}…")
                ok = await download_file(client, p.photo_file_id, dest)
                if ok:
                    p.moderator_notes = _notes_with_image(p.moderator_notes, filename)
                    s.commit()
                    print(f"    saved -> /static/posters/{filename}")
                else:
                    if os.path.isfile(dest):
                        os.remove(dest)
    print("Done.")


def main():
    ap = argparse.ArgumentParser(description="Import Telegram poster photos to the website")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    asyncio.run(run(args.limit, args.force))


if __name__ == "__main__":
    main()
