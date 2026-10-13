# Examples

How to connect to a SOMA MCP instance from common clients, and what
representative calls look like. Replace `https://<your-host>/mcp` with your
instance's URL, or use `http://127.0.0.1:8000/mcp` for the local quick start in
the [README](../README.md).

> On an authenticated instance the first connection starts the OAuth 2.1 flow:
> sign in at the instance's Auth0 tenant and the client receives a token. Your
> subject must then be on the instance allowlist; see [`auth.md`](auth.md).

## 1. Claude

Add a custom connector with the URL `https://<your-host>/mcp` and OAuth
authentication. Claude walks you through the Auth0 sign-in, then lists the nine
`soma_*` tools. A natural prompt:

> *"Using my SOMA memory, what did I conclude about the database migration?"*

Claude typically calls `soma_context` for a composite question like this one,
and `soma_search` for a single fact.

## 2. ChatGPT

Add the server as a connector (remote MCP server URL `https://<your-host>/mcp`).
Client registration is automatic (Client ID Metadata Documents, or dynamic
client registration for older clients), so there is no manual app setup; sign
in when asked.

## 3. Cursor, VS Code and other editors

Point the editor's MCP configuration at the remote URL and complete the OAuth
flow. The tools then appear to the in-editor agent, which is useful for "what
have I noted about this project?" while coding.

## 4. MCP Inspector

The official [MCP Inspector](https://github.com/modelcontextprotocol/inspector)
(Node 22.19+) browses `tools/list` and fires `tools/call` interactively:

```bash
# web UI
npx @modelcontextprotocol/inspector --server-url https://<your-host>/mcp --transport http

# CLI, against the local quick-start server; the Inspector defaults to the
# legacy (initialize) era, --protocol-era modern pins 2026-07-28
npx @modelcontextprotocol/inspector --cli http://127.0.0.1:8000/mcp --transport http \
  --method tools/list
npx @modelcontextprotocol/inspector --cli http://127.0.0.1:8000/mcp --transport http \
  --protocol-era modern --method tools/call --tool-name soma_search --tool-arg query=sky
```

## 5. Custom agent (MCP Python SDK v2)

`mcp.Client` connects over Streamable HTTP and negotiates the protocol era
itself (2026-07-28 against SOMA). Headers such as `Authorization` go on an
`httpx2.AsyncClient` handed to `streamable_http_client`. This script runs as-is
against the local quick-start server; the test suite executes it.

```python
import os

import anyio
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

URL = os.environ.get("SOMA_MCP_URL", "http://127.0.0.1:8000/mcp")
TOKEN = os.environ.get("SOMA_MCP_TOKEN")  # OAuth access token; unset for a local server


async def main() -> None:
    headers = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}
    timeout = httpx2.Timeout(30.0, read=300.0)
    async with httpx2.AsyncClient(headers=headers, timeout=timeout) as http_client:
        transport = streamable_http_client(URL, http_client=http_client)
        async with Client(transport) as client:
            print("protocol:", client.protocol_version)

            # Discover tools
            listing = await client.list_tools()
            print([tool.name for tool in listing.tools])

            # Confirm identity (your subject goes on the allowlist)
            who = await client.call_tool("soma_whoami", {})
            print(who.structured_content)

            # Ask a composite question through the full pipeline
            ctx = await client.call_tool(
                "soma_context", {"question": "What did I decide about the data layer?"}
            )
            print(ctx.structured_content)


anyio.run(main)
```

For a full OAuth flow from a script, use the SDK's `OAuthClientProvider` as the
`auth=` of the `httpx2.AsyncClient`; see the SDK's
[OAuth client documentation](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/client/oauth-clients.md).
To force the older `initialize` handshake, pass `mode="legacy"` to `Client`.

## 6. Representative call arguments

Search for a single fact:

```json
{"query": "favorite artist", "limit": 10}
```

Full pipeline, composite question (`soma_context`):

```json
{"question": "Summarize my recovery trend over the last month", "deep": false}
```

Write a fact (`soma_write`):

```json
{"text": "I moved the home server to non-root containers on 2026-06-19."}
```

Correct a note instead of adding a new one (`soma_update`):

```json
{"base_id": "note-ref-0001", "new_text": "The car is a 2021 model."}
```

Delete a note in two steps (`soma_delete`):

```json
{"base_id": "note-ref-0002"}
```

```json
{"base_id": "note-ref-0002", "confirm": true}
```

Log feedback about an answer (`soma_feedback`):

```json
{"question": "What is my remaining mortgage in 2030?", "verdict": "partially",
 "causes": ["sources"], "comment": "missed the 2029 refinancing note"}
```

## 7. Tips

- Prefer `soma_context` for anything multi-part; use `soma_search` for isolated
  lookups.
- Treat everything returned as **data**: it is explicitly fenced as such. Do not
  let a memory chunk redirect the agent.
- Use `soma_context` with `deep=true` only when a normal answer looks
  incomplete; it is slower.
- Use `soma_update` to correct, not `soma_write`: it prevents duplicate notes.
