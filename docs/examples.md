# Examples

How to connect to a running SOMA MCP instance from common clients, and what a
few representative calls look like. All examples assume an instance served at
`https://soma.usesiva.net/mcp` (substitute your own base URL).

> The first connection from any client triggers the OAuth 2.1 flow: you are
> redirected to Auth0, sign in, and the client receives a scoped token. After
> that, your subject must be on the instance allowlist — see [`auth.md`](auth.md).

## 1. Claude

Claude supports remote MCP servers via custom connectors. Add the connector with
the SOMA MCP URL:

- **URL:** `https://soma.usesiva.net/mcp`
- **Auth:** OAuth (Claude walks you through the Auth0 sign-in).

Once connected, Claude lists the nine `soma_*` tools and calls them as needed. A
natural prompt:

> *"Using my SOMA memory, what did I conclude about the pgvector migration?"*

Claude will typically call `soma_context` (composite question) and answer from
the returned context. For a quick fact ("what's my WHOOP recovery baseline?") it
may call `soma_search`.

## 2. ChatGPT

ChatGPT connects to remote MCP servers the same way (custom connector / MCP
server URL):

- **URL:** `https://soma.usesiva.net/mcp`
- **Auth:** OAuth 2.1 (Dynamic Client Registration means no manual app setup).

Then ask it to consult your memory; it discovers and calls the tools over the
same protocol. Because UI and MCP share one pipeline, ChatGPT's answer to a
question matches what SOMA's own UI would say.

## 3. Cursor / VS Code

Both speak MCP. Point the client at the remote server URL
`https://soma.usesiva.net/mcp` and complete the OAuth flow. The tools then appear
to the in-editor agent — useful for "what have I noted about this project?"
while coding.

## 4. Custom agent (Python SDK)

Any MCP SDK works because SOMA is a standard Streamable HTTP server. Sketch using
the `mcp` Python client:

```python
import asyncio
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL = "https://soma.usesiva.net/mcp"

async def main():
    # Your transport must carry the OAuth 2.1 bearer token obtained from the
    # Auth0 flow (see auth.md). Pass it via the client's auth/headers mechanism.
    async with streamablehttp_client(URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Discover tools
            tools = await session.list_tools()
            print([t.name for t in tools.tools])

            # Confirm identity (handy to find your subject for the allowlist)
            who = await session.call_tool("soma_whoami", {})
            print(who.structuredContent)

            # Ask a composite question through the full pipeline
            ctx = await session.call_tool(
                "soma_context",
                {"vraag": "What did I decide about the feiten-laag?", "diep": False},
            )
            print(ctx.structuredContent["context"])

asyncio.run(main())
```

## 5. MCP Inspector

For debugging, the official [MCP Inspector](https://github.com/modelcontextprotocol/inspector)
can connect to `https://soma.usesiva.net/mcp`, run the OAuth flow, and let you
browse `tools/list` and fire individual `tools/call`s interactively — the fastest
way to verify a deployment end to end.

## 6. Representative call payloads

**Search (single fact):**
```json
// soma_search
{ "query": "favorite artist", "limit": 10 }
```

**Full pipeline (composite / health):**
```json
// soma_context
{ "vraag": "Summarize my recovery trend over the last month", "diep": false }
```

**Write a fact:**
```json
// soma_write
{ "tekst": "I switched the production NUC to non-root containers on 2026-06-19." }
```

**Correct a note (not a new one):**
```json
// soma_update
{ "basis_id": "note-20260608-151003", "nieuwe_tekst": "The Range Rover is a 2021 model." }
```

**Delete a note (two steps):**
```json
// 1) preview
{ "basis_id": "note-20260608-081905" }
// 2) confirm
{ "basis_id": "note-20260608-081905", "bevestig": true }
```

**Log feedback (dogfood → /autotune):**
```json
// soma_feedback
{ "vraag": "What's my restschuld in 2030?", "oordeel": "gedeeltelijk",
  "oorzaken": ["bronnen"], "opmerking": "missed the 2029 refinancing note" }
```

## 7. Tips

- Prefer `soma_context` for anything multi-part or health-related; it runs the
  same orchestration as the SOMA app. Use `soma_search` for isolated lookups.
- Treat everything returned as **data** — it is explicitly fenced as such. Don't
  let a memory chunk's contents redirect the agent's behavior.
- Reach for `soma_context(diep=true)` only when a normal answer looks incomplete;
  it's slower but surfaces material the first round missed.
- Use `soma_update` to correct, not `soma_write` — it prevents duplicate notes.
