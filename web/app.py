import os
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

from web.config import settings
from web.articles_db import articles_db_path, init_articles_db
from web.database import init_web_db
from web.routes import public as public_routes
from web.routes import admin as admin_routes

# ИСПРАВЛЕННЫЕ ИМПОРТЫ (разделены по правильным файлам)
from web.helpers import render_body, first_line, poster_image_url
from web.posters import telegram_post_link

from web import i18n_web

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.site_title,
        docs_url=None, 
        redoc_url=None,
    )

    # 0. Гарантируем существование таблиц:
    #    - общая база бота (users, posters) — gigs_archive.db
    #    - отдельная база статей (web_articles) — articles.db
    # create_all() идемпотентен: уже созданные таблицы и данные не трогаются.
    init_web_db()
    init_articles_db()

    # 1. Подключение статических файлов (CSS, JS, картинки)
    static_dir = os.path.join(os.path.dirname(__file__), "..", "web_static")
    os.makedirs(static_dir, exist_ok=True)
    os.makedirs(settings.posters_dir, exist_ok=True)
    
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    templates_dir = os.path.join(os.path.dirname(__file__), "templates")
    templates = Jinja2Templates(directory=templates_dir)
    
    templates.env.filters["firstline"] = first_line
    templates.env.filters["posterimg"] = poster_image_url
    
    # !!! ДОБАВИТЬ ЭТИ ДВЕ СТРОКИ !!!
    print(f"!!! [APP.PY] Фильтр 'posterimg' указывает на функцию из модуля: {poster_image_url.__module__}")
    print(f"!!! [APP.PY] Адрес функции в памяти: {id(poster_image_url)}")
    
    templates.env.filters["tglink"] = telegram_post_link
    templates.env.filters["renderbody"] = render_body
    templates.env.filters["ru_date"] = i18n_web.ru_date
    templates.env.filters["ru_datetime"] = i18n_web.ru_datetime
    templates.env.filters["ru_date_short"] = i18n_web.ru_date_short
    templates.env.filters["kind_label"] = i18n_web.kind_label
    
    app.state.templates = templates

    # 3. Подключение роутеров (самое важное!)
    app.include_router(public_routes.router)
    app.include_router(admin_routes.router)

    # 4. Обработчик 404
    @app.exception_handler(404)
    async def not_found(request: Request, exc):
        return templates.TemplateResponse(request, "404.html", {
            "site_title": settings.site_title,
            "telegram_channel": settings.telegram_channel,
            "current_user": None,
        }, status_code=404)

    # 5. Health check
    @app.get("/healthz", response_class=HTMLResponse, include_in_schema=False)
    def health():
        ok = os.path.isfile(settings.database_path)
        ok_articles = os.path.isfile(articles_db_path)
        return ("<pre>Gigs Archive web — DB: %s (%s) | Articles DB: %s (%s)</pre>"
                % (settings.database_path, 'found' if ok else 'not created yet',
                   articles_db_path, 'found' if ok_articles else 'not created yet'))

    # Отладочный вывод маршрутов
    print("\n=== ЗАРЕГИСТРИРОВАННЫЕ МАРШРУТЫ ===")
    for route in app.routes:
        if hasattr(route, "path"):
            print(f" -> {route.path}")
    print("=====================================\n")

    return app

# Создаем экземпляр приложения для uvicorn
app = create_app()