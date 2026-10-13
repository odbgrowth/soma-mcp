"""
Tests for instructions.py: the drift guard between the tools registered in
server.py and the server instructions / annotations declared alongside them.

If a tool is added to server.py without a matching entry in GROUPS/ANNOTATIONS
(or a mention in TEXT), these tests fail loudly and point at instructions.py.
"""

import asyncio
import hashlib
import re

import pytest
from mcp.types import ToolAnnotations

from soma_mcp.instructions import ANNOTATIONS, GROUPS, TEXT, VERSION, build_instructions

ALL_GROUP_TOOLS = set().union(*GROUPS.values())

READ_ONLY_TOOLS = {"soma_search", "soma_get", "soma_debug", "soma_context", "soma_whoami"}
DESTRUCTIVE_TOOLS = {"soma_update", "soma_delete"}


def _registered_tools():
    """Tools FastMCP actually registers, built without an auth env."""
    from soma_mcp.server import build_server

    mcp = build_server()
    return asyncio.run(mcp.list_tools())


def _registered_tool_names() -> set[str]:
    return {t.name for t in _registered_tools()}


def test_groups_cover_exactly_the_registered_tools():
    registered = _registered_tool_names()
    assert registered == ALL_GROUP_TOOLS, (
        f"tools registered in server.py ({sorted(registered)}) do not match "
        f"GROUPS in instructions.py ({sorted(ALL_GROUP_TOOLS)}) -- update "
        "src/soma_mcp/instructions.py"
    )


def test_annotations_cover_exactly_the_registered_tools():
    registered = _registered_tool_names()
    assert registered == set(ANNOTATIONS), (
        f"tools registered in server.py ({sorted(registered)}) do not match "
        f"ANNOTATIONS keys in instructions.py ({sorted(ANNOTATIONS)}) -- update "
        "src/soma_mcp/instructions.py"
    )


def test_groups_and_annotations_agree():
    assert ALL_GROUP_TOOLS == set(ANNOTATIONS)


@pytest.mark.parametrize("tool", sorted(ALL_GROUP_TOOLS))
def test_every_tool_named_as_a_whole_word_in_text(tool):
    assert re.search(rf"\b{re.escape(tool)}\b", TEXT), (
        f"{tool} is not mentioned in instructions.TEXT -- update it in "
        "src/soma_mcp/instructions.py"
    )


def test_every_soma_name_in_text_is_a_real_tool():
    mentioned = set(re.findall(r"soma_[a-z_]+", TEXT))
    unknown = mentioned - ALL_GROUP_TOOLS
    assert not unknown, f"TEXT mentions unknown tool name(s): {sorted(unknown)}"


def test_text_length_bound():
    assert len(TEXT) <= 2500


def test_build_instructions_is_deterministic():
    assert build_instructions() == build_instructions() == TEXT


def test_version_matches_text_hash():
    assert VERSION == hashlib.sha256(TEXT.encode("utf-8")).hexdigest()[:12]


def test_read_only_hint_true_for_exactly_the_read_tools():
    read_only = {t for t, a in ANNOTATIONS.items() if a.read_only_hint}
    assert read_only == READ_ONLY_TOOLS


def test_destructive_hint_true_for_exactly_update_and_delete():
    destructive = {t for t, a in ANNOTATIONS.items() if a.destructive_hint}
    assert destructive == DESTRUCTIVE_TOOLS


WIRE_HINT_KEYS = {"readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint"}


def _wire_hints(annotations: ToolAnnotations) -> dict[str, bool]:
    """The four hints exactly as they serialize onto the MCP wire (camelCase)."""
    dumped = annotations.model_dump(by_alias=True, exclude_none=True, mode="json")
    return {k: v for k, v in dumped.items() if k in WIRE_HINT_KEYS}


@pytest.mark.parametrize("tool", sorted(ANNOTATIONS))
def test_every_hint_is_explicit_and_serializes_camelcase(tool):
    annotations = ANNOTATIONS[tool]
    assert isinstance(annotations, ToolAnnotations)
    hints = _wire_hints(annotations)
    assert set(hints) == WIRE_HINT_KEYS, f"{tool} leaves a hint to its default"
    assert hints["readOnlyHint"] is annotations.read_only_hint
    assert hints["destructiveHint"] is annotations.destructive_hint
    assert hints["idempotentHint"] is annotations.idempotent_hint
    assert hints["openWorldHint"] is annotations.open_world_hint is False


def test_server_instructions_and_tool_annotations_match(monkeypatch):
    """Build the real server (no auth env needed) and check both surfaces."""
    monkeypatch.setenv("MCP_SINGLE_USER", "1")
    from soma_mcp.server import build_server

    mcp = build_server()
    assert mcp.instructions == build_instructions()

    by_name = {t.name: t.annotations for t in _registered_tools()}
    assert set(by_name) == set(ANNOTATIONS)
    for name, expected in ANNOTATIONS.items():
        actual = by_name[name]
        assert actual is not None, f"{name} has no annotations"
        assert _wire_hints(actual) == _wire_hints(expected)
