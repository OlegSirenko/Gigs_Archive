"""
Dynamic sitemap.xml and robots.txt for Yandex Search (and other engines).

Yandex requirements honoured here:
  * absolute http(s) URLs, one <url> block per page;
  * <lastmod> in W3C Date and Time format (YYYY-MM-DDThh:mm:ss+03:00);
  * UTF-8 encoding + xml-stylesheet hint so the file renders in a browser;
  * robots.txt carries the Yandex-specific "Host:" directive and a
    "Sitemap:" line pointing at /sitemap.xml;
  * only publicly indexable pages are listed (approved posters, published
    articles, list pages). Admin/API/health endpoints are never included.

Both files are generated on the fly from the two SQLite databases, so they
always reflect fresh content — no cron job or manual regeneration needed.
Limits per Yandex: max 50 000 URLs and 10 MB per sitemap file; we cap the
number of poster/article URLs defensively well below that.
"""

from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import escape

from fastapi import FastAPI, Request
from fastapi.responses import Response

from web.articles_db import Article, get_article_session
from web.config import settings
from web.database import ModerationStatus, Poster, get_session

# Defensive caps (Yandex allows up to 50 000 URLs per file).
MAX_POSTER_URLS = 5000
MAX_ARTICLE_URLS = 2000

# Moscow time offset used for naive DB timestamps when emitting <lastmod>.
MSK = timezone(timedelta(hours=3))


def _base_url(request: Request) -> str:
    """Absolute site origin: SITE_URL env var wins, Host header is fallback."""
    if settings.site_url:
        # Sanitize: replace backslashes with forward slashes
        return settings.site_url.replace("\\", "/")
    forwarded_proto = request.headers.get("x-forwarded-proto")
    scheme = (forwarded_proto or request.url.scheme).replace("\\", "/")
    host = (request.headers.get("host") or request.url.netloc).replace("\\", "/")
    return f"{scheme}://{host}"


def _iso(dt) -> str | None:
    """Naive DB datetime -> ISO 8601 with Moscow offset (Yandex format)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=MSK)
    return dt.astimezone(MSK).strftime("%Y-%m-%dT%H:%M:%S%z")[:-2] + ":" \
        + dt.astimezone(MSK).strftime("%z")[-2:]


def _url_block(loc: str, lastmod: str | None = None,
               changefreq: str | None = None, priority: str | None = None) -> str:
    parts = [f"    <loc>{escape(loc)}</loc>"]
    if lastmod:
        parts.append(f"    <lastmod>{lastmod}</lastmod>")
    if changefreq:
        parts.append(f"    <changefreq>{changefreq}</changefreq>")
    if priority:
        parts.append(f"    <priority>{priority}</priority>")
    return "  <url>\n" + "\n".join(parts) + "\n  </url>"


def build_sitemap(base: str) -> str:
    base = base.rstrip("/")
    blocks: list[str] = []

    now = _iso(datetime.now(MSK))

    # ---- Static section pages ----
    blocks.append(_url_block(f"{base}/", now, "hourly", "1.0"))
    blocks.append(_url_block(f"{base}/posters", now, "daily", "0.9"))
    blocks.append(_url_block(f"{base}/articles", now, "weekly", "0.8"))

    # ---- Poster detail pages (approved events only) ----
    try:
        with get_session() as s:
            posters = (
                s.query(Poster.id, Poster.updated_at, Poster.created_at)
                .filter(Poster.status == ModerationStatus.APPROVED)
                .order_by(Poster.event_date.desc().nullslast(),
                          Poster.created_at.desc())
                .limit(MAX_POSTER_URLS)
                .all()
            )
        for pid, updated_at, created_at in posters:
            lm = _iso(updated_at or created_at)
            blocks.append(_url_block(f"{base}/posters/{pid}", lm, "monthly", "0.7"))
    except Exception as exc:  # site must still serve a valid sitemap
        print(f"[sitemap] posters skipped: {exc}")

    # ---- Article pages (published only) ----
    try:
        with get_article_session() as s:
            articles = (
                s.query(Article.slug, Article.updated_at, Article.published_at)
                .filter(Article.is_published.is_(True))
                .order_by(Article.published_at.desc().nullslast())
                .limit(MAX_ARTICLE_URLS)
                .all()
            )
        for slug, updated_at, published_at in articles:
            lm = _iso(updated_at or published_at)
            blocks.append(_url_block(f"{base}/articles/{slug}", lm, "monthly", "0.6"))
    except Exception as exc:
        print(f"[sitemap] articles skipped: {exc}")

    body = "\n".join(blocks)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}\n"
        "</urlset>\n"
    )


def build_robots(base: str, fallback_host: str = "") -> str:
    base = base.rstrip("/")
    host = (base.removeprefix("https://").removeprefix("http://")
            or fallback_host)
    return (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin/\n"
        "Disallow: /api/\n"
        "Disallow: /healthz\n"
        "\n"
        f"Sitemap: {base}/sitemap.xml\n"
    )


async def sitemap_endpoint(request: Request) -> Response:
    xml = build_sitemap(_base_url(request))
    return Response(content=xml.encode("utf-8"),
                    media_type="application/xml; charset=utf-8")


async def robots_endpoint(request: Request) -> Response:
    base = _base_url(request)
    text = build_robots(base, fallback_host=request.headers.get("host", ""))
    return Response(content=text.encode("utf-8"),
                    media_type="text/plain; charset=utf-8")


def register_seo_routes(app: FastAPI) -> None:
    """Attach /sitemap.xml and /robots.txt routes to the app."""
    app.add_route("/sitemap.xml", sitemap_endpoint, methods=["GET"],
                  name="sitemap")
    app.add_route("/robots.txt", robots_endpoint, methods=["GET"],
                  name="robots")
