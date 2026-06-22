# Tools Reference

SOMA MCP advertises the `tools` capability with **nine tools**. Input schemas are
derived from the Python signatures; the descriptions clients see are the
docstrings in `soma_mcp.py`. Logic lives in `soma_mcp_kern.py`.

Conventions used below:
- **Guard** — the authorization required (see [`auth.md`](auth.md)).
- All returned memory text is **fenced** as data, not instructions (see
  [`security.md`](security.md) §5).
- Errors are returned as a result with a `fout` field, not thrown.

> Tool parameters use SOMA's Dutch names (`vraag` = question, `tekst` = text,
> `bevestig` = confirm, `diep` = deep). They are documented in English here.
>
> **Reference vs. live server:** this document describes the **live** SOMA server.
> The reference implementation in this repository (`src/soma_mcp/`) anglicizes the
> parameter names (`question`, `text`, `confirm`, `deep`, `verdict`) and some
> result strings; the semantics are identical. See the repository README, "Note
> on language".

---

## Read tools

### `soma_search(query, limit=15) → list[dict]`
**Guard:** instance access. Vector search + Haiku relevance filter. Returns the
filtered chunks with metadata. Use for **single-fact lookups**.

Each item:
```json
{ "id": "...", "tekst": "<fenced text>", "domein": "", "datum": "",
  "herkomst": "claude|chatgpt|whoop|spotify|upload|note", "gesprekstitel": "" }
```

### `soma_get(id) → dict`
**Guard:** instance access. Fetch one chunk by exact id. Returns the same shape as
a `soma_search` item, or `{ "fout": "Geen chunk gevonden met id '...'" }`.

### `soma_context(vraag, max_tekens=30000, diep=False) → dict`
**Guard:** instance access. The **full retrieval pipeline** — the same route the
SOMA app uses: sub-question decomposition, health aggregation (WHOOP
counts/trends), type-pull on list questions, Haiku relevance filtering. Returns
assembled context; the calling model formulates the answer from it. Use for
**health questions and composite questions**; use `soma_search` for isolated
lookups.

- `max_tekens` is clamped to `[500, 200000]`; context beyond it is truncated with
  a marker.
- `diep=true` runs a **deep-search** second round over reformulations that
  excludes all first-round sources — use when the normal answer looks incomplete
  or the user asks for a thorough search (slower; finds material round one missed).

```json
{ "context": "<fenced text>", "status": "...",
  "bronnen": [ { "id": "...", "herkomst": "...", "datum": "..." } ] }
```

### `soma_debug(query, limit=25) → dict`
**Guard:** instance access. Diagnostic view of retrieval per stage — stage 1 raw
search, stage 2 after the Haiku filter — plus the keyword and counts. For tuning
and troubleshooting retrieval.

```json
{ "trefwoord": "...", "aantal_ruw": 65, "stap1_zoek": [ { "id": "...", "snippet": "..." } ],
  "haiku_uitleg": "...", "aantal_na_haiku": 12, "stap2_haiku": [ ... ] }
```

### `soma_whoami() → dict`
**No access guard** (intentional — a misconnected user must be able to read their
own subject to configure allowlists). Returns identity:
```json
{ "subject": "auth0|...", "client_id": "...", "scopes": ["..."], "expires_at": "..." }
```

---

## Write tools

### `soma_write(tekst) → dict`
**Guard:** write access. Add a new note. Only for **facts/memories** — feedback
goes via `soma_feedback`, and a correction of an existing note via `soma_update`
(avoids duplicates). Text over 25,000 chars is rejected. Audited.
```json
{ "status": "opgeslagen", "chunks": 3 }
```

### `soma_update(basis_id, nieuwe_tekst) → dict`
**Guard:** write access. Overwrite an existing note in place — use for
**corrections** instead of adding another note (prevents duplicates like three
separate Range Rover notes). `basis_id` looks like `note-20260608-151003`. Only
`note-*` ids are accepted; empty text is rejected (use `soma_delete`); identical
text is a no-op. Audited.
```json
{ "status": "bijgewerkt", "oude_chunks": 2, "nieuwe_chunks": 3 }
// or { "status": "ongewijzigd", "reden": "nieuwe tekst is identiek aan de huidige" }
```

### `soma_delete(basis_id, bevestig=False) → dict`
**Guard:** write access. Delete a note (all its chunks). **Two-step safety
valve:** without `bevestig=true` you get only a *preview* — review it with the
user, then call again with `bevestig=true`. Only `note-*` ids. Audited.
```json
// preview (bevestig omitted/false):
{ "preview": "first 500 chars…", "datum": "...",
  "actie": "definitief verwijderen = opnieuw aanroepen met bevestig=true" }
// confirmed:
{ "status": "verwijderd", "basis_id": "note-...", "chunks": 3 }
```

### `soma_feedback(vraag, oordeel, antwoord="", opmerking="", oorzaken=None, bron_ids=None) → dict`
**Guard:** instance access. Log dogfood feedback about a SOMA answer to the
feedback log — **not** to memory (use `soma_write` only for facts). `oordeel`
(verdict) is `ja` / `gedeeltelijk` / `nee` (yes / partially / no). Optional
`oorzaken` (causes): `trefwoord`, `bronnen`, `prompt`, `model`,
`vraag te vaag`, `onbekend`. The log feeds the `/autotune` improvement loop.
```json
{ "status": "gelogd", "oordeel": "✅ Ja" }
```

---

## Choosing a tool

| You want to… | Use |
|---|---|
| Look up an isolated fact | `soma_search` |
| Answer a health or multi-part question | `soma_context` |
| Dig deeper when an answer seems incomplete | `soma_context(diep=true)` |
| Fetch one specific chunk by id | `soma_get` |
| Remember a new fact | `soma_write` |
| Correct an existing note | `soma_update` |
| Remove a note | `soma_delete` (preview, then confirm) |
| Record whether an answer was good | `soma_feedback` |
| Inspect retrieval stages | `soma_debug` |
| Find your own subject id | `soma_whoami` |
