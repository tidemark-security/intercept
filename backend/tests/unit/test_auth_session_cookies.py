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


def test_oidc_browser_binding_cookie_is_host_only_even_when_sessions_share_a_domain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = {
        "auth.session.cookie_name": "intercept_session",
        "auth.session.cookie_path": "/",
        "auth.session.cookie_http_only": True,
        "auth.session.cookie_secure": True,
        "auth.session.cookie_same_site": "lax",
        "auth.session.cookie_domain": ".example.com",
        "auth.session.idle_timeout_hours": 1,
        "oidc.browser_binding.cookie_name": "intercept_oidc_binding",
        "oidc.redirect_uri": "https://intercept.example/api/v1/auth/oidc/callback",
    }
    monkeypatch.setattr(route_utils, "get_local", settings.__getitem__)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    issue_response = Response()
    route_utils.issue_oidc_browser_binding_cookie(
        issue_response,
        "browser-bound-verifier",
        expires_at,
    )
    issued = _cookie_by_name(issue_response, "__Host-intercept_oidc_binding")[
        "__Host-intercept_oidc_binding"
    ]

    assert issued["domain"] == ""
    assert issued["path"] == "/"
    assert issued["secure"] is True
    assert issued["httponly"] is True

    revoke_response = Response()
    route_utils.revoke_oidc_browser_binding_cookie(revoke_response)
    revoked = _cookie_by_name(revoke_response, "__Host-intercept_oidc_binding")[
        "__Host-intercept_oidc_binding"
    ]
    assert revoked["domain"] == ""
    assert revoked["path"] == "/"
    assert revoked["secure"] is True


def test_oidc_browser_binding_cookie_preserves_loopback_http_development_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = {
        "auth.session.cookie_http_only": True,
        "auth.session.cookie_secure": False,
        "auth.session.cookie_same_site": "lax",
        "auth.session.cookie_domain": None,
        "auth.session.idle_timeout_hours": 1,
        "oidc.browser_binding.cookie_name": "__Host-intercept_oidc_binding",
        "oidc.redirect_uri": "http://localhost:8080/api/v1/auth/oidc/callback",
    }
    monkeypatch.setattr(route_utils, "get_local", settings.__getitem__)

    response = Response()
    route_utils.issue_oidc_browser_binding_cookie(
        response,
        "browser-bound-verifier",
        datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    issued = _cookie_by_name(response, "intercept_oidc_binding")[
        "intercept_oidc_binding"
    ]

    assert issued["domain"] == ""
    assert issued["path"] == "/"
    assert issued["secure"] == ""


def test_oidc_browser_binding_cookie_uses_lax_when_session_cookie_is_strict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = {
        "auth.session.cookie_http_only": True,
        "auth.session.cookie_secure": True,
        "auth.session.cookie_same_site": "strict",
        "auth.session.cookie_domain": None,
        "auth.session.idle_timeout_hours": 1,
        "oidc.browser_binding.cookie_name": "intercept_oidc_binding",
        "oidc.redirect_uri": "https://intercept.example/api/v1/auth/oidc/callback",
    }
    monkeypatch.setattr(route_utils, "get_local", settings.__getitem__)

    response = Response()
    route_utils.issue_oidc_browser_binding_cookie(
        response,
        "browser-bound-verifier",
        datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    issued = _cookie_by_name(response, "__Host-intercept_oidc_binding")[
        "__Host-intercept_oidc_binding"
    ]

    assert issued["samesite"].lower() == "lax"
