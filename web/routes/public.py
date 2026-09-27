"""Public site routes: home, posters (re-posted from Telegram), articles."""

from datetime import datetime

from fastapi import APIRouter, Query, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import joinedload, lazyload, noload

from web.auth import get_current_user
from web.config import settings
from web.database import ModerationStatus, Poster, User, Article, get_session
from web.helpers import render_body
from web.posters import first_line, poster_image_url, telegram_post_link

router = APIRouter()

templates = Jinja2Templates(directory="web/templates")
templates.env.filters["firstline"] = first_line
templates.env.filters["posterimg"] = poster_image_url
templates.env.filters["tglink"] = telegram_post_link
templates.env.filters["renderbody"] = render_body
noload_poster = noload(Article.poster)


def _ctx(request: Request, **extra):
    """Template context. `request` is passed to TemplateResponse separately."""
    user = get_current_user(request)
    return {
        "site_title": settings.site_title,
        "telegram_channel": settings.telegram_channel,
        "current_user": user,
        "now": datetime.now(),
        **extra,
    }


# ---------------- Home ----------------

@router.get("/")
def home(request: Request):
    with get_session() as s:
        upcoming = (
            s.query(Poster)
            .filter(
                Poster.status == ModerationStatus.APPROVED,
                Poster.event_date >= datetime.now(),
            )
            .order_by(Poster.event_date.asc())
            .limit(6)
            .all()
        )
        recent_articles = (
            s.query(Article)
            .outerjoin(Poster, Article.poster_id == Poster.id)
            .options(joinedload(Article.poster))
            .filter(Article.is_published.is_(True))
            .order_by(Article.published_at.desc())
            .limit(3)
            .all()
        )
        total_events = (
            s.query(Poster)
            .filter(Poster.status == ModerationStatus.APPROVED)
            .count()
        )
    return templates.TemplateResponse(request, "index.html", _ctx(
        request, upcoming=upcoming, recent_articles=recent_articles,
        total_events=total_events,
    ))


# ---------------- Posters (events re-posted from Telegram) ----------------

@router.get("/posters")
def posters_list(
    request: Request,
    q: str = Query("", max_length=100),
    page: int = Query(1, ge=1),
    per_page: int = 12,
):
    with get_session() as s:
        query = s.query(Poster).filter(Poster.status == ModerationStatus.APPROVED)
        if q.strip():
            like = f"%{q.strip()}%"
            query = query.filter(or_(Poster.caption.ilike(like),
                                     Poster.moderator_notes.ilike(like)))
        total = query.count()
        items = (
            query.order_by(Poster.event_date.desc().nullslast(),
                           Poster.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
    pages = max(1, (total + per_page - 1) // per_page)
    return templates.TemplateResponse(request, "posters.html", _ctx(
        request, posters=items, q=q, page=page, pages=pages, total=total,
    ))


@router.get("/posters/{poster_id}")
def poster_detail(request: Request, poster_id: int):
    with get_session() as s:
        poster = (s.query(Poster)
                  .outerjoin(User, Poster.user_id == User.telegram_id)
                  .options(joinedload(Poster.user))
                  .filter(
                      Poster.id == poster_id,
                      Poster.status == ModerationStatus.APPROVED,
                  ).first())
        if not poster:
            return templates.TemplateResponse(request, "404.html", _ctx(request), status_code=404)
        related_articles = (
            s.query(Article)
            .options(noload_poster)
            .filter(Article.poster_id == poster_id,
                    Article.is_published.is_(True))
            .order_by(Article.published_at.desc())
            .all()
        )
        # simple view counter
        poster.view_count = (poster.view_count or 0) + 1
        s.commit()
    return templates.TemplateResponse(request, "poster_detail.html", _ctx(
        request, poster=poster, related_articles=related_articles,
    ))


# ---------------- Articles (admin long-form content) ----------------

@router.get("/articles")
def articles_list(
    request: Request,
    kind: str = Query("", pattern="^(|article|interview|review)$"),
    page: int = Query(1, ge=1),
    per_page: int = 12,
):
    with get_session() as s:
        query = s.query(Article).filter(Article.is_published.is_(True))
        if kind:
            query = query.filter(Article.kind == kind)
        total = query.count()
        items = (
            query.outerjoin(Poster, Article.poster_id == Poster.id)
            .options(joinedload(Article.poster))
            .order_by(Article.published_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
    pages = max(1, (total + per_page - 1) // per_page)
    return templates.TemplateResponse(request, "articles.html", _ctx(
        request, articles=items, kind=kind, page=page, pages=pages, total=total,
    ))


@router.get("/articles/{slug}")
def article_detail(request: Request, slug: str):
    with get_session() as s:
        article = (s.query(Article)
                   .outerjoin(Poster, Article.poster_id == Poster.id)
                   .options(joinedload(Article.poster))
                   .filter(
                       Article.slug == slug, Article.is_published.is_(True)
                   ).first())
        if not article:
            return templates.TemplateResponse(request, "404.html", _ctx(request), status_code=404)
    return templates.TemplateResponse(request, "article_detail.html", _ctx(
        request, article=article,
    ))
