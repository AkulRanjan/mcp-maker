# MCP Maker — Version Ideas & Decisions

A running log of the product questions we've asked, what we decided, and what's parked for later versions.

## Product goal

People plug our code into their project and it automatically (1) turns their stuff into an MCP server and (2) connects it properly — both to local AI clients (Claude Desktop, Claude Code, Cursor, …) and as a remotely reachable server.

---

## Decisions so far

### Q1. What does the user already have that we turn into an MCP server?
- **A.** Their app's existing functions (decorators / annotations → MCP tools)
- **B.** Their existing HTTP API (OpenAPI spec or framework routes → MCP tools)
- **C.** A plain-language description ("an MCP that manages my Notion tasks") → generated server code
- **D.** Something else / a mix

**Decision:** Wedge (v1) = **B**. A and C are planned for later versions — keep the architecture open for them.

### Q2. What does "connect them properly" mean?
- Auto-register the server with local AI clients (Claude Desktop, Claude Code, Cursor)
- Host it so it's reachable over the internet

**Decision:** **Both.**

### Q3. What does "plug in our code" look like for the developer?
- **A.** Middleware inside their running app (`mount_mcp(app)`) — serves `/mcp` alongside their API, same auth, same deploy
- **B.** Standalone CLI pointed at an OpenAPI spec (`uvx ourtool ./openapi.json`) — separate proxy process, language-agnostic
- **C.** Both — middleware as the main product, CLI as fallback for APIs whose code you don't control

**Decision:** **C** — middleware primary, CLI fallback.

### Q4. Which framework/ecosystem does the wedge target first?
- **A.** FastAPI / Python — real OpenAPI + Pydantic types for free; one core engine, two entry points
- **B.** Express / Node (TypeScript) — bigger market, but routes carry no schemas
- **C.** Both from day one — two cores, not recommended for a wedge

**Decision:** **A — FastAPI / Python.**

### Q5. Which routes become MCP tools by default?
- **A.** Read-only by default — GETs auto-exposed; writes (POST/PUT/PATCH/DELETE) require opt-in per route or `include_writes=True`
- **B.** Everything by default, developer excludes
- **C.** Nothing by default, opt-in only

**Decision:** **A — read-only by default, writes opt-in.**

### Q6. How does auth work when an AI calls a tool?
- **A.** Pass-through — client sends a header (e.g. `Authorization: Bearer …`), middleware forwards it to the user's route; their existing FastAPI auth does the checking
- **B.** Full MCP-spec OAuth 2.1 (login pop-up, scoped tokens)
- **C.** Pass-through now, design leaves a slot for OAuth later

**Decision:** **C — pass-through in v1, OAuth-ready design.**

### Q7. Which AI clients does `connect` auto-register in v1?
Mechanism: a `connect` CLI command detects installed clients and writes the server (URL + auth header) into each client's config file.
- **A.** Claude Code, Cursor, Claude Desktop (Desktop via bundled stdio→HTTP bridge)
- **B.** Claude Code + Cursor only
- **C.** Wider: A plus VS Code (Copilot), Windsurf, others

**Decision:** **C — wide client support.** Each client = one config adapter; keep adapters pluggable.

---

### Q8. Build approach?
- **1.** Build on FastMCP as the conversion engine (isolated behind one adapter module); our value = policy, auth, connect/doctor
- **2.** Build converter from scratch
- **3.** Connect-only product (no conversion)

**Decision:** **1 — build on FastMCP.** Revisit owning the converter when A (decorators) / C (NL → server) land.

---

## Competitive landscape (researched 2026-09-29)

- **FastMCP** — `FastMCP.from_fastapi(app)` / `from_openapi(spec)`: every operation → tool, auto schemas. https://gofastmcp.com/integrations/fastapi
- **fastapi-mcp** (tadata-org) — native FastAPI extension, mounts `/mcp`. https://github.com/tadata-org/fastapi_mcp
- **fastapi-mcp-openapi** — introspection tools only (listEndpoints / getEndpointDocs).

Takeaway: FastAPI/OpenAPI → MCP conversion alone is commoditized. Our wedge must win on the **"connect it properly"** half (multi-client auto-registration, auth wiring, Desktop bridge, doctor/verification) plus safe defaults.

## Parked for later versions

| Idea | Origin | Notes |
|---|---|---|
| Functions → MCP tools (decorators) | Q1-A | The in-process middleware hook is the natural place for this to land |
| Plain-language description → generated MCP server | Q1-C | Likely LLM-driven codegen on top of the same core |
| Express / Node support | Q4-B | Needs a schema source (zod, JSDoc, or an existing spec) to be good |
| MCP-spec OAuth 2.1 for remote clients | Q6-B | v1 auth is pass-through; keep an auth-provider interface so OAuth drops in |
| Other Python frameworks (Flask, Django, Starlette) | Q4 follow-up | Flask/Django lack built-in OpenAPI; would need a spec source |

---

## Open questions (still to decide)

- Transport: Streamable HTTP only, or also stdio for local clients?
- Tool naming & descriptions — from `operationId` / docstrings? Allow overrides?
- Package name / branding.
