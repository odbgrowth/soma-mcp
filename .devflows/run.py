#!/usr/bin/env python3
"""Guarded, vendor-neutral project development workflow."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTECTED = {"main", "master", "staging", "production"}
VENV_PYTHON = ROOT / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


class FlowGuardError(RuntimeError):
    """Raised when an operation violates project delivery policy."""


def run(
    command: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
) -> None:
    print("+", " ".join(command))
    result = subprocess.run(command, cwd=cwd, check=False, env=env)
    if result.returncode:
        raise FlowGuardError(
            f"command failed with exit code {result.returncode}: {command[0]}"
        )


def git(*args: str, capture: bool = False) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=capture,
    )
    if result.returncode:
        raise FlowGuardError(result.stderr.strip() or "git command failed")
    return result.stdout.strip() if capture else ""


def branch_name() -> str:
    return git("branch", "--show-current", capture=True)


def require_feature_branch() -> str:
    value = branch_name()
    if not value or value in PROTECTED:
        raise FlowGuardError("delivery is forbidden from a protected or detached branch")
    return value


def validate_commit_path(path: str) -> str:
    candidate = (ROOT / path).resolve(strict=False)
    try:
        relative = candidate.relative_to(ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise FlowGuardError(f"commit path escapes the repository: {path!r}") from exc
    if relative in {"", "."} or candidate.is_dir():
        raise FlowGuardError(f"commit path must name one file: {path!r}")
    name = candidate.name.lower()
    if name.startswith(".env") and name != ".env.example":
        raise FlowGuardError(f"secret profile cannot be committed: {path!r}")
    return relative


def require_clean_index() -> None:
    staged = git("diff", "--cached", "--name-only", capture=True)
    if staged:
        raise FlowGuardError(
            "index already contains staged changes; unstage them before guarded commit"
        )


def verify_staged_scope(allowed_paths: list[str]) -> None:
    staged = set(git("diff", "--cached", "--name-only", capture=True).splitlines())
    allowed = set(allowed_paths)
    if not staged:
        raise FlowGuardError("no changes were staged for commit")
    unexpected = sorted(staged - allowed)
    if unexpected:
        raise FlowGuardError(
            "staged changes exceed requested paths: " + ", ".join(unexpected)
        )


def executable(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    suffix = ".exe" if sys.platform == "win32" else ""
    candidates = [Path.home() / ".local" / "bin" / f"{name}{suffix}"]
    if sys.platform == "win32":
        candidates.append(
            Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Links" / f"{name}.exe"
        )
        package_root = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
        if package_root.is_dir():
            candidates.extend(package_root.glob(f"**/{name}.exe"))
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def run_staged_secret_scan() -> None:
    scanner = executable("gitleaks")
    if not scanner:
        raise FlowGuardError("gitleaks is required before commit (fail-closed)")
    run([scanner, "git", "--pre-commit", "--staged", "--redact", "--verbose"])


def validate_post_commit_hook() -> None:
    hook = Path(git("rev-parse", "--git-path", "hooks/post-commit", capture=True))
    if not hook.is_absolute():
        hook = ROOT / hook
    if not hook.is_file():
        return
    content = hook.read_text(encoding="utf-8", errors="replace")
    if "git push" in content and "SKIP_AUTO_PUSH" not in content:
        raise FlowGuardError(
            "post-commit hook auto-pushes without SKIP_AUTO_PUSH support"
        )


def checks(kind: str) -> None:
    python = str(VENV_PYTHON if VENV_PYTHON.exists() else Path(sys.executable))
    if kind == "lint":
        run([python, "-m", "compileall", "-q", "src", "tests"])
    elif kind == "test":
        run([python, "-m", "pytest"])
    elif kind == "typecheck":
        raise FlowGuardError("NOT_CONFIGURED: no static type checker is configured")


def verify() -> None:
    checks("lint")
    checks("test")
    run(["git", "diff", "--check"])


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "action",
        choices=[
            "verify",
            "lint",
            "test",
            "typecheck",
            "commit",
            "push",
            "pr",
            "deploy-staging",
            "deploy-production",
            "rollback",
        ],
    )
    result.add_argument("--message")
    result.add_argument("--title")
    result.add_argument("--confirm", action="store_true")
    result.add_argument("--onno-approval-id")
    result.add_argument("paths", nargs="*")
    return result


def require_confirmation(args: argparse.Namespace) -> None:
    if not args.confirm:
        raise FlowGuardError(f"{args.action} requires explicit --confirm")
    if args.action in {"deploy-production", "rollback"} and not (
        args.onno_approval_id or ""
    ).strip():
        raise FlowGuardError(
            f"{args.action} requires --onno-approval-id for this exact operation"
        )


def main() -> int:
    args = parser().parse_args()
    if args.action == "verify":
        verify()
        return 0
    if args.action in {"lint", "test", "typecheck"}:
        checks(args.action)
        return 0

    require_confirmation(args)

    if args.action == "commit":
        require_feature_branch()
        if not (args.message or "").strip():
            raise FlowGuardError("commit requires --message")
        if not args.paths:
            raise FlowGuardError("commit requires explicit file paths")
        verify()
        paths = [validate_commit_path(path) for path in args.paths]
        require_clean_index()
        for path in paths:
            run(["git", "add", "--", path])
        verify_staged_scope(paths)
        run_staged_secret_scan()
        validate_post_commit_hook()
        environment = os.environ.copy()
        environment["SKIP_AUTO_PUSH"] = "1"
        run(["git", "commit", "-m", args.message], env=environment)
    elif args.action == "push":
        branch = require_feature_branch()
        verify()
        run(["git", "push", "--set-upstream", "origin", branch])
    elif args.action == "pr":
        require_feature_branch()
        verify()
        gh = executable("gh")
        if not gh:
            raise FlowGuardError("GitHub CLI is required for draft PR creation")
        command = ["gh", "pr", "create", "--draft", "--title", args.title or "Draft change", "--fill"]
        command[0] = gh
        run(command)
    elif args.action == "deploy-staging":
        raise FlowGuardError(
            "no direct staging command is configured; use the documented guarded delivery path"
        )
    elif args.action in {"deploy-production", "rollback"}:
        raise FlowGuardError(
            f"{args.action} is intentionally unavailable; follow the reviewed runbook"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FlowGuardError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
