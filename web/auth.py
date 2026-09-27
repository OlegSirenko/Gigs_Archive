"""
Admin authentication for the web site.

Privilege model:
  * ADMIN (web)  — username listed in ADMIN_USERNAMES (.env) or web/admins.json.
                   Can write/edit/publish Articles (interviews, reviews).
  * USER         — anyone; read-only access to public posters & articles.

The admin list is tied to Telegram usernames, matching the bot's own
ADMIN_IDS-based privileges: the same people who moderate in Telegram
moderate on the site.

Sessions are signed cookies via itsdangerous (no server-side state).
"""

from dataclasses import dataclass

import itsdangerous
from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from web.config import settings

_SIGNER = itsdangerous.URLSafeTimedSerializer(settings.secret_key)
_SALT = "gigs-web-session"


@dataclass
class CurrentUser:
    username: str
    is_admin: bool


def create_session_cookie(username: str) -> str:
    return _SIGNER.dumps({"u": username}, salt=_SALT)


def read_session_cookie(token: str) -> dict | None:
    try:
        data = _SIGNER.loads(token, salt=_SALT, max_age=settings.session_max_age)
    except itsdangerous.BadSignature:
        return None
    return data if isinstance(data, dict) else None


def get_current_user(request: Request) -> CurrentUser | None:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        return None
    data = read_session_cookie(token)
    if not data or not data.get("u"):
        return None
    username = str(data["u"])
    return CurrentUser(
        username=username,
        is_admin=settings.is_admin_username(username),
    )


def require_login(request: Request) -> CurrentUser:
    user = get_current_user(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_302_FOUND,
            headers={"Location": "/admin/login?next=" + request.url.path},
        )
    return user


def require_admin(request: Request) -> CurrentUser:
    user = get_current_user(request)
    if not user or not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_302_FOUND,
            headers={"Location": "/admin/login?next=" + request.url.path},
        )
    return user


def logout_response(redirect_to: str = "/") -> RedirectResponse:
    response = RedirectResponse(redirect_to, status_code=status.HTTP_302_FOUND)
    response.delete_cookie(settings.session_cookie_name, path="/")
    return response
