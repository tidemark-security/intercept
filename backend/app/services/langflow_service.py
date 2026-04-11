"""
LangFlow service for AI chat integration.

Provides a wrapper around LangFlow API for:
- Sending chat messages
- Managing conversation sessions
- Streaming responses
- Error handling and retry logic
"""
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, AsyncGenerator
from uuid import UUID
import httpx
from datetime import datetime, timezone

from app.services.settings_service import SettingsService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LangFlowCheckResult:
    """Represents the outcome of a LangFlow environment validation check."""

    check_id: str
    label: str
    success: bool
    message: str


@dataclass(frozen=True)
class LangFlowSummaryResult:
    """Represents a successful LangFlow API read plus the returned flow metadata."""

    check_result: LangFlowCheckResult
    flows: list[dict[str, Any]]


class LangFlowError(Exception):
    """Base exception for LangFlow-related errors."""
    pass


class LangFlowConnectionError(LangFlowError):
    """Raised when unable to connect to LangFlow."""
    pass


class LangFlowConfigurationError(LangFlowError):
    """Raised when LangFlow is not properly configured."""
    pass


class LangFlowService:
    """
    Service for interacting with LangFlow API.
    
    Handles communication with external LangFlow instance, including:
    - Session management
    - Message sending
    - Response streaming
    - Error handling
    """
    
    def __init__(self, base_url: str, api_key: Optional[str] = None, timeout: float = 30.0):
        """
        Initialize LangFlow service.
        
        Args:
            base_url: LangFlow API base URL
            api_key: Optional API key for authentication
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.timeout = timeout
        
        # Configure headers
        headers = {
            "Content-Type": "application/json",
        }
        if api_key:
            # LangFlow uses x-api-key header for authentication
            headers["x-api-key"] = api_key
        
        # Create async HTTP client
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=timeout,
        )
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    def _get_health_url(self) -> str:
        """Return the root health endpoint URL for the configured LangFlow host."""
        scheme = self.client.base_url.scheme.decode() if isinstance(self.client.base_url.scheme, bytes) else self.client.base_url.scheme
        netloc = self.client.base_url.netloc.decode() if isinstance(self.client.base_url.netloc, bytes) else self.client.base_url.netloc
        return f"{scheme}://{netloc}/health"
    
    async def send_message(
        self,
        flow_id: str,
        message: str,
        session_id: Optional[UUID] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Send a message to LangFlow and get a response.
        
        Args:
            flow_id: LangFlow flow identifier
            message: User message content
            session_id: Optional session ID for conversation continuity
            context: Optional additional context for the flow
            
        Returns:
            Response from LangFlow containing the assistant's reply
            
        Raises:
            LangFlowConnectionError: If unable to connect to LangFlow
            LangFlowError: For other LangFlow-related errors
        """
        try:
            # LangFlow SimplifiedAPIRequest format
            payload = {
                "input_value": message,
                "input_type": "chat",
                "output_type": "chat",
            }
            
            if session_id:
                payload["session_id"] = str(session_id)
            
            if context:
                payload["tweaks"] = context
            
            logger.info(
                f"Sending message to LangFlow",
                extra={
                    "flow_id": flow_id,
                    "session_id": str(session_id) if session_id else None,
                    "message_length": len(message),
                }
            )
            
            # Flow ID is part of the URL path
            response = await self.client.post(
                f"/run/{flow_id}",
                json=payload,
            )
            response.raise_for_status()
            
            data = response.json()
            
            logger.info(
                f"Received response from LangFlow",
                extra={
                    "flow_id": flow_id,
                    "session_id": str(session_id) if session_id else None,
                    "response_keys": list(data.keys()) if isinstance(data, dict) else None,
                }
            )
            
            return data
            
        except httpx.ConnectError as e:
            logger.error(f"Failed to connect to LangFlow: {e}")
            raise LangFlowConnectionError(
                f"Unable to connect to LangFlow at {self.base_url}. "
                "Please check your LangFlow configuration."
            ) from e
        except httpx.HTTPStatusError as e:
            logger.error(f"LangFlow API error: {e.response.status_code} - {e.response.text}")
            raise LangFlowError(
                f"LangFlow API returned error {e.response.status_code}"
            ) from e
        except httpx.TimeoutException as e:
            logger.error(f"LangFlow request timed out: {e}")
            raise LangFlowError(
                f"LangFlow request timed out after {self.timeout} seconds"
            ) from e
        except Exception as e:
            logger.error(f"Unexpected error communicating with LangFlow: {e}")
            raise LangFlowError(f"Unexpected error: {str(e)}") from e
    
    async def stream_message(
        self,
        flow_id: str,
        message: str,
        session_id: Optional[UUID] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Send a message to LangFlow and stream the response.
        
        Args:
            flow_id: LangFlow flow identifier
            message: User message content
            session_id: Optional session ID for conversation continuity
            context: Optional additional context for the flow
            
        Yields:
            Response chunks from LangFlow as they arrive
            
        Raises:
            LangFlowConnectionError: If unable to connect to LangFlow
            LangFlowError: For other LangFlow-related errors
        """
        try:
            # LangFlow SimplifiedAPIRequest format
            payload = {
                "input_value": message,
                "input_type": "chat",
                "output_type": "chat",
            }
            
            if session_id:
                payload["session_id"] = str(session_id)
            
            if context:
                payload["tweaks"] = context
            
            logger.info(
                f"Starting streaming message to LangFlow",
                extra={
                    "flow_id": flow_id,
                    "session_id": str(session_id) if session_id else None,
                    "message_length": len(message),
                }
            )
            
            # Flow ID is part of URL path, stream is a query param
            async with self.client.stream("POST", f"/run/{flow_id}?stream=true", json=payload) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    logger.debug(f"LangFlow stream line: {line[:200] if len(line) > 200 else line}")
                    if line.startswith("data: "):
                        # Parse SSE data format
                        data_str = line[6:].strip()
                        if data_str and data_str != "[DONE]":
                            try:
                                import json
                                data = json.loads(data_str)
                                logger.info(f"LangFlow SSE data keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
                                yield data
                            except json.JSONDecodeError:
                                logger.warning(f"Failed to parse SSE data: {data_str}")
                                continue
                    elif line.strip():
                        # Handle other line formats - might be raw JSON
                        try:
                            import json
                            data = json.loads(line)
                            logger.info(f"LangFlow raw JSON keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
                            yield data
                        except json.JSONDecodeError:
                            logger.debug(f"Received non-JSON SSE line: {line[:100]}")
            
            logger.info(
                f"Finished streaming from LangFlow",
                extra={
                    "flow_id": flow_id,
                    "session_id": str(session_id) if session_id else None,
                }
            )
            
        except httpx.ConnectError as e:
            logger.error(f"Failed to connect to LangFlow: {e}")
            raise LangFlowConnectionError(
                f"Unable to connect to LangFlow at {self.base_url}"
            ) from e
        except httpx.HTTPStatusError as e:
            logger.error(f"LangFlow API error: {e.response.status_code}")
            raise LangFlowError(
                f"LangFlow API returned error {e.response.status_code}"
            ) from e
        except Exception as e:
            logger.error(f"Unexpected error streaming from LangFlow: {e}")
            raise LangFlowError(f"Unexpected error: {str(e)}") from e
    
    async def test_connection(self) -> bool:
        """
        Test connection to LangFlow.
        
        Returns:
            True if connection successful, False otherwise
        """
        result = await self.run_connectivity_check()
        return result.success

    async def run_connectivity_check(self) -> LangFlowCheckResult:
        """Validate basic network connectivity to the LangFlow health endpoint."""
        try:
            health_url = self._get_health_url()
            response = await self.client.get(health_url)            
            # Validate both status code and response content
            # LangFlow returns {"status":"ok"} for health endpoint
            # Invalid endpoints may redirect to home page with 200 status
            if response.status_code != 200:
                return LangFlowCheckResult(
                    check_id="connectivity",
                    label="Connectivity",
                    success=False,
                    message=f"LangFlow health endpoint returned HTTP {response.status_code}",
                )
            
            try:
                data = response.json()
                if data.get("status") == "ok":
                    return LangFlowCheckResult(
                        check_id="connectivity",
                        label="Connectivity",
                        success=True,
                        message="Connected to the LangFlow health endpoint",
                    )

                return LangFlowCheckResult(
                    check_id="connectivity",
                    label="Connectivity",
                    success=False,
                    message="LangFlow health endpoint did not return the expected status payload",
                )
            except Exception:
                # Response is not valid JSON or doesn't have expected format
                logger.warning("LangFlow health response is not valid JSON: %s", response.text[:100])
                return LangFlowCheckResult(
                    check_id="connectivity",
                    label="Connectivity",
                    success=False,
                    message="LangFlow health endpoint returned an unexpected response body",
                )
        except Exception as e:
            logger.warning(f"LangFlow health check failed: {e}")
            return LangFlowCheckResult(
                check_id="connectivity",
                label="Connectivity",
                success=False,
                message=f"LangFlow health check failed: {str(e)}",
            )

    def _extract_flow_items(self, payload: Any) -> Optional[list[dict[str, Any]]]:
        """Normalize LangFlow flow-list payloads across supported response shapes."""
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]

        if isinstance(payload, dict):
            items = payload.get("items")
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]

        return None

    async def list_flows(self) -> LangFlowSummaryResult:
        """Read flows from LangFlow using the configured API key."""
        if not self.api_key:
            return LangFlowSummaryResult(
                check_result=LangFlowCheckResult(
                    check_id="flow_listing",
                    label="Authenticated flow listing",
                    success=False,
                    message="LangFlow API key not configured",
                ),
                flows=[],
            )

        try:
            response = await self.client.get(
                "/flows/",
                params={
                    "remove_example_flows": "false",
                    "components_only": "false",
                    "get_all": "true",
                    "header_flows": "false",
                    "page": 1,
                    "size": 100,
                },
            )
            if response.status_code == 200:
                payload = response.json()
                flows = self._extract_flow_items(payload)
                if not isinstance(flows, list):
                    return LangFlowSummaryResult(
                        check_result=LangFlowCheckResult(
                            check_id="flow_listing",
                            label="Authenticated flow listing",
                            success=False,
                            message="LangFlow flow listing returned an unexpected response body",
                        ),
                        flows=[],
                    )

                return LangFlowSummaryResult(
                    check_result=LangFlowCheckResult(
                        check_id="flow_listing",
                        label="Authenticated flow listing",
                        success=True,
                        message=f"Authenticated LangFlow API returned {len(flows)} flows",
                    ),
                    flows=flows,
                )

            if response.status_code in {401, 403}:
                return LangFlowSummaryResult(
                    check_result=LangFlowCheckResult(
                        check_id="flow_listing",
                        label="Authenticated flow listing",
                        success=False,
                        message="LangFlow rejected the configured API key",
                    ),
                    flows=[],
                )

            return LangFlowSummaryResult(
                check_result=LangFlowCheckResult(
                    check_id="flow_listing",
                    label="Authenticated flow listing",
                    success=False,
                    message=f"LangFlow flow listing returned HTTP {response.status_code}",
                ),
                flows=[],
            )
        except httpx.ConnectError as e:
            logger.warning("LangFlow flow listing failed to connect: %s", e)
            return LangFlowSummaryResult(
                check_result=LangFlowCheckResult(
                    check_id="flow_listing",
                    label="Authenticated flow listing",
                    success=False,
                    message=f"Unable to connect to LangFlow flows API: {str(e)}",
                ),
                flows=[],
            )
        except httpx.TimeoutException as e:
            logger.warning("LangFlow flow listing timed out: %s", e)
            return LangFlowSummaryResult(
                check_result=LangFlowCheckResult(
                    check_id="flow_listing",
                    label="Authenticated flow listing",
                    success=False,
                    message=f"LangFlow flow listing request timed out after {self.timeout} seconds",
                ),
                flows=[],
            )
        except Exception as e:
            logger.warning("LangFlow flow listing failed: %s", e)
            return LangFlowSummaryResult(
                check_result=LangFlowCheckResult(
                    check_id="flow_listing",
                    label="Authenticated flow listing",
                    success=False,
                    message=f"LangFlow flow listing failed: {str(e)}",
                ),
                flows=[],
            )

    def validate_configured_flows(
        self,
        configured_flows: dict[str, str],
        flows: list[dict[str, Any]],
    ) -> LangFlowCheckResult:
        """Validate that every configured flow reference matches a known LangFlow flow."""
        if not configured_flows:
            return LangFlowCheckResult(
                check_id="configured_flows",
                label="Configured flow existence",
                success=True,
                message="No LangFlow flow IDs are configured",
            )

        known_identifiers: set[str] = set()
        for flow in flows:
            for key in ("id", "endpoint_name", "name"):
                value = flow.get(key)
                if isinstance(value, str) and value.strip():
                    known_identifiers.add(value.strip())

        missing = [
            f"{label} ({flow_id})"
            for label, flow_id in configured_flows.items()
            if flow_id not in known_identifiers
        ]

        if missing:
            return LangFlowCheckResult(
                check_id="configured_flows",
                label="Configured flow existence",
                success=False,
                message="Missing configured LangFlow flows: " + ", ".join(missing),
            )

        return LangFlowCheckResult(
            check_id="configured_flows",
            label="Configured flow existence",
            success=True,
            message=f"Validated {len(configured_flows)} configured LangFlow flow references",
        )
    
    @staticmethod
    async def from_settings(settings_service: SettingsService) -> "LangFlowService":
        """
        Create LangFlow service from application settings.
        
        Args:
            settings_service: Settings service instance
            
        Returns:
            Configured LangFlow service
            
        Raises:
            LangFlowConfigurationError: If required settings are missing
        """
        base_url = await settings_service.get_typed_value("langflow.base_url")
        if not base_url:
            raise LangFlowConfigurationError(
                "LangFlow base URL not configured. "
                "Please set 'langflow.base_url' in settings or LANGFLOW__BASE_URL environment variable."
            )
        
        api_key = await settings_service.get_typed_value("langflow.api_key")
        timeout = await settings_service.get_typed_value("langflow.timeout", default=30.0)
        
        return LangFlowService(
            base_url=base_url,
            api_key=api_key,
            timeout=float(timeout),
        )
