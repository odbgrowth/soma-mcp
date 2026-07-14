"""Advisory Codex lifecycle policy shared by parity-enabled projects.

Filesystem permission profiles and GitHub rulesets are the enforcement boundaries.
Hooks add context and warnings; current PreToolUse hooks do not block execution.
"""

from __future__ import annotations

import json
import re
import shlex
import sys
from typing import Any


WARNING_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bgh\s+pr\s+create\b", re.I), "direct PR creation is forbidden; use the guarded project devflow"),
    (re.compile(r"\bgh\s+pr\s+merge\b", re.I), "direct merge is forbidden"),
    (re.compile(r"\bgh\s+workflow\s+run\b", re.I), "manual workflow dispatch is forbidden"),
    (
        re.compile(r"(?:^|[\\/\s])tools[\\/]deploy_prod\.sh\b", re.I),
        "run production through the guarded devflow only",
    ),
)

_GIT_OPTIONS_WITH_VALUE = {
    "-C",
    "-c",
    "--config-env",
    "--git-dir",
    "--namespace",
    "--super-prefix",
    "--work-tree",
}
_SHELL_SEPARATORS = {";", "&&", "||", "|", "&"}


def _command_segments(command: str) -> list[list[str]]:
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|")
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        tokens = command.replace('"', " ").replace("'", " ").split()

    segments: list[list[str]] = [[]]
    for token in tokens:
        if token in _SHELL_SEPARATORS:
            if segments[-1]:
                segments.append([])
            continue
        segments[-1].append(token)
    return [segment for segment in segments if segment]


def _git_reason(command: str) -> str | None:
    for segment in _command_segments(command):
        for index, token in enumerate(segment):
            executable = token.replace("\\", "/").rsplit("/", 1)[-1].lower()
            if executable not in {"git", "git.exe"}:
                continue

            cursor = index + 1
            while cursor < len(segment):
                option = segment[cursor]
                if option in _GIT_OPTIONS_WITH_VALUE:
                    cursor += 2
                    continue
                if (
                    (option.startswith("-C") and option != "-C")
                    or (option.startswith("-c") and option != "-c")
                    or (option.startswith("--") and "=" in option)
                ):
                    cursor += 1
                    continue
                if option.startswith("-"):
                    cursor += 1
                    continue
                break

            if cursor >= len(segment):
                continue
            subcommand = segment[cursor].lower()
            arguments = [argument.lower() for argument in segment[cursor + 1 :]]

            if subcommand == "reset" and any(arg.startswith("--hard") for arg in arguments):
                return "git reset --hard is forbidden"
            if subcommand == "clean" and any(
                arg == "--force" or re.fullmatch(r"-[^-]*f[^-]*", arg)
                for arg in arguments
            ):
                return "destructive git clean is forbidden"
            if subcommand == "push":
                if any(
                    arg in {"-f", "--force"} or arg.startswith("--force-with-lease")
                    for arg in arguments
                ):
                    return "force push is forbidden"
                return "direct git push is forbidden; use the guarded project devflow"
            if subcommand == "commit":
                return "direct git commit is forbidden; use the guarded project devflow"
            if subcommand == "merge":
                return "direct merge is forbidden"
    return None


def _secret_path_reason(command: str) -> str | None:
    for segment in _command_segments(command):
        for token in segment:
            candidate = token.strip("<>()[]{}:,").replace("\\", "/")
            basename = candidate.rsplit("/", 1)[-1].lower()
            if basename == ".env.example":
                continue
            if basename == ".env" or basename.startswith(".env."):
                return "direct secret-profile access is forbidden"
    return None


def command_from(payload: dict[str, Any]) -> str:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return ""
    command = tool_input.get("command")
    return command if isinstance(command, str) else ""


def blocked_reason(command: str) -> str | None:
    for reason in (_secret_path_reason(command), _git_reason(command)):
        if reason:
            return reason
    for pattern, reason in WARNING_PATTERNS:
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
            return {"systemMessage": f"Project policy warning: {reason}. Do not proceed."}
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
