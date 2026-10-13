#!/usr/bin/env python3
"""Smoke-test an *installed* soma-mcp (a built wheel in a clean virtualenv).

    python -I tools/smoke_test.py [--expect-version 0.2.0]

Run it with the interpreter of the clean environment and `-I`, so the package is
imported from site-packages and never from the source tree; editable installs
hide packaging mistakes (missing modules, missing py.typed, broken entry point).
Exercises: import, version contract, server construction, the in-memory MCP
round trip on both protocol eras, and the `soma-mcp --version` console script.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path


class SmokeTestError(Exception):
    """The installed package does not behave like the released one must."""


def _require(condition: bool, message: str) -> None:
    # Explicit checks rather than `assert`, which `python -O` would strip.
    if not condition:
        raise SmokeTestError(message)


async def _round_trip(expected_version: str) -> None:
    from fastmcp import Client

    from soma_mcp import build_server

    for mode in ("auto", "legacy"):
        async with Client(build_server(), mode=mode) as client:
            info = client.server_info
            _require(info is not None and info.version == expected_version,
                     f"{mode}: serverInfo {info!r} does not advertise {expected_version}")
            tools = {tool.name for tool in await client.list_tools()}
            _require(len(tools) == 9 and "soma_whoami" in tools, f"{mode}: tools {tools}")
            result = await client.call_tool("soma_whoami", {})
            _require(result.structured_content == {
                "subject": None, "note": "unauthenticated reference server"},
                f"{mode}: soma_whoami returned {result!r}")
            print(f"ok: {mode} -> protocol {client.protocol_version}, {len(tools)} tools")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--expect-version", help="fail unless soma_mcp.__version__ equals this")
    args = parser.parse_args()

    import soma_mcp

    location = Path(soma_mcp.__file__).resolve()
    if "site-packages" not in location.parts:
        print(f"smoke test must import an installed package, got {location}", file=sys.stderr)
        return 1
    if args.expect_version and soma_mcp.__version__ != args.expect_version:
        print(f"version {soma_mcp.__version__} != expected {args.expect_version}",
              file=sys.stderr)
        return 1
    if not (location.parent / "py.typed").is_file():
        print("py.typed missing from the installed package", file=sys.stderr)
        return 1
    print(f"ok: imported soma_mcp {soma_mcp.__version__} from {location.parent}")

    os.environ["MCP_SINGLE_USER"] = "1"
    try:
        asyncio.run(_round_trip(soma_mcp.__version__))
    except SmokeTestError as exc:
        print(f"smoke test failed: {exc}", file=sys.stderr)
        return 1

    script = shutil.which("soma-mcp", path=str(Path(sys.executable).parent))
    if script is None:
        print("console script soma-mcp not installed next to the interpreter", file=sys.stderr)
        return 1
    out = subprocess.run([script, "--version"], check=True, capture_output=True, text=True)
    if not out.stdout.startswith(f"soma-mcp {soma_mcp.__version__} "):
        print(f"unexpected --version output: {out.stdout!r}", file=sys.stderr)
        return 1
    print(f"ok: {out.stdout.strip()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
