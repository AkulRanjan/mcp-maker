"""Facts about a FastAPI app that aren't in its OpenAPI document."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.routing import APIRoute


def endpoint_names(app: FastAPI) -> dict[tuple[str, str], str]:
    """(METHOD, path) -> endpoint function name, for routes without a developer-set operation_id."""
    names: dict[tuple[str, str], str] = {}
    for route in app.routes:
        if isinstance(route, APIRoute) and route.include_in_schema and route.operation_id is None:
            for method in route.methods:
                names[(method.upper(), route.path_format)] = route.name
    return names
