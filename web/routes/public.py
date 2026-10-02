from datetime import datetime, timedelta
from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse  # <-- ДОБАВЬТЕ RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import joinedload, noload

from web.articles_db import Article, get_article_session
from web.auth import get_current_user
from web.config import settings
from web.database import ModerationStatus, Poster, User, get_session
from web.helpers import render_body
from web.posters import first_line, telegram_post_link
from web.helpers import poster_image_url
from web import i18n_web
import httpx
from fastapi.responses import HTMLResponse, StreamingResponse, Response
import aiohttp
from fastapi.responses import StreamingResponse
from fastapi.responses import RedirectResponse



router = APIRouter()

# Инициализация Jinja2 и фильтров (как в оригинальном проекте)
templates = Jinja2Templates(directory="web/templates")
templates.env.filters["firstline"] = first_line
templates.env.filters["posterimg"] = poster_image_url
templates.env.filters["tglink"] = telegram_post_link
templates.env.filters["renderbody"] = render_body
templates.env.filters["ru_date"] = i18n_web.ru_date
templates.env.filters["ru_datetime"] = i18n_web.ru_datetime
templates.env.filters["ru_date_short"] = i18n_web.ru_date_short
templates.env.filters["kind_label"] = i18n_web.kind_label


def _attach_posters(articles):
    """Articles live in a separate DB from posters, so the ORM relationship is
    gone; load linked posters manually and attach them as a plain attribute
    (readable by templates after the session is closed)."""
    ids = {a.poster_id for a in articles if a.poster_id}
    if not ids:
        return
    with get_session() as s:
        by_id = {p.id: p for p in s.query(Poster).filter(Poster.id.in_(ids)).all()}
    for a in articles:
        a.poster = by_id.get(a.poster_id)

def _ctx(request: Request, **extra):
    user = get_current_user(request)
    return {
        "site_title": settings.site_title,
        "telegram_channel": settings.telegram_channel,
        "current_user": user,
        "now": datetime.now(),
        "timedelta": timedelta,
        **extra,
    }

def _event_dt(p: Poster):
    """Нормализует дату события для корректного сравнения с now().

    Проблема: event_date может храниться как дата без времени (полночь,
    например из date-picker в боте) или как datetime с временем.
    Наивная полночь «сегодня» (00:00) при now()==04:45 ошибочно считалась
    прошедшей, хотя концерт в 20:00 ещё не начался.

    Правила:
    - если время события == 00:00 (дата без времени) — событие «весь день»:
      оно считается прошедшим только после окончания текущих суток;
    - иначе сравниваем дату+время напрямую.
    """
    dt = p.event_date
    if dt is None:
        return None
    if isinstance(dt, datetime):
        d = dt
    else:  # date без времени
        d = datetime.combine(dt, datetime.min.time())
    if d.hour == 0 and d.minute == 0 and d.second == 0:
        # дата хранится без времени -> событие актуально до конца суток
        return d.replace(hour=23, minute=59, second=59)
    return d


# ---------------- Home (Главная страница) ----------------
@router.get("/")
def home(request: Request):
    now = datetime.now()
    with get_session() as s:
        approved = s.query(Poster).filter(Poster.status == ModerationStatus.APPROVED)

        # 1. Скорые события: у них ещё НЕ наступили дата И время.
        #    Событие «сегодня в 20:00» при now()==04:45 остаётся скорым
        #    и получает зелёный бейдж «Скоро».
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        raw_upcoming = (
            approved.filter(
                or_(
                    Poster.event_date >= now,
                    Poster.event_date >= today_start,
                )
            )
            .order_by(Poster.event_date.asc())
            .limit(12)
            .all()
        )
        upcoming = sorted((p for p in raw_upcoming if _event_dt(p) >= now),
                          key=_event_dt)[:6]

        # 2. Недавно прошедшие события: реально завершились (наступили
        #    дата И время, либо законные сутки для событий без времени).
        raw_past = (
            approved.filter(Poster.event_date < now)
            .order_by(Poster.event_date.desc())
            .limit(12)
            .all()
        )
        past_events = sorted((p for p in raw_past if _event_dt(p) < now),
                             key=_event_dt, reverse=True)[:3]

        # Бейдж «Скоро»: событие пройдёт в течение ближайших суток
        soon_cutoff = timedelta(hours=24)
        for p in upcoming:
            edt = _event_dt(p)
            p.is_soon = bool(edt and now <= edt <= now + soon_cutoff)

        total_events = s.query(Poster).filter(Poster.status == ModerationStatus.APPROVED).count()

    # Последние опубликованные статьи — из отдельной БД статей (articles.db)
    with get_article_session() as sa:
        recent_articles = (
            sa.query(Article)
            .filter(Article.is_published.is_(True))
            .order_by(Article.published_at.desc().nullslast(),
                      Article.updated_at.desc())
            .limit(3)
            .all()
        )
        total_articles = (sa.query(Article)
                          .filter(Article.is_published.is_(True)).count())

    return templates.TemplateResponse(request, "index.html", _ctx(
        request, 
        upcoming=upcoming,
        past_events=past_events, # Передаем новые данные
        total_events=total_events,
        recent_articles=recent_articles,
        total_articles=total_articles,
    ))


# ---------------- Posters (Афиши) ----------------
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

    # Зелёный бейдж «Скоро»: событие ещё не прошло И пройдёт в течение суток
    now = datetime.now()
    soon_cutoff = now + timedelta(hours=24)
    for p in items:
        edt = _event_dt(p)
        p.is_soon = bool(edt and now <= edt <= soon_cutoff)

    pages = max(1, (total + per_page - 1) // per_page)
    return templates.TemplateResponse(request, "posters.html", _ctx(
        request, posters=items, q=q, page=page, pages=pages, total=total,
    ))


@router.get("/posters/{poster_id}")
def poster_detail(request: Request, poster_id: int):
    print(f"!!! [ROUTE] Запрос на /posters/{poster_id}")
    
    with get_session() as s:
        poster = (s.query(Poster)
                  .outerjoin(User, Poster.user_id == User.telegram_id)
                  .options(joinedload(Poster.user))
                  .filter(
                      Poster.id == poster_id,
                      Poster.status == ModerationStatus.APPROVED,
                  ).first())
        
        print(f"!!! [ROUTE] Постер из БД: {'НАЙДЕН (ID=' + str(poster.id) + ')' if poster else 'НЕ НАЙДЕН'}")
        
        if not poster:
            return templates.TemplateResponse(request, "404.html", _ctx(request), status_code=404)
        
        poster.view_count = (poster.view_count or 0) + 1
        s.commit()
        
        # !!! ПРЯМОЙ ВЫЗОВ ФУНКЦИИ В ОБХОД ФИЛЬТРОВ JINJA2 !!!
        print("!!! [ПРЯМОЙ ВЫЗОВ] Вызываю poster_image_url напрямую из Python-кода...")
        manual_url = poster_image_url(poster)
        print(f"!!! [ПРЯМОЙ ВЫЗОВ] Результат прямого вызова: {manual_url}")
        
        return templates.TemplateResponse(request, "poster_detail.html", _ctx(
            request, 
            poster=poster,
            manual_test_url=manual_url  # <-- Передаем результат в шаблон
        ))

# ---------------- Articles (Статьи) ----------------
@router.get("/articles")
def articles_list(
    request: Request,
    kind: str = Query("", pattern="^(|article|interview|review)$"),
    page: int = Query(1, ge=1),
    per_page: int = 12,
):
    with get_article_session() as s:
        query = s.query(Article).filter(Article.is_published.is_(True))
        if kind:
            query = query.filter(Article.kind == kind)
        total = query.count()
        items = (query.order_by(Article.published_at.desc())
                 .offset((page - 1) * per_page)
                 .limit(per_page)
                 .all())
    _attach_posters(items)
    pages = max(1, (total + per_page - 1) // per_page)
    return templates.TemplateResponse(request, "articles.html", _ctx(
        request, articles=items, kind=kind, page=page, pages=pages, total=total,
    ))

@router.get("/articles/{slug}")
def article_detail(request: Request, slug: str):
    with get_article_session() as s:
        article = (s.query(Article)
                   .filter(
                       Article.slug == slug, Article.is_published.is_(True)
                   ).first())
        if not article:
            return templates.TemplateResponse(request, "404.html", _ctx(request), status_code=404)
    _attach_posters([article])
    return templates.TemplateResponse(request, "article_detail.html", _ctx(
        request, article=article,
    ))


@router.get("/api/poster-image/{poster_id}")
async def proxy_poster_image(poster_id: int):
    """
    Безопасно проксирует картинку с Telegram. 
    Токен бота остается на сервере и никогда не передается в браузер.
    """
    with get_session() as s:
        poster = s.query(Poster).filter(
            Poster.id == poster_id,
            Poster.status == ModerationStatus.APPROVED
        ).first()
        
        if not poster or not poster.photo_file_id:
            return Response(content="Not Found", status_code=404)
    
    from web.config import settings
    
    # 1. Запрашиваем путь к файлу через Bot API (внутри сервера)
    file_info_url = f"https://api.telegram.org/bot{settings.bot_token}/getFile"
    
    async with httpx.AsyncClient() as client:
        file_resp = await client.get(file_info_url, params={"file_id": poster.photo_file_id})
        file_data = file_resp.json()
        
        if not file_data.get("ok"):
            return Response(content="Telegram API Error", status_code=502)
            
        file_path = file_data["result"]["file_path"]
        
        # 2. Скачиваем саму картинку с CDN Telegram (внутри сервера)
        cdn_url = f"https://api.telegram.org/file/bot{settings.bot_token}/{file_path}"
        img_resp = await client.get(cdn_url)
        
        if img_resp.status_code != 200:
            return Response(content="Failed to download image", status_code=502)
        
        # 3. Отдаем байты картинки браузеру напрямую из памяти нашего сервера
        # Браузер видит только ответ от НАШЕГО домена. Токен скрыт.
        return Response(
            content=img_resp.content,
            media_type=img_resp.headers.get("content-type", "image/jpeg"),
            headers={
                "Cache-Control": "public, max-age=86400", # Разрешаем браузеру кэшировать на 1 день
            }
        )