"""Import an external article by URL -> markdown body for the editor.

Uses ready-made, battle-tested libraries instead of hand-written parsers:

* readability-lxml (Mozilla Readability port) — extracts the main article
  content from arbitrary web pages (drops nav/ads/footers);
* html2text (Aaron Swartz's library) — converts the extracted HTML to
  markdown while preserving block structure (headings, lists, quotes,
  paragraphs stay on their own lines — newlines are never lost).
"""

import re

import html2text
import requests
from readability import Document

_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _abs_url(base: str, src: str) -> str:
    """Resolve a possibly-relative image src against the page URL."""
    if src.startswith("//"):
        return "https:" + src
    if src.startswith(("http://", "https://", "data:", "/")):
        return src
    root = re.match(r"https?://[^/]+", base)
    prefix = root.group(0) if root else base.rstrip("/")
    if src.startswith("./"):
        src = src[2:]
    return f"{prefix}/{src.lstrip('/')}"


def _extract_images(html: str, base: str) -> list[str]:
    """Content <img> urls in document order (icons/badges are skipped)."""
    urls = []
    for m in re.finditer(r"<img[^>]+>", html, flags=re.I):
        tag = m.group(0)
        sm = re.search(r"""src\s*=\s*["']([^"']+)["']""", tag, flags=re.I)
        if not sm:
            continue
        src = sm.group(1).strip()
        if not src or src.startswith("data:"):
            continue
        # typographic icons / tracking pixels are not article images
        if re.search(r"(icon|logo|badge|avatar|pixel|sprite|emoji)",
                     src, flags=re.I):
            continue
        w = re.search(r"""\bwidth\s*=\s*["']?(\d+)""", tag, flags=re.I)
        if w and int(w.group(1)) < 100:
            continue
        urls.append(_abs_url(base, src))
    return urls


def fetch_article_md(url: str, timeout: float = 15.0) -> tuple[str, str]:
    """Download `url` and return (title, markdown_body).

    Raises ValueError on unusable input, requests.RequestException on
    network failures — the caller turns them into a user-visible error.
    """
    if not re.match(r"^https?://", url, flags=re.I):
        raise ValueError("URL должен начинаться с http(s)://")
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": _UA})
    resp.raise_for_status()
    ctype = resp.headers.get("content-type", "")
    if "html" not in ctype and "<html" not in resp.text[:2000].lower():
        raise ValueError("По этому адресу не HTML-страница")

    doc = Document(resp.text)
    title = (doc.short_title() or "").strip()
    content_html = doc.summary()

    h = html2text.HTML2Text()
    h.body_width = 0            # не переносить строки по ширине
    h.ignore_images = True      # картинки вставим отдельными блоками ниже
    h.ignore_emphasis = False
    h.mark_code = False
    md = h.handle(content_html)
    md = re.sub(r"\n{3,}", "\n\n", md).strip()
    if not md:
        raise ValueError("Не удалось извлечь текст со страницы")

    # Картинки: вставляем после первого абзаца и перед заголовками разделов,
    # чтобы они «разбивали» текст так же, как на исходной странице.
    images = _extract_images(content_html, url)
    if images:
        figs = "\n\n".join(f"![]({u})" for u in images[:12])
        paras = md.split("\n\n")
        out = [paras[0], figs] + paras[1:]
        md = "\n\n".join(out)

    return title, md
