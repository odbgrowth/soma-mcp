#!/usr/bin/env python3
"""Assert that the installed versions equal the floors pyproject.toml declares.

    python tools/check_floors.py

Run in the dependency-floor CI job after `uv pip install --resolution
lowest-direct`: printing the resolved versions is not proof, a mismatch must
fail. Covers the runtime dependencies and the `auth` extra. Standard library
only and Python 3.10 compatible (no tomllib), so it reads the two dependency
arrays itself, and only in the layout pyproject.toml uses: an array over
several lines, one double-quoted requirement per line, comments allowed.
Anything else is an error, so no dependency is ever skipped silently.
"""

from __future__ import annotations

import importlib.metadata
import re
import sys
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"
KEY = re.compile(r"(dependencies|auth)\s*=(.*)")
OPEN = re.compile(r"\s*\[\s*(?:#.*)?")
CLOSE = re.compile(r"\s*\]\s*(?:#.*)?")
BLANK = re.compile(r"\s*(?:#.*)?")
ENTRY = re.compile(r'\s*"((?:[^"\\]|\\.)*)"\s*,?\s*(?:#.*)?')
REQUIREMENT = re.compile(r"\s*([A-Za-z0-9_.-]+)\s*(?:\[[^\]]*\])?\s*([^;]*)")
LOWER = re.compile(r">=\s*([0-9][^,\s]*)")


class FloorError(ValueError):
    """The dependency arrays cannot be read, or an entry has no `>=` floor."""


def _requirements(text: str) -> list[str]:
    """Requirement strings of the `dependencies` and `auth` arrays."""
    lines = text.splitlines()
    requirements: list[str] = []
    for index, line in enumerate(lines):
        key = KEY.fullmatch(line)
        if key is None:
            continue
        name = key.group(1)
        if OPEN.fullmatch(key.group(2)) is None:
            raise FloorError(
                f"{name}: write the array over several lines, one requirement per line")
        for body in lines[index + 1:]:
            if CLOSE.fullmatch(body):
                break
            if BLANK.fullmatch(body):
                continue
            entry = ENTRY.fullmatch(body)
            if entry is None:
                raise FloorError(f"{name}: unsupported entry {body.strip()!r} "
                                 "(one double-quoted requirement per line)")
            requirements.append(entry.group(1).replace('\\"', '"'))
        else:
            raise FloorError(f"{name}: the array is not closed")
    return requirements


def declared_floors(pyproject: Path = PYPROJECT) -> dict[str, str]:
    """`>=` floors of the runtime dependencies and the `auth` extra, in any
    specifier order. An entry without a floor is an error."""
    floors: dict[str, str] = {}
    missing: list[str] = []
    for requirement in _requirements(pyproject.read_text(encoding="utf-8")):
        match = REQUIREMENT.match(requirement)
        lower = LOWER.search(match.group(2)) if match else None
        if match is None or lower is None:
            missing.append(requirement)
            continue
        floors[match.group(1)] = lower.group(1)
    if missing:
        raise FloorError(f"no >= floor declared for: {', '.join(missing)}")
    return floors


def release(version: str) -> tuple[int, ...]:
    """Numeric release tuple with trailing zeros dropped: 4.1 == 4.1.0."""
    match = re.match(r"\d+(?:\.\d+)*", version)
    if match is None:
        raise ValueError(f"not a release version: {version!r}")
    parts = [int(p) for p in match.group(0).split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def main(pyproject: Path = PYPROJECT) -> int:
    try:
        floors = declared_floors(pyproject)
    except FloorError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    if not floors:
        print(f"no dependency floors found in {pyproject}", file=sys.stderr)
        return 1
    failed = False
    for name, floor in sorted(floors.items()):
        try:
            installed = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            print(f"FAIL {name}: not installed (floor {floor})")
            failed = True
            continue
        ok = release(installed) == release(floor)
        failed |= not ok
        print(f"{'ok  ' if ok else 'FAIL'} {name}: installed {installed}, floor {floor}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
