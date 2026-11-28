"""Resolve originating client addresses across explicitly trusted proxies."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Any, Iterable

from app.core.settings_registry import get_local


IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network
MAX_FORWARDED_FOR_BYTES = 4096
MAX_FORWARDED_FOR_HOPS = 32


@dataclass(frozen=True, slots=True)
class ClientAddressResolver:
    """Resolve X-Forwarded-For only when the direct peer is trusted."""

    trusted_proxy_networks: tuple[IPNetwork, ...] = ()

    @classmethod
    def from_cidrs(cls, values: Iterable[str]) -> "ClientAddressResolver":
        networks: list[IPNetwork] = []
        for value in values:
            if not isinstance(value, str):
                raise TypeError("trusted proxy networks must be strings")
            raw_value = value.strip()
            if not raw_value:
                raise ValueError("trusted proxy networks cannot be empty")
            network = ipaddress.ip_network(raw_value, strict=False)
            if network.prefixlen == 0:
                raise ValueError("universal trusted proxy networks are not permitted")
            networks.append(network)
        return cls(tuple(networks))

    def _is_trusted(self, address: IPAddress) -> bool:
        return any(address in network for network in self.trusted_proxy_networks)

    def resolve(
        self,
        *,
        peer_address: str | None,
        forwarded_for: str | None,
    ) -> str | None:
        """Return the originating address, or the direct peer when untrusted."""

        if peer_address is None:
            return None
        try:
            peer = ipaddress.ip_address(peer_address)
        except ValueError:
            return peer_address

        if not forwarded_for or not self._is_trusted(peer):
            return str(peer)

        if len(forwarded_for) > MAX_FORWARDED_FOR_BYTES:
            return str(peer)
        raw_hops = forwarded_for.split(",")
        if not raw_hops or len(raw_hops) > MAX_FORWARDED_FOR_HOPS:
            return str(peer)

        try:
            forwarded = [ipaddress.ip_address(item.strip()) for item in raw_hops]
        except ValueError:
            return str(peer)
        if not forwarded:
            return str(peer)
        for address in reversed(forwarded):
            if not self._is_trusted(address):
                return str(address)
        return str(forwarded[0])

    def resolve_scope(self, scope: dict[str, Any]) -> str | None:
        """Resolve a client address from an ASGI HTTP/WebSocket scope."""

        forwarded_values = [
            value.decode("latin1")
            for name, value in scope.get("headers", ())
            if name.lower() == b"x-forwarded-for"
        ]
        return self.resolve(
            peer_address=scope_peer_address(scope),
            forwarded_for=", ".join(forwarded_values) or None,
        )


def scope_peer_address(scope: dict[str, Any]) -> str | None:
    """Return the ASGI direct-peer address without consulting headers."""

    client = scope.get("client")
    return str(client[0]) if client else None


def load_client_address_resolver() -> ClientAddressResolver:
    """Load and validate the startup-frozen trusted-proxy allowlist."""

    raw_cidrs = get_local("http.trusted_proxy_cidrs")
    if not isinstance(raw_cidrs, list):
        raise RuntimeError("HTTP_TRUSTED_PROXY_CIDRS must be a JSON array")
    try:
        return ClientAddressResolver.from_cidrs(raw_cidrs)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            "HTTP_TRUSTED_PROXY_CIDRS must contain valid explicit IP networks"
        ) from exc


client_address_resolver = load_client_address_resolver()


def request_client_address(request: Any) -> str | None:
    """Resolve a Starlette/FastAPI request using its application's policy."""

    scope = getattr(request, "scope", {}) or {}
    app = scope.get("app")
    if app is None:
        try:
            app = getattr(request, "app", None)
        except KeyError:
            # Starlette's ``Request.app`` property indexes ``scope["app"]``.
            # Direct unit/service callers may intentionally provide no app.
            app = None
    state = getattr(app, "state", None)
    resolver = getattr(state, "client_address_resolver", client_address_resolver)
    return resolver.resolve_scope(scope)


__all__ = [
    "ClientAddressResolver",
    "client_address_resolver",
    "load_client_address_resolver",
    "request_client_address",
    "scope_peer_address",
]
