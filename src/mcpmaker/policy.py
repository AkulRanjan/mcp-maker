"""Decide which OpenAPI operations become MCP tools, and what they're called.

Pure functions: no FastAPI, no FastMCP. Shared by `mount_mcp` and `mcpmaker serve`.
"""

from __future__ import annotations

import copy
import fnmatch
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

WRITE_REASON = "write method (pass include_writes=True or set openapi_extra={'x-mcp': True})"
EXCLUDED_REASON = "excluded"
MCP_PATH_REASON = "mcp endpoint"
METHOD_REASON = "unsupported method"

MAX_NAME_LEN = 64
_BAD_NAME_CHARS = re.compile(r"[^a-zA-Z0-9_-]")


@dataclass(frozen=True)
class Operation:
    operation_id: str
    method: str  # upper-case
    path: str
    summary: str = ""
    description: str = ""
    x_mcp: bool | None = None
    function_name: str | None = None


@dataclass(frozen=True)
class Hidden:
    operation: Operation
    reason: str


@dataclass
class Selection:
    operations: dict[str, Operation]
    exposed: dict[str, str] = field(default_factory=dict)  # operation_id -> tool name
    hidden: list[Hidden] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def sanitize_name(raw: str) -> str:
    name = _BAD_NAME_CHARS.sub("_", raw).strip("_") or "tool"
    return name[:MAX_NAME_LEN]


def ensure_operation_ids(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deep copy of `spec` in which every operation has an operationId."""
    out = copy.deepcopy(dict(spec))
    for path, item in (out.get("paths") or {}).items():
        for method in HTTP_METHODS:
            op = item.get(method)
            if isinstance(op, dict) and not op.get("operationId"):
                op["operationId"] = sanitize_name(f"{method}_{path}")
    return out


def operations_from_spec(
    spec: Mapping[str, Any],
    endpoint_names: Mapping[tuple[str, str], str] | None = None,
) -> list[Operation]:
    """List operations in `spec`. Every operation must have an operationId (see ensure_operation_ids)."""
    endpoint_names = endpoint_names or {}
    ops: list[Operation] = []
    for path, item in (spec.get("paths") or {}).items():
        for method in HTTP_METHODS:
            raw = item.get(method)
            if not isinstance(raw, dict):
                continue
            upper = method.upper()
            x_mcp = raw.get("x-mcp")
            ops.append(
                Operation(
                    operation_id=raw["operationId"],
                    method=upper,
                    path=path,
                    summary=raw.get("summary") or "",
                    description=raw.get("description") or "",
                    x_mcp=x_mcp if isinstance(x_mcp, bool) else None,
                    function_name=endpoint_names.get((upper, path)),
                )
            )
    return ops


def select_operations(
    operations: Sequence[Operation],
    *,
    include_writes: bool = False,
    exclude: Sequence[str] = (),
    mount_path: str = "/mcp",
    max_tools_warning: int = 40,
) -> Selection:
    sel = Selection(operations={op.operation_id: op for op in operations})
    used: set[str] = set()
    undocumented: list[str] = []

    for op in operations:
        reason = _hidden_reason(op, include_writes, exclude, mount_path)
        if reason is not None:
            sel.hidden.append(Hidden(op, reason))
            continue
        base = sanitize_name(op.function_name or op.operation_id)
        name = _dedupe(base, used)
        if name != base:
            sel.warnings.append(f"tool name collision: {op.method} {op.path} renamed '{base}' -> '{name}'")
        used.add(name)
        sel.exposed[op.operation_id] = name
        if not (op.summary or op.description):
            undocumented.append(name)

    if undocumented:
        sel.warnings.append(f"{len(undocumented)} tools have no description: {', '.join(undocumented)}")
    count = len(sel.exposed)
    if count > max_tools_warning:
        sel.warnings.append(
            f"{count} tools exposed; models pick tools less reliably above {max_tools_warning}. "
            "Consider exclude=[...]"
        )
    if count == 0:
        writes = sum(1 for h in sel.hidden if h.reason == WRITE_REASON)
        if writes:
            sel.warnings.append(
                f"0 tools exposed: {writes} write routes are hidden - pass include_writes=True "
                "or mark routes with openapi_extra={'x-mcp': True}"
            )
        else:
            sel.warnings.append("0 tools exposed: no routes matched")
    return sel


def _hidden_reason(op: Operation, include_writes: bool, exclude: Sequence[str], mount_path: str) -> str | None:
    mount = mount_path.rstrip("/")
    if op.path == mount or op.path.startswith(mount + "/"):
        return MCP_PATH_REASON
    if op.x_mcp is False or any(fnmatch.fnmatchcase(op.path, pattern) for pattern in exclude):
        return EXCLUDED_REASON
    if op.x_mcp is True or op.method == "GET":
        return None
    if op.method in WRITE_METHODS:
        return None if include_writes else WRITE_REASON
    return METHOD_REASON


def _dedupe(base: str, used: set[str]) -> str:
    if base not in used:
        return base
    n = 2
    while True:
        suffix = f"_{n}"
        candidate = base[: MAX_NAME_LEN - len(suffix)] + suffix
        if candidate not in used:
            return candidate
        n += 1
