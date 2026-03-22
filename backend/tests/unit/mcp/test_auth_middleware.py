"""Unit tests for MCP API Key Authentication Middleware."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, timedelta, timezone

from app.main import MCPApiKeyAuthMiddleware, _extract_api_key_from_headers
from app.services.api_key_service import (
    ApiKeyNotFoundError,
    ApiKeyExpiredError,
    ApiKeyRevokedError,
    UserInactiveError,
)


class TestExtractApiKeyFromHeaders:
    """Test the _extract_api_key_from_headers function."""
    
    def test_extract_from_authorization_bearer(self):
        """Test extracting API key from Authorization: Bearer header."""
        headers = {
            b"authorization": b"Bearer int_test_key_12345"
        }
        
        key = _extract_api_key_from_headers(headers)
        assert key == "int_test_key_12345"
    
    def test_extract_from_authorization_bearer_with_whitespace(self):
        """Test extraction handles whitespace."""
        headers = {
            b"authorization": b"Bearer  int_test_key_12345  "
        }
        
        key = _extract_api_key_from_headers(headers)
        assert key == "int_test_key_12345"
    
    def test_extract_from_x_api_key_header(self):
        """Test extracting API key from X-API-Key header."""
        headers = {
            b"x-api-key": b"int_test_key_12345"
        }
        
        key = _extract_api_key_from_headers(headers)
        assert key == "int_test_key_12345"
    
    def test_authorization_takes_precedence(self):
        """Test Authorization header takes precedence over X-API-Key."""
        headers = {
            b"authorization": b"Bearer int_from_auth",
            b"x-api-key": b"int_from_x_api_key"
        }
        
        key = _extract_api_key_from_headers(headers)
        assert key == "int_from_auth"
    
    def test_returns_none_when_no_headers(self):
        """Test returns None when no API key headers present."""
        headers = {
            b"content-type": b"application/json"
        }
        
        key = _extract_api_key_from_headers(headers)
        assert key is None
    
    def test_returns_none_when_authorization_not_bearer(self):
        """Test returns None when Authorization is not Bearer scheme."""
        headers = {
            b"authorization": b"Basic dXNlcjpwYXNz"
        }
        
        key = _extract_api_key_from_headers(headers)
        assert key is None
    
    def test_handles_malformed_authorization_header(self):
        """Test handles malformed Authorization header gracefully."""
        headers = {
            b"authorization": b"Bearer"  # Missing key
        }
        
        key = _extract_api_key_from_headers(headers)
        assert key is None


class TestMCPApiKeyAuthMiddleware:
    """Test the MCPApiKeyAuthMiddleware class."""
    
    @pytest.fixture
    def mock_app(self):
        """Create a mock ASGI app."""
        app = AsyncMock()
        return app
    
    @pytest.fixture
    def middleware(self, mock_app):
        """Create middleware instance."""
        return MCPApiKeyAuthMiddleware(mock_app)
    
    @pytest.fixture
    def mock_scope(self):
        """Create a mock ASGI scope."""
        return {
            "type": "http",
            "method": "POST",
            "path": "/mcp/v1/tools/list",
            "headers": [],
            "client": ("127.0.0.1", 12345),
        }
    
    @pytest.fixture
    def mock_receive(self):
        """Create a mock receive callable."""
        return AsyncMock()
    
    @pytest.fixture
    def mock_send(self):
        """Create a mock send callable."""
        return AsyncMock()
    
    @pytest.mark.asyncio
    async def test_passes_through_non_http_requests(
        self, middleware, mock_app, mock_receive, mock_send
    ):
        """Test non-HTTP requests pass through without authentication."""
        scope = {"type": "lifespan"}
        
        await middleware(scope, mock_receive, mock_send)
        
        mock_app.assert_called_once_with(scope, mock_receive, mock_send)
    
    @pytest.mark.asyncio
    async def test_rejects_request_without_api_key(
        self, middleware, mock_scope, mock_receive, mock_send
    ):
        """Test request without API key is rejected with 401."""
        await middleware(mock_scope, mock_receive, mock_send)
        
        # Check that send was called with 401 response
        assert mock_send.call_count > 0
        
        # Find the response start call
        response_calls = [call for call in mock_send.call_args_list 
                         if call[0][0]["type"] == "http.response.start"]
        assert len(response_calls) > 0
        
        status = response_calls[0][0][0]["status"]
        assert status == 401
    
    @pytest.mark.asyncio
    async def test_authenticates_with_valid_api_key(
        self, middleware, mock_app, mock_scope, mock_receive, mock_send
    ):
        """Test successful authentication with valid API key."""
        # Add API key to headers
        mock_scope["headers"] = [
            (b"authorization", b"Bearer int_test_key_12345")
        ]
        
        # Mock the api_key_service
        with patch("app.main.async_session_factory") as mock_session_factory, \
             patch("app.main.api_key_service") as mock_api_key_service:
            
            # Setup mock session
            mock_session = AsyncMock()
            mock_session_factory.return_value.__aenter__.return_value = mock_session
            
            # Setup mock validation result
            mock_user = Mock()
            mock_user.id = "user-123"
            mock_user.username = "test_user"
            
            mock_result = Mock()
            mock_result.user = mock_user
            
            mock_api_key_service.validate_api_key = AsyncMock(return_value=mock_result)
            
            await middleware(mock_scope, mock_receive, mock_send)
            
            # Verify API key was validated
            mock_api_key_service.validate_api_key.assert_called_once()
            
            # Verify user was stored in scope
            assert "mcp_user" in mock_scope
            assert mock_scope["mcp_user"] == mock_user
            
            # Verify request was passed to app
            mock_app.assert_called_once_with(mock_scope, mock_receive, mock_send)
    
    @pytest.mark.asyncio
    async def test_rejects_invalid_api_key(
        self, middleware, mock_scope, mock_receive, mock_send
    ):
        """Test request with invalid API key is rejected."""
        mock_scope["headers"] = [
            (b"authorization", b"Bearer int_invalid_key")
        ]
        
        with patch("app.main.async_session_factory") as mock_session_factory, \
             patch("app.main.api_key_service") as mock_api_key_service:
            
            mock_session = AsyncMock()
            mock_session_factory.return_value.__aenter__.return_value = mock_session
            
            # Simulate invalid key
            mock_api_key_service.validate_api_key = AsyncMock(
                side_effect=ApiKeyNotFoundError("Invalid key")
            )
            
            await middleware(mock_scope, mock_receive, mock_send)
            
            # Verify 401 response
            response_calls = [call for call in mock_send.call_args_list 
                             if call[0][0]["type"] == "http.response.start"]
            assert len(response_calls) > 0
            assert response_calls[0][0][0]["status"] == 401
    
    @pytest.mark.asyncio
    async def test_rejects_expired_api_key(
        self, middleware, mock_scope, mock_receive, mock_send
    ):
        """Test request with expired API key is rejected."""
        mock_scope["headers"] = [
            (b"authorization", b"Bearer int_expired_key")
        ]
        
        with patch("app.main.async_session_factory") as mock_session_factory, \
             patch("app.main.api_key_service") as mock_api_key_service:
            
            mock_session = AsyncMock()
            mock_session_factory.return_value.__aenter__.return_value = mock_session
            
            # Simulate expired key
            mock_api_key_service.validate_api_key = AsyncMock(
                side_effect=ApiKeyExpiredError("Key expired")
            )
            
            await middleware(mock_scope, mock_receive, mock_send)
            
            # Verify 401 response
            response_calls = [call for call in mock_send.call_args_list 
                             if call[0][0]["type"] == "http.response.start"]
            assert len(response_calls) > 0
            assert response_calls[0][0][0]["status"] == 401
    
    @pytest.mark.asyncio
    async def test_rejects_revoked_api_key(
        self, middleware, mock_scope, mock_receive, mock_send
    ):
        """Test request with revoked API key is rejected."""
        mock_scope["headers"] = [
            (b"authorization", b"Bearer int_revoked_key")
        ]
        
        with patch("app.main.async_session_factory") as mock_session_factory, \
             patch("app.main.api_key_service") as mock_api_key_service:
            
            mock_session = AsyncMock()
            mock_session_factory.return_value.__aenter__.return_value = mock_session
            
            # Simulate revoked key
            mock_api_key_service.validate_api_key = AsyncMock(
                side_effect=ApiKeyRevokedError("Key revoked")
            )
            
            await middleware(mock_scope, mock_receive, mock_send)
            
            # Verify 401 response
            response_calls = [call for call in mock_send.call_args_list 
                             if call[0][0]["type"] == "http.response.start"]
            assert len(response_calls) > 0
            assert response_calls[0][0][0]["status"] == 401
    
    @pytest.mark.asyncio
    async def test_rejects_when_user_inactive(
        self, middleware, mock_scope, mock_receive, mock_send
    ):
        """Test request rejected when user account is inactive."""
        mock_scope["headers"] = [
            (b"authorization", b"Bearer int_test_key_12345")
        ]
        
        with patch("app.main.async_session_factory") as mock_session_factory, \
             patch("app.main.api_key_service") as mock_api_key_service:
            
            mock_session = AsyncMock()
            mock_session_factory.return_value.__aenter__.return_value = mock_session
            
            # Simulate inactive user
            mock_api_key_service.validate_api_key = AsyncMock(
                side_effect=UserInactiveError("User not active")
            )
            
            await middleware(mock_scope, mock_receive, mock_send)
            
            # Verify 403 response
            response_calls = [call for call in mock_send.call_args_list 
                             if call[0][0]["type"] == "http.response.start"]
            assert len(response_calls) > 0
            assert response_calls[0][0][0]["status"] == 403
    
    @pytest.mark.asyncio
    async def test_handles_x_api_key_header(
        self, middleware, mock_app, mock_scope, mock_receive, mock_send
    ):
        """Test authentication works with X-API-Key header."""
        mock_scope["headers"] = [
            (b"x-api-key", b"int_test_key_12345")
        ]
        
        with patch("app.main.async_session_factory") as mock_session_factory, \
             patch("app.main.api_key_service") as mock_api_key_service:
            
            mock_session = AsyncMock()
            mock_session_factory.return_value.__aenter__.return_value = mock_session
            
            mock_user = Mock()
            mock_result = Mock()
            mock_result.user = mock_user
            
            mock_api_key_service.validate_api_key = AsyncMock(return_value=mock_result)
            
            await middleware(mock_scope, mock_receive, mock_send)
            
            # Verify request was passed to app
            mock_app.assert_called_once_with(mock_scope, mock_receive, mock_send)
            assert "mcp_user" in mock_scope
    
    @pytest.mark.asyncio
    async def test_includes_audit_context(
        self, middleware, mock_app, mock_scope, mock_receive, mock_send
    ):
        """Test that audit context is passed to validation."""
        mock_scope["headers"] = [
            (b"authorization", b"Bearer int_test_key_12345"),
            (b"user-agent", b"MCPClient/1.0"),
            (b"x-request-id", b"req-123"),
        ]
        
        with patch("app.main.async_session_factory") as mock_session_factory, \
             patch("app.main.api_key_service") as mock_api_key_service:
            
            mock_session = AsyncMock()
            mock_session_factory.return_value.__aenter__.return_value = mock_session
            
            mock_user = Mock()
            mock_result = Mock()
            mock_result.user = mock_user
            
            mock_api_key_service.validate_api_key = AsyncMock(return_value=mock_result)
            
            await middleware(mock_scope, mock_receive, mock_send)
            
            # Verify validation was called with audit context
            call_args = mock_api_key_service.validate_api_key.call_args
            assert call_args is not None
            
            context = call_args[1]["context"]
            assert context.ip_address == "127.0.0.1"
            assert context.user_agent == "MCPClient/1.0"
            assert context.correlation_id == "req-123"
