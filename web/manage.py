"""
Small admin CLI for the web site.

Usage (from project root):
    python -m web.manage add-admin <telegram_username>   # + permanent password
    python -m web.manage remove-admin <telegram_username>
    python -m web.manage list-admins
    python -m web.manage gen-password --for <username> [--rotate] [--length 16]
    python -m web.manage gen-passwords [--all]           # every admin in the list
    python -m web.manage set-password --for <username>   # type your own password
    python -m web.manage init-db          # create tables in the shared SQLite DB
    python -m web.manage seed-demo        # demo article + sample pending poster
    python -m web.manage runserver [--host 0.0.0.0] [--port 8000] [--reload]

Passwords are permanent (no expiry) and shown only once — on disk there is
nothing but a PBKDF2 hash (web/admin_passwords.json), so a lost password has to
be re-issued with `gen-password --rotate`.
"""

import argparse
import getpass
import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web.config import settings
from web.passwords import password_store


def _print_password_table(rows: dict):
    """rows: {username: plaintext_password}"""
    if not rows:
        return
    width = max(len(u) for u in rows) + 2
    print()
    print(f"{'ADMIN':<{width}}PASSWORD")
    print("-" * (width + 24))
    for username, password in sorted(rows.items()):
        print(f"@{username:<{width - 1}}{password}")
    print()
    print("Shown ONE TIME ONLY — store them in your password manager now.")
    print("Login at /admin with the Telegram nickname + this password.")


def cmd_add_admin(username: str, password_length: int = 16):
    key = username.lstrip("@").lower()
    settings.add_admin_username(key)
    print(f"Admin added: @{key}")
    print(f"Admins now: {sorted(settings.all_admin_usernames())}")

    if password_store.has_password(key):
        print(f"Password for @{key} already exists — leaving it unchanged.")
        print("Rotate it with: python -m web.manage gen-password --for "
              f"{key} --rotate")
        return
    generated = password_store.generate_for(key, length=password_length)
    _print_password_table({key: generated})


def cmd_remove_admin(username: str):
    username = username.lstrip("@").lower()
    keep_env = sorted(settings.admin_usernames)  # env-based admins can't be removed here
    remaining = [u for u in settings.admins_file_usernames() if u != username]
    with open(settings.admins_json_path, "w", encoding="utf-8") as f:
        json.dump({"admins": remaining}, f, indent=2)
    dropped = password_store.remove(username)
    print(f"Removed @{username} from admins.json (ADMIN_USERNAMES still has: {keep_env})")
    if dropped:
        print("Also deleted its stored password hash.")


def cmd_list_admins():
    admins = sorted(settings.all_admin_usernames())
    if not admins:
        print("No web admins yet! Add one:")
        print("  python -m web.manage add-admin your_telegram_username")
        return
    without_pw = [a for a in admins if not password_store.has_password(a)]
    print("Web admins (nickname -> permanent password):")
    for a in admins:
        state = "password set" if password_store.has_password(a) else "NO PASSWORD"
        print(f"  @{a:<24} {state}")
    if without_pw:
        print()
        print("Generate passwords for all of them:")
        print("  python -m web.manage gen-passwords --all")


def cmd_gen_password(username: str, rotate: bool, length: int):
    key = username.lstrip("@").lower()
    if not settings.is_admin_username(key):
        print(f"@{key} is not in the admin list — add it first:")
        print(f"  python -m web.manage add-admin {key}")
        raise SystemExit(1)
    if password_store.has_password(key) and not rotate:
        print(f"@{key} already has a permanent password. To issue a new one:")
        print(f"  python -m web.manage gen-password --for {key} --rotate")
        raise SystemExit(1)
    generated = password_store.generate_for(key, length=length)
    _print_password_table({key: generated})


def cmd_set_password(username: str):
    key = username.lstrip("@").lower()
    if not settings.is_admin_username(key):
        print(f"@{key} is not in the admin list — add it first:")
        print(f"  python -m web.manage add-admin {key}")
        raise SystemExit(1)
    first = getpass.getpass(f"New permanent password for @{key}: ")
    if len(first) < 8:
        print("Too short — use at least 8 characters.")
        raise SystemExit(1)
    if getpass.getpass("Repeat it: ") != first:
        print("Passwords do not match, nothing changed.")
        raise SystemExit(1)
    password_store.set_password(key, first)
    print(f"Password saved for @{key} (hash only, shown to nobody).")


def cmd_gen_passwords(all_admins: bool, length: int, rotate: bool):
    """Generate permanent passwords for every admin in the list."""
    admins = sorted(settings.all_admin_usernames())
    if not admins:
        print("Admin list is empty — add admins first:")
        print("  python -m web.manage add-admin your_telegram_username")
        raise SystemExit(1)

    targets = admins if (all_admins or rotate) else [
        a for a in admins if not password_store.has_password(a)]

    if not targets:
        print("Every admin in the list already has a permanent password ✔")
        return

    if rotate:
        print(f"WARNING: rotating passwords for {len(targets)} admin(s); "
              "the old ones stop working immediately.")

    issued = {}
    for key in targets:
        issued[key] = password_store.generate_for(key, length=length)
    _print_password_table(issued)

    skipped = [a for a in admins if a not in targets]
    if skipped and not rotate:
        print(f"Already had passwords (untouched): {', '.join('@' + s for s in skipped)}")

    # Drop hashes of accounts that are no longer in the admin list.
    _, stale = password_store.sync_with(admins)
    if stale:
        print(f"Removed stale password hashes: {', '.join('@' + s for s in stale)}")



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
    p.add_argument("--length", type=int, default=16,
                   help="generated password length (default 16)")
    p = sub.add_parser("remove-admin"); p.add_argument("username")
    sub.add_parser("list-admins")

    p = sub.add_parser("gen-password",
                       help="generate a permanent password for one admin")
    p.add_argument("--for", dest="username", required=True)
    p.add_argument("--rotate", action="store_true",
                   help="replace the existing password")
    p.add_argument("--length", type=int, default=16)

    p = sub.add_parser("gen-passwords",
                       help="generate permanent passwords for every admin in the list")
    p.add_argument("--all", dest="all_admins", action="store_true",
                   help="re-issue even for admins that already have one")
    p.add_argument("--rotate", action="store_true",
                   help="same as --all: rotate every password")
    p.add_argument("--length", type=int, default=16)

    p = sub.add_parser("set-password", help="type your own permanent password")
    p.add_argument("--for", dest="username", required=True)

    sub.add_parser("init-db")
    sub.add_parser("seed-demo")
    p = sub.add_parser("runserver")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--reload", action="store_true")

    args = ap.parse_args()
    if args.cmd == "add-admin":
        cmd_add_admin(args.username, password_length=args.length)
    elif args.cmd == "remove-admin":
        cmd_remove_admin(args.username)
    elif args.cmd == "list-admins":
        cmd_list_admins()
    elif args.cmd == "gen-password":
        cmd_gen_password(args.username, rotate=args.rotate, length=args.length)
    elif args.cmd == "gen-passwords":
        cmd_gen_passwords(all_admins=args.all_admins or args.rotate,
                          length=args.length, rotate=args.rotate)
    elif args.cmd == "set-password":
        cmd_set_password(args.username)
    elif args.cmd == "init-db":
        cmd_init_db()
    elif args.cmd == "seed-demo":
        cmd_seed_demo()
    elif args.cmd == "runserver":
        cmd_runserver(args.host, args.port, args.reload)


if __name__ == "__main__":
    main()
