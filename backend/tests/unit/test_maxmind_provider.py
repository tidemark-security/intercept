import shutil
from pathlib import Path

import pytest

from app.services.enrichment.providers.maxmind import maxmind_provider
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


def test_can_enrich_supported_ip_items() -> None:
    assert maxmind_provider.can_enrich(
        {"type": "observable", "observable_type": "IP", "observable_value": "81.2.69.160"}
    )
    assert maxmind_provider.can_enrich({"type": "system", "ip_address": "81.2.69.160"})
    assert maxmind_provider.can_enrich(
        {"type": "network_traffic", "source_ip": "1.128.0.0", "destination_ip": "81.2.69.160"}
    )
    assert not maxmind_provider.can_enrich(
        {"type": "observable", "observable_type": "DOMAIN", "observable_value": "example.com"}
    )
    assert not maxmind_provider.can_enrich({"type": "system", "ip_address": "10.0.0.5"})


def test_build_cache_key_is_deterministic() -> None:
    assert (
        maxmind_provider.build_cache_key(
            {
                "type": "network_traffic",
                "source_ip": "81.2.69.160",
                "destination_ip": "1.128.0.0",
            }
        )
        == "1.128.0.0|81.2.69.160"
    )


@pytest.mark.asyncio
async def test_enrich_returns_results_and_aliases(maxmind_test_data_dir: Path, tmp_path: Path) -> None:
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
            "enrichment.maxmind.ttl_seconds": 3600,
        }
    )

    result = await maxmind_provider.enrich(
        db=None,  # type: ignore[arg-type]
        settings=settings,  # type: ignore[arg-type]
        item={
            "type": "network_traffic",
            "source_ip": "1.128.0.0",
            "destination_ip": "81.2.69.160",
        },
        entity_type="alert",
        entity_id=1,
    )

    assert result.provider_id == "maxmind"
    assert result.cache_key == "1.128.0.0|81.2.69.160"
    assert result.ttl_seconds == 3600
    assert result.enrichment_data["results"]["1.128.0.0"]["databases"]["GeoLite2-ASN"]["autonomous_system_organization"] == "Telstra Pty Ltd"
    assert result.enrichment_data["results"]["81.2.69.160"]["databases"]["GeoLite2-City"]["country"]["iso_code"] == "GB"
    alias_types = {alias.alias_type for alias in result.aliases}
    assert "asn_organization" in alias_types
    assert "country_iso_code" in alias_types

    await maxmind_service.close_readers()