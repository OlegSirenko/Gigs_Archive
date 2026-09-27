"""
Small admin CLI for the web site.

Usage (from project root):
    python -m web.manage add-admin <telegram_username>
    python -m web.manage remove-admin <telegram_username>
    python -m web.manage list-admins
    python -m web.manage init-db          # create tables in the shared SQLite DB
    python -m web.manage seed-demo        # demo article + sample pending poster
    python -m web.manage runserver [--host 0.0.0.0] [--port 8000] [--reload]
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web.config import settings


def cmd_add_admin(username: str):
    settings.add_admin_username(username)
    print(f"Admin added: @{username.lstrip('@').lower()}")
    print(f"Admins now: {sorted(settings.all_admin_usernames())}")


def cmd_remove_admin(username: str):
    username = username.lstrip("@").lower()
    keep_env = sorted(settings.admin_usernames)  # env-based admins can't be removed here
    remaining = [u for u in settings.admins_file_usernames() if u != username]
    with open(settings.admins_json_path, "w", encoding="utf-8") as f:
        json.dump({"admins": remaining}, f, indent=2)
    print(f"Removed @{username} from admins.json (ADMIN_USERNAMES still has: {keep_env})")


def cmd_list_admins():
    admins = sorted(settings.all_admin_usernames())
    if not admins:
        print("No web admins yet! Add one:")
        print("  python -m web.manage add-admin your_telegram_username")
    else:
        print("Web admins:", ", ".join(f"@{a}" for a in admins))


def cmd_init_db():
    from web.database import init_web_db
    init_web_db()
    print(f"Tables ready in {settings.database_path}")


def cmd_seed_demo():
    from web.database import Article, ModerationStatus, Poster, User, get_session, init_web_db
    init_web_db()
    with get_session() as s:
        user = s.query(User).filter(User.username == "demo_organizer").first()
        if not user:
            user = User(telegram_id=900000001, username="demo_organizer",
                        first_name="Demo", language_code="en")
            s.add(user)
            s.flush()

        poster = s.query(Poster).filter(Poster.user_id == user.telegram_id).first()
        if not poster:
            poster = Poster(
                user_id=user.telegram_id,
                photo_file_id="DEMO_FILE_ID",
                caption="🎸 Демо-вечер: The Test Signals + открытый микрофон\n"
                        "Клуб «Пример», главный зал\nДвери 19:00 · Старт 20:00 · Вход свободный",
                event_date=datetime.now() + timedelta(days=5),
                is_anonymous=False,
                status=ModerationStatus.APPROVED,
                moderated_at=datetime.now(),
            )
            s.add(poster)
            s.flush()

        if not s.query(Article).filter(Article.slug.like("demo-interview%")).first():
            article = Article(
                title="Интервью: The Test Signals — как удержать сцену живой",
                slug="demo-interview-the-test-signals",
                lead="За два дня до демо-вечера мы поговорили о репточках, пустых "
                     "площадках и о том, почему по вторникам они играют бесплатно.",
                body=(
                    "**В 2023-м вы играли для трёх человек. Теперь клубы зовут вас дважды за сезон. Что изменилось?**\n\n"
                    "Честно — упрямство. Мы *организировали свои вечера сами*, когда ни один "
                    "промоутер не хотел с нами связываться. https://example.org/our-nights\n\n"
                    "---\n\n"
                    "В комнате пахнет припоем и кофе. Группа пришла с коробкой "
                    "флаеров, отпечатанных вручную, — половина из них ради этого самого концерта.\n\n"
                    "\"Архив афишей помогает, — говорит вокалист. — Люди видят стену "
                    "и понимают: между концертами существует целая сцена.\""
                ),
                kind="interview",
                author_username="admin",
                poster_id=poster.id,
                is_published=True,
                published_at=datetime.now(),
            )
            s.add(article)
        s.commit()
    print("Demo content created: 1 approved poster + 1 published interview.")
    print("Log in at /admin (add yourself first: python -m web.manage add-admin you)")


def cmd_runserver(host, port, reload_):
    import uvicorn
    uvicorn.run("web.app:app", host=host, port=port, reload=reload_)


def main():
    ap = argparse.ArgumentParser(prog="web.manage")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add-admin"); p.add_argument("username")
    p = sub.add_parser("remove-admin"); p.add_argument("username")
    sub.add_parser("list-admins")
    sub.add_parser("init-db")
    sub.add_parser("seed-demo")
    p = sub.add_parser("runserver")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--reload", action="store_true")

    args = ap.parse_args()
    if args.cmd == "add-admin":
        cmd_add_admin(args.username)
    elif args.cmd == "remove-admin":
        cmd_remove_admin(args.username)
    elif args.cmd == "list-admins":
        cmd_list_admins()
    elif args.cmd == "init-db":
        cmd_init_db()
    elif args.cmd == "seed-demo":
        cmd_seed_demo()
    elif args.cmd == "runserver":
        cmd_runserver(args.host, args.port, args.reload)


if __name__ == "__main__":
    main()
