# web/helpers.py
"""Slug + tiny markdown helpers shared by routes."""

import re
import unicodedata
import requests
from markupsafe import Markup

# ОГРОМНЫЙ ПРИНТ, ЧТОБЫ УБЕДИТЬСЯ, ЧТО ФАЙЛ ЧИТАЕТСЯ
print("=" * 60)
print("!!! ФАЙЛ web/helpers.py БЫЛ ПРОЧИТАН PYTHON ПРИ ЗАПУСКЕ !!!")
print("=" * 60)


def poster_image_url(poster) -> str | None:
    """Возвращает URL нашего прокси-эндпоинта для картинки."""
    if not poster or not hasattr(poster, 'photo_file_id') or not poster.photo_file_id:
        return None
    
    # Просто возвращаем ссылку на наш прокси, который использует Bot API
    return f"/api/poster-image/{poster.id}"


def slugify(text: str, max_len: int = 180) -> str:
    """URL-safe slug; supports Cyrillic transliteration."""
    text = (text or "").strip().lower()
    _TRANSLIT = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
        "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
        "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    }
    text = "".join(_TRANSLIT.get(ch, ch) for ch in text)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:max_len] or "untitled"


def unique_slug(session, model, base_slug: str, exclude_id: int | None = None) -> str:
    """Append -2, -3... until the slug is free in `model`."""
    slug = base_slug
    n = 1
    while True:
        q = session.query(model).filter(model.slug == slug)
        if exclude_id is not None:
            q = q.filter(model.id != exclude_id)
        if q.first() is None:
            return slug
        n += 1
        slug = f"{base_slug}-{n}"


# Диапазоны кодовых точек эмодзи и декоративных пиктограмм (Telegram-тексты)
_EMOJI_RE = re.compile(
    "["
    "\U0001F1E6-\U0001F1FF"   # флаги-символы
    "\U0001F300-\U0001FAFF"   # основной блок эмодзи (включая 🎸, 🔥 и т.п.)
    "\U00002600-\U000027BF"   #Misc symbols и дингбаты (☀–➿, ✔, ✨)
    "\U0001F000-\U0001F0FF"   # маджонг/домино/карты
    "\U00002B00-\U00002BFF"   # стрелки и прочие символы (⬆–⭐)
    "\U0000FE00-\U0000FE0F"   # variation selectors (варианты написания)
    "\U0000200D"              # zero-width joiner (склейки составных эмодзи)
    "\U00002049\U0000203C"    # ⁉ ‼
    "\U00002122\U00002139"    # ™ ℹ
    "\U00002194-\U000021AA"   # ↔ … ↪ стрелки
    "\U0000231A-\U0000231B"   # ⌚ ⌛
    "\U00002328"              # ⌨
    "\U000023CF-\U000023FA"   # ⏏ – ⏺ (часы, кнопки)
    "\U000024C2"              # Ⓜ
    "\U000025AA-\U000025FE"   # геометрические фигуры ▪ – ◾
    "\U00002934-\U00002935"   # ⤴ ⤵
    "\U00003030\U0000303D"    # 〰 〽
    "\U00003297\U00003299"    # ㊗ ㊙
    "]+",
    flags=re.UNICODE,
)


def strip_emoji(text: str | None) -> str:
    """Удаляет все эмодзи и декоративные пиктограммы из текста."""
    if not text:
        return ""
    cleaned = _EMOJI_RE.sub("", text)
    # после удаления эмодзи могут остаться «висячие» двойные пробелы
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r" +(\n)", r"\1", cleaned)
    cleaned = re.sub(r"(\n) +", r"\1", cleaned)
    return cleaned.strip()


# Остатки telegram-разметки: <a href="...">...</a>, <b>/<i>/&nbsp; и т.п.,
# markdown-ссылки [текст](url), одиночные символы разметки ** __ ~~ || `( )
_TG_LINK_TAG_RE = re.compile(
    r'<a\b[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL
)
_TG_HTML_TAG_RE = re.compile(
    r'</?\s*(?:a|u|s|strong|ins|del|span|pre|code|blockquote)\b[^>]*>',
    re.IGNORECASE,
)
# теги <i>/<em> и <b> сохраняем как валидный HTML — сайт выделит их стилизацией
_MD_LINK_RE = re.compile(r'\[([^ \]]*)\]\((?:https?://|tg://)[^)]*\)')
_MD_LINK_FULL_RE = re.compile(r'\[([^\]]*)\]\(((?:https?://|tg://)[^)]*)\)')
# пары **/__ и ~~ (spoiler/strike): их обрабатывает _markdown_emphasis,
# поэтому в «мусорных» маркерах их нет — остаются одиночные *, ~, |, `
# одиночные маркеры: '~' в паре (~~спойлер~~) убираем, одиночный '*' внутри
# слова не трогаем (цензурные вставки вроде «Отс*си» — часть текста)
_MD_MARKERS_RE = re.compile(r'~~|[~|`]')
# одиночная '*' только если она не в составе слова (например « *выдел.* »),
# чтобы цензурные вставки вида «Отс*си» оставались как есть
_LONE_STAR_RE = re.compile(r'(?<!\S)\*(?!\*)|\*(?!\*)(?!\S)')
_BARE_URL_LINK_RE = re.compile(
    r'(?<!["\w/>])(?:https?://|tg://)[^\s<>"\']+', re.IGNORECASE)
# Картинки в текстах статей: ![описание](/static/uploads/… или https://…)
_MD_IMAGE_RE = re.compile(
    r'!\[([^\]]*)\]\(\s*((?:https?://|/)[^)\s]+)(?:\s+"[^"]*")?\s*\)')
# Разрешаем <img> только для картинок, загруженных на наш сервер (или голых
# ссылок на /static/uploads/...); внешние URL остаются обычным текстом.
_ALLOWED_IMG_SRC_RE = re.compile(r'^(?:/static/uploads/|https?://)', re.IGNORECASE)
_LOCAL_UPLOAD_URL_RE = re.compile(
    r'(?<![\w/"\'(])((?:/static/uploads/|\./static/uploads/)[^\s<>"\']+)', re.IGNORECASE)
_TG_EMPH_TAG_RE = re.compile(
    r'</?\s*(?:b|i|em|strong)\b[^>]*>', re.IGNORECASE
)
_BARE_URL_RE = re.compile(r'(?:https?://|tg://)\S+', re.IGNORECASE)


def _unescape_tg(text: str) -> str:
    """Расэкранивает telegram-HTML (&lt; &gt; &amp; &quot; &#39;)."""
    return (text.replace("&lt;", "<").replace("&gt;", ">")
                .replace("&quot;", '"').replace("&#39;", "'")
                .replace("&amp;", "&"))


def _render_md_image(alt: str, url: str) -> str:
    """![alt](url) -> валидный <figure><img>; только безопасные URL."""
    from html import escape
    url = url.strip()
    if url.startswith("./"):
        url = url[1:]  # ./static/... -> /static/...
    if not _ALLOWED_IMG_SRC_RE.match(url):
        return f"![{alt}]({url})"  # оставляем как есть (обычный текст)
    figclass = ' class="article-inline-figure"'
    img = (f'<img src="{escape(url, quote=True)}" '
           f'alt="{escape(alt or "", quote=True)}" loading="lazy">')
    if alt.strip():
        return (f'<figure{figclass}>{img}'
                f'<figcaption>{escape(alt, quote=True)}</figcaption></figure>')
    return f"<figure{figclass}>{img}</figure>"


def _markdown_emphasis(text: str) -> str:
    """Конвертирует markdown-выделения Telegram в HTML.

    Сначала обрабатываются пары **жирный** / __жирный__, затем *курсив* /
    _курсив_. Ссылки-плейсхолдеры (\x00LINKn\x00) и уже готовые теги не
    затрагиваются, одиночные '*'/'_' внутри слов сохраняются.
    """
    # жирный: **текст** / __текст__ (до курсива!)
    text = re.sub(r'(?:\*\*|__)((?!\s).+?(?<!\s))(?:\*\*|__)',
                  r'<strong>\1</strong>', text)
    # курсив: *текст* / _текст_ (без пробелов по краям, минимум 2 символа)
    text = re.sub(r'(?<!\w)(?:_|\*)((?!\s)[^*_\n]{2,}?(?<!\s))(?:_|\*)(?!\w)',
                  r'<em>\1</em>', text)
    return text


def strip_telegram_markup(text: str | None) -> str:
    """Полностью убирает разметку Telegram, оставляя только чистый текст.

    Ссылки <a href="...">текст</a> и [текст](url) превращаются просто в «текст»
    (сами ссылки удаляются), голые URL вырезаются, теги <b>/<i> и символы
    **/__ заменяются на обычный текст без выделения.
    Используется там, где ссылки не допускаются (например, FirstLine на главной).
    """
    if not text:
        return ""
    text = _TG_LINK_TAG_RE.sub(lambda m: m.group(1), text)
    text = _MD_LINK_RE.sub(lambda m: m.group(1), text)
    text = _TG_HTML_TAG_RE.sub("", text)
    text = _TG_EMPH_TAG_RE.sub("", text)
    text = _unescape_tg(text)
    text = _BARE_URL_RE.sub("", text)
    # пары **/__ и одиночные маркеры разметки
    text = re.sub(r'(?:\*\*|__)((?!\s).+?(?<!\s))(?:\*\*|__)', r'\1', text)
    text = _MD_MARKERS_RE.sub("", text)
    text = re.sub(r'(?<!\w)_((?!\s)[^_\n]{2,}?(?<!\s))_(?!\w)', r'\1', text)
    return text


def clean_telegram_markup(text: str | None, links: bool = True,
                          emphasis: bool = True) -> str:
    """Готовит telegram-текст для отображения на сайте.

    Эмодзи должны быть удалены заранее (strip_emoji).

    links=True  — ссылки (<a href="...">текст</a> и [текст](url)) остаются
                  кликабельными <a>; links=False — ссылки вырезаются, остаётся
                  только текст.
    emphasis=True — выделения <b>/<i> сохраняются как валидные HTML-теги
                  (отображаются стилизацией сайта); emphasis=False — теги и
                  markdown-символы (**, __) убираются, текст остаётся обычным.
    """
    if not text:
        return ""
    # сначала достаем текст ссылок, чтобы защититься от дальнейшей обработки
    placeholders: list[str] = []

    def _keep_link(m: re.Match) -> str:
        inner = m.group(1)
        href = re.search(r'''href\s*=\s*["']([^"']+)["']''', m.group(0))
        url = _unescape_tg(href.group(1)) if href else ""
        if not links or not url:
            return inner
        token = f"\x00LINK{len(placeholders)}\x00"
        placeholders.append(
            f'<a href="{url}" target="_blank" rel="noopener noreferrer">{inner}</a>'
        )
        return token

    def _keep_md_link(m: re.Match) -> str:
        inner, url = m.group(1), m.group(2)
        if not links or not url:
            return inner
        token = f"\x00LINK{len(placeholders)}\x00"
        placeholders.append(
            f'<a href="{url}" target="_blank" rel="noopener noreferrer">{inner}</a>'
        )
        return token

    text = _TG_LINK_TAG_RE.sub(_keep_link, text)
    text = _MD_LINK_FULL_RE.sub(_keep_md_link, text)
    if links:
        # картинки в markdown-синтаксисе (![..](http://..)) уже вынуты в
        # плейсхолдеры на уровне render_body; сюда они не доходят
        def _linkify(m: re.Match) -> str:
            url = m.group(0).rstrip('.,;:!?)»—-')
            tail = m.group(0)[len(url):]
            token = f"\x00LINK{len(placeholders)}\x00"
            placeholders.append(
                f'<a href="{url}" target="_blank" rel="noopener noreferrer">{url}</a>'
            )
            return token + tail
        text = _BARE_URL_LINK_RE.sub(_linkify, text)
        # голые ссылки на загруженные картинки (/static/uploads/...) тоже
        # превращаем в <img>, а не в <a>
        def _inline_upload(m: re.Match) -> str:
            url = m.group(1).rstrip('.,;:!?)»—-')
            token = f"\x00LINK{len(placeholders)}\x00"
            placeholders.append(_render_md_image("", url))
            return token
        text = _LOCAL_UPLOAD_URL_RE.sub(_inline_upload, text)
    if emphasis:
        # <b>/<i>/<em>/<strong> и пары **/__ превращаем в валидный HTML-тег —
        # сайт отобразит выделение стилизацией, а не текстом разметки
        text = _markdown_emphasis(text)
    else:
        # выделения не нужны: остаётся только сам текст
        text = _TG_EMPH_TAG_RE.sub("", text)
        text = re.sub(r'(?:\*\*|__)((?!\s).+?(?<!\s))(?:\*\*|__)', r'\1', text)
        text = re.sub(r'(?<!\w)(?:_|\*)((?!\s)[^*_\n]{2,}?(?<!\s))(?:_|\*)(?!\w)',
                      r'\1', text)
    # прочий мусор разметки (~~, ||, `, одиночные * между словами); '_' внутри
    # слов и цензурные вставки вида «Отс*си» сохраняем
    text = _MD_MARKERS_RE.sub("", text)
    text = _LONE_STAR_RE.sub("", text)
    # экранированные символы telegram-HTML (&lt; &gt; &amp; &quot;)
    text = _unescape_tg(text)
    for i, repl in enumerate(placeholders):
        text = text.replace(f"\x00LINK{i}\x00", repl)
    return text


def render_body(text: str) -> Markup:
    """Преобразует текст с переносами строк из Telegram в HTML-абзацы.

    Эмодзи удаляются полностью; ссылки остаются кликабельными, выделения
    (<b>/<i>/markdown) отображаются стилизацией сайта, а не текстом разметки.
    """
    if not text:
        return Markup("")
    text = strip_emoji(text)
    # <a href="...">текст</a> (в т.ч. с переносом строки внутри тега) вынимаем
    # в плейсхолдеры до разбиения на абзацы, чтобы разметка не «ломалась»
    links: list[str] = []

    def _stash(m: re.Match) -> str:
        token = f"\x00P{len(links)}\x00"
        inner = m.group(1).replace("\n", " ").strip()
        href = re.search(r'''href\s*=\s*["']([^"']+)["']''', m.group(0))
        url = href.group(1) if href else ""
        if url:
            links.append(
                f'<a href="{url}" target="_blank" rel="noopener noreferrer">{inner}</a>'
            )
        else:
            links.append(inner)
        return token

    def _stash_image(m: re.Match) -> str:
        """![alt](url) -> <figure><img> (картинки внутри текста статьи)."""
        token = f"\x00P{len(links)}\x00"
        links.append(_render_md_image(m.group(1), m.group(2)))
        return token

    # Картинки вынимаем первыми: их синтаксис ![..](..) пересекается со
    # ссылочным [..](..), и не должен быть съеден обработкой ссылок.
    text = _MD_IMAGE_RE.sub(_stash_image, text)
    # <a href="...">текст</a> (в т.ч. с переносом строки внутри тега) вынимаем
    # в плейсхолдеры до разбиения на абзацы, чтобы разметка не «ломалась»
    text = _TG_LINK_TAG_RE.sub(_stash, text)
    paragraphs = re.split(r'\n\s*\n', text)
    formatted = []
    for p in paragraphs:
        p = clean_telegram_markup(p).strip()
        for i, raw in enumerate(links):
            p = p.replace(f"\x00P{i}\x00", raw)
        if not p:
            continue
        if p.startswith('<'):
            formatted.append(p)
        else:
            p_with_br = p.replace('\n', '<br>')
            formatted.append(f'<p>{p_with_br}</p>')
    return Markup('\n'.join(formatted))


def first_line(caption: str | None, fallback: str = "Event") -> str:
    """Первая строка описания для карточек на главной.

    Без эмодзи и без какой-либо разметки: ссылки не допускаются,
    остаётся только чистый текст.
    """
    if not caption:
        return fallback
    for line in caption.splitlines():
        line = strip_telegram_markup(strip_emoji(line)).strip()
        if line:
            return line[:120]
    return fallback