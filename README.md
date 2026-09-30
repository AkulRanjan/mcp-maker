# mcpmaker

Turn your FastAPI app into an MCP server with one line, then connect it to every AI client with one command.

## Install

```bash
pip install mcpmaker
```

## 1. Add it to your app

```python
from fastapi import FastAPI
from mcpmaker import mount_mcp

app = FastAPI()
# ... your routes ...
mount_mcp(app)   # serves MCP at /mcp
```

At startup you'll see what the AI can use:

```
mcpmaker: 12 tools exposed at /mcp (7 write routes hidden - pass include_writes=True or mark routes)
```

**Safe by default:** only GET routes become tools. To expose writes:

```python
mount_mcp(app, include_writes=True)                   # all writes
@app.post("/items/{id}/star", openapi_extra={"x-mcp": True})   # just this one
mount_mcp(app, exclude=["/admin/*"])                  # hide paths
```

Auth: the `Authorization` and `Cookie` headers sent by the AI client are passed to your routes, so your existing auth keeps working. Add more with `forward_headers=["X-API-Key"]`.

## 2. Connect your AI clients

```bash
mcpmaker connect --url http://localhost:8000/mcp --header "Authorization: Bearer ${API_TOKEN}"
```

This detects Claude Code, Cursor, VS Code, Windsurf, and Claude Desktop, and adds the server to each (Claude Desktop is connected through the bundled `mcpmaker bridge`). It never clobbers your other servers, and it keeps a `.bak` of every file it touches. Where a client supports it, `${API_TOKEN}` stays an env-var reference instead of a pasted secret. (VS Code and Claude Desktop need the real value, so it's written there in plain text and `connect` warns you.)

## 3. Check everything works

```bash
mcpmaker doctor --url http://localhost:8000/mcp
```

## No access to the API's code?

```bash
mcpmaker serve ./openapi.json --base-url https://api.example.com
```
