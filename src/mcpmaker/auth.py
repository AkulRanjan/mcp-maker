"""How the MCP caller's credentials reach the user's API routes.

Every module that needs auth headers goes through an AuthProvider; v2 OAuth is a second implementation.
"""

from __future__ import annotations

from typing import Mapping, Protocol, Sequence

DEFAULT_FORWARD = ("authorization", "cookie")


class AuthProvider(Protocol):
    def headers_for(self, incoming: Mapping[str, str]) -> dict[str, str]:
        """Headers to send to the API route, given the inbound MCP HTTP request headers."""
        ...


class PassThroughAuth:
    def __init__(self, forward_headers: Sequence[str] = ()) -> None:
        names = (*DEFAULT_FORWARD, *(h.lower() for h in forward_headers))
        self.names = tuple(dict.fromkeys(names))

    def headers_for(self, incoming: Mapping[str, str]) -> dict[str, str]:
        lowered = {k.lower(): v for k, v in incoming.items()}
        return {name: lowered[name] for name in self.names if name in lowered}


def parse_header(raw: str) -> tuple[str, str]:
    name, sep, value = raw.partition(":")
    if not sep or not name.strip():
        raise ValueError("invalid header: expected 'Name: value'")
    return name.strip(), value.strip()
