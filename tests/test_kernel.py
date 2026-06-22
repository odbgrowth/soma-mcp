"""
Tests for the FastMCP-free kernel, over the in-memory reference engine.

These mirror SOMA's production approach: the security-critical logic (fail-closed
guards, the data-boundary fence, the two-step delete, size caps) is covered
without standing up an auth environment.
"""

import importlib

import pytest

from soma_mcp.engine import InMemoryEngine
from soma_mcp.kernel import Kernel, _DATA_BOUNDARY


@pytest.fixture
def single_user(monkeypatch):
    """A kernel in deliberate single-user mode (no allowlist needed)."""
    monkeypatch.setenv("MCP_SINGLE_USER", "1")
    monkeypatch.setenv("MCP_RATE_LIMIT", "0")  # disable rate limit for determinism
    # Reset the guard's module-level call window between tests.
    import soma_mcp.guard as guard
    importlib.reload(guard)
    return Kernel(InMemoryEngine())


def test_fail_closed_without_allowlist(monkeypatch):
    """No allowlist and MCP_SINGLE_USER off -> every read is denied."""
    monkeypatch.delenv("MCP_SINGLE_USER", raising=False)
    monkeypatch.delenv("MCP_TOEGANG_SUBJECTS", raising=False)
    monkeypatch.setenv("MCP_RATE_LIMIT", "0")
    k = Kernel(InMemoryEngine())
    out = k.search("anyone", "hello")
    assert isinstance(out, list) and "error" in out[0]


def test_search_is_fenced(single_user):
    single_user.write("subj", "the sky is blue")
    out = single_user.search("subj", "sky")
    assert out and out[0]["tekst"].startswith(_DATA_BOUNDARY)


def test_write_size_cap(single_user):
    out = single_user.write("subj", "x" * 25_001)
    assert "error" in out and "too long" in out["error"]


def test_update_requires_note_prefix(single_user):
    out = single_user.update("subj", "chunk-123", "new")
    assert out["error"].startswith("only notes")


def test_delete_two_step(single_user):
    single_user.write("subj", "delete me")
    # find the note's base id via search metadata is engine-specific; use the
    # known reference id scheme.
    base_id = "note-ref-0001"
    preview = single_user.delete("subj", base_id)
    assert "preview" in preview and "status" not in preview
    confirmed = single_user.delete("subj", base_id, confirm=True)
    assert confirmed["status"] == "deleted"


def test_feedback_verdict_validation(single_user):
    bad = single_user.feedback("subj", "q", "maybe")
    assert "error" in bad
    good = single_user.feedback("subj", "q", "yes")
    assert good["status"] == "logged"
