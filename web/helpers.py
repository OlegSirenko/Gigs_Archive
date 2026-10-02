# web/helpers.py
"""Slug + tiny markdown helpers shared by routes."""

import re
import unicodedata
import requests
from markupsafe import Markup

# Маркеры-плейсхолдеры для render_body: U+0000 гарантированно отсутствует в
# пользовательском тексте (обычный текст его не содержит), поэтому маркеры
# вида \x00SEP\x00 (разделитель «---») и \x00Pn\x00 (готовый HTML) невозможно
# случайно «съесть» обработкой markdown-выделений.
SEP_TOKEN = chr(0) + "SEP" + chr(0)


def _ptoken(i: int) -> str:
    """Маркер готового HTML-блока (картинка/ссылка) с индексом i."""
    return chr(0) + f"P{i}" + chr(0)


def _is_block_markup(p: str) -> bool:
    """True, если абзац — готовая HTML-разметка (<figure>/<hr>/<blockquote>…)."""
    if p.startswith("<"):
        return True
    # абзацы из нескольких блоков, разделённых маркерами \x00P0\x00 и т.п.
    stripped = re.sub(r"[ \t]*" + chr(0) + r"P\d+" + chr(0) + r"[ \t]*",
                      "", p)
    return not stripped and chr(0) + "P" in p

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
    # служебные маркеры-плейсхолдеры (\x00... — ссылки, картинки, разделители)
    # не должны склеиваться с соседними переносами строк: иначе «\n +\n»
    # схлопнется в один перевод и абзац-разделитель «---» перестанет быть
    # отдельным блоком
    cleaned = re.sub(r"([^\x00\x0a]) +(\n)", r"\1\2", cleaned)
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
# пары **/__, ~~ и <s></s>: их обрабатывает _markdown_emphasis (пары ~~ ->
# <s>зачёркнутый</s>), поэтому здесь остаются только одиночные ~, |, ` —
# раньше пары ~~ вырезались как «мусор» и зачёркнутый текст не отображался
# в просмотре опубликованной статьи
_MD_MARKERS_RE = re.compile(r'[~|`]')
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


_H_RE = re.compile(r"(?m)^\s*#{1,6}\s+(.+?)\s*$")
_QUOTE_RE = re.compile(r"(?m)^\s*>+ ?(.*)$")
_UL_RE = re.compile(r"(?m)^\s*[-\u2022]\s+(.+)$")
_OL_RE = re.compile(r"(?m)^\s*(\d+)[.)]\s+(.+)$")


def _render_blocks(p: str) -> str:
    """Блочный markdown внутри абзаца: # заголовки, > цитаты, списки.

    Возвращает строку без обёртки <p>, если весь абзац — блочный элемент;
    иначе — None (абзац остаётся обычным текстом).
    """
    lines = p.split("\n")
    # подзаголовки: «## Текст» (## -> h3, ### -> h4 и т.д.)
    if all(re.match(r"^\s*#{1,6}\s+", l) for l in lines if l.strip()):
        out = []
        for l in lines:
            m = re.match(r"^\s*(#{1,6})\s+(.+?)\s*$", l)
            if m:
                lvl = min(len(m.group(1)) + 1, 5)
                out.append(f'<h{lvl} class="article-subhead">{m.group(2)}</h{lvl}>')
        return "\n".join(out)
    # цитаты: каждая непустая строка начинается с «>»
    if all(re.match(r"^\s*>", l) for l in lines if l.strip()):
        inner = "<br>".join(re.sub(r"^\s*>+ ?", "", l) for l in lines if l.strip())
        return f"<blockquote>{inner}</blockquote>"
    # одиночная строка-картинка «![](..)»: не абзац — блок обрабатывается
    # отдельно в render_body; сюда приходить не должна, но на всякий случай
    # отдаём её как есть (без обёртки <p>)
    if _MD_IMAGE_RE.fullmatch(p.strip()):
        return p.strip()
    # маркированный список
    if all(re.match(r"^\s*[-\u2022]\s+", l) for l in lines if l.strip()) \
            and any(_UL_RE.match(l) for l in lines):
        items = "".join(f"<li>{m}</li>" for m in _UL_RE.findall(p))
        return f'<ul class="article-list">{items}</ul>'
    # нумерованный список
    if all(re.match(r"^\s*\d+[.)]\s+", l) for l in lines if l.strip()) \
            and any(_OL_RE.match(l) for l in lines):
        items = "".join(f"<li>{t}</li>" for _, t in _OL_RE.findall(p))
        return f'<ol class="article-list">{items}</ol>'
    return ""


def _has_block_markup(p: str) -> bool:
    """True, если в абзаце есть маркер-плейсхолдер \x00Pn\x00 (картинка/ссылка)."""
    return chr(0) + "P" in p


def _markdown_emphasis(text: str) -> str:
    """Конвертирует markdown-выделения Telegram в HTML.

    Сначала обрабатываются пары **жирный** / __жирный__, затем *курсив* /
    _курсив_. Маркеры-плейсхолдеры (\x00...) на время обработки маскируются
    символом-страхом, чтобы жадные пары __..__ / *...* их не «съели».
    """
    nul = chr(0)
    guard = "\x1f"  # unit separator — тоже не встречается в пользовательском тексте
    masked: list[str] = []

    def _mask(m: re.Match) -> str:
        masked.append(m.group(0))
        return guard + f"{len(masked) - 1:04d}" + guard

    text = re.sub(nul + r"(?:SEP|P\d+|LINK\d+)" + nul, _mask, text)
    # жирный: **текст** / __текст__ (до курсива!)
    text = re.sub(r"__((?!\s).+?(?<!\s))__", r"<strong>\1</strong>", text)
    text = re.sub(r"\*\*((?!\s).+?(?<!\s))\*\*", r"<strong>\1</strong>", text)
    # зачёркнутый: ~~текст~~ (пары обрабатываем здесь; в «мусорных» маркерах
    # пары ~~ больше нет — иначе зачёркнутый текст исчезал из просмотра статьи)
    text = re.sub(r"~~((?!\s).+?(?<!\s))~~", r"<s>\1</s>", text)
    # курсив: *текст* / _текст_ (без пробелов по краям, минимум 2 символа,
    # не внутри слов)
    text = re.sub(r"(?<![\w*_])[*_]((?!\s)[^*_\n]{2,}?(?<!\s))[*_](?![\w*_])",
                  r"<em>\1</em>", text)
    # возвращаем замаскированные маркеры
    for i, tok in enumerate(masked):
        text = text.replace(guard + f"{i:04d}" + guard, tok)
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
        token = chr(0) + f"LINK{len(placeholders)}" + chr(0)
        placeholders.append(
            f'<a href="{url}" target="_blank" rel="noopener noreferrer">{inner}</a>'
        )
        return token

    def _keep_md_link(m: re.Match) -> str:
        inner, url = m.group(1), m.group(2)
        if not links or not url:
            return inner
        token = chr(0) + f"LINK{len(placeholders)}" + chr(0)
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
            token = chr(0) + f"LINK{len(placeholders)}" + chr(0)
            placeholders.append(
                f'<a href="{url}" target="_blank" rel="noopener noreferrer">{url}</a>'
            )
            return token + tail
        text = _BARE_URL_LINK_RE.sub(_linkify, text)
        # голые ссылки на загруженные картинки (/static/uploads/...) тоже
        # превращаем в <img>, а не в <a>
        def _inline_upload(m: re.Match) -> str:
            url = m.group(1).rstrip('.,;:!?)»—-')
            token = chr(0) + f"LINK{len(placeholders)}" + chr(0)
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
        text = text.replace(chr(0) + f"LINK{i}" + chr(0), repl)
    return text


def render_body(text: str) -> Markup:
    """Преобразует markdown-текст статьи в HTML-абзацы.

    Эмодзи удаляются; ссылки остаются кликабельными, выделения
    (**жирный**, *курсив*) отображаются стилизацией сайта, а не текстом
    разметки. Картинки ![подпись](url) превращаются в <figure> с подписью —
    «картинка внутри текста», как на realt.onliner.by. Строка из одних
    «---» становится разделителем <hr class="article-sep"> между блоками.
    """
    if not text:
        return Markup("")
    text = strip_emoji(text)
    # Готовые HTML-блоки (картинки, ссылки) вынимаем в плейсхолдеры вида
    # \x00Pn\x00 до разбиения на абзацы и до обработки разметки, чтобы её
    # синтаксис не пересекался со ссылочным [..](..) и не «ломался».
    blocks: list[str] = []

    def _stash(m: re.Match) -> str:
        token = chr(0) + f"P{len(blocks)}" + chr(0)
        inner = m.group(1).replace("\n", " ").strip()
        href = re.search(r'''href\s*=\s*["']([^"']+)["']''', m.group(0))
        url = href.group(1) if href else ""
        if url:
            blocks.append(
                f'<a href="{url}" target="_blank" rel="noopener noreferrer">{inner}</a>'
            )
        else:
            blocks.append(inner)
        return token

    def _stash_image(m: re.Match) -> str:
        """![alt](url) -> <figure><img> (картинки внутри текста статьи)."""
        token = chr(0) + f"P{len(blocks)}" + chr(0)
        blocks.append(_render_md_image(m.group(1), m.group(2)))
        return token

    # Картинки вынимаем первыми: их синтаксис ![..](..) пересекается со
    # ссылочным [..](..), и не должен быть съеден обработкой ссылок.
    text = _MD_IMAGE_RE.sub(_stash_image, text)
    # <a href="...">текст</a> (в т.ч. с переносом строки внутри тега)
    text = _TG_LINK_TAG_RE.sub(_stash, text)
    # markdown-разделители «---» (строка из 3+ дефисов) -> маркер-плейсхолдер,
    # который ниже превратится в <hr class="article-sep"> (как на realt.onliner.by:
    # между смысловыми блоками текста стоят разделители)
    text = re.sub(r'(?m)^\s*-{3,}\s*$', SEP_TOKEN, text)
    # абзацы разделяются пустой строкой; разделитель-маркер тоже должен
    # начинать новый блок (в т.ч. когда «---» идёт сразу после картинки,
    # без пустой строки перед ней)
    text = re.sub(SEP_TOKEN, "\n\n" + SEP_TOKEN + "\n\n", text)

    nul = chr(0)
    parts_out: list[str] = []

    def _emit(chunk: str) -> None:
        """Один смысловой блок текста -> <p>/<h*>/<blockquote>/<ul>..."""
        chunk = clean_telegram_markup(chunk).strip()
        if not chunk:
            return
        block = _render_blocks(chunk)
        if block:
            parts_out.append(block)
        else:
            parts_out.append(f"<p>{chunk.replace(chr(10), '<br>')}</p>")

    for para in re.split(r"\n\s*\n", text):
        # нормализуем пробелы вокруг маркеров перед обработкой
        para = re.sub(r"[ \t]*" + nul + r"(?:SEP|P\d+)" + nul + r"[ \t]*",
                      lambda m: m.group(0).strip(" \t"), para)
        # режем абзац на чередование «текст» и «маркер-блок» (картинки/ссылки)
        pieces = re.split(r"(" + nul + r"P\d+" + nul + r")", para)
        first_text = True
        for piece in pieces:
            seps = piece.count(SEP_TOKEN)
            piece = piece.replace(SEP_TOKEN, "")
            stripped = piece.strip()
            if re.fullmatch(nul + r"P\d+" + nul, stripped or "\x01"):
                # готовый HTML-блок (figure/ссылка) — вставляем как есть;
                # перед картинкой после текста — молчаливый разделитель не нужен,
                # картинки и так визуально отделены
                parts_out.append(stripped)
                continue
            if seps:
                parts_out.extend(['<hr class="article-sep">'] * seps)
            if not stripped:
                continue
            _emit(piece)

    html = "\n".join(parts_out)
    # подставляем готовые блоки; порядок не важен — токены уникальны
    for i, raw in enumerate(blocks):
        html = html.replace(chr(0) + f"P{i}" + chr(0), raw)
    # на всякий случай: любые оставшиеся маркеры (например, из битого ввода)
    html = re.sub(nul + r"(?:SEP|P\d+|LINK\d+)" + nul, "", html)
    return Markup(html)


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

