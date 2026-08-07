"""Trusted-proxy client-address resolution behavior."""

from types import SimpleNamespace

import pytest

from app.core.client_address import ClientAddressResolver, request_client_address


def test_trusted_proxy_chain_resolves_first_untrusted_hop_from_the_right() -> None:
    resolver = ClientAddressResolver.from_cidrs(["172.31.250.0/24"])

    resolved = resolver.resolve(
        peer_address="172.31.250.10",
        forwarded_for="198.51.100.99, 203.0.113.42, 172.31.250.11",
    )

    assert resolved == "203.0.113.42"


def test_malformed_forwarded_chain_fails_closed_to_direct_peer() -> None:
    resolver = ClientAddressResolver.from_cidrs(["172.31.250.0/24"])

    resolved = resolver.resolve(
        peer_address="172.31.250.10",
        forwarded_for="203.0.113.42, definitely-not-an-ip",
    )

    assert resolved == "172.31.250.10"


def test_oversized_forwarded_chain_fails_closed_to_direct_peer() -> None:
    resolver = ClientAddressResolver.from_cidrs(["172.31.250.0/24"])

    resolved = resolver.resolve(
        peer_address="172.31.250.10",
        forwarded_for=", ".join(["203.0.113.42"] * 33),
    )

    assert resolved == "172.31.250.10"


def test_oversized_forwarded_header_fails_closed_to_direct_peer() -> None:
    resolver = ClientAddressResolver.from_cidrs(["172.31.250.0/24"])

    resolved = resolver.resolve(
        peer_address="172.31.250.10",
        forwarded_for="1" * 4097,
    )

    assert resolved == "172.31.250.10"


def test_untrusted_peer_cannot_supply_forwarded_client_address() -> None:
    resolver = ClientAddressResolver.from_cidrs(["172.31.250.0/24"])

    resolved = resolver.resolve(
        peer_address="198.51.100.20",
        forwarded_for="203.0.113.42",
    )

    assert resolved == "198.51.100.20"


def test_spoofed_leftmost_forwarded_entry_does_not_fan_out_source() -> None:
    resolver = ClientAddressResolver.from_cidrs(["172.31.250.0/24"])

    first = resolver.resolve(
        peer_address="172.31.250.10",
        forwarded_for="192.0.2.1, 203.0.113.42",
    )
    second = resolver.resolve(
        peer_address="172.31.250.10",
        forwarded_for="192.0.2.2, 203.0.113.42",
    )

    assert first == second == "203.0.113.42"


def test_asgi_scope_resolution_combines_forwarded_headers_in_wire_order() -> None:
    resolver = ClientAddressResolver.from_cidrs(["172.31.250.0/24"])
    scope = {
        "client": ("172.31.250.10", 43123),
        "headers": [
            (b"x-forwarded-for", b"192.0.2.1, 203.0.113.42"),
            (b"x-forwarded-for", b"172.31.250.11"),
        ],
    }

    assert resolver.resolve_scope(scope) == "203.0.113.42"


def test_request_resolution_uses_the_application_proxy_policy() -> None:
    resolver = ClientAddressResolver.from_cidrs(["172.31.250.0/24"])
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(client_address_resolver=resolver),
        ),
        scope={
            "client": ("172.31.250.10", 43123),
            "headers": [(b"x-forwarded-for", b"203.0.113.42")],
        },
    )

    assert request_client_address(request) == "203.0.113.42"


@pytest.mark.parametrize("cidr", ["0.0.0.0/0", "::/0", "", 123])
def test_trusted_proxy_configuration_rejects_non_explicit_networks(
    cidr: object,
) -> None:
    with pytest.raises((TypeError, ValueError)):
        ClientAddressResolver.from_cidrs([cidr])  # type: ignore[list-item]
