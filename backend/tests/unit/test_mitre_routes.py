import pytest
from fastapi import HTTPException

from app.api.routes import mitre as mitre_routes
from app.api.routes.mitre import lookup_attack_object
from app.services.mitre_service import MitreDataUnavailableError


def test_lookup_returns_not_found_for_valid_missing_attack_id() -> None:
    with pytest.raises(HTTPException) as exc_info:
        lookup_attack_object("T9999")

    assert exc_info.value.status_code == 404


def test_lookup_rejects_malformed_attack_id() -> None:
    with pytest.raises(HTTPException) as exc_info:
        lookup_attack_object("not-an-attack-id")

    assert exc_info.value.status_code == 400


def test_lookup_reports_unavailable_bundle_separately_from_missing_object(
    monkeypatch,
) -> None:
    def unavailable(_attack_id: str):
        raise MitreDataUnavailableError("internal path and parser details")

    monkeypatch.setattr(mitre_routes._service, "get_attack_object", unavailable)

    with pytest.raises(HTTPException) as exc_info:
        lookup_attack_object("T1059")

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "MITRE ATT&CK data is unavailable"
