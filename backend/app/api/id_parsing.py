"""HTTP adapter for dependency-free entity-ID parsing."""

from fastapi import HTTPException

from app.core.id_parser import EntityIdParseError, parse_entity_id


def parse_entity_id_or_400(raw: str, expected_kind: str) -> tuple[int, str]:
    """Parse an entity ID and translate domain validation into HTTP 400."""
    try:
        return parse_entity_id(raw, expected_kind)
    except EntityIdParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
