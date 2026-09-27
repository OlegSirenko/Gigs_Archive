"""FastAPI application factory for the Gigs Archive web site."""

import os

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from web.config import settings
from web.database import init_web_db
from web.posters import first_line, poster_image_url, telegram_post_link
from web.helpers import render_body
from web.routes import admin as admin_routes
from web.routes import public as public_routes

WEB_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_ROOT = os.path.join(os.path.dirname(WEB_DIR), "web_static")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.site_title,
        docs_url=None, redoc_url=None,  # keep the site clean; use code as docs
    )

    # Ensure shared DB tables exist (bot tables + web_articles).
    init_web_db()

    # Static files: CSS/JS + imported Telegram poster images (/static/posters/...)
    os.makedirs(settings.posters_dir, exist_ok=True)
    app.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")

    # Shared template engine with our filters
    templates = Jinja2Templates(directory=os.path.join(WEB_DIR, "templates"))
    templates.env.filters["firstline"] = first_line
    templates.env.filters["posterimg"] = poster_image_url
    templates.env.filters["tglink"] = telegram_post_link
    templates.env.filters["renderbody"] = render_body
    app.state.templates = templates

    app.include_router(public_routes.router)
    app.include_router(admin_routes.router)

    @app.exception_handler(404)
    async def not_found(request: Request, exc):
        return templates.TemplateResponse("404.html", {
            "request": request,
            "site_title": settings.site_title,
            "telegram_channel": settings.telegram_channel,
            "current_user": None,
        }, status_code=404)

    @app.get("/healthz", response_class=HTMLResponse, include_in_schema=False)
    def health():
        ok = os.path.isfile(settings.database_path)
        return f"<pre>Gigs Archive web — DB: {settings.database_path} ({'found' if ok else 'not created yet'})</pre>"

    return app


app = create_app()
