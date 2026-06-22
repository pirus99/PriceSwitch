"""Minimal session-cookie authentication.

Login is only enforced when AUTH_REQUIRED=true in the .env file.
The password is compared in constant time to mitigate timing attacks.
"""

from __future__ import annotations

import hmac

from fastapi import Request
from fastapi.responses import RedirectResponse

from .env_config import env_config

SESSION_KEY = "authenticated"


def auth_enabled() -> bool:
    return env_config.auth_required


def verify_password(password: str) -> bool:
    return hmac.compare_digest(password or "", env_config.auth_password or "")


def is_authenticated(request: Request) -> bool:
    if not auth_enabled():
        return True
    return bool(request.session.get(SESSION_KEY))


def login_session(request: Request) -> None:
    request.session[SESSION_KEY] = True


def logout_session(request: Request) -> None:
    request.session.pop(SESSION_KEY, None)


def require_auth(request: Request) -> RedirectResponse | None:
    """Return a redirect to /login when the request is unauthenticated."""
    if is_authenticated(request):
        return None
    return RedirectResponse(url="/login", status_code=303)
