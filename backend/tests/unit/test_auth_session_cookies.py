from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from http.cookies import SimpleCookie

import pytest
from fastapi import Response

from app.api import route_utils


def _cookie_by_name(response: Response, name: str) -> SimpleCookie:
    cookie = SimpleCookie()
    for header_name, header_value in response.raw_headers:
        if header_name.lower() == b"set-cookie":
            cookie.load(header_value.decode("latin-1"))
    assert name in cookie
    return cookie


def test_authenticated_cookies_live_until_the_absolute_session_expiration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = {
        "auth.session.cookie_name": "intercept_session",
        "auth.csrf.cookie_name": "XSRF-TOKEN",
        "auth.session.cookie_path": "/",
        "auth.session.cookie_http_only": True,
        "auth.session.cookie_secure": True,
        "auth.session.cookie_same_site": "lax",
        "auth.session.cookie_domain": None,
        "auth.session.idle_timeout_hours": 1,
    }
    monkeypatch.setattr(route_utils, "get_local", settings.__getitem__)
    monkeypatch.setattr(route_utils, "generate_csrf_token", lambda: "csrf-token")

    response = Response()
    absolute_expiration = datetime.now(timezone.utc) + timedelta(hours=12)

    route_utils.issue_authenticated_session_cookies(
        response,
        "session-token",
        absolute_expiration,
    )

    for cookie_name in ("intercept_session", "XSRF-TOKEN"):
        cookie = _cookie_by_name(response, cookie_name)[cookie_name]
        max_age = int(cookie["max-age"])
        assert 11 * 60 * 60 < max_age <= 12 * 60 * 60
        assert parsedate_to_datetime(cookie["expires"]) == absolute_expiration.replace(
            microsecond=0,
        )
