#!/usr/bin/env python3
"""Assert that the installed versions equal the floors pyproject.toml declares.

    python tools/check_floors.py

Run in the dependency-floor CI job after `uv pip install --resolution
lowest-direct`: printing the resolved versions is not proof, a mismatch must
fail. Covers the runtime dependencies and the `auth` extra. Standard library
only and Python 3.10 compatible (no tomllib), so it parses the two dependency
arrays with a regular expression.
"""

from __future__ import annotations

import importlib.metadata
import re
import sys
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"
ARRAY = re.compile(r"^(?:dependencies|auth) = \[(.*?)^\]", re.M | re.S)
FLOOR = re.compile(r'"([A-Za-z0-9_.-]+)(?:\[[^\]]*\])?\s*>=\s*([0-9][^,";\s]*)')


def declared_floors(pyproject: Path = PYPROJECT) -> dict[str, str]:
    text = pyproject.read_text(encoding="utf-8")
    floors: dict[str, str] = {}
    for array in ARRAY.findall(text):
        for name, version in FLOOR.findall(array):
            floors[name] = version
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


def main() -> int:
    floors = declared_floors()
    if not floors:
        print(f"no dependency floors found in {PYPROJECT}", file=sys.stderr)
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
