"""
LangFlow API routes for AI chat functionality.

Provides endpoints for:
- Managing chat sessions
- Sending messages
- Retrieving conversation history
- Streaming responses via SSE
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, col
from datetime import datetime, timedelta, timezone
import httpx

from app.api.routes.admin_auth import require_admin_user, require_authenticated_user
from app.core.database import get_db
from app.models.models import (
    ApiKeyRead,
    AppSettingCreate,
    AppSettingUpdate,
    LangFlowSession,
    LangFlowSessionCreate,
    LangFlowSessionUpdate,
    LangFlowSessionRead,
    LangFlowMessage,
    LangFlowMessageCreate,
    LangFlowMessageRead,
    UserAccount,
)
from app.models.enums import (
    AccountType,
    MessageFeedback,
    MessageRole,
    SettingType,
    SessionStatus,
    UserRole,
    UserStatus,
)
from app.services.langflow_service import (
    LangFlowCheckResult,
    LangFlowProvisioningResult,
    LangFlowService,
    LangFlowConfigurationError,
    LangFlowConnectionError,
    LangFlowError,
)
from app.services.api_key_service import api_key_service
from app.services.audit_service import AuditContext
from app.services.settings_service import SettingsService
from app.services.sse_service import get_sse_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/langflow", tags=["langflow"])

LANGFLOW_SETUP_SERVER_NAME = "intercept"
LANGFLOW_SETUP_VARIABLE_NAME = "intercept_api_key"
LANGFLOW_SETUP_DEFAULT_NHI_USERNAME = "tidemark_ai"
LANGFLOW_SETUP_DEFAULT_API_KEY_NAME = "Intercept Langflow MCP"
LANGFLOW_SETUP_NHI_DESCRIPTION = "Dedicated Langflow MCP automation account"
LANGFLOW_SETUP_PROJECT_NAME = "Intercept"
LANGFLOW_SETUP_PROJECT_DESCRIPTION = "Bundled Intercept flows and MCP setup assets"
LANGFLOW_BUNDLED_FLOW_ASSETS = (
    {
        "asset_name": "tmi_general_purpose.json",
        "label": "General purpose flow",
        "setting_key": "langflow.default_flow_id",
    },
    {
        "asset_name": "tmi_case_agent.json",
        "label": "Case detail flow",
        "setting_key": "langflow.case_detail_flow_id",
    },
    {
        "asset_name": "tmi_task_agent.json",
        "label": "Task detail flow",
        "setting_key": "langflow.task_detail_flow_id",
    },
    {
        "asset_name": "tmi_alert_triage.json",
        "label": "Alert triage flow",
        "setting_key": "langflow.alert_triage_flow_id",
    },
    {
        "asset_name": "tmi_rag_confluence.json",
        "label": "Confluence ingest flow",
        "setting_key": None,
    },
)


# Request/Response Models

class ChatRequest(BaseModel):
    """Request to send a chat message."""
    session_id: UUID = Field(description="Session ID for the conversation")
    content: str = Field(min_length=1, max_length=10000, description="Message content")
    context: Optional[Dict[str, Any]] = Field(default=None, description="Additional context")


class ChatResponse(BaseModel):
    """Response after sending a chat message."""
    message_id: UUID = Field(description="ID of the created message")
    session_id: UUID = Field(description="Session ID")
    status: str = Field(description="Processing status")
    stream_url: Optional[str] = Field(default=None, description="URL for streaming response")


class StreamChatRequest(BaseModel):
    """Request to stream a chat message response."""
    message: str = Field(min_length=1, max_length=10000, description="Message content")
    context: Optional[Dict[str, Any]] = Field(default=None, description="Additional context")


class SessionWithMessages(BaseModel):
    """Session with message count."""
    session: LangFlowSessionRead
    message_count: int


class TestConnectionResponse(BaseModel):
    """Response from connection test."""
    checks: List["LangFlowConnectionCheck"] = Field(default_factory=list)
    success: bool
    message: str


class LangFlowConnectionCheck(BaseModel):
    """Single LangFlow environment validation result."""

    id: str
    label: str
    success: bool
    message: str


def _default_langflow_api_key_expires_at() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=365)


class LangFlowSetupRequest(BaseModel):
    """Admin request to provision the Intercept MCP server in LangFlow."""

    backend_api_base_url: str = Field(
        min_length=1,
        description="Intercept backend API base URL, used to derive the /mcp/streamable/ endpoint",
    )
    nhi_username: str = Field(
        default=LANGFLOW_SETUP_DEFAULT_NHI_USERNAME,
        min_length=3,
        max_length=1024,
        description="Username for the dedicated LangFlow automation NHI account",
    )
    api_key_name: str = Field(
        default=LANGFLOW_SETUP_DEFAULT_API_KEY_NAME,
        min_length=1,
        max_length=100,
        description="Display name for the generated NHI API key",
    )
    api_key_expires_at: datetime = Field(
        default_factory=_default_langflow_api_key_expires_at,
        description="Expiration timestamp for the generated NHI API key",
    )


class LangFlowSetupStep(BaseModel):
    """Single step result for the LangFlow setup wizard."""

    id: str
    label: str
    status: str
    message: str


class LangFlowSetupResponse(BaseModel):
    """Structured result for LangFlow MCP setup orchestration."""

    success: bool
    message: str
    steps: List[LangFlowSetupStep] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    nhi_user_id: Optional[UUID] = None
    nhi_username: Optional[str] = None
    api_key: Optional[ApiKeyRead] = None
    mcp_server_name: Optional[str] = None
    mcp_server_url: Optional[str] = None
    variable_name: Optional[str] = None
    flow_assignments: Dict[str, str] = Field(default_factory=dict)


class MessageFeedbackRequest(BaseModel):
    """Request to set feedback on a message."""
    feedback: MessageFeedback = Field(description="Feedback type (POSITIVE or NEGATIVE)")


# Helper Functions

async def get_langflow_service(db: AsyncSession) -> LangFlowService:
    """Get configured LangFlow service from settings."""
    settings_service = SettingsService(db)  # type: ignore[arg-type]
    try:
        return await LangFlowService.from_settings(settings_service)
    except LangFlowConfigurationError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )


def _build_audit_context(request: Request) -> AuditContext:
    client_host: Optional[str] = None
    if request.client:
        client_host = request.client.host
    return AuditContext(
        ip_address=client_host,
        user_agent=request.headers.get("user-agent"),
        correlation_id=request.headers.get("x-request-id"),
    )


def _record_setup_step(
    steps: list[LangFlowSetupStep],
    *,
    step_id: str,
    label: str,
    step_status: str,
    message: str,
) -> None:
    steps.append(
        LangFlowSetupStep(
            id=step_id,
            label=label,
            status=step_status,
            message=message,
        )
    )


def _get_langflow_asset_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "static" / "langflow"


def _derive_intercept_mcp_streamable_url(api_base_url: str) -> str:
    normalized = api_base_url.strip()
    if not normalized:
        raise ValueError("backend_api_base_url must not be blank")

    parsed = httpx.URL(normalized)
    if not parsed.scheme or not parsed.host:
        raise ValueError("backend_api_base_url must be an absolute URL")

    normalized_path = parsed.path.rstrip("/")
    for suffix in ("/api/v1", "/api"):
        if normalized_path.endswith(suffix):
            normalized_path = normalized_path[: -len(suffix)]
            break

    root_path = normalized_path or "/"
    root_url = str(parsed.copy_with(path=root_path, query=None, fragment=None)).rstrip("/")
    return f"{root_url}/mcp/streamable/"


def _replace_cached_intercept_mcp_server_url(payload: Any, mcp_server_url: str) -> Any:
    if isinstance(payload, dict):
        value = payload.get("value")
        if (
            isinstance(value, dict)
            and value.get("name") == LANGFLOW_SETUP_SERVER_NAME
            and isinstance(value.get("config"), dict)
            and isinstance(value["config"].get("url"), str)
        ):
            return {
                **payload,
                "value": {
                    **value,
                    "config": {
                        **value["config"],
                        "url": mcp_server_url,
                    },
                },
            }

        return {
            key: _replace_cached_intercept_mcp_server_url(value, mcp_server_url)
            for key, value in payload.items()
        }

    if isinstance(payload, list):
        return [
            _replace_cached_intercept_mcp_server_url(item, mcp_server_url)
            for item in payload
        ]

    return payload


async def _ensure_langflow_nhi_account(
    db: AsyncSession,
    username: str,
) -> tuple[UserAccount, str]:
    normalized_username = username.strip().lower()
    result = await db.execute(
        select(UserAccount).where(col(UserAccount.username) == normalized_username)
    )
    existing = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)

    if existing is not None:
        if existing.account_type != AccountType.NHI:
            raise LangFlowError(
                f"Username '{normalized_username}' already belongs to a human account"
            )
        if existing.status != UserStatus.ACTIVE:
            raise LangFlowError(
                f"NHI account '{normalized_username}' is not active"
            )

        updated = False
        if existing.role != UserRole.ANALYST:
            existing.role = UserRole.ANALYST
            updated = True
        if existing.description != LANGFLOW_SETUP_NHI_DESCRIPTION:
            existing.description = LANGFLOW_SETUP_NHI_DESCRIPTION
            updated = True

        if updated:
            existing.updated_at = now
            await db.flush()
            return existing, "updated"

        return existing, "reused"

    nhi_account = UserAccount(
        username=normalized_username,
        role=UserRole.ANALYST,
        description=LANGFLOW_SETUP_NHI_DESCRIPTION,
        account_type=AccountType.NHI,
        status=UserStatus.ACTIVE,
        must_change_password=False,
        created_at=now,
        updated_at=now,
    )
    db.add(nhi_account)
    await db.flush()
    return nhi_account, "created"


def _build_api_key_response(api_key) -> ApiKeyRead:
    return ApiKeyRead(
        id=api_key.id,
        user_id=api_key.user_id,
        name=api_key.name,
        prefix=api_key.prefix,
        expires_at=api_key.expires_at,
        last_used_at=api_key.last_used_at,
        revoked_at=api_key.revoked_at,
        created_at=api_key.created_at,
    )


async def _upsert_setting_value(
    settings_service: SettingsService,
    *,
    key: str,
    value: str,
    performed_by: Optional[str],
    audit_context: Optional[AuditContext],
) -> None:
    try:
        await settings_service.update_setting(
            key,
            AppSettingUpdate(value=value),
            performed_by=performed_by,
            audit_context=audit_context,
        )
    except ValueError as exc:
        if "not found" not in str(exc):
            raise

        await settings_service.create_setting(
            AppSettingCreate(
                key=key,
                value=value,
                value_type=SettingType.STRING,
                is_secret=False,
                description=key,
                category="langflow",
            ),
            performed_by=performed_by,
            audit_context=audit_context,
        )


def _describe_provisioning_action(result: LangFlowProvisioningResult, noun: str) -> str:
    return {
        "created": f"Created {noun}",
        "updated": f"Updated {noun}",
        "reused": f"Reused existing {noun}",
    }.get(result.action, f"Processed {noun}")


async def verify_session_access(
    session_id: UUID,
    user: UserAccount,
    db: AsyncSession,
    target_user_id: Optional[UUID] = None,
    target_username: Optional[str] = None,
) -> LangFlowSession:
    """Verify user has access to the session."""
    result = await db.execute(
        select(LangFlowSession).where(LangFlowSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found"
        )
    
    # By default users can only access their own sessions.
    expected_owner_id = target_user_id or user.id
    if session.user_id != expected_owner_id:
        # Admin callers requesting another user's data should not see sessions outside that scope.
        if user.role == UserRole.ADMIN and target_user_id is not None:
            target_desc = f" for user '{target_username}'" if target_username else ""
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found{target_desc}"
            )

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this session"
        )
    
    return session


async def resolve_target_chat_user(
    current_user: UserAccount,
    db: AsyncSession,
    username: Optional[str],
) -> UserAccount:
    """Resolve target chat owner for read operations with admin-only override."""
    if username is None:
        return current_user

    normalized_username = username.strip().lower()
    if not normalized_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="username query parameter must not be blank"
        )

    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can query chats for other users"
        )

    result = await db.execute(
        select(UserAccount).where(col(UserAccount.username) == normalized_username)
    )
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{normalized_username}' not found"
        )

    return target_user


@router.post("/admin/setup-intercept-mcp", response_model=LangFlowSetupResponse)
async def setup_intercept_mcp_server(
    payload: LangFlowSetupRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_admin_user),
):
    """Provision the Intercept MCP server, credential variable, and bundled flows in LangFlow."""
    steps: list[LangFlowSetupStep] = []
    warnings: list[str] = []
    flow_assignments: dict[str, str] = {}
    audit_context = _build_audit_context(request)
    api_key_response: Optional[ApiKeyRead] = None
    nhi_user: Optional[UserAccount] = None
    mcp_server_url: Optional[str] = None
    langflow_project_id: Optional[str] = None
    langflow_service: Optional[LangFlowService] = None

    try:
        mcp_server_url = _derive_intercept_mcp_streamable_url(payload.backend_api_base_url)
        _record_setup_step(
            steps,
            step_id="mcp_url",
            label="Intercept MCP URL",
            step_status="reused",
            message=f"Derived Intercept MCP streamable HTTP URL: {mcp_server_url}",
        )

        langflow_service = await get_langflow_service(db)

        nhi_user, nhi_action = await _ensure_langflow_nhi_account(db, payload.nhi_username)
        _record_setup_step(
            steps,
            step_id="nhi_account",
            label="Automation NHI account",
            step_status=nhi_action,
            message=(
                f"Created NHI account '{nhi_user.username}'"
                if nhi_action == "created"
                else f"Prepared NHI account '{nhi_user.username}'"
            ),
        )

        api_key, raw_key = await api_key_service.create_api_key(
            db,
            user_id=nhi_user.id,
            name=payload.api_key_name,
            expires_at=payload.api_key_expires_at,
            created_by_user_id=current_user.id,
            context=audit_context,
        )
        api_key_response = _build_api_key_response(api_key)
        _record_setup_step(
            steps,
            step_id="api_key",
            label="NHI API key",
            step_status="created",
            message=f"Created API key '{api_key.name}' for '{nhi_user.username}'",
        )

        variable_result = await langflow_service.upsert_credential_variable(
            name=LANGFLOW_SETUP_VARIABLE_NAME,
            value=raw_key,
        )
        _record_setup_step(
            steps,
            step_id="langflow_variable",
            label="Langflow credential variable",
            step_status=variable_result.action,
            message=(
                f"{_describe_provisioning_action(variable_result, 'credential variable')} "
                f"'{LANGFLOW_SETUP_VARIABLE_NAME}'"
            ),
        )

        server_result = await langflow_service.upsert_mcp_server(
            server_name=LANGFLOW_SETUP_SERVER_NAME,
            url=mcp_server_url,
            api_key_variable_name=LANGFLOW_SETUP_VARIABLE_NAME,
        )
        _record_setup_step(
            steps,
            step_id="mcp_server",
            label="Langflow MCP server",
            step_status=server_result.action,
            message=(
                f"{_describe_provisioning_action(server_result, 'MCP server')} "
                f"'{LANGFLOW_SETUP_SERVER_NAME}'"
            ),
        )

        project_result = await langflow_service.ensure_project(
            name=LANGFLOW_SETUP_PROJECT_NAME,
            description=LANGFLOW_SETUP_PROJECT_DESCRIPTION,
        )
        project_id = project_result.payload.get("id")
        if not isinstance(project_id, str) or not project_id.strip():
            raise LangFlowError("LangFlow project provisioning did not return a usable id")
        langflow_project_id = project_id.strip()
        _record_setup_step(
            steps,
            step_id="langflow_project",
            label="Langflow project",
            step_status=project_result.action,
            message=(
                f"{_describe_provisioning_action(project_result, 'project')} "
                f"'{LANGFLOW_SETUP_PROJECT_NAME}'"
            ),
        )

        settings_service = SettingsService(db)  # type: ignore[arg-type]
        flow_summary = await langflow_service.list_flows()
        if not flow_summary.check_result.success:
            raise LangFlowError(flow_summary.check_result.message)

        flows_by_endpoint: dict[str, dict[str, Any]] = {}
        for flow in flow_summary.flows:
            endpoint_name = flow.get("endpoint_name")
            if isinstance(endpoint_name, str) and endpoint_name.strip():
                flows_by_endpoint[endpoint_name.strip()] = flow

        for flow_def in LANGFLOW_BUNDLED_FLOW_ASSETS:
            asset_path = _get_langflow_asset_dir() / flow_def["asset_name"]
            try:
                raw_payload = json.loads(asset_path.read_text(encoding="utf-8"))
            except FileNotFoundError as e:
                raise LangFlowError(f"Missing bundled Langflow asset: {flow_def['asset_name']}") from e

            if not isinstance(raw_payload, dict):
                raise LangFlowError(
                    f"Bundled Langflow asset '{flow_def['asset_name']}' did not contain a JSON object"
                )

            raw_payload = _replace_cached_intercept_mcp_server_url(raw_payload, mcp_server_url)
            sanitized_payload = langflow_service.sanitize_flow_payload(raw_payload)
            sanitized_payload["folder_id"] = langflow_project_id
            endpoint_name = sanitized_payload.get("endpoint_name")
            if not isinstance(endpoint_name, str) or not endpoint_name.strip():
                raise LangFlowError(
                    f"Bundled Langflow asset '{flow_def['asset_name']}' is missing endpoint_name"
                )

            existing_flow = flows_by_endpoint.get(endpoint_name)
            provisioned_flow: dict[str, Any]
            step_status = "created"
            if existing_flow is None:
                provisioned_flow = await langflow_service.create_flow(sanitized_payload)
                flows_by_endpoint[endpoint_name] = provisioned_flow
                step_message = f"Created bundled flow '{flow_def['label']}'"
            else:
                provisioned_flow = existing_flow
                existing_flow_id = existing_flow.get("id")
                if not isinstance(existing_flow_id, str) or not existing_flow_id.strip():
                    raise LangFlowError(
                        f"Existing Langflow flow '{flow_def['label']}' did not return a usable id"
                    )

                project_assignment_updated = False
                if existing_flow.get("folder_id") != langflow_project_id:
                    provisioned_flow = await langflow_service.update_flow(
                        existing_flow_id,
                        {"folder_id": langflow_project_id},
                    )
                    flows_by_endpoint[endpoint_name] = provisioned_flow
                    project_assignment_updated = True

                if langflow_service.flow_matches_expected(existing_flow, sanitized_payload):
                    if project_assignment_updated:
                        step_status = "updated"
                        step_message = (
                            f"Reused existing bundled flow '{flow_def['label']}' and assigned it to "
                            f"project '{LANGFLOW_SETUP_PROJECT_NAME}'"
                        )
                    else:
                        step_status = "reused"
                        step_message = f"Reused existing bundled flow '{flow_def['label']}'"
                else:
                    step_status = "warning"
                    step_message = (
                        f"Existing flow '{flow_def['label']}' differs from the bundled asset and was not overwritten"
                    )
                    if project_assignment_updated:
                        step_message = (
                            f"{step_message}; updated its project assignment to '{LANGFLOW_SETUP_PROJECT_NAME}'"
                        )
                    warnings.append(step_message)

            flow_id = provisioned_flow.get("id")
            if flow_def["setting_key"] is not None:
                if not isinstance(flow_id, str) or not flow_id.strip():
                    raise LangFlowError(
                        f"Langflow flow '{flow_def['label']}' did not return a usable id"
                    )

                await _upsert_setting_value(
                    settings_service,
                    key=flow_def["setting_key"],
                    value=flow_id,
                    performed_by=current_user.username,
                    audit_context=audit_context,
                )
                flow_assignments[flow_def["setting_key"]] = flow_id
                step_message = f"{step_message}; updated {flow_def['setting_key']}"

            _record_setup_step(
                steps,
                step_id=f"flow:{endpoint_name}",
                label=flow_def["label"],
                step_status=step_status,
                message=step_message,
            )

        success_message = "Intercept MCP server setup completed"
        if warnings:
            success_message = f"{success_message} with warnings"

        return LangFlowSetupResponse(
            success=True,
            message=success_message,
            steps=steps,
            warnings=warnings,
            nhi_user_id=nhi_user.id if nhi_user else None,
            nhi_username=nhi_user.username if nhi_user else None,
            api_key=api_key_response,
            mcp_server_name=LANGFLOW_SETUP_SERVER_NAME,
            mcp_server_url=mcp_server_url,
            variable_name=LANGFLOW_SETUP_VARIABLE_NAME,
            flow_assignments=flow_assignments,
        )
    except LangFlowConfigurationError as e:
        message = str(e)
    except (LangFlowError, ValueError) as e:
        message = str(e)
    except Exception as e:
        logger.exception("Intercept MCP setup failed")
        message = f"Intercept MCP setup failed: {str(e)}"

    _record_setup_step(
        steps,
        step_id="setup_failed",
        label="Setup failed",
        step_status="failed",
        message=message,
    )
    return LangFlowSetupResponse(
        success=False,
        message=message,
        steps=steps,
        warnings=warnings,
        nhi_user_id=nhi_user.id if nhi_user else None,
        nhi_username=nhi_user.username if nhi_user else None,
        api_key=api_key_response,
        mcp_server_name=LANGFLOW_SETUP_SERVER_NAME,
        mcp_server_url=mcp_server_url,
        variable_name=LANGFLOW_SETUP_VARIABLE_NAME,
        flow_assignments=flow_assignments,
    )


# Endpoints

@router.post("/sessions", response_model=LangFlowSessionRead, status_code=status.HTTP_201_CREATED)
async def create_session(
    session_create: LangFlowSessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
):
    """
    Create a new LangFlow chat session.
    
    Requires authentication. Creates a session linked to the current user.
    The flow_id is determined by the context_type from server settings.
    """
    # Determine flow_id based on context_type from server settings
    settings_service = SettingsService(db)  # type: ignore[arg-type]
    context_type = session_create.context_type or "general"
    
    try:
        flow_id = await settings_service.get_flow_id_for_context(context_type)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    session = LangFlowSession(
        flow_id=flow_id,
        title=session_create.title,
        context=session_create.context or {},
        user_id=current_user.id,
    )
    
    db.add(session)
    await db.commit()
    await db.refresh(session)
    
    logger.info(
        f"Created LangFlow session",
        extra={
            "session_id": str(session.id),
            "user_id": str(current_user.id),
            "flow_id": session.flow_id,
        }
    )
    
    return LangFlowSessionRead(
        **session.model_dump(),
        message_count=0,
    )


@router.get("/sessions", response_model=List[LangFlowSessionRead])
async def list_sessions(
    skip: int = 0,
    limit: int = 50,
    username: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
):
    """
    List chat sessions for the current user by default.
    
    Requires authentication. Returns sessions in reverse chronological order (most recent first).
    Supports pagination with skip and limit parameters. Admin users may provide
    a username query parameter to list sessions for a specific user.
    """
    from sqlalchemy import func

    target_user = await resolve_target_chat_user(current_user, db, username)
    
    # Query sessions for current user with message counts
    result = await db.execute(
        select(LangFlowSession)
        .where(LangFlowSession.user_id == target_user.id)
        .order_by(col(LangFlowSession.updated_at).desc())
        .offset(skip)
        .limit(limit)
    )
    sessions = result.scalars().all()
    
    # Get message counts for each session
    session_reads = []
    for session in sessions:
        msg_result = await db.execute(
            select(func.count(LangFlowMessage.id))
            .where(LangFlowMessage.session_id == session.id)
        )
        message_count = msg_result.scalar() or 0
        session_reads.append(LangFlowSessionRead(
            **session.model_dump(),
            message_count=message_count,
        ))
    
    logger.info(
        f"Listed LangFlow sessions",
        extra={
            "requesting_user_id": str(current_user.id),
            "target_user_id": str(target_user.id),
            "target_username": target_user.username,
            "count": len(session_reads),
            "skip": skip,
            "limit": limit,
        }
    )
    
    return session_reads


@router.get("/sessions/{session_id}", response_model=LangFlowSessionRead)
async def get_session(
    session_id: UUID,
    username: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
):
    """
    Get a specific session for the current user by default.
    
    Requires authentication. Users can only access their own sessions.
    Admin users may provide a username query parameter to get sessions for a specific user.
    """
    target_user = await resolve_target_chat_user(current_user, db, username)
    session = await verify_session_access(
        session_id,
        current_user,
        db,
        target_user_id=target_user.id,
        target_username=target_user.username,
    )
    
    # Count messages
    messages_result = await db.execute(
        select(LangFlowMessage).where(LangFlowMessage.session_id == session_id)
    )
    message_count = len(messages_result.scalars().all())
    
    return LangFlowSessionRead(
        **session.model_dump(),
        message_count=message_count,
    )


@router.patch("/sessions/{session_id}", response_model=LangFlowSessionRead)
async def update_session(
    session_id: UUID,
    session_update: LangFlowSessionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
):
    """
    Update a session (context or status).
    
    Requires authentication. Users can only update their own sessions.
    """
    session = await verify_session_access(session_id, current_user, db)
    
    # Update fields
    update_data = session_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(session, field, value)
    
    session.updated_at = datetime.now(timezone.utc)
    
    # If status is being set to completed, set completed_at
    if session_update.status in [SessionStatus.COMPLETED, SessionStatus.FAILED, SessionStatus.TIMEOUT]:
        if not session.completed_at:
            session.completed_at = datetime.now(timezone.utc)
    
    await db.commit()
    await db.refresh(session)
    
    logger.info(
        f"Updated LangFlow session",
        extra={
            "session_id": str(session.id),
            "user_id": str(current_user.id),
            "status": session.status,
        }
    )
    
    # Count messages
    messages_result = await db.execute(
        select(LangFlowMessage).where(LangFlowMessage.session_id == session_id)
    )
    message_count = len(messages_result.scalars().all())
    
    return LangFlowSessionRead(
        **session.model_dump(),
        message_count=message_count,
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
):
    """
    Delete a chat session and all its messages.
    
    Requires authentication. Users can only delete their own sessions.
    """
    session = await verify_session_access(session_id, current_user, db)
    
    # Delete all messages first (cascade may not be set up)
    await db.execute(
        select(LangFlowMessage).where(LangFlowMessage.session_id == session_id)
    )
    from sqlalchemy import delete as sql_delete
    await db.execute(
        sql_delete(LangFlowMessage).where(LangFlowMessage.session_id == session_id)
    )
    
    # Delete the session
    await db.delete(session)
    await db.commit()
    
    logger.info(
        f"Deleted LangFlow session",
        extra={
            "session_id": str(session_id),
            "user_id": str(current_user.id),
        }
    )


@router.get("/sessions/{session_id}/messages", response_model=List[LangFlowMessageRead])
async def get_session_messages(
    session_id: UUID,
    username: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
):
    """
    Get all messages for a session.
    
    Requires authentication. Users can only access messages from their own sessions.
    Returns messages in chronological order. Admin users may provide a username
    query parameter to access messages for sessions belonging to a specific user.
    """
    target_user = await resolve_target_chat_user(current_user, db, username)

    # Verify access
    await verify_session_access(
        session_id,
        current_user,
        db,
        target_user_id=target_user.id,
        target_username=target_user.username,
    )
    
    # Get messages
    result = await db.execute(
        select(LangFlowMessage)
        .where(LangFlowMessage.session_id == session_id)
        .order_by(LangFlowMessage.created_at)
    )
    messages = result.scalars().all()
    
    return [LangFlowMessageRead(**msg.model_dump()) for msg in messages]


@router.patch("/messages/{message_id}/feedback", response_model=LangFlowMessageRead)
async def set_message_feedback(
    message_id: UUID,
    request: MessageFeedbackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
):
    """
    Set feedback on a chat message.
    
    Requires authentication. Users can only set feedback on messages from their own sessions.
    """
    # Get the message
    result = await db.execute(
        select(LangFlowMessage).where(LangFlowMessage.id == message_id)
    )
    message = result.scalar_one_or_none()
    
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )
    
    # Verify user has access to the session
    await verify_session_access(message.session_id, current_user, db)
    
    # Update feedback
    message.feedback = request.feedback
    db.add(message)
    await db.commit()
    await db.refresh(message)
    
    logger.info(
        f"Set feedback on message",
        extra={
            "message_id": str(message_id),
            "feedback": request.feedback.value,
            "user_id": str(current_user.id),
        }
    )
    
    return LangFlowMessageRead(**message.model_dump())


@router.delete("/messages/{message_id}/feedback", response_model=LangFlowMessageRead)
async def clear_message_feedback(
    message_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
):
    """
    Clear feedback on a chat message.
    
    Requires authentication. Users can only clear feedback on messages from their own sessions.
    """
    # Get the message
    result = await db.execute(
        select(LangFlowMessage).where(LangFlowMessage.id == message_id)
    )
    message = result.scalar_one_or_none()
    
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )
    
    # Verify user has access to the session
    await verify_session_access(message.session_id, current_user, db)
    
    # Clear feedback
    message.feedback = None
    db.add(message)
    await db.commit()
    await db.refresh(message)
    
    logger.info(
        f"Cleared feedback on message",
        extra={
            "message_id": str(message_id),
            "user_id": str(current_user.id),
        }
    )
    
    return LangFlowMessageRead(**message.model_dump())


@router.post("/chat", response_model=ChatResponse)
async def send_chat_message(
    chat_request: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
):
    """
    Send a chat message to LangFlow.
    
    Requires authentication. Creates user message and sends to LangFlow.
    Returns response with message ID and streaming URL.
    """
    # Verify session access
    session = await verify_session_access(chat_request.session_id, current_user, db)
    
    # Validate session is active
    if session.status != SessionStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Session is {session.status}, not ACTIVE"
        )
    
    # Create user message
    user_message = LangFlowMessage(
        session_id=session.id,
        role=MessageRole.USER,
        content=chat_request.content,
        message_metadata={},
    )
    db.add(user_message)
    await db.commit()
    await db.refresh(user_message)
    
    logger.info(
        f"Created user message",
        extra={
            "message_id": str(user_message.id),
            "session_id": str(session.id),
            "user_id": str(current_user.id),
        }
    )
    
    # Get LangFlow service
    langflow_service = await get_langflow_service(db)
    
    try:
        # Send message to LangFlow (non-streaming for now)
        response = await langflow_service.send_message(
            flow_id=session.flow_id,
            message=chat_request.content,
            session_id=session.id,
            context=chat_request.context or session.context,
        )
        
        # Extract response content
        # This depends on LangFlow's response format - adjust as needed
        assistant_content = response.get("output", response.get("text", str(response)))
        
        # Create assistant message
        assistant_message = LangFlowMessage(
            session_id=session.id,
            role=MessageRole.ASSISTANT,
            content=assistant_content,
            message_metadata={"langflow_response": response},
        )
        db.add(assistant_message)
        
        # Update session context if provided in response
        if "context" in response:
            session.context = response["context"]
        
        session.updated_at = datetime.now(timezone.utc)
        
        await db.commit()
        await db.refresh(assistant_message)
        
        logger.info(
            f"Created assistant message",
            extra={
                "message_id": str(assistant_message.id),
                "session_id": str(session.id),
            }
        )
        
        return ChatResponse(
            message_id=user_message.id,
            session_id=session.id,
            status="completed",
            stream_url=None,  # Will be used for SSE in Phase 5
        )
        
    except LangFlowConnectionError as e:
        logger.error(f"LangFlow connection error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to connect to LangFlow service. Please try again later."
        )
    except LangFlowError as e:
        logger.error(f"LangFlow error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing your message."
        )
    finally:
        await langflow_service.close()


@router.post("/test-connection", response_model=TestConnectionResponse)
async def test_langflow_connection(
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
):
    """
    Test connection to LangFlow.
    
    Requires authentication. Useful for validating configuration.
    """
    try:
        langflow_service = await get_langflow_service(db)
        settings_service = SettingsService(db)  # type: ignore[arg-type]
        try:
            configured_flow_settings = [
                ("Default flow", "langflow.default_flow_id"),
                ("Case detail flow", "langflow.case_detail_flow_id"),
                ("Task detail flow", "langflow.task_detail_flow_id"),
                ("Alert triage flow", "langflow.alert_triage_flow_id"),
            ]
            configured_flows = {}
            for label, setting_key in configured_flow_settings:
                value = await settings_service.get_typed_value(setting_key)
                if isinstance(value, str) and value.strip():
                    configured_flows[label] = value.strip()

            flow_summary = await langflow_service.list_flows()
            check_results = [
                await langflow_service.run_connectivity_check(),
                flow_summary.check_result,
                langflow_service.validate_configured_flows(
                    configured_flows=configured_flows,
                    flows=flow_summary.flows,
                ) if flow_summary.check_result.success else LangFlowCheckResult(
                    check_id="configured_flows",
                    label="Configured flow existence",
                    success=False,
                    message="Unable to validate configured flows because LangFlow flow listing failed",
                ),
            ]
        finally:
            await langflow_service.close()

        checks = [
            LangFlowConnectionCheck(
                id=result.check_id,
                label=result.label,
                success=result.success,
                message=result.message,
            )
            for result in check_results
        ]
        success = all(check.success for check in checks)
        passed_checks = sum(1 for check in checks if check.success)
        total_checks = len(checks)

        return TestConnectionResponse(
            success=success,
            message=(
                "LangFlow connectivity, flow listing, and configured flow checks passed"
                if success
                else f"{passed_checks} of {total_checks} LangFlow checks passed"
            ),
            checks=checks,
        )
    except LangFlowConfigurationError as e:
        message = str(e)
        return TestConnectionResponse(
            success=False,
            message=message,
            checks=[
                LangFlowConnectionCheck(
                    id="connectivity",
                    label="Connectivity",
                    success=False,
                    message=message,
                ),
                LangFlowConnectionCheck(
                    id="flow_listing",
                    label="Authenticated flow listing",
                    success=False,
                    message=message,
                ),
                LangFlowConnectionCheck(
                    id="configured_flows",
                    label="Configured flow existence",
                    success=False,
                    message=message,
                ),
            ],
        )
    except Exception as e:
        logger.error(f"Connection test error: {e}")
        return TestConnectionResponse(
            success=False,
            message=f"Connection test failed: {str(e)}",
            checks=[
                LangFlowConnectionCheck(
                    id="connectivity",
                    label="Connectivity",
                    success=False,
                    message=f"Connection test failed: {str(e)}",
                ),
                LangFlowConnectionCheck(
                    id="flow_listing",
                    label="Authenticated flow listing",
                    success=False,
                    message=f"Connection test failed: {str(e)}",
                ),
                LangFlowConnectionCheck(
                    id="configured_flows",
                    label="Configured flow existence",
                    success=False,
                    message=f"Connection test failed: {str(e)}",
                ),
            ],
        )


@router.post("/stream/{session_id}")
async def stream_langflow_response(
    session_id: UUID,
    body: StreamChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
):
    """
    Stream LangFlow response via Server-Sent Events (SSE).
    
    Requires authentication. Users can only stream from their own sessions.
    
    This endpoint establishes an SSE connection and streams AI responses in real-time.
    Use EventSource API on frontend to consume the stream.
    
    Request body:
    - message: The message to send to LangFlow
    """
    # Verify session access
    session = await verify_session_access(session_id, current_user, db)
    
    # Validate session is active
    if session.status != SessionStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Session is {session.status}, not ACTIVE"
        )
    
    # Get services
    langflow_service = await get_langflow_service(db)
    sse_service = get_sse_service()
    
    async def event_generator():
        """Generate SSE events from LangFlow stream."""
        try:
            # Create user message
            user_message = LangFlowMessage(
                session_id=session.id,
                role=MessageRole.USER,
                content=body.message,
                message_metadata={},
            )
            db.add(user_message)
            await db.commit()
            await db.refresh(user_message)
            
            logger.info(
                f"Starting LangFlow stream",
                extra={
                    "session_id": str(session.id),
                    "user_id": str(current_user.id),
                }
            )
            
            # Accumulate assistant response
            assistant_content = ""
            
            # Stream from LangFlow
            async for chunk in langflow_service.stream_message(
                flow_id=session.flow_id,
                message=body.message,
                session_id=session.id,
                context=body.context or session.context,
            ):
                # LangFlow SSE events have multiple types:
                # 1. {'event': 'add_message', 'data': {'sender': 'User'|'Machine', 'text': '...', 'properties': {'state': 'partial'|'complete'}}}
                # 2. {'event': 'token', 'data': {'chunk': '...'}} - streaming tokens
                # 3. {'event': 'end', 'data': {...}} - stream complete
                
                event_type = chunk.get("event", "")
                event_data = chunk.get("data", {})
                
                # Handle token events - these are the actual streaming tokens
                if event_type == "token":
                    token_content = event_data.get("chunk", "")
                    if token_content:
                        assistant_content += token_content
                        # Yield token as SSE event
                        yield {
                            "event": "message",
                            "data": {
                                "content": token_content,
                                "partial": True,
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            }
                        }
                    continue
                
                # Handle add_message events - skip User messages and partial Machine messages
                if event_type == "add_message":
                    sender = event_data.get("sender", "")
                    if sender == "User":
                        logger.debug(f"Skipping user message echo")
                        continue
                    
                    # Check if this is a complete message (not partial)
                    properties = event_data.get("properties", {})
                    state = properties.get("state", "")
                    
                    # When we get the complete message, use its text as the authoritative version
                    # (it has proper formatting that may be lost in token accumulation)
                    if state == "complete":
                        complete_text = event_data.get("text", "")
                        if complete_text:
                            # Use the complete message text - it has proper formatting
                            assistant_content = complete_text
                    continue
                
                # Handle end event - stream is complete
                if event_type == "end":
                    logger.debug("Received end event from LangFlow")
                    continue
            
            # Create assistant message with full content
            assistant_message = LangFlowMessage(
                session_id=session.id,
                role=MessageRole.ASSISTANT,
                content=assistant_content,
                message_metadata={"streamed": True},
            )
            db.add(assistant_message)
            
            # Update session
            session.updated_at = datetime.now(timezone.utc)
            
            await db.commit()
            
            logger.info(
                f"Completed LangFlow stream",
                extra={
                    "session_id": str(session.id),
                    "response_length": len(assistant_content),
                }
            )
            
            # Send final event
            yield {
                "event": "complete",
                "data": {
                    "message_id": str(assistant_message.id),
                    "content": assistant_content,
                    "partial": False,
                }
            }
            
        except Exception as e:
            logger.error(f"Error in LangFlow stream: {e}")
            yield {
                "event": "error",
                "data": {
                    "error": "An error occurred while processing your message",
                }
            }
        finally:
            await langflow_service.close()
    
    # Return SSE response
    return StreamingResponse(
        sse_service.stream_events(session_id, event_generator()),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
