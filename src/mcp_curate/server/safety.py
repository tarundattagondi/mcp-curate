"""SSRF guard for outbound tool-call requests.

A tool call sends the user's bring-your-own auth headers to whatever server URL
the OpenAPI spec declares. A malicious or mistaken spec could point that URL at
the cloud metadata endpoint (169.254.169.254), localhost, or an internal host —
leaking credentials or reaching internal services. By default we refuse to send
requests to link-local, loopback, private, or otherwise non-public addresses.

Pass ``allow_local=True`` (CLI: ``--allow-local-network``) only when you are
intentionally serving a spec whose API runs on localhost or a private network.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeURLError(ValueError):
    """Raised when a request target resolves to a disallowed address."""


def assert_safe_url(url: str, allow_local: bool = False) -> None:
    """Validate a request URL, blocking SSRF-prone targets by default."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError(f"unsupported URL scheme: {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise UnsafeURLError("request URL has no host")

    for ip in _resolve(host):
        # Link-local (incl. 169.254.169.254 cloud metadata) is never allowed.
        if ip.is_link_local:
            raise UnsafeURLError(
                f"refusing to call link-local/metadata address {ip} "
                f"(host {host!r}); this is a common SSRF target"
            )
        if not allow_local and not _is_public(ip):
            raise UnsafeURLError(
                f"refusing to call non-public address {ip} (host {host!r}); "
                "pass --allow-local-network to permit localhost/private hosts"
            )


def _resolve(host: str) -> list[ipaddress._BaseAddress]:
    """Resolve a host to IPs. If the host is a literal IP, use it directly."""
    try:
        return [ipaddress.ip_address(host)]
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        # Unresolvable: let httpx surface the connection error instead.
        return []
    return [ipaddress.ip_address(info[4][0]) for info in infos]


def _is_public(ip: ipaddress._BaseAddress) -> bool:
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )
