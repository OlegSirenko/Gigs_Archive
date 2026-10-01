"""Admin panel routes: login, article CRUD, dashboard.

Access is restricted to web admins (ADMIN_USERNAMES / web/admins.json —
Telegram usernames of the same people who moderate in the bot).
"""

from datetime import datetime

from sqlalchemy.orm import noload
from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from web.articles_db import Article, get_article_session
from web.auth import (
    create_session_cookie,
    get_current_user,
    logout_response,
    require_admin,
)
from web.config import settings
from web.database import ModerationStatus, Poster, get_session
from web.helpers import slugify, unique_slug
from web.posters import first_line, poster_image_url

router = APIRouter(prefix="/admin")

from web import i18n_web
from web.i18n_web import KIND_LABELS as KINDS

templates = Jinja2Templates(directory="web/templates")
templates.env.filters["firstline"] = first_line
templates.env.filters["posterimg"] = poster_image_url
templates.env.filters["ru_date"] = i18n_web.ru_date
templates.env.filters["ru_datetime"] = i18n_web.ru_datetime
templates.env.filters["ru_date_short"] = i18n_web.ru_date_short
templates.env.filters["kind_label"] = i18n_web.kind_label


def _ctx(request: Request, **extra):
    """Template context. `request` is passed to TemplateResponse separately."""
    user = get_current_user(request)
    return {
        "site_title": settings.site_title,
        "telegram_channel": settings.telegram_channel,
        "current_user": user,
        "kinds": KINDS,
        **extra,
    }


# ---------------- Login / logout ----------------

@router.get("/login")
def login_form(request: Request, next: str = "/admin", error: str = "",
               username: str = ""):
    user = get_current_user(request)
    if user and user.is_admin:
        return RedirectResponse("/admin", status_code=302)
    return templates.TemplateResponse(request, "admin/login.html",
                                      _ctx(request, next=next, error=error,
                                           username=username))


@router.post("/login")
def login(request: Request, username: str = Form(...),
          password: str = Form(""), next: str = Form("/admin")):
    """Admin sign-in: Telegram nickname from the admin list + permanent password.

    Passwords are generated per admin (`python -m web.manage gen-passwords`)
    and stored only as PBKDF2 hashes in web/admin_passwords.json.
    """
    username = username.strip().lstrip("@")
    if not username or ".." in next or next.startswith("//"):
        next = "/admin"

    def denied(message: str, status_code: int = 403):
        return templates.TemplateResponse(
            request, "admin/login.html",
            _ctx(request, next=next, error=message, username=username),
            status_code=status_code,
        )

    if not settings.is_admin_username(username):
        return denied("Access denied: this username is not on the admin list.")

    # Nickname alone is never enough any more — a permanent password is required.
    if not password:
        return denied("Введите пароль администратора. / Please enter your "
                      "admin password.", status_code=401)

    if not settings.has_admin_password(username):
        return denied(f"No password generated for @{username} yet. An existing "
                      "admin must run: python -m web.manage gen-passwords "
                      f"--for {username.lower()}")

    if not settings.verify_admin_password(username, password):
        return denied("Неверный пароль. / Incorrect password.")

    response = RedirectResponse(next if next.startswith("/admin") else "/admin",
                                status_code=302)
    response.set_cookie(
        settings.session_cookie_name,
        create_session_cookie(username.lower()),
        max_age=settings.session_max_age,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/logout")
def logout(request: Request):
    return logout_response("/")


# ---------------- Admin team & permanent passwords ----------------

@router.get("/admins")
def admins_page(request: Request):
    """Admin list with password status. Nicknames + hashes only, never secrets."""
    require_admin(request)
    from web.passwords import password_store

    hashes = settings.admin_password_hashes()
    admins = []
    for username in sorted(settings.all_admin_usernames()):
        record = hashes.get(username)
        admins.append({
            "username": username,
            "has_password": record is not None,
            "kdf": (record or {}).get("kdf", ""),
            "iterations": (record or {}).get("iterations", ""),
        })
    return templates.TemplateResponse(request, "admin/admins.html",
                                      _ctx(request, admins=admins))


@router.post("/admins/{username}/rotate")
def rotate_password(request: Request, username: str):
    """Issue a NEW permanent password for an admin and show it once."""
    user = require_admin(request)
    from web.passwords import password_store

    username = username.lstrip("@").lower()
    if not settings.is_admin_username(username):
        return RedirectResponse("/admin/admins?error=not_admin", status_code=302)

    new_password = password_store.generate_for(username)
    # The plaintext can only travel out of here once — straight to the browser.
    response = templates.TemplateResponse(
        request, "admin/password_shown.html",
        _ctx(request, target=username, password=new_password,
             actor=user.username),
    )
    response.headers["Cache-Control"] = "no-store"
    return response


# ---------------- Dashboard ----------------

@router.get("")
@router.get("/")
def dashboard(request: Request):
    user = require_admin(request)
    # Articles live in their own DB file (articles.db); posters in the bot DB.
    with get_article_session() as as_:
        articles = (as_.query(Article)
                    .order_by(Article.updated_at.desc()).all())
    with get_session() as s:
        stats = {
            "posters_total": s.query(Poster).count(),
            "posters_approved": s.query(Poster).filter(
                Poster.status == ModerationStatus.APPROVED).count(),
            "posters_pending": s.query(Poster).filter(
                Poster.status == ModerationStatus.PENDING).count(),
            "articles_total": len(articles),
            "articles_published": sum(1 for a in articles if a.is_published),
        }
    no_password = [a for a in sorted(settings.all_admin_usernames())
                   if not settings.has_admin_password(a)]
    return templates.TemplateResponse(request, "admin/dashboard.html",
                                      _ctx(request, articles=articles, stats=stats,
                                           admins_without_password=no_password))


# ---------------- Article CRUD ----------------

@router.get("/articles/new")
def article_new(request: Request):
    require_admin(request)
    with get_session() as s:
        posters = (s.query(Poster)
                   .filter(Poster.status == ModerationStatus.APPROVED)
                   .order_by(Poster.created_at.desc()).limit(200).all())
    return templates.TemplateResponse(request, "admin/article_form.html", _ctx(
        request, article=None, posters=posters,
        form={}, selected_poster_id="",
    ))


@router.post("/articles/new")
def article_create(
    request: Request,
    title: str = Form(...),
    kind: str = Form("article"),
    lead: str = Form(""),
    body: str = Form(...),
    cover_image_url: str = Form(""),
    poster_id: str = Form(""),
    publish: str = Form(""),
):
    user = require_admin(request)
    kind = kind if kind in KINDS else "article"
    with get_article_session() as s:
        article = Article(
            title=title.strip()[:200],
            slug=unique_slug(s, Article, slugify(title)),
            lead=lead.strip(),
            body=body,
            cover_image_url=cover_image_url.strip() or None,
            kind=kind,
            author_username=user.username,
            poster_id=int(poster_id) if poster_id.isdigit() else None,
            is_published=bool(publish),
            published_at=datetime.now() if publish else None,
        )
        s.add(article)
        s.commit()
        new_id = article.id
    return RedirectResponse(f"/admin/articles/{new_id}/edit?created=1", status_code=302)


@router.get("/articles/{article_id}/edit")
def article_edit(request: Request, article_id: int, created: str = "", saved: str = ""):
    require_admin(request)
    with get_article_session() as s:
        article = s.query(Article).get(article_id)
        if not article:
            return templates.TemplateResponse(request, "404.html", _ctx(request), status_code=404)
        form = {
            "title": article.title,
            "kind": article.kind,
            "lead": article.lead or "",
            "body": article.body,
            "cover_image_url": article.cover_image_url or "",
        }
    with get_session() as s:
        posters = (s.query(Poster)
                   .filter(Poster.status == ModerationStatus.APPROVED)
                   .order_by(Poster.created_at.desc()).limit(200).all())
    return templates.TemplateResponse(request, "admin/article_form.html", _ctx(
        request, article=article, posters=posters, form=form,
        selected_poster_id=str(article.poster_id or ""),
        flash=("Article created." if created else
               "Article saved." if saved else ""),
    ))


@router.post("/articles/{article_id}/edit")
def article_update(
    request: Request,
    article_id: int,
    title: str = Form(...),
    kind: str = Form("article"),
    lead: str = Form(""),
    body: str = Form(...),
    cover_image_url: str = Form(""),
    poster_id: str = Form(""),
    publish: str = Form(""),
):
    require_admin(request)
    kind = kind if kind in KINDS else "article"
    with get_article_session() as s:
        article = s.query(Article).get(article_id)
        if not article:
            return templates.TemplateResponse(request, "404.html", _ctx(request), status_code=404)
        new_title = title.strip()[:200]
        if new_title != article.title:
            article.slug = unique_slug(s, Article, slugify(new_title),
                                       exclude_id=article.id)
            article.title = new_title
        article.kind = kind
        article.lead = lead.strip()
        article.body = body
        article.cover_image_url = cover_image_url.strip() or None
        article.poster_id = int(poster_id) if poster_id.isdigit() else None
        was_published = article.is_published
        article.is_published = bool(publish)
        if article.is_published and not was_published:
            article.published_at = datetime.now()
        s.commit()
    return RedirectResponse(f"/admin/articles/{article_id}/edit?saved=1", status_code=302)


@router.post("/articles/{article_id}/delete")
def article_delete(request: Request, article_id: int):
    require_admin(request)
    with get_article_session() as s:
        article = s.query(Article).get(article_id)
        if article:
            s.delete(article)
            s.commit()
    return RedirectResponse("/admin", status_code=302)
