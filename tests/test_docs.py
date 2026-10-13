"""
Documentation checks: the docs must describe the repository as it is.

* every relative Markdown link and every backticked repository path exists;
* current documents carry no stale claims (old SDK APIs, old repository URLs,
  private hosts, deployment scripts this repository does not have);
* every Python snippet parses and its imports resolve;
* the MCP SDK client example in docs/examples.md runs against a real server.

Historical documents (CHANGELOG.md, docs/upgrading.md, ADRs) may name old
behavior on purpose and are exempt from the stale-claim check only.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

from soma_mcp import server

ROOT = Path(__file__).resolve().parents[1]
MARKDOWN = sorted(
    path for pattern in ("*.md", "docs/**/*.md", ".github/**/*.md")
    for path in ROOT.glob(pattern) if path.is_file()
)
HISTORICAL = {ROOT / "CHANGELOG.md", ROOT / "docs" / "upgrading.md", *ROOT.glob("docs/adr/*.md")}
CURRENT = [path for path in MARKDOWN if path not in HISTORICAL]

LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)")
# A file (`tools/check_release.py`) or a directory (`docs/adr/`); MCP method
# names such as `tools/list` have neither a suffix nor a trailing slash.
REPO_PATH = re.compile(
    r"`((?:src|tests|tools|docs|\.github|\.devflows|\.codex)/(?:[\w.-]+/)*(?:[\w-]+\.\w+)?)`")
PYTHON_BLOCK = re.compile(r"```python\n(.*?)```", re.S)
PLACEHOLDER_MODULES = {"my_stack"}

# Public documentation names only public hosts and placeholders; a private
# deployment's host name fails here without this file having to spell it out.
URL_HOST = re.compile(r"https?://([^/\s)>\"'`]+)")
PUBLIC_HOSTS = {
    "github.com", "modelcontextprotocol.io", "img.shields.io", "semver.org",
    "keepachangelog.com", "docs.pypi.org", "datatracker.ietf.org",
}

STALE = {
    "jlowin/fastmcp": "FastMCP moved to github.com/PrefectHQ/fastmcp",
    "streamablehttp_client": "removed in MCP SDK v2; use mcp.Client",
    "ClientSession(": "MCP SDK v1 client pattern; use mcp.Client",
    "session.initialize()": "MCP SDK v1 client pattern; use mcp.Client",
    "deploy_prod.sh": "no deployment scripts in this public repository",
    "deploy_staging.sh": "no deployment scripts in this public repository",
    "release candidate": "2026-07-28 is the current stable revision",
    "is in draft": "2026-07-28 is the current stable revision",
    "fastmcp>=3": "FastMCP 4 is the supported line",
    "mcp>=1.": "MCP SDK 2 is the supported line",
    "soma_mcp_kern": "the kernel module is src/soma_mcp/kernel.py",
    "_omhein": "the fence function is kernel._fence",
    "MAX_NOTE_TEKENS": "the constant is MAX_NOTE_CHARS",
    "`fout`": "denials use the `error` field",
    "encrypted `DiskStore`": "token storage is an encrypted FileTreeStore",
    "Fernet-encrypted `DiskStore`": "token storage is an encrypted FileTreeStore",
}


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def test_markdown_files_found():
    assert ROOT / "README.md" in MARKDOWN and ROOT / "docs" / "README.md" in MARKDOWN


@pytest.mark.parametrize("doc", MARKDOWN, ids=_rel)
def test_relative_links_resolve(doc: Path):
    broken = []
    for target in LINK.findall(doc.read_text(encoding="utf-8")):
        if re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith("#"):
            continue  # external URL or same-page anchor
        if not (doc.parent / target.split("#", 1)[0]).exists():
            broken.append(target)
    assert not broken, f"{_rel(doc)} links to missing files: {broken}"


@pytest.mark.parametrize("doc", MARKDOWN, ids=_rel)
def test_backticked_repository_paths_exist(doc: Path):
    paths = [p for p in REPO_PATH.findall(doc.read_text(encoding="utf-8"))
             if p.endswith("/") or "." in p.rsplit("/", 1)[-1]]
    missing = [p for p in paths if not (ROOT / p).exists()]
    assert not missing, f"{_rel(doc)} names files that do not exist: {missing}"


@pytest.mark.parametrize("doc", CURRENT, ids=_rel)
def test_no_stale_claims(doc: Path):
    text = doc.read_text(encoding="utf-8")
    found = {needle: why for needle, why in STALE.items() if needle in text}
    assert not found, f"{_rel(doc)} contains stale statements: {found}"


@pytest.mark.parametrize("doc", [*CURRENT, ROOT / ".env.example"], ids=_rel)
def test_only_public_hosts_and_placeholders(doc: Path):
    hosts = set(URL_HOST.findall(doc.read_text(encoding="utf-8")))
    private = {host for host in hosts
               if host.split(":")[0] not in PUBLIC_HOSTS | {"127.0.0.1", "localhost"}
               and not host.startswith("<") and not host.endswith(".example")}
    assert not private, f"{_rel(doc)} names non-public hosts: {sorted(private)}"


def _python_blocks() -> list[tuple[str, int, str]]:
    blocks = []
    for doc in MARKDOWN:
        for index, code in enumerate(PYTHON_BLOCK.findall(doc.read_text(encoding="utf-8"))):
            blocks.append((_rel(doc), index, code))
    return blocks


@pytest.mark.parametrize(("doc", "index", "code"), _python_blocks(),
                         ids=lambda value: str(value) if not isinstance(value, str)
                         or "\n" not in value else "code")
def test_python_snippets_parse_and_import(doc: str, index: int, code: str):
    tree = ast.parse(code, filename=f"{doc}[{index}]")
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            module = node.module
            if module.split(".")[0] in PLACEHOLDER_MODULES:
                continue
            loaded = importlib.import_module(module)
            for alias in node.names:
                assert hasattr(loaded, alias.name), f"{doc}: {module} has no {alias.name}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in PLACEHOLDER_MODULES:
                    spec = importlib.util.find_spec(alias.name)
                    assert spec is not None, f"{doc}: cannot import {alias.name}"


@pytest.mark.integration
def test_sdk_client_example_runs_against_a_real_server(monkeypatch, serve_http, tmp_path):
    examples = (ROOT / "docs" / "examples.md").read_text(encoding="utf-8")
    [code] = [block for block in PYTHON_BLOCK.findall(examples) if "SOMA_MCP_URL" in block]
    script = Path(tmp_path) / "client_example.py"
    script.write_text(code, encoding="utf-8")

    monkeypatch.setenv("MCP_SINGLE_USER", "1")
    monkeypatch.setenv("MCP_RATE_LIMIT", "0")
    http = serve_http(server.build_server())
    result = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True, timeout=120,
        env={"SOMA_MCP_URL": http.url, "PATH": "", "SYSTEMROOT": ""}, check=False)
    assert result.returncode == 0, result.stderr
    assert "protocol: 2026-07-28" in result.stdout
    assert "soma_context" in result.stdout
    assert "unauthenticated reference server" in result.stdout
