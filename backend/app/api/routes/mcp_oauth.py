"""OAuth 2.1 endpoints for remote MCP clients."""
from __future__ import annotations

from html import escape
from typing import Any
from urllib.parse import parse_qs, urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.route_utils import read_session_cookie
from app.api.routes.admin_auth import _build_audit_context, require_authenticated_user
from app.core.database import get_db
from app.models.models import MCPOAuthClientRead, UserAccount
from app.services.auth_service import SessionNotFoundError, auth_service
from app.services.mcp_oauth_service import (
    MCP_OAUTH_SCOPE,
    OAuthConfigurationError,
    OAuthDisabledError,
    OAuthInactiveUserError,
    OAuthInvalidClientError,
    OAuthInvalidGrantError,
    OAuthInvalidRequestError,
    mcp_oauth_service,
)


router = APIRouter(tags=["mcp-oauth"])
management_router = APIRouter(
    prefix="/mcp/oauth",
    tags=["mcp-oauth"],
    dependencies=[Depends(require_authenticated_user)],
)


def _oauth_error_response(exc: Exception, *, status_code: int = 400) -> JSONResponse:
    error = getattr(exc, "error", "invalid_request")
    description = getattr(exc, "description", str(exc) or "Invalid OAuth request")
    return JSONResponse(
        status_code=status_code,
        content={"error": error, "error_description": description},
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


def _parse_form_body(raw_body: bytes) -> dict[str, str]:
    parsed = parse_qs(raw_body.decode("utf-8"), keep_blank_values=True)
    return {key: values[-1] for key, values in parsed.items() if values}


def _with_query(url: str, params: dict[str, str | None]) -> str:
    filtered = {key: value for key, value in params.items() if value is not None}
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode(filtered)}"


async def _current_session_user(request: Request, db: AsyncSession) -> UserAccount | None:
    session_token = read_session_cookie(request)
    if not session_token:
        return None
    try:
        login_result = await auth_service.validate_session(db, session_token=session_token)
    except SessionNotFoundError:
        return None
    return login_result.user


def _authorize_url_from_request(request: Request, public_base_url: str) -> str:
    query = request.url.query
    suffix = f"?{query}" if query else ""
    return f"{public_base_url}{request.url.path}{suffix}"


def _consent_page(
    *,
    client_name: str,
    client_id: str,
    client_uri: str | None,
    redirect_uri: str,
    scope: str,
    approve_url: str,
    deny_url: str,
) -> str:
    display_client_uri = client_uri or "Unknown client domain"
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Authorize MCP Client</title>
    <style>
      body {{ margin: 0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f7f7f8; color: #171717; }}
      main {{ min-height: 100vh; display: grid; place-items: center; padding: 24px; }}
      section {{ width: min(560px, 100%); border: 1px solid #d7d7db; border-radius: 8px; background: white; padding: 24px; box-shadow: 0 8px 28px rgba(0,0,0,.08); }}
      h1 {{ margin: 0 0 12px; font-size: 24px; line-height: 1.2; }}
      p {{ margin: 0 0 16px; line-height: 1.5; color: #555; }}
      dl {{ display: grid; grid-template-columns: 140px 1fr; gap: 10px 16px; margin: 20px 0; }}
      dt {{ font-weight: 650; color: #333; }}
      dd {{ margin: 0; overflow-wrap: anywhere; color: #555; }}
      .warning {{ border: 1px solid #f1c232; background: #fff8dc; color: #594500; border-radius: 6px; padding: 12px; margin: 16px 0; }}
      .actions {{ display: flex; justify-content: flex-end; gap: 12px; margin-top: 24px; }}
      a {{ display: inline-flex; align-items: center; justify-content: center; min-height: 40px; padding: 0 14px; border-radius: 6px; text-decoration: none; font-weight: 650; }}
      .deny {{ border: 1px solid #cfcfd5; color: #333; background: white; }}
      .approve {{ color: white; background: #1c6b54; }}
    </style>
  </head>
  <body>
    <main>
      <section>
        <h1>Authorize MCP access</h1>
        <p>{escape(client_name)} wants to connect to this Intercept deployment as your user account.</p>
        <dl>
          <dt>Client</dt><dd>{escape(client_name)}</dd>
          <dt>Client ID</dt><dd>{escape(client_id)}</dd>
          <dt>Client domain</dt><dd>{escape(display_client_uri)}</dd>
          <dt>Redirect URI</dt><dd>{escape(redirect_uri)}</dd>
          <dt>Access</dt><dd>{escape(scope)}</dd>
        </dl>
        <div class="warning">Only approve local agent clients that you started and recognize. The redirect URI should point to localhost or another loopback address.</div>
        <p>After authorization, Intercept will return you to your local agent. You can close this tab once the agent confirms the connection is complete.</p>
        <div class="actions">
          <a class="deny" href="{escape(deny_url)}">Deny</a>
          <a class="approve" href="{escape(approve_url)}">Authorize</a>
        </div>
      </section>
    </main>
  </body>
</html>"""


@router.get("/.well-known/oauth-protected-resource{resource_path:path}")
async def protected_resource_metadata(
    resource_path: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    try:
        metadata = await mcp_oauth_service.protected_resource_metadata(db, resource_path or "/mcp")
    except OAuthDisabledError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP OAuth is not enabled")
    return JSONResponse(metadata)


@router.get("/.well-known/oauth-authorization-server")
async def authorization_server_metadata(
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    try:
        metadata = await mcp_oauth_service.authorization_server_metadata(db)
    except OAuthDisabledError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP OAuth is not enabled")
    return JSONResponse(metadata)


@router.post("/oauth/register", status_code=status.HTTP_201_CREATED)
async def register_client(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise OAuthInvalidClientError()
        client = await mcp_oauth_service.register_dynamic_client(
            db,
            payload=payload,
            context=_build_audit_context(request),
        )
        await db.commit()
    except (OAuthDisabledError, OAuthConfigurationError, OAuthInvalidClientError) as exc:
        await db.rollback()
        return _oauth_error_response(exc)

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "client_id": client.client_id,
            "client_name": client.client_name,
            "client_uri": client.client_uri,
            "redirect_uris": client.redirect_uris,
            "grant_types": client.grant_types,
            "response_types": client.response_types,
            "token_endpoint_auth_method": client.token_endpoint_auth_method,
            "scope": client.scope,
            "client_id_issued_at": int(client.created_at.timestamp()),
        },
    )


@router.get("/oauth/authorize", include_in_schema=False)
async def authorize(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    params = request.query_params
    state = params.get("state")
    redirect_uri = params.get("redirect_uri") or ""

    try:
        settings = await mcp_oauth_service.get_enabled_settings(db)
    except OAuthDisabledError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP OAuth is not enabled")

    # Only redirect to redirect_uri if it matches the resolved client's registered URIs.
    client_id = params.get("client_id") or ""
    redirect_uri_is_registered = False
    if redirect_uri and client_id:
        try:
            resolved_client = await mcp_oauth_service.resolve_client(db, client_id)
            redirect_uri_is_registered = redirect_uri in resolved_client.redirect_uris
        except OAuthInvalidClientError:
            redirect_uri_is_registered = False

    if params.get("response_type") != "code":
        if redirect_uri_is_registered:
            return RedirectResponse(
                _with_query(redirect_uri, {"error": "unsupported_response_type", "state": state}),
                status_code=status.HTTP_302_FOUND,
            )
        return _oauth_error_response(OAuthInvalidRequestError("response_type=code is required"))

    required = ["client_id", "redirect_uri", "code_challenge", "resource"]
    missing = [key for key in required if not params.get(key)]
    if missing:
        return _oauth_error_response(OAuthInvalidRequestError(f"Missing required parameter: {', '.join(missing)}"))

    if params.get("deny") == "1":
        if not redirect_uri_is_registered:
            return _oauth_error_response(OAuthInvalidRequestError("redirect_uri is not registered for this client"))
        return RedirectResponse(
            _with_query(redirect_uri, {"error": "access_denied", "state": state}),
            status_code=status.HTTP_302_FOUND,
        )

    user = await _current_session_user(request, db)
    if user is None:
        authorize_url = _authorize_url_from_request(request, settings.public_base_url)
        return RedirectResponse(
            mcp_oauth_service.login_redirect_for_authorize(settings.login_base_url, authorize_url),
            status_code=status.HTTP_302_FOUND,
        )

    try:
        client = await mcp_oauth_service.resolve_client(db, params["client_id"])
    except OAuthInvalidClientError as exc:
        return _oauth_error_response(exc)

    scope = params.get("scope") or MCP_OAUTH_SCOPE
    approved = params.get("approve") == "1"
    if not approved and not await mcp_oauth_service.has_active_consent(
        db,
        user=user,
        client=client,
        scope=scope,
    ):
        approve_url = _with_query(str(request.url), {"approve": "1"})
        deny_url = _with_query(str(request.url), {"deny": "1"})
        return HTMLResponse(
            _consent_page(
                client_name=client.client_name,
                client_id=client.client_id,
                client_uri=client.client_uri,
                redirect_uri=redirect_uri,
                scope=scope,
                approve_url=approve_url,
                deny_url=deny_url,
            )
        )

    try:
        code = await mcp_oauth_service.create_authorization_code(
            db,
            client=client,
            user=user,
            redirect_uri=redirect_uri,
            code_challenge=params["code_challenge"],
            code_challenge_method=params.get("code_challenge_method") or "plain",
            scope=scope,
            resource=params["resource"],
            context=_build_audit_context(request),
        )
        await db.commit()
    except (OAuthInvalidRequestError, OAuthConfigurationError) as exc:
        await db.rollback()
        return _oauth_error_response(exc)

    return RedirectResponse(
        mcp_oauth_service.build_redirect_uri(redirect_uri, {"code": code, "state": state}),
        status_code=status.HTTP_302_FOUND,
    )


@router.post("/oauth/token")
async def token(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    form = _parse_form_body(await request.body())
    grant_type = form.get("grant_type")
    client_id = form.get("client_id") or ""
    try:
        if grant_type == "authorization_code":
            payload = await mcp_oauth_service.exchange_authorization_code(
                db,
                code=form.get("code") or "",
                client_id=client_id,
                redirect_uri=form.get("redirect_uri") or "",
                code_verifier=form.get("code_verifier") or "",
                resource=form.get("resource") or "",
                context=_build_audit_context(request),
            )
        elif grant_type == "refresh_token":
            payload = await mcp_oauth_service.refresh_access_token(
                db,
                refresh_token=form.get("refresh_token") or "",
                client_id=client_id,
                resource=form.get("resource"),
                context=_build_audit_context(request),
            )
        else:
            raise OAuthInvalidGrantError("Unsupported grant type")
        await db.commit()
    except OAuthInvalidClientError as exc:
        await db.rollback()
        return _oauth_error_response(exc, status_code=status.HTTP_401_UNAUTHORIZED)
    except (
        OAuthDisabledError,
        OAuthConfigurationError,
        OAuthInactiveUserError,
        OAuthInvalidGrantError,
        OAuthInvalidRequestError,
    ) as exc:
        await db.rollback()
        return _oauth_error_response(exc)

    return JSONResponse(
        payload,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


@router.post("/oauth/revoke", status_code=status.HTTP_200_OK)
async def revoke_token(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    form = _parse_form_body(await request.body())
    try:
        await mcp_oauth_service.revoke_token(
            db,
            token=form.get("token") or "",
            client_id=form.get("client_id"),
            context=_build_audit_context(request),
        )
        await db.commit()
    except OAuthInvalidClientError as exc:
        await db.rollback()
        return _oauth_error_response(exc, status_code=status.HTTP_401_UNAUTHORIZED)
    except (OAuthDisabledError, OAuthConfigurationError) as exc:
        await db.rollback()
        return _oauth_error_response(exc)
    return JSONResponse({})


@management_router.get("/clients", response_model=list[MCPOAuthClientRead])
async def list_connected_mcp_clients(
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
) -> list[MCPOAuthClientRead]:
    return await mcp_oauth_service.list_connected_clients(db, user=current_user)


@management_router.delete("/clients/{consent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_connected_mcp_client(
    consent_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
) -> Response:
    try:
        await mcp_oauth_service.revoke_connected_client(
            db,
            user=current_user,
            consent_id=consent_id,
            context=_build_audit_context(request),
        )
        await db.commit()
    except OAuthInvalidRequestError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connected MCP client not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
