# ADR-002: Public SOMA MCP exception

Status: Accepted

`odbgrowth/soma-mcp` is the sole current public repository. It is the reference
implementation and integration boundary for the self-owned memory framework. All other
SOMA and customer repositories are private by default.

Public status permits only reusable implementation, protocol documentation, tests, and
safe examples. Secrets, token stores, tenant data, customer data, private infrastructure,
production configuration, and internal evidence never belong in this repository.
