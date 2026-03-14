import shutil
from pathlib import Path

import pytest

from app.services.maxmind_service import maxmind_service


class StubSettings:
    def __init__(self, values: dict[str, object]):
        self._values = values

    async def get(self, key: str, default: object = None) -> object:
        return self._values.get(key, default)


def _prepare_local_mmdbs(source_dir: Path, target_dir: Path, file_names: list[str]) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    for file_name in file_names:
        edition_id = file_name.replace("-Test.mmdb", "")
        shutil.copy2(source_dir / file_name, target_dir / f"{edition_id}.mmdb")


@pytest.mark.asyncio
async def test_parse_geoip_conf_extracts_credentials_and_editions() -> None:
    parsed = maxmind_service.parse_geoip_conf(
        """
        # Example GeoIP.conf
        AccountID 1234567
        LicenseKey REDACTED_TEST_LICENSE_KEY_placeholder00
        EditionIDs GeoLite2-ASN GeoLite2-City GeoLite2-Country
        """
    )

    assert parsed["account_id"] == "1234567"
    assert parsed["license_key"] == "REDACTED_TEST_LICENSE_KEY_placeholder00"
    assert parsed["edition_ids"] == ["GeoLite2-ASN", "GeoLite2-City", "GeoLite2-Country"]


@pytest.mark.asyncio
async def test_lookup_ip_reads_real_mmdb_data(maxmind_test_data_dir: Path, tmp_path: Path) -> None:
    await maxmind_service.close_readers()
    local_cache_dir = tmp_path / "maxmind"
    _prepare_local_mmdbs(
        maxmind_test_data_dir,
        local_cache_dir,
        ["GeoLite2-ASN-Test.mmdb", "GeoLite2-City-Test.mmdb", "GeoLite2-Country-Test.mmdb"],
    )
    settings = StubSettings(
        {
            "enrichment.maxmind.edition_ids": ["GeoLite2-ASN", "GeoLite2-City", "GeoLite2-Country"],
            "enrichment.maxmind.local_cache_dir": str(local_cache_dir),
            "enrichment.maxmind.storage_prefix": "maxmind/",
        }
    )

    await maxmind_service.ensure_readers_loaded(settings=settings)  # type: ignore[arg-type]

    city_result = await maxmind_service.lookup_ip("81.2.69.160")
    assert city_result["databases"]["GeoLite2-City"]["country"]["iso_code"] == "GB"
    assert city_result["databases"]["GeoLite2-City"]["country"]["name"] == "United Kingdom"
    assert city_result["databases"]["GeoLite2-Country"]["country"]["iso_code"] == "GB"

    asn_result = await maxmind_service.lookup_ip("1.128.0.0")
    assert asn_result["databases"]["GeoLite2-ASN"]["autonomous_system_number"] == 1221
    assert asn_result["databases"]["GeoLite2-ASN"]["autonomous_system_organization"] == "Telstra Pty Ltd"

    await maxmind_service.close_readers()


@pytest.mark.asyncio
async def test_get_database_status_handles_unavailable_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    await maxmind_service.close_readers()

    settings = StubSettings(
        {
            "enrichment.maxmind.edition_ids": ["GeoLite2-ASN", "GeoLite2-City"],
            "enrichment.maxmind.local_cache_dir": str(tmp_path / "maxmind"),
            "enrichment.maxmind.storage_prefix": "maxmind/",
            "enrichment.maxmind.account_id": "1234567",
            "enrichment.maxmind.license_key": "test-license",
            "enrichment.maxmind.ttl_seconds": 604800,
            "enrichment.maxmind.update_frequency_hours": 24,
        }
    )

    async def fake_get_settings(
        _db: object,
        *,
        strict_editions: bool = True,
    ) -> tuple[StubSettings, dict[str, object]]:
        return settings, {
            "account_id": "1234567",
            "license_key": "test-license",
            "edition_ids": ["GeoLite2-ASN", "GeoLite2-City"],
            "storage_prefix": "maxmind/",
            "local_cache_dir": str(tmp_path / "maxmind"),
            "ttl_seconds": 604800,
            "update_frequency_hours": 24,
        }

    async def fake_ensure_bucket() -> None:
        raise ConnectionError("storage unavailable")

    monkeypatch.setattr(maxmind_service, "_get_settings", fake_get_settings)
    monkeypatch.setattr(maxmind_service, "_ensure_bucket", fake_ensure_bucket)

    statuses = await maxmind_service.get_database_status(db=None)  # type: ignore[arg-type]

    assert [status["edition_id"] for status in statuses] == ["GeoLite2-ASN", "GeoLite2-City"]
    assert all(status["available_in_storage"] is False for status in statuses)
    assert all(status["loaded"] is False for status in statuses)
    assert all(status["local_path"] is None for status in statuses)

    await maxmind_service.close_readers()