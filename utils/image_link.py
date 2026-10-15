# utils/image_link.py
"""Скачать картинку по ссылке на пост Instagram.

Сценарий: пользователь прислал только ссылку на пост, картинку не приложил.

Стратегии (по порядку):
  1. https://www.instagram.com/p/<code>/media/?size=l — отдаёт сам файл JPEG
     без логина и JS. Основной и почти всегда достаточный путь.
  2. embed-страница /embed/captioned/ -> og:image (запас, если п.1 не сработал).

Ручная проверка:
    python3 -m utils.image_link "https://www.instagram.com/p/<code>/" --save out.jpg

Публичный API:
    is_instagram_link(text) -> bool
    looks_like_instagram_url(text) -> bool
    extract_instagram_link(text) -> str | None
    instagram_media_url(url) -> str | None
    instagram_embed_url(url) -> str | None
    fetch_image_from_link(url, *, timeout, max_bytes, user_agent, trace) -> LinkedImage | None
    async download_image_from_link(url, **kwargs) -> LinkedImage | None
"""

from __future__ import annotations

import asyncio
import html as html_lib
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional

DEFAULT_TIMEOUT = 15.0
DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 МБ
MAX_HTML_BYTES = 2 * 1024 * 1024
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; PosterBot/1.0; +https://t.me/) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
)

# instagram.com/p/<code>/, /reel/<code>/, /tv/<code>/
_IG_POST_RE = re.compile(
    r"^https?://(?:www\.)?instagram\.com/(?:(?:[A-Za-z0-9_.]+)/)?(p|reel|reels|tv)/([A-Za-z0-9_-]+)",
    re.IGNORECASE,
)
# то же, но как поиск внутри произвольного текста (без привязки к началу)
_IG_LINK_SEARCH_RE = re.compile(
    r"https?://(?:www\.)?instagram\.com/(?:(?:[A-Za-z0-9_.]+)/)?(?:p|reel|reels|tv)/[A-Za-z0-9_-]+",
    re.IGNORECASE,
)
# любая ссылка на Instagram (включая профиль/истории) — чтобы отличить
# "обрабатываемую" ссылку на пост от ссылки, которую мы не умеем читать
_IG_ANY_URL_RE = re.compile(
    r"https?://(?:www\.)?instagram\.com/[^\s<>\"']*",
    re.IGNORECASE,
)
# og:image из embed-страницы
_OG_IMAGE_RE = re.compile(
    r"<meta\b[^>]*?(?:property|name)\s*=\s*[\"']og:image(?::secure_url)?[\"']"
    r"[^>]*?content\s*=\s*[\"']([^\"']+)[\"']",
    re.IGNORECASE | re.DOTALL,
)


@dataclass
class LinkedImage:
    """Результат: сырые байты картинки + откуда она взялась."""
    data: bytes
    content_type: str          # напр. "image/jpeg"
    image_url: str             # прямая ссылка на картинку
    source_url: str            # исходная ссылка пользователя
    filename: str = ""         # имя файла из URL (если есть)

    @property
    def size(self) -> int:
        return len(self.data)


# --------------------------------------------------------------------------- #
#                             чистые функции                                  #
# --------------------------------------------------------------------------- #

def _match_ig(url: str):
    return _IG_POST_RE.match(url.strip()) if url else None


def instagram_media_url(url: str) -> Optional[str]:
    """instagram.com/<p|reel|tv>/<code>/media/?size=l -> прямая картинка поста.

    Легаси-эндпоинт Instagram: отдаёт сам файл-картинку (image/jpeg) без
    логина и без JS. Для карусели вернёт только первое фото, для видео —
    кадр-обложку.
    """
    match = _match_ig(url)
    if not match:
        return None
    return f"https://www.instagram.com/p/{match.group(2)}/media/?size=l"


def instagram_embed_url(url: str) -> Optional[str]:
    """instagram.com/<p|reel|tv>/<code> -> embed-страница /embed/captioned/.

    Embed-вариант отдаёт обычный HTML с og:image, без JS-стены. Запасной путь.
    """
    match = _match_ig(url)
    if not match:
        return None
    kind = "reel" if match.group(1).lower() in ("reel", "reels") else match.group(1).lower()
    return f"https://www.instagram.com/{kind}/{match.group(2)}/embed/captioned/"


def extract_instagram_link(text: str) -> Optional[str]:
    """Найти ссылку на пост Instagram внутри произвольного текста.

    Возвращает первую найденную ссылку или None. Используется, чтобы понять,
    что пользователь прислал только ссылку (без картинки).
    """
    if not text:
        return None
    match = _IG_LINK_SEARCH_RE.search(text)
    return match.group(0) if match else None


def is_instagram_link(text: str) -> bool:
    """True, если текст содержит ссылку на пост Instagram."""
    return extract_instagram_link(text) is not None


def looks_like_instagram_url(text: str) -> bool:
    """True, если текст содержит любую ссылку на Instagram (пост, профиль...).

    В отличие от ``is_instagram_link`` срабатывает и на ссылках, которые мы не
    умеем обрабатывать (профиль, истории) — чтобы всё равно ответить
    пользователю и подсказать, что нужна ссылка на пост.
    """
    return bool(text and _IG_ANY_URL_RE.search(text))


def _looks_like_image(data: bytes, content_type: str = "") -> bool:
    if content_type.lower().startswith("image/"):
        return True
    if data.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"GIF87a", b"GIF89a", b"BM")):
        return True
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return True
    return False


def _filename_from_url(url: str) -> str:
    path = urllib.parse.urlsplit(url).path
    name = urllib.parse.unquote(path.rsplit("/", 1)[-1])
    return name if "." in name else ""


# --------------------------------------------------------------------------- #
#                          сетевая часть (sync)                               #
# --------------------------------------------------------------------------- #

def _http_get(url: str, *, timeout: float, max_bytes: int, user_agent: str):
    """GET с ограничением размера. Возвращает (final_url, headers, body) | None."""
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,image/*,*/*;q=0.8",
        "Accept-Language": "ru,en;q=0.8",
        "Referer": "https://www.instagram.com/",
    }
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            final_url = response.geturl() or url
            resp_headers = {k.lower(): v for k, v in response.headers.items()}
            body = response.read(max_bytes + 1)
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError,
            TimeoutError, OSError):
        return None
    if len(body) > max_bytes:
        return None
    return final_url, resp_headers, body


def fetch_image_from_link(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    max_bytes: int = DEFAULT_MAX_BYTES,
    user_agent: str = DEFAULT_USER_AGENT,
    trace: Optional[list] = None,
) -> Optional[LinkedImage]:
    """Скачать картинку по ссылке на пост Instagram (синхронно).

    Возвращает LinkedImage или None. Никогда не бросает исключения наружу.
    ``trace`` — необязательный список для диагностики (CLI).
    """
    def _log(message: str) -> None:
        if trace is not None:
            trace.append(message)

    if not url:
        return None
    url = url.strip()
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url

    for page_url in (instagram_media_url(url), instagram_embed_url(url)):
        if not page_url:
            continue
        _log(f"[page] пробую: {page_url}")
        page = _http_get(page_url, timeout=timeout, max_bytes=MAX_HTML_BYTES,
                         user_agent=user_agent)
        if not page:
            _log(f"[page]   запрос не удался: {page_url}")
            continue
        final_url, headers, body = page
        content_type = (headers.get("content-type") or "").split(";")[0].strip().lower()
        _log(f"[page]   HTTP ок, {len(body)} байт, content-type={content_type or '?'}")

        # Сервер отдал картинку напрямую (media/?size=l)
        if _looks_like_image(body, content_type):
            _log("[page]   сервер вернул картинку напрямую")
            return LinkedImage(data=body, content_type=content_type,
                               image_url=final_url, source_url=url,
                               filename=_filename_from_url(final_url))

        # HTML (embed) -> og:image
        markup = body.decode("utf-8", errors="replace")
        match = _OG_IMAGE_RE.search(markup)
        if not match:
            _log("[page]   og:image в HTML не найден (вероятно, требуется логин)")
            continue
        image_url = html_lib.unescape(match.group(1).strip())
        _log(f"[page]   найдена картинка: {image_url}")
        page = _http_get(image_url, timeout=timeout, max_bytes=max_bytes,
                         user_agent=user_agent)
        if not page:
            _log("[page]   картинка по найденному URL не скачалась")
            continue
        img_final, img_headers, data = page
        img_type = (img_headers.get("content-type") or "").split(";")[0].strip()
        return LinkedImage(data=data, content_type=img_type,
                           image_url=img_final, source_url=url,
                           filename=_filename_from_url(img_final))

    return None


async def download_image_from_link(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    max_bytes: int = DEFAULT_MAX_BYTES,
    user_agent: str = DEFAULT_USER_AGENT,
    trace: Optional[list] = None,
) -> Optional[LinkedImage]:
    """Асинхронная обёртка: блокирующий urllib уходит в отдельный поток."""
    return await asyncio.to_thread(
        fetch_image_from_link, url,
        timeout=timeout, max_bytes=max_bytes, user_agent=user_agent, trace=trace,
    )


# --------------------------------------------------------------------------- #
#                    CLI: ручная проверка ссылки (python -m …)                #
# --------------------------------------------------------------------------- #

def _cli() -> int:
    """`python3 -m utils.image_link <URL> [--save out.jpg] [--timeout 20]`"""
    import argparse

    parser = argparse.ArgumentParser(description="Достать картинку из поста Instagram.")
    parser.add_argument("url", help="ссылка на пост Instagram")
    parser.add_argument("--save", metavar="FILE", help="сохранить картинку в файл")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--max-mb", type=float, default=DEFAULT_MAX_BYTES / 1024 / 1024)
    parser.add_argument("-q", "--quiet", action="store_true", help="без шагов поиска")
    args = parser.parse_args()

    trace: list[str] = []
    result = fetch_image_from_link(
        args.url, timeout=args.timeout,
        max_bytes=int(args.max_mb * 1024 * 1024), trace=trace,
    )

    if not args.quiet:
        for line in trace:
            print(line)

    if not result:
        print("РЕЗУЛЬТАТ: картинку достать не удалось (None).")
        return 1

    print(f"РЕЗУЛЬТАТ: {len(result.data)} байт, {result.content_type or '?'}, "
          f"url={result.image_url}")
    if result.filename:
        print(f"           filename={result.filename}")
    if args.save:
        with open(args.save, "wb") as f:
            f.write(result.data)
        print(f"           сохранено в {args.save}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
