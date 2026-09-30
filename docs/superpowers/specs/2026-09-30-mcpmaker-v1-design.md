# mcpmaker v1 — Design Spec

- **Date:** 2026-09-30
- **Status:** Draft, awaiting review
- **Decision log:** see `versionideas.md` (Q1–Q8)

## 1. Goal

A Python package that a FastAPI developer adds with **one line** to expose their existing API as an MCP server, plus a CLI that **connects** that server to every installed AI client correctly.

The value we add over existing FastAPI→MCP converters (FastMCP, fastapi-mcp) is the "connect it properly" half:
- multi-client auto-registration
- auth wiring
- a stdio bridge for clients that need one
- end-to-end verification (`doctor`)
- safe defaults (read-only unless opted in)

### Success criteria

1. `mount_mcp(app)` on an unmodified FastAPI app boots and serves Streamable-HTTP MCP at `/mcp`, with one tool per exposed route.
2. `mcpmaker connect` registers the server in every supported installed client without damaging existing config.
3. `mcpmaker doctor` reports ✓ for a correctly wired setup and gives an actionable ✗ for each broken link.
4. A tool call reaches the real route with the caller's auth header, and route errors come back to the model as MCP error results.

### Non-goals for v1 (parked in `versionideas.md`)

- Function decorators → tools
- Natural-language → generated server
- Express/Node support
- Other Python frameworks
- MCP-spec OAuth 2.1
- Hosting service

## 2. Developer experience

```python
from fastapi import FastAPI
from mcpmaker import mount_mcp

app = FastAPI()
# ... existing routes ...
mount_mcp(app)
```

```
mcpmaker connect --url http://localhost:8000/mcp --header "Authorization: Bearer ${API_TOKEN}"
mcpmaker doctor  --url http://localhost:8000/mcp
mcpmaker serve   ./openapi.json --base-url https://api.example.com    # fallback: no app code needed
mcpmaker bridge  --url http://localhost:8000/mcp                      # stdio↔HTTP, used by client configs
```

### Public API

```python
def mount_mcp(
    app: FastAPI,
    *,
    path: str = "/mcp",
    name: str | None = None,              # server name; default: app.title
    include_writes: bool = False,
    exclude: Sequence[str] = (),            # glob patterns on route paths, e.g. "/admin/*"
    forward_headers: Sequence[str] = (),    # extra headers beyond Authorization and Cookie
    auth: AuthProvider | None = None,     # default: PassThroughAuth(forward_headers)
    max_tools_warning: int = 40,
) -> MountHandle   # .report: MountReport, filled in when the app starts
```

`MountHandle.report` (a `MountReport`, set at app startup because the server is built then) lists exposed tools, hidden routes (with reasons), skipped routes (with errors), and warnings. It is also logged at startup.

## 3. Architecture

Package layout: `src/mcpmaker/`

| Unit | Responsibility | Depends on |
|---|---|---|
| `engine.py` | **Sole importer of FastMCP.** `build_server(spec, name, selection, client) -> (FastMCP, skipped)` (one code path for app and spec: an app is its `app.openapi()` + an in-process ASGI httpx client), `make_api_client(...)`, `probe(url, headers)` for doctor, `run_stdio_bridge(url, headers)` via `create_proxy`. | FastMCP 3.x |
| `policy.py` | `operations_from_spec(spec, endpoint_names)`, `select_operations(ops, ...) -> Selection` (exposed / hidden+reason), tool-name derivation and dedup. Works on OpenAPI operations so `mount` and `serve` share it. Pure functions. | — |
| `auth.py` | `AuthProvider` protocol `headers_for(incoming: Mapping[str, str]) -> dict[str, str]`; `PassThroughAuth`. | — |
| `mount.py` | `mount_mcp`: registers an exact-path route at `path` and chains lifespans; at app startup it runs policy, builds via engine, and emits `MountReport`. | policy, engine, auth |
| `report.py` | `MountReport` dataclass and its startup-table formatting. | — |
| `clients/base.py` | `ClientAdapter` protocol: `name`, `detect() -> bool`, `config_path()`, `install(entry) -> InstallResult`, `read_entry(name)`. | — |
| `clients/{claude_code,cursor,claude_desktop,vscode,windsurf}.py` | One adapter per client. | base, `configio` |
| `configio.py` | Safe JSON config editing: read → validate → merge → backup `*.bak` → atomic write (temp file + `os.replace`). | — |
| `cli/` | `connect`, `doctor`, `serve`, `bridge` commands (Typer). `bridge` and `doctor` call `engine.run_stdio_bridge` / `engine.probe`. | all above |

### Runtime data flow

1. The AI client calls `/mcp` in the user's app.
2. FastMCP (via `engine`) receives the call and asks the `AuthProvider` for headers.
3. It makes an in-process ASGI call to the real route.
4. The route's own dependencies, auth and validation run.
5. The response is mapped to an MCP tool result.

### Lifespan

FastMCP's HTTP app needs its lifespan to run. Because `mount_mcp` is called *after* `FastAPI()` is constructed, it wraps the app's existing `router.lifespan_context`: on startup it enters the user's lifespan, then **builds** the MCP server from `app.openapi()` (so routes registered after `mount_mcp` are still included), then enters the MCP session manager's lifespan. `/mcp` is registered as an exact-path Starlette `Route` (not a `Mount`) so clients never hit a `/mcp` → `/mcp/` redirect. Requests to `/mcp` before startup completes get 503. This must be tested with apps that do and don't define their own lifespan.

## 4. Route policy and naming

Rules are evaluated in order; the first match wins.

1. **Always hidden:** docs/openapi/redoc routes, the MCP mount path itself, `include_in_schema=False` routes.
2. **Excluded:** path matches an `exclude` glob, or the route has `openapi_extra={"x-mcp": False}`.
3. **Included:** the route has `openapi_extra={"x-mcp": True}`. Works for any method.
4. **Default:** `GET` is exposed. `POST/PUT/PATCH/DELETE` are exposed only if `include_writes=True`.

**Tool name:**
- If the developer set a custom `operationId`, use it.
- Otherwise use the endpoint's Python function name.
- On collision, append `_2`, `_3`, … and warn.
- Names are sanitized to `[a-zA-Z0-9_-]{1,64}`.

**Description:** route `summary` + `description`, falling back to the endpoint docstring. Parameter descriptions come from the Pydantic schema.

**Warnings (in `MountReport`):**
- tools without descriptions
- tool count > `max_tools_warning`
- zero tools exposed, with the likely cause

## 5. Auth

- `PassThroughAuth` forwards `Authorization`, `Cookie`, and every name in `forward_headers` from the inbound MCP HTTP request to the route call.
- Header **values are never logged**; only names appear in reports.
- `AuthProvider` is the v2 OAuth insertion point. No other module may read auth headers directly.

## 6. Client adapters

The formats below are the current understanding. **Each must be re-verified against the client's current docs during implementation**, and adapter tests pin the verified format.

| Client | Config location | Entry shape | Notes |
|---|---|---|---|
| Claude Code | via `claude mcp add --transport http --scope user <name> <url> --header …` | CLI-managed | Prefer the `claude` CLI when on PATH; otherwise report a manual snippet. |
| Cursor | `~/.cursor/mcp.json` | `mcpServers.<name> = {url, headers}` | Supports `${env:VAR}` interpolation. |
| Claude Desktop | `%APPDATA%\Claude\claude_desktop_config.json` / `~/Library/Application Support/Claude/claude_desktop_config.json` | `mcpServers.<name> = {command: "mcpmaker", args: ["bridge","--url",…], env: {…}}` | stdio only → uses `bridge`. Headers are passed via `env`. |
| VS Code | user `mcp.json` (profile dir) | `servers.<name> = {type: "http", url, headers}` | Supports `${env:VAR}` / `${input:…}`. |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` | `mcpServers.<name> = {serverUrl, headers}` | |

**Secrets:** if the `--header` value contains `${VAR}`, write the client's env-reference syntax where supported. Where a client can't interpolate, write the literal value and print a warning naming the file.

## 7. CLI behaviour

### `connect`
1. Detect all clients and print ✓/✗ per client.
2. Prompt for a selection (`--all`, `--client X` (repeatable), `--yes` skip prompts).
3. Per client, `configio` does: parse → if a same-name entry exists, confirm replace (skipped with `--yes`) → merge → backup → atomic write.
4. Print reload instructions per client.
5. Offer to run `doctor`.

The server name defaults to the `/mcp` server's reported name, slugified. It can be set with `--name`.

### `doctor` checks
1. URL reachable.
2. MCP `initialize` succeeds.
3. `tools/list` returns ≥1 tool.
4. Optionally (`--call <tool>`), a real call with the configured header succeeds.
5. Each detected client has an entry pointing at this URL.
6. The Claude Desktop entry's `mcpmaker` command resolves on PATH.

Each FAIL comes with one concrete fix. CLI status markers are ASCII (`OK` / `FAIL` / `--`) so they're safe on legacy Windows consoles. The exit code is non-zero if any check fails.

### `serve`
Loads an OpenAPI 3.x JSON/YAML (file or URL), applies the same policy/auth, proxies to `--base-url`, and serves on `--host/--port` (default `127.0.0.1:8765`).

### `bridge`
stdio ↔ Streamable HTTP. Reads headers from env vars `MCPMAKER_HEADER_<N>` (format `Name: value`).

## 8. Error handling

| Where | Failure | Behaviour |
|---|---|---|
| mount | Conversion fails for a route | Skip the route, record it in `MountReport.skipped` with the reason, continue booting. |
| mount | Zero tools | Loud warning with the likely cause. The app still boots. |
| tool call | Route returns 4xx/5xx | MCP result `isError: true` with status and (truncated to 4 KB) body. The session stays up. |
| tool call | 401/403 | As above, plus the hint "auth failed — check the header configured in your client; run `mcpmaker doctor`". |
| tool call | Route raises | `isError: true`, generic message. No traceback is sent to the model; the full traceback goes to the server log. |
| connect | Malformed config JSON | Do not write. Report the path and parse location. `--force` overwrites (the backup is still made). |
| connect | Permission denied | Print the path and a copy-paste snippet. |
| connect | Name exists | Confirm before replacing; `--yes` replaces. |
| bridge | Upstream unreachable | The stdio side stays alive; each request that can't reach upstream gets an MCP error naming the URL; the next request retries the connection. |
| doctor | Any check fails | ✗ + fix, non-zero exit. |

## 9. Testing

- **Unit:**
  - `policy` (every rule and precedence, naming, dedup, sanitization)
  - `configio` (merge, backup, atomic write, malformed input)
  - each client adapter against fixture configs in a temp home dir
  - `PassThroughAuth`
- **Integration:**
  - a sample FastAPI app with GET, POST, auth-protected and failing routes, and a custom lifespan
  - `mount_mcp` on it, then a real MCP client over HTTP:
    - list tools, and assert hidden writes are absent
    - call a GET, and a 401 route → error result
    - call a route that raises → error result without a traceback
- **CLI:**
  - `connect --all --yes` into a temp home → configs written, backups exist, other servers preserved
  - `doctor` against a running test app → exit 0, and against a dead URL → non-zero
- **Platforms:** tests use a fake home dir so config paths for Windows, macOS and Linux are all exercised locally; no hosted CI (no GitHub).

## 10. Tech choices

- Python ≥ 3.10
- FastMCP 3.x (`>=3.2,<4`; confined to `engine.py`)
- Typer (CLI)
- pytest
- Packaging via `pyproject.toml` (hatchling); installable with `pip install mcpmaker` / `uvx mcpmaker`

## 11. Open items (non-blocking)

- Final package name / branding (placeholder: `mcpmaker`).
- Wider client list beyond the five above: add as adapters once v1 ships.
