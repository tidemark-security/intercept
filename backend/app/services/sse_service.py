"""
SSE (Server-Sent Events) service for real-time streaming.

Provides event streaming infrastructure for:
- LangFlow response streaming
- Connection lifecycle management
- Event formatting and delivery
"""
import asyncio
import logging
from typing import AsyncGenerator, Dict, Any, Optional
from uuid import UUID
from datetime import datetime, timezone
import json

logger = logging.getLogger(__name__)


class SSEService:
    """
    Service for managing Server-Sent Events connections.
    
    Handles:
    - Event formatting (SSE protocol)
    - Connection timeout management
    - Cleanup on disconnect
    """
    
    def __init__(self, timeout_seconds: int = 300):
        """
        Initialize SSE service.
        
        Args:
            timeout_seconds: Connection timeout (default 5 minutes)
        """
        self.timeout_seconds = timeout_seconds
        self.active_connections: Dict[UUID, datetime] = {}
    
    async def stream_events(
        self,
        session_id: UUID,
        event_generator: AsyncGenerator[Dict[str, Any], None],
    ) -> AsyncGenerator[str, None]:
        """
        Stream events in SSE format.
        
        Args:
            session_id: Session identifier for tracking
            event_generator: Async generator yielding event data
            
        Yields:
            SSE-formatted event strings
        """
        try:
            # Track connection
            self.active_connections[session_id] = datetime.now(timezone.utc)
            
            logger.info(
                f"Started SSE stream",
                extra={"session_id": str(session_id)}
            )
            
            # Send initial connection event
            yield self.format_event(
                event="connected",
                data={"session_id": str(session_id), "timestamp": datetime.now(timezone.utc).isoformat()}
            )
            
            # Stream events from generator
            async for event_data in event_generator:
                # Update connection timestamp
                self.active_connections[session_id] = datetime.now(timezone.utc)
                
                # Format and yield event
                event_type = event_data.get("event", "message")
                data = event_data.get("data", event_data)
                
                yield self.format_event(event=event_type, data=data)
            
            # Send completion event
            yield self.format_event(
                event="complete",
                data={"session_id": str(session_id), "status": "completed"}
            )
            
            logger.info(
                f"Completed SSE stream",
                extra={"session_id": str(session_id)}
            )
            
        except asyncio.CancelledError:
            logger.info(
                f"SSE stream cancelled",
                extra={"session_id": str(session_id)}
            )
            # Send cancellation event
            yield self.format_event(
                event="cancelled",
                data={"session_id": str(session_id), "status": "cancelled"}
            )
        except Exception as e:
            logger.error(
                f"SSE stream error: {e}",
                extra={"session_id": str(session_id)}
            )
            # Send error event
            yield self.format_event(
                event="error",
                data={"session_id": str(session_id), "error": "Stream error occurred"}
            )
        finally:
            # Cleanup connection
            if session_id in self.active_connections:
                del self.active_connections[session_id]
            
            logger.info(
                f"Cleaned up SSE connection",
                extra={"session_id": str(session_id)}
            )
    
    @staticmethod
    def format_event(event: str, data: Any, event_id: Optional[str] = None) -> str:
        """
        Format data as SSE event.
        
        Args:
            event: Event type/name
            data: Event data (will be JSON-serialized)
            event_id: Optional event ID for client-side tracking
            
        Returns:
            SSE-formatted event string
        """
        lines = []
        
        # Add event ID if provided
        if event_id:
            lines.append(f"id: {event_id}")
        
        # Add event type
        lines.append(f"event: {event}")
        
        # Add data (JSON-serialized)
        if isinstance(data, str):
            data_str = data
        else:
            data_str = json.dumps(data)
        lines.append(f"data: {data_str}")
        
        # SSE format: lines joined with \n, terminated with \n\n
        return "\n".join(lines) + "\n\n"
    
    @staticmethod
    def format_heartbeat() -> str:
        """
        Format a heartbeat comment (keeps connection alive).
        
        Returns:
            SSE comment string
        """
        return f": heartbeat {datetime.now(timezone.utc).isoformat()}\n\n"
    
    async def send_heartbeats(
        self,
        interval_seconds: int = 30,
    ) -> AsyncGenerator[str, None]:
        """
        Generate periodic heartbeat events.
        
        Args:
            interval_seconds: Heartbeat interval
            
        Yields:
            Heartbeat comment strings
        """
        while True:
            await asyncio.sleep(interval_seconds)
            yield self.format_heartbeat()
    
    def get_active_connection_count(self) -> int:
        """Get count of active SSE connections."""
        return len(self.active_connections)
    
    def cleanup_stale_connections(self, max_age_seconds: int = 3600) -> int:
        """
        Remove stale connection tracking.
        
        Args:
            max_age_seconds: Max age before considering stale
            
        Returns:
            Number of connections cleaned up
        """
        now = datetime.now(timezone.utc)
        stale_sessions = [
            session_id
            for session_id, timestamp in self.active_connections.items()
            if (now - timestamp).total_seconds() > max_age_seconds
        ]
        
        for session_id in stale_sessions:
            del self.active_connections[session_id]
            logger.warning(
                f"Cleaned up stale SSE connection",
                extra={"session_id": str(session_id)}
            )
        
        return len(stale_sessions)


# Global SSE service instance
_sse_service: Optional[SSEService] = None


def get_sse_service() -> SSEService:
    """Get the global SSE service instance."""
    global _sse_service
    if _sse_service is None:
        _sse_service = SSEService()
    return _sse_service
