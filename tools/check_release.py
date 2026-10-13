#!/usr/bin/env python3
"""Release consistency check: version, tag and changelog must agree.

    python tools/check_release.py                      # CI: version + changelog
    python tools/check_release.py --tag v0.2.0         # release: tag == v{version}
    python tools/check_release.py --notes notes.md     # write this version's notes
    python tools/check_release.py --notes notes.md --link-base URL
                                       # ... with repository-relative links made absolute

The version is read from src/soma_mcp/__init__.py without importing the package
(the same literal setuptools reads), so the check runs before any install.
Standard library only.
"""

from __future__ import annotations

import argparse
import ast
import datetime
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INIT = ROOT / "src" / "soma_mcp" / "__init__.py"
CHANGELOG = ROOT / "CHANGELOG.md"
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
# A Markdown link target that is relative to the repository root: no URL scheme,
# no same-page anchor, no absolute path.
RELATIVE_LINK = re.compile(r"\]\((?![a-zA-Z][a-zA-Z0-9+.-]*:|#|/)([^)\s]+)\)")


class ReleaseCheckError(Exception):
    """The repository is not in a releasable state."""


def package_version(init: Path = INIT) -> str:
    """Return the literal assigned to __version__ in the package __init__."""
    for node in ast.parse(init.read_text(encoding="utf-8")).body:
        if (isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "__version__" for t in node.targets)
                and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
            return node.value.value
    raise ReleaseCheckError(f"no literal __version__ assignment in {init}")


def check_version(version: str) -> None:
    if not SEMVER.match(version):
        raise ReleaseCheckError(
            f"version {version!r} is not a stable semantic version (MAJOR.MINOR.PATCH)")


def check_tag(version: str, tag: str) -> None:
    if tag != f"v{version}":
        raise ReleaseCheckError(
            f"tag {tag!r} does not match package version: expected 'v{version}'")


def changelog_section(version: str, changelog: Path = CHANGELOG) -> str:
    """Return the body of `## [version] - YYYY-MM-DD`, validating the heading."""
    if not changelog.is_file():
        raise ReleaseCheckError(f"{changelog.name} not found")
    text = changelog.read_text(encoding="utf-8")
    heading = re.compile(rf"^## \[{re.escape(version)}\] - (?P<date>\S+)[ \t]*$", re.M)
    match = heading.search(text)
    if match is None:
        raise ReleaseCheckError(
            f"CHANGELOG.md has no '## [{version}] - YYYY-MM-DD' section")
    try:
        datetime.date.fromisoformat(match["date"])
    except ValueError:
        raise ReleaseCheckError(
            f"CHANGELOG.md section for {version} has no valid ISO date: {match['date']!r}"
        ) from None
    following = re.compile(r"^## \[", re.M).search(text, match.end())
    body = text[match.end():following.start() if following else len(text)].strip()
    # Keep-a-Changelog link references at the bottom are not release notes.
    body = re.sub(r"^\[[^\]]+\]: \S+$", "", body, flags=re.M).strip()
    if not body:
        raise ReleaseCheckError(f"CHANGELOG.md section for {version} is empty")
    return body


def absolute_links(markdown: str, base: str) -> str:
    """Point repository-relative links at `base` (for example the tag's tree), so
    they keep working on the GitHub Release page, which resolves them elsewhere."""
    base = base if base.endswith("/") else base + "/"
    return RELATIVE_LINK.sub(lambda m: f"]({base}{m.group(1).removeprefix('./')})", markdown)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tag", help="release tag to validate, e.g. v0.2.0")
    parser.add_argument("--notes", type=Path, help="write the changelog section to this file")
    parser.add_argument("--link-base", help="make repository-relative links in --notes absolute")
    args = parser.parse_args(argv)
    if args.link_base and args.notes is None:
        parser.error("--link-base needs --notes")
    try:
        version = package_version()
        check_version(version)
        if args.tag is not None:
            check_tag(version, args.tag)
        notes = changelog_section(version)
    except ReleaseCheckError as exc:
        print(f"release check failed: {exc}", file=sys.stderr)
        return 1
    if args.notes is not None:
        if args.link_base:
            notes = absolute_links(notes, args.link_base)
        args.notes.write_text(notes + "\n", encoding="utf-8")
    print(f"release check ok: soma-mcp {version}"
          + (f", tag {args.tag}" if args.tag else "") + ", changelog section present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
