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


@dataclass(frozen=True)
class LangFlowProvisioningResult:
    """Represents the result of creating, updating, or reusing a LangFlow resource."""

    action: str
    payload: dict[str, Any]


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

    def _get_api_root(self) -> str:
        """Return the scheme/host prefix for versioned LangFlow API routes."""
        parsed = httpx.URL(self.base_url)
        normalized_path = parsed.path.rstrip("/")
        for suffix in ("/api/v1", "/api/v2"):
            if normalized_path.endswith(suffix):
                normalized_path = normalized_path[: -len(suffix)]
                break

        root_path = normalized_path or "/"
        return str(parsed.copy_with(path=root_path, query=None, fragment=None)).rstrip("/")

    def _build_versioned_url(self, api_version: str, path: str) -> str:
        """Build an absolute LangFlow API URL for endpoints outside the configured base path."""
        normalized_path = path if path.startswith("/") else f"/{path}"
        return f"{self._get_api_root()}/api/{api_version}{normalized_path}"

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

    def sanitize_flow_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Reduce exported flow JSON to the fields accepted by LangFlow create endpoints."""
        allowed_keys = (
            "name",
            "description",
            "icon",
            "icon_bg_color",
            "gradient",
            "data",
            "is_component",
            "webhook",
            "endpoint_name",
            "tags",
            "locked",
            "mcp_enabled",
            "folder_id",
        )
        sanitized = {
            key: payload.get(key)
            for key in allowed_keys
            if key in payload
        }

        if "locked" not in sanitized:
            sanitized["locked"] = None

        return sanitized

    def flow_matches_expected(self, existing_flow: dict[str, Any], expected_flow: dict[str, Any]) -> bool:
        """Compare a live LangFlow flow against the bundled import payload we would create."""
        comparable_keys = (
            "name",
            "description",
            "icon",
            "icon_bg_color",
            "gradient",
            "data",
            "is_component",
            "webhook",
            "endpoint_name",
            "tags",
            "locked",
            "mcp_enabled",
        )
        for key in comparable_keys:
            if expected_flow.get(key) != existing_flow.get(key):
                return False
        return True

    async def list_variables(self) -> list[dict[str, Any]]:
        """List LangFlow global variables using the hidden variables API."""
        try:
            response = await self.client.get(self._build_versioned_url("v1", "/variables/"))
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise LangFlowError(
                f"LangFlow variables API returned error {e.response.status_code}"
            ) from e
        except httpx.HTTPError as e:
            raise LangFlowError(f"Unable to query LangFlow variables API: {str(e)}") from e

        payload = response.json()
        if not isinstance(payload, list):
            raise LangFlowError("LangFlow variables API returned an unexpected response body")

        return [item for item in payload if isinstance(item, dict)]

    async def upsert_credential_variable(
        self,
        *,
        name: str,
        value: str,
    ) -> LangFlowProvisioningResult:
        """Create or update a credential variable used by LangFlow MCP headers."""
        variables = await self.list_variables()
        existing = next(
            (
                item for item in variables
                if isinstance(item.get("name"), str) and item["name"] == name
            ),
            None,
        )
        payload = {
            "name": name,
            "value": value,
            "type": "Credential",
            "default_fields": [],
        }

        try:
            if existing is None:
                response = await self.client.post(
                    self._build_versioned_url("v1", "/variables/"),
                    json=payload,
                )
                response.raise_for_status()
                return LangFlowProvisioningResult(action="created", payload=response.json())

            variable_id = existing.get("id")
            payload["id"] = variable_id
            response = await self.client.patch(
                self._build_versioned_url("v1", f"/variables/{variable_id}"),
                json=payload,
            )
            response.raise_for_status()
            return LangFlowProvisioningResult(action="updated", payload=response.json())
        except httpx.HTTPStatusError as e:
            raise LangFlowError(
                f"LangFlow variable upsert returned error {e.response.status_code}"
            ) from e
        except httpx.HTTPError as e:
            raise LangFlowError(f"Unable to upsert LangFlow variable '{name}': {str(e)}") from e

    async def get_mcp_server(self, server_name: str) -> Optional[dict[str, Any]]:
        """Return an MCP server config by name, if it exists."""
        try:
            response = await self.client.get(
                self._build_versioned_url("v2", f"/mcp/servers/{server_name}")
            )
        except httpx.HTTPError as e:
            raise LangFlowError(
                f"Unable to query LangFlow MCP server '{server_name}': {str(e)}"
            ) from e

        if response.status_code == 404:
            return None

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise LangFlowError(
                f"LangFlow MCP server lookup returned error {e.response.status_code}"
            ) from e

        payload = response.json()
        if payload is None:
            return None

        if not isinstance(payload, dict):
            raise LangFlowError("LangFlow MCP server lookup returned an unexpected response body")

        return payload

    def _mcp_server_matches_expected(
        self,
        existing_server: dict[str, Any],
        expected_payload: dict[str, Any],
    ) -> bool:
        existing_headers = existing_server.get("headers")
        if not isinstance(existing_headers, dict):
            existing_headers = {}

        return (
            existing_server.get("url") == expected_payload.get("url")
            and existing_headers == expected_payload.get("headers")
        )

    async def upsert_mcp_server(
        self,
        *,
        server_name: str,
        url: str,
        api_key_variable_name: str,
    ) -> LangFlowProvisioningResult:
        """Create or update the Intercept MCP server definition in LangFlow."""
        desired_payload = {
            "url": url,
            "headers": {
                "x-api-key": api_key_variable_name,
            },
        }
        existing = await self.get_mcp_server(server_name)
        if existing is not None and self._mcp_server_matches_expected(existing, desired_payload):
            return LangFlowProvisioningResult(action="reused", payload=existing)

        try:
            if existing is None:
                response = await self.client.post(
                    self._build_versioned_url("v2", f"/mcp/servers/{server_name}"),
                    json=desired_payload,
                )
                response.raise_for_status()
                return LangFlowProvisioningResult(action="created", payload=response.json())

            response = await self.client.patch(
                self._build_versioned_url("v2", f"/mcp/servers/{server_name}"),
                json=desired_payload,
            )
            response.raise_for_status()
            return LangFlowProvisioningResult(action="updated", payload=response.json())
        except httpx.HTTPStatusError as e:
            raise LangFlowError(
                f"LangFlow MCP server upsert returned error {e.response.status_code}"
            ) from e
        except httpx.HTTPError as e:
            raise LangFlowError(
                f"Unable to upsert LangFlow MCP server '{server_name}': {str(e)}"
            ) from e

    async def create_flow(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a new flow from a sanitized flow payload."""
        try:
            response = await self.client.post(
                self._build_versioned_url("v1", "/flows/"),
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise LangFlowError(
                f"LangFlow flow creation returned error {e.response.status_code}"
            ) from e
        except httpx.HTTPError as e:
            raise LangFlowError(f"Unable to create LangFlow flow: {str(e)}") from e

        created_flow = response.json()
        if not isinstance(created_flow, dict):
            raise LangFlowError("LangFlow flow creation returned an unexpected response body")

        return created_flow

    async def update_flow(self, flow_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Patch an existing flow with a partial update payload."""
        try:
            response = await self.client.patch(
                self._build_versioned_url("v1", f"/flows/{flow_id}"),
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise LangFlowError(
                f"LangFlow flow update returned error {e.response.status_code}"
            ) from e
        except httpx.HTTPError as e:
            raise LangFlowError(f"Unable to update LangFlow flow '{flow_id}': {str(e)}") from e

        updated_flow = response.json()
        if not isinstance(updated_flow, dict):
            raise LangFlowError("LangFlow flow update returned an unexpected response body")

        return updated_flow

    async def list_projects(self) -> list[dict[str, Any]]:
        """List LangFlow projects."""
        try:
            response = await self.client.get(self._build_versioned_url("v1", "/projects/"))
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise LangFlowError(
                f"LangFlow projects API returned error {e.response.status_code}"
            ) from e
        except httpx.HTTPError as e:
            raise LangFlowError(f"Unable to query LangFlow projects API: {str(e)}") from e

        payload = response.json()
        if not isinstance(payload, list):
            raise LangFlowError("LangFlow projects API returned an unexpected response body")

        return [item for item in payload if isinstance(item, dict)]

    async def create_project(
        self,
        *,
        name: str,
        description: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create a LangFlow project."""
        project_payload: dict[str, Any] = {"name": name}
        if description is not None:
            project_payload["description"] = description

        try:
            response = await self.client.post(
                self._build_versioned_url("v1", "/projects/"),
                json=project_payload,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise LangFlowError(
                f"LangFlow project creation returned error {e.response.status_code}"
            ) from e
        except httpx.HTTPError as e:
            raise LangFlowError(f"Unable to create LangFlow project '{name}': {str(e)}") from e

        created_project = response.json()
        if not isinstance(created_project, dict):
            raise LangFlowError("LangFlow project creation returned an unexpected response body")

        return created_project

    async def ensure_project(
        self,
        *,
        name: str,
        description: Optional[str] = None,
    ) -> LangFlowProvisioningResult:
        """Return an existing LangFlow project by name or create it."""
        normalized_name = name.strip().casefold()
        if not normalized_name:
            raise LangFlowError("LangFlow project name must not be blank")

        projects = await self.list_projects()
        existing = next(
            (
                item
                for item in projects
                if isinstance(item.get("name"), str)
                and item["name"].strip().casefold() == normalized_name
            ),
            None,
        )
        if existing is not None:
            return LangFlowProvisioningResult(action="reused", payload=existing)

        created = await self.create_project(name=name.strip(), description=description)
        return LangFlowProvisioningResult(action="created", payload=created)

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
