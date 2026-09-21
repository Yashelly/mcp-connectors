"""Exact source allowlists and public-address checks for browser requests."""
import asyncio
import ipaddress
import re
import socket
from urllib.parse import urlsplit, urlunsplit

from .errors import ConnectorError


def validate_url(url: str, hosts: frozenset[str] | None = None) -> str:
    try:
        if not isinstance(url, str) or len(url) > 4096 or re.search(r"[\s\\\x00-\x1f\x7f]", url):
            raise ValueError("Malformed URL")
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise ValueError("Only HTTP(S) URLs are supported")
        if parts.username is not None or parts.password is not None:
            raise ValueError("URL credentials are not allowed")
        if parts.port not in {None, 80 if parts.scheme == "http" else 443}:
            raise ValueError("Non-default ports are not allowed")
        host = parts.hostname.lower()
        if hosts is not None and host not in hosts:
            raise ValueError("URL must belong to the selected source's exact domain")
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            raise ValueError("Local destinations are not allowed")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise ValueError("Non-public addresses are not allowed")
        return urlunsplit(parts._replace(fragment=""))
    except (ValueError, TypeError) as error:
        raise ConnectorError("invalid_url", str(error)) from error


async def public_host(host: str) -> None:
    """Reject mixed public/private DNS responses too; fail closed on DNS errors."""
    try:
        records = await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as error:
        raise ConnectorError("network_error", f"DNS lookup failed for {host}") from error
    if not records or any(not ipaddress.ip_address(r[4][0]).is_global for r in records):
        raise ConnectorError("invalid_url", "DNS resolved to a non-public address")
