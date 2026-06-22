"""SOMA MCP — a reference implementation of a private, self-hosted MCP server.

`server`/`build_server`/`main` are imported lazily so the engine and kernel (and
their tests) can be used without FastMCP installed.
"""

from .engine import Engine, InMemoryEngine
from .kernel import Kernel

__all__ = ["Engine", "InMemoryEngine", "Kernel", "build_server", "main"]
__version__ = "0.1.0"


def __getattr__(name):  # PEP 562 lazy import — avoids importing FastMCP eagerly
    if name in ("build_server", "main"):
        from . import server
        return getattr(server, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
