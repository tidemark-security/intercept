"""Unit tests for Mermaid MCP validation."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.mcp.schemas import ValidateMermaidInput, ValidateMermaidOutput
from app.services import mcp_service


class _FakeProcess:
    def __init__(self, returncode: int, stdout: bytes = b"", stderr: bytes = b"") -> None:
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr
        self.killed = False

    async def communicate(self, _input: bytes | None = None) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr

    def kill(self) -> None:
        self.killed = True


def test_validate_mermaid_schema_accepts_expected_fields() -> None:
    payload = ValidateMermaidInput(diagram="graph TD\nA-->B")

    assert payload.diagram == "graph TD\nA-->B"


def test_validate_mermaid_output_defaults_errors_list() -> None:
    result = ValidateMermaidOutput(valid=True, message="ok")

    assert result.errors == []


@pytest.mark.asyncio
async def test_validate_mermaid_returns_success_for_valid_diagram(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_create_subprocess_exec(*args, **kwargs):  # type: ignore[no-untyped-def]
        assert args[0] == "/usr/bin/node"
        assert args[1].endswith("validate_mermaid_syntax.mjs")
        return _FakeProcess(returncode=0)

    monkeypatch.setattr(mcp_service.shutil, "which", lambda name: "/usr/bin/node" if name == "node" else None)
    monkeypatch.setattr(
        mcp_service,
        "_MERMAID_VALIDATOR_SCRIPT_CANDIDATES",
        (Path("/tmp/validate_mermaid_syntax.mjs"),),
    )
    monkeypatch.setattr(Path, "exists", lambda self: str(self) == "/tmp/validate_mermaid_syntax.mjs")
    monkeypatch.setattr(mcp_service.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    result = await mcp_service.validate_mermaid("graph TD\nA-->B")

    assert result.valid is True
    assert result.errors == []


@pytest.mark.asyncio
async def test_validate_mermaid_returns_invalid_for_parse_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_create_subprocess_exec(*args, **kwargs):  # type: ignore[no-untyped-def]
        return _FakeProcess(
            returncode=1,
            stderr=b"Parse error on line 2:\n...A-->\nExpecting 'TEXT', got 'EOF'",
        )

    monkeypatch.setattr(mcp_service.shutil, "which", lambda name: "/usr/bin/node" if name == "node" else None)
    monkeypatch.setattr(
        mcp_service,
        "_MERMAID_VALIDATOR_SCRIPT_CANDIDATES",
        (Path("/tmp/validate_mermaid_syntax.mjs"),),
    )
    monkeypatch.setattr(Path, "exists", lambda self: str(self) == "/tmp/validate_mermaid_syntax.mjs")
    monkeypatch.setattr(mcp_service.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    result = await mcp_service.validate_mermaid("graph TD\nA-->")

    assert result.valid is False
    assert result.message == "Mermaid diagram syntax is invalid."
    assert any("Parse error" in line for line in result.errors)


@pytest.mark.asyncio
async def test_validate_mermaid_raises_when_node_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_service.shutil, "which", lambda _name: None)

    with pytest.raises(HTTPException) as exc_info:
        await mcp_service.validate_mermaid("graph TD\nA-->B")

    assert exc_info.value.status_code == 503
    assert "node" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_validate_mermaid_raises_for_operational_cli_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_create_subprocess_exec(*args, **kwargs):  # type: ignore[no-untyped-def]
        return _FakeProcess(
            returncode=1,
            stderr=b"Error [ERR_MODULE_NOT_FOUND]: Cannot find package 'mermaid'",
        )

    monkeypatch.setattr(mcp_service.shutil, "which", lambda name: "/usr/bin/node" if name == "node" else None)
    monkeypatch.setattr(
        mcp_service,
        "_MERMAID_VALIDATOR_SCRIPT_CANDIDATES",
        (Path("/tmp/validate_mermaid_syntax.mjs"),),
    )
    monkeypatch.setattr(Path, "exists", lambda self: str(self) == "/tmp/validate_mermaid_syntax.mjs")
    monkeypatch.setattr(mcp_service.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    with pytest.raises(HTTPException) as exc_info:
        await mcp_service.validate_mermaid("graph TD\nA-->B")

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_validate_mermaid_raises_for_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    class _TimeoutProcess(_FakeProcess):
        async def communicate(self, _input: bytes | None = None) -> tuple[bytes, bytes]:
            await asyncio.sleep(0)
            return b"", b""

    async def fake_create_subprocess_exec(*args, **kwargs):  # type: ignore[no-untyped-def]
        return _TimeoutProcess(returncode=0)

    async def fake_wait_for(_awaitable, timeout):  # type: ignore[no-untyped-def]
        close = getattr(_awaitable, "close", None)
        if callable(close):
            close()
        raise asyncio.TimeoutError

    monkeypatch.setattr(mcp_service.shutil, "which", lambda name: "/usr/bin/node" if name == "node" else None)
    monkeypatch.setattr(
        mcp_service,
        "_MERMAID_VALIDATOR_SCRIPT_CANDIDATES",
        (Path("/tmp/validate_mermaid_syntax.mjs"),),
    )
    monkeypatch.setattr(Path, "exists", lambda self: str(self) == "/tmp/validate_mermaid_syntax.mjs")
    monkeypatch.setattr(mcp_service.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(mcp_service.asyncio, "wait_for", fake_wait_for)

    with pytest.raises(HTTPException) as exc_info:
        await mcp_service.validate_mermaid("graph TD\nA-->B")

    assert exc_info.value.status_code == 504
