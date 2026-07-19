from __future__ import annotations

from typing import Any

import pytest

from app.services.enrichment.providers.cross_case_observable import (
    cross_case_observable_provider,
)
from app.services.enrichment.providers.maxmind import maxmind_provider


@pytest.mark.parametrize(
    "provider",
    [
        pytest.param(cross_case_observable_provider, id="cross-case-observable"),
        pytest.param(maxmind_provider, id="maxmind"),
    ],
)
@pytest.mark.parametrize(
    ("address", "eligible"),
    [
        pytest.param("8.8.8.8", True, id="public-ipv4"),
        pytest.param("2606:4700:4700::1111", True, id="public-ipv6"),
        pytest.param("100.64.0.1", True, id="shared-carrier-grade-nat"),
        pytest.param("10.0.0.1", False, id="private-ipv4"),
        pytest.param("fc00::1", False, id="private-ipv6"),
        pytest.param("127.0.0.1", False, id="loopback-ipv4"),
        pytest.param("::1", False, id="loopback-ipv6"),
        pytest.param("169.254.1.1", False, id="link-local-ipv4"),
        pytest.param("fe80::1", False, id="link-local-ipv6"),
        pytest.param("224.0.0.1", False, id="multicast-ipv4"),
        pytest.param("ff02::1", False, id="multicast-ipv6"),
        pytest.param("0.0.0.0", False, id="unspecified-ipv4"),
        pytest.param("::", False, id="unspecified-ipv6"),
        pytest.param("240.0.0.1", False, id="reserved-ipv4"),
        pytest.param("192.0.2.1", False, id="documentation-ipv4"),
        pytest.param("not-an-ip", False, id="invalid"),
    ],
)
def test_enrichment_providers_share_public_ip_eligibility(
    provider: Any,
    address: str,
    eligible: bool,
) -> None:
    item = {"type": "system", "ip_address": address}

    assert provider.can_enrich(item) is eligible
