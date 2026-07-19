"""Intercept-facing UI routes for native FastMCP authorization."""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Any, Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.route_utils import read_session_cookie
from app.api.routes.admin_auth import _build_audit_context, require_authenticated_user
from app.core.database import get_db
from app.core.settings_registry import get_local
from app.mcp.local_oauth_provider import PendingAuthorizationUnavailableError
from app.models.models import MCPOAuthClientRead, UserAccount
from app.services.auth_service import SessionNotFoundError, auth_service
from app.services.mcp_oauth_service import OAuthInvalidRequestError, mcp_oauth_service


consent_router = APIRouter(
    prefix="/mcp/oauth/consent",
    tags=["mcp-oauth"],
    include_in_schema=False,
)
management_router = APIRouter(
    prefix="/mcp/oauth",
    tags=["mcp-oauth"],
    dependencies=[Depends(require_authenticated_user)],
)


class ConsentDecision(BaseModel):
    decision: Literal["approve", "deny"]


async def _current_session_user(
    request: Request,
    db: AsyncSession,
) -> UserAccount | None:
    """Return only the browser-session user; API keys cannot approve consent."""

    session_token = read_session_cookie(request)
    if not session_token:
        return None
    try:
        login_result = await auth_service.validate_session(
            db,
            session_token=session_token,
        )
    except SessionNotFoundError:
        return None
    return login_result.user


def _runtime_and_local_provider(request: Request) -> tuple[Any, Any]:
    runtime = getattr(request.app.state, "mcp_runtime", None)
    provider = getattr(runtime, "provider", None)
    required_methods = (
        "get_pending_authorization",
        "get_client",
        "complete_authorization",
    )
    if runtime is None or provider is None or not all(
        callable(getattr(provider, name, None)) for name in required_methods
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Local MCP OAuth is not enabled",
        )
    return runtime, provider


def _login_redirect(runtime: Any, request: Request) -> str:
    login_origin = runtime.snapshot.login_origin.rstrip("/")
    public_origin = runtime.snapshot.public_origin.rstrip("/")
    return_to = f"{public_origin}{request.url.path}"
    if request.url.query:
        return_to = f"{return_to}?{request.url.query}"
    return f"{login_origin}/login?next={quote(return_to, safe='')}"


def _consent_page(
    *,
    client_name: str,
    client_id: str,
    client_uri: str | None,
    redirect_uri: str,
    scope: str,
    submit_url: str,
) -> str:
    """Render a same-origin, CSRF-header-bearing consent decision form."""

    csrf_cookie_name = str(get_local("auth.csrf.cookie_name"))
    csrf_header_name = str(get_local("auth.csrf.header_name"))
    display_client_uri = client_uri or "Unknown client domain"
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Authorize MCP Client</title>
    <style>
      body {{ margin: 0; font-family: Inter, ui-sans-serif, system-ui, sans-serif; background: #0b0d12; color: #f4f7fb; }}
      main {{ min-height: 100vh; display: grid; place-items: center; padding: 24px; }}
      section {{ width: min(560px, 100%); border: 1px solid #313744; border-radius: 8px; background: #151923; padding: 24px; box-shadow: 0 12px 40px rgba(0,0,0,.35); }}
      h1 {{ margin: 0 0 12px; font-size: 24px; }}
      p {{ margin: 0 0 16px; line-height: 1.5; color: #b8c0cf; }}
      dl {{ display: grid; grid-template-columns: 130px 1fr; gap: 10px 16px; margin: 20px 0; }}
      dt {{ font-weight: 650; color: #e4e8ef; }}
      dd {{ margin: 0; overflow-wrap: anywhere; color: #b8c0cf; }}
      .warning {{ border: 1px solid #9c7b20; background: #28220f; color: #f3d877; border-radius: 6px; padding: 12px; margin: 16px 0; }}
      .actions {{ display: flex; justify-content: flex-end; gap: 12px; margin-top: 24px; }}
      button {{ min-height: 40px; padding: 0 14px; border-radius: 6px; font: inherit; font-weight: 650; cursor: pointer; }}
      .deny {{ border: 1px solid #4b5362; color: #e4e8ef; background: transparent; }}
      .approve {{ border: 1px solid #17e5a1; color: #07120e; background: #17e5a1; }}
      #error {{ color: #ff8f8f; min-height: 1.5em; }}
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
        <div class="warning">Only approve an MCP client you started and recognize. Check the redirect URI before continuing.</div>
        <p id="error" role="alert"></p>
        <form id="consent" method="post" action="{escape(submit_url, quote=True)}" data-csrf-cookie="{escape(csrf_cookie_name, quote=True)}" data-csrf-header="{escape(csrf_header_name, quote=True)}">
          <div class="actions">
            <button class="deny" type="submit" name="decision" value="deny">Deny</button>
            <button class="approve" type="submit" name="decision" value="approve">Authorize</button>
          </div>
        </form>
        <noscript>JavaScript is required to send the CSRF-protected authorization decision.</noscript>
      </section>
    </main>
    <script src="/api/v1/mcp/oauth/consent/client.js" defer></script>
  </body>
</html>"""


CONSENT_CLIENT_JAVASCRIPT = r"""(() => {
  const form = document.getElementById("consent");
  const error = document.getElementById("error");
  if (!form || !error) return;
  function cookie(name) {
    const prefix = encodeURIComponent(name) + "=";
    const item = document.cookie.split("; ").find(value => value.startsWith(prefix));
    return item ? decodeURIComponent(item.slice(prefix.length)) : "";
  }
  form.addEventListener("submit", async event => {
    event.preventDefault();
    error.textContent = "";
    const decision = event.submitter && event.submitter.value;
    const headers = {"Content-Type": "application/json"};
    const csrf = cookie(form.dataset.csrfCookie || "");
    if (csrf) headers[form.dataset.csrfHeader] = csrf;
    try {
      const response = await fetch(form.action, {
        method: "POST",
        credentials: "same-origin",
        headers,
        body: JSON.stringify({decision}),
      });
      const payload = await response.json();
      if (!response.ok || !payload.redirect_to) {
        throw new Error(payload.detail || "Authorization request could not be completed");
      }
      window.location.assign(payload.redirect_to);
    } catch (reason) {
      error.textContent = reason instanceof Error
        ? reason.message
        : "Authorization request could not be completed";
    }
  });
})();
"""


@consent_router.get("/client.js")
async def consent_client_javascript() -> Response:
    """Serve consent behavior as a CSP-compatible same-origin script."""

    return Response(
        CONSENT_CLIENT_JAVASCRIPT,
        media_type="text/javascript",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@consent_router.get("/{request_id}")
async def show_consent(
    request_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    runtime, provider = _runtime_and_local_provider(request)
    pending = await provider.get_pending_authorization(request_id)
    if pending is None:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="MCP authorization request is expired or already used",
        )

    current_user = await _current_session_user(request, db)
    if current_user is None:
        return RedirectResponse(
            _login_redirect(runtime, request),
            status_code=status.HTTP_302_FOUND,
        )

    client = await provider.get_client(pending.client_id)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="MCP client registration is no longer available",
        )

    return HTMLResponse(
        _consent_page(
            client_name=str(client.client_name or client.client_id),
            client_id=str(client.client_id),
            client_uri=str(client.client_uri) if client.client_uri else None,
            redirect_uri=pending.redirect_uri,
            scope=" ".join(pending.scopes),
            submit_url=str(request.url),
        ),
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


@consent_router.post("/{request_id}")
async def decide_consent(
    request_id: UUID,
    decision: ConsentDecision,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    _runtime, provider = _runtime_and_local_provider(request)
    current_user = await _current_session_user(request, db)
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="An authenticated browser session is required",
        )
    try:
        callback = await provider.complete_authorization(
            request_id,
            user=current_user,
            approved=decision.decision == "approve",
            context=_build_audit_context(request),
        )
    except PendingAuthorizationUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="MCP authorization request is expired or already used",
        ) from exc
    return JSONResponse(
        {"redirect_to": callback},
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


@management_router.get("/clients", response_model=list[MCPOAuthClientRead])
async def list_connected_mcp_clients(
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
) -> list[MCPOAuthClientRead]:
    return await mcp_oauth_service.list_connected_clients(db, user=current_user)


@management_router.delete(
    "/clients/{consent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_connected_mcp_client(
    consent_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
) -> Response:
    try:
        consent, _client = await mcp_oauth_service.resolve_connected_client(
            db,
            user=current_user,
            consent_id=consent_id,
        )
        if consent.provider_mode == "oidc":
            runtime = getattr(request.app.state, "mcp_runtime", None)
            revoke_native = getattr(
                getattr(runtime, "provider", None),
                "revoke_projected_client",
                None,
            )
            if not callable(revoke_native):
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="OIDC client revocation is not available in this worker",
                )
            references = (
                await mcp_oauth_service.list_active_provider_grant_references(
                    db,
                    consent_id=consent.id,
                )
            )
            reference_pairs: list[tuple[Any | None, str]] = [
                (reference, reference.provider_reference_hash)
                for reference in references
            ]
            # Compatibility for a projection written between migration 014 and
            # normalized family-reference rollout.
            if not reference_pairs and consent.provider_reference_hash:
                reference_pairs.append((None, consent.provider_reference_hash))
            if not reference_pairs:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="OIDC grant references are not available for revocation",
                )

            for reference, reference_hash in reference_pairs:
                revoked = await revoke_native(
                    user_id=current_user.id,
                    provider_reference_hash=reference_hash,
                )
                if not revoked:
                    await db.rollback()
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="OIDC grant revocation could not be confirmed",
                    )
                if reference is not None:
                    reference.revoked_at = datetime.now(timezone.utc)
                    # Persist progress per token family. If a later native
                    # family fails, a retry does not attempt to revoke an
                    # already-deleted native reference again.
                    await db.commit()
        await mcp_oauth_service.revoke_connected_client(
            db,
            user=current_user,
            consent_id=consent_id,
            context=_build_audit_context(request),
        )
        await db.commit()
    except OAuthInvalidRequestError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connected MCP client not found",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["consent_router", "management_router"]
