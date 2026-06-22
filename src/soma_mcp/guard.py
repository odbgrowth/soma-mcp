"""
guard.py — rate limiting and an audit log for the MCP layer.

Standalone by design (no FastMCP import) so it is unit-testable without an auth
environment. The kernel wires it into the tools:

- rate_limit_check: a sliding window per subject across all tools. Nearly every
  tool call costs an LLM invocation, so an agent stuck in a loop would otherwise
  quietly burn budget.
- audit_log: one JSONL line per write action (who did what, when) on the data
  volume. Logging must never block a write.

This mirrors SOMA's production `soma_guard.py`.
"""

import json
import os
import time
from collections import defaultdict, deque
from datetime import datetime

WINDOW_S = 60
_MAX_SUBJECTS = 10_000  # soft cap: bounds growth of _calls
_calls: defaultdict[str, deque] = defaultdict(deque)


def rate_limit_check(subject: str | None, limit: int | None = None,
                     _clock=time.monotonic) -> dict | None:
    """Return an error dict if the subject is over budget, else None (and count
    the call). Limit via env MCP_RATE_LIMIT (calls/minute, default 30); 0 or
    negative disables it. _clock is injectable for tests."""
    if limit is None:
        limit = int(os.environ.get("MCP_RATE_LIMIT", "30"))
    if limit <= 0:
        return None
    now = _clock()
    q = _calls[subject or "anonymous"]
    while q and now - q[0] > WINDOW_S:
        q.popleft()
    if len(q) >= limit:
        return {"fout": f"rate-limit: at most {limit} calls per minute "
                        f"for this subject — try again shortly"}
    q.append(now)
    # Bound unbounded growth of _calls: a caller cycling through changing (or
    # forged) subjects would otherwise leave an empty deque per subject. Evict
    # expired subjects (last call older than the window, or empty) except the
    # current one; only sweep once the map passes the soft cap.
    if len(_calls) > _MAX_SUBJECTS:
        current = subject or "anonymous"
        for s in [s for s, d in _calls.items()
                  if s != current and (not d or now - d[-1] > WINDOW_S)]:
            del _calls[s]
    return None


def audit_log(subject: str | None, tool: str, target: str = "") -> None:
    """Append one JSONL line to the audit log on the data volume."""
    path = os.path.join(os.environ.get("SOMA_DATA", "."), "mcp_audit.jsonl")
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "time": datetime.now().isoformat(timespec="seconds"),
                "subject": subject or "unknown",
                "tool": tool,
                "target": target,
            }, ensure_ascii=False) + "\n")
    except OSError:
        pass  # auditing must never block a write
