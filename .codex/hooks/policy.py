"""Deterministic Codex lifecycle guard shared by parity-enabled projects."""

from __future__ import annotations

import json
import re
import sys
from typing import Any


BLOCKED_COMMANDS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bgit\s+reset\s+--hard\b", re.I), "git reset --hard is forbidden"),
    (re.compile(r"\bgit\s+clean\s+-[^\s]*[fd][^\s]*\b", re.I), "destructive git clean is forbidden"),
    (re.compile(r"\bgit\b[^\r\n]*\bpush\b", re.I), "direct git push is forbidden; use the guarded project devflow"),
    (re.compile(r"\bgit\b[^\r\n]*\bcommit\b", re.I), "direct git commit is forbidden; use the guarded project devflow"),
    (re.compile(r"\bgh\s+pr\s+create\b", re.I), "direct PR creation is forbidden; use the guarded project devflow"),
    (re.compile(r"\b(?:git\s+merge|gh\s+pr\s+merge)\b", re.I), "direct merge is forbidden"),
    (re.compile(r"\bgh\s+workflow\s+run\b", re.I), "manual workflow dispatch is forbidden"),
    (
        re.compile(
            r"\b(?:cat|type|more|less|Get-Content|gc|Select-String|rg)\b[^\r\n]*"
            r"(?:[\\/\s])\.env(?!\.example\b)(?:\.|\s|$)",
            re.I,
        ),
        "direct secret-profile reads are forbidden",
    ),
)


def command_from(payload: dict[str, Any]) -> str:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return ""
    command = tool_input.get("command")
    return command if isinstance(command, str) else ""


def blocked_reason(command: str) -> str | None:
    for pattern, reason in BLOCKED_COMMANDS:
        if pattern.search(command):
            return reason
    return None


def response(payload: dict[str, Any]) -> dict[str, Any] | None:
    event = payload.get("hook_event_name")
    if event == "SessionStart":
        return {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": (
                    "Read AGENTS.md, PROJECT.yaml, CURRENT_TASK.md, ARCHITECTURE.md, "
                    "and DECISIONS.md before non-trivial work. Use a dedicated task "
                    "branch/worktree. Never read secret values. Architecture, merge, "
                    "environment sync, and production each require their documented approval."
                ),
            }
        }
    if event == "SubagentStart":
        return {
            "hookSpecificOutput": {
                "hookEventName": "SubagentStart",
                "additionalContext": (
                    "Stay within the delegated role. Do not push, merge, deploy, change "
                    "architecture, or access production/secrets. Return a structured handoff."
                ),
            }
        }
    if event == "PreToolUse":
        reason = blocked_reason(command_from(payload))
        if reason:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"invalid hook input: {exc}", file=sys.stderr)
        return 2
    result = response(payload)
    if result is not None:
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
