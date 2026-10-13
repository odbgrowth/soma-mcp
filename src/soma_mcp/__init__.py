"""SOMA MCP: a reference implementation of a private, self-hosted MCP server.

Supported public API: `Engine`, `InMemoryEngine`, `Kernel`, `build_server`,
`serve`, `main` and `__version__`. Everything else is internal and may change
between minor releases.

`server`, `build_server`, `serve` and `main` are imported lazily so the engine
and kernel (and their tests) can be used without FastMCP installed.
"""

from typing import Any

from .engine import Engine, InMemoryEngine
from .kernel import Kernel

__all__ = ["Engine", "InMemoryEngine", "Kernel", "__version__", "build_server", "main", "serve"]

# The single version source: pyproject.toml reads it (setuptools dynamic
# version), the MCP server advertises it as serverInfo.version, and release tags
# must be exactly f"v{__version__}" (tools/check_release.py enforces that).
__version__ = "0.2.0"


def __getattr__(name: str) -> Any:  # PEP 562 lazy import, avoids importing FastMCP eagerly
    if name in ("build_server", "main", "serve"):
        from . import server

        return getattr(server, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
