"""
LangFlow API routes for AI chat functionality.

Provides endpoints for:
- Managing chat sessions
- Sending messages
- Retrieving conversation history
- Streaming responses via SSE
"""
from __future__ import annotations

from typing import List, Optional, Dict, Any
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, col
from datetime import datetime, timezone

from app.api.routes.admin_auth import require_authenticated_user
from app.core.database import get_db
from app.models.models import (
    LangFlowSession,
    LangFlowSessionCreate,
    LangFlowSessionUpdate,
    LangFlowSessionRead,
    LangFlowMessage,
    LangFlowMessageCreate,
    LangFlowMessageRead,
    UserAccount,
)
from app.models.enums import SessionStatus, MessageRole, MessageFeedback
from app.services.langflow_service import (
    LangFlowService,
    LangFlowConfigurationError,
    LangFlowConnectionError,
    LangFlowError,
)
from app.services.settings_service import SettingsService
from app.services.sse_service import get_sse_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/langflow", tags=["langflow"])


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


class SessionWithMessages(BaseModel):
    """Session with message count."""
    session: LangFlowSessionRead
    message_count: int


class TestConnectionResponse(BaseModel):
    """Response from connection test."""
    success: bool
    message: str


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


async def verify_session_access(
    session_id: UUID,
    user: UserAccount,
    db: AsyncSession,
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
    
    # Users can only access their own sessions
    if session.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this session"
        )
    
    return session


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
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
):
    """
    List all chat sessions for the current user.
    
    Requires authentication. Returns sessions in reverse chronological order (most recent first).
    Supports pagination with skip and limit parameters.
    """
    from sqlalchemy import func
    
    # Query sessions for current user with message counts
    result = await db.execute(
        select(LangFlowSession)
        .where(LangFlowSession.user_id == current_user.id)
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
            "user_id": str(current_user.id),
            "count": len(session_reads),
            "skip": skip,
            "limit": limit,
        }
    )
    
    return session_reads


@router.get("/sessions/{session_id}", response_model=LangFlowSessionRead)
async def get_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
):
    """
    Get a specific session.
    
    Requires authentication. Users can only access their own sessions.
    """
    session = await verify_session_access(session_id, current_user, db)
    
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
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
):
    """
    Get all messages for a session.
    
    Requires authentication. Users can only access messages from their own sessions.
    Returns messages in chronological order.
    """
    # Verify access
    await verify_session_access(session_id, current_user, db)
    
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
        success = await langflow_service.test_connection()
        await langflow_service.close()
        
        if success:
            return TestConnectionResponse(
                success=True,
                message="Successfully connected to LangFlow"
            )
        else:
            return TestConnectionResponse(
                success=False,
                message="LangFlow is not responding to health checks"
            )
    except LangFlowConfigurationError as e:
        return TestConnectionResponse(
            success=False,
            message=str(e)
        )
    except Exception as e:
        logger.error(f"Connection test error: {e}")
        return TestConnectionResponse(
            success=False,
            message=f"Connection test failed: {str(e)}"
        )


@router.get("/stream/{session_id}")
async def stream_langflow_response(
    session_id: UUID,
    message: str,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(require_authenticated_user),
):
    """
    Stream LangFlow response via Server-Sent Events (SSE).
    
    Requires authentication. Users can only stream from their own sessions.
    
    This endpoint establishes an SSE connection and streams AI responses in real-time.
    Use EventSource API on frontend to consume the stream.
    
    Query params:
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
                content=message,
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
                message=message,
                session_id=session.id,
                context=session.context,
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
