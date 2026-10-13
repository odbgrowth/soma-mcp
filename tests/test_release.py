"""
Version contract and release tooling: package metadata, soma_mcp.__version__,
the advertised MCP serverInfo.version (see test_transport.py), the changelog and
the release tag must all agree. Also covers the `soma-mcp` console entry point.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import logging
import sys
from pathlib import Path
from types import ModuleType

import pytest
from fastmcp import FastMCP

import soma_mcp
from soma_mcp import server

ROOT = Path(__file__).resolve().parents[1]


def _load_check_release() -> ModuleType:
    path = ROOT / "tools" / "check_release.py"
    spec = importlib.util.spec_from_file_location("check_release", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_release"] = module
    spec.loader.exec_module(module)
    return module


check_release = _load_check_release()


def test_installed_metadata_matches_dunder_version():
    try:
        installed = importlib.metadata.version("soma-mcp")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("soma-mcp is not installed (run `pip install -e .`)")
    assert installed == soma_mcp.__version__


def test_pyproject_reads_the_single_version_source():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'dynamic = ["version"]' in pyproject
    assert 'version = { attr = "soma_mcp.__version__" }' in pyproject
    assert check_release.package_version() == soma_mcp.__version__


def test_version_is_semver_with_a_dated_changelog_section():
    check_release.check_version(soma_mcp.__version__)
    assert check_release.changelog_section(soma_mcp.__version__)
    assert check_release.main([]) == 0


def test_tag_must_be_v_plus_version():
    check_release.check_tag("0.2.0", "v0.2.0")
    for bad in ("0.2.0", "v0.2", "release-0.2", "latest", "v0.2.1"):
        with pytest.raises(check_release.ReleaseCheckError):
            check_release.check_tag("0.2.0", bad)
    assert check_release.main(["--tag", "v9.9.9"]) == 1


@pytest.mark.parametrize("version", ["0.2", "v0.2.0", "0.2.0rc1", "01.2.3", "1.2.3.4"])
def test_non_semver_versions_are_rejected(version):
    with pytest.raises(check_release.ReleaseCheckError):
        check_release.check_version(version)


def test_changelog_section_rules(tmp_path):
    changelog = Path(tmp_path) / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## [Unreleased]\n\n## [1.0.0] - YYYY-MM-DD\n\n- x\n")
    with pytest.raises(check_release.ReleaseCheckError, match="ISO date"):
        check_release.changelog_section("1.0.0", changelog)
    changelog.write_text("## [1.0.0] - 2026-10-13\n\n## [0.9.0] - 2026-01-01\n- old\n")
    with pytest.raises(check_release.ReleaseCheckError, match="empty"):
        check_release.changelog_section("1.0.0", changelog)
    with pytest.raises(check_release.ReleaseCheckError, match=r"no '## \[2\.0\.0\]"):
        check_release.changelog_section("2.0.0", changelog)
    changelog.write_text("## [1.0.0] - 2026-10-13\n### Added\n- new\n\n"
                         "## [0.9.0] - 2026-01-01\n- old\n\n[1.0.0]: https://example/1\n")
    assert check_release.changelog_section("1.0.0", changelog) == "### Added\n- new"


def test_release_notes_are_written_from_the_changelog(tmp_path):
    notes = Path(tmp_path) / "notes.md"
    assert check_release.main(["--tag", f"v{soma_mcp.__version__}", "--notes", str(notes)]) == 0
    assert notes.read_text(encoding="utf-8").strip() == check_release.changelog_section(
        soma_mcp.__version__)


# --- console entry point ---

def test_cli_version_reports_the_whole_stack(capsys):
    with pytest.raises(SystemExit) as exc:
        server.main(["--version"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert out.startswith(f"soma-mcp {soma_mcp.__version__} ")
    assert f"fastmcp {importlib.metadata.version('fastmcp')}" in out
    assert f"mcp {importlib.metadata.version('mcp')}" in out
    assert "protocol 2026-07-28" in out
    assert out.count("\n") == 1  # one line, safe to grep in logs and bug reports


def test_cli_refuses_partial_auth_without_echoing_secrets(monkeypatch):
    monkeypatch.setenv("AUTH0_CLIENT_SECRET", "do-not-print-me")
    with pytest.raises(SystemExit) as exc:
        server.main([])
    message = str(exc.value.code)
    assert "configuration error" in message and "AUTH0_CONFIG_URL" in message
    assert "do-not-print-me" not in message


@pytest.fixture
def captured_run(monkeypatch):
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(FastMCP, "run", lambda self, **kwargs: calls.append(kwargs))
    return calls


def test_cli_unauthenticated_serves_loopback_with_a_strict_guard(captured_run):
    server.main([])
    assert captured_run == [{"transport": "http", "host": "127.0.0.1", "port": 8000,
                             "show_banner": False, "host_origin_protection": True}]


def test_cli_warns_when_unauthenticated_server_is_exposed(monkeypatch, captured_run, caplog):
    monkeypatch.setenv("MCP_HOST", "0.0.0.0")
    monkeypatch.setenv("MCP_PORT", "8123")
    with caplog.at_level(logging.WARNING, logger="soma_mcp"):
        server.main([])
    # Still strict: the guard also covers non-loopback binds without auth.
    assert captured_run == [{"transport": "http", "host": "0.0.0.0", "port": 8123,
                             "show_banner": False, "host_origin_protection": True}]
    assert "UNAUTHENTICATED server bound to 0.0.0.0" in caplog.text


def test_cli_authenticated_binds_all_interfaces_and_defers_the_guard(auth_env, captured_run):
    server.main([])
    assert captured_run == [{"transport": "http", "host": "0.0.0.0", "port": 8000,
                             "show_banner": False, "host_origin_protection": None}]


def test_serve_runs_a_custom_engine_with_the_same_defaults(captured_run, monkeypatch):
    from soma_mcp import InMemoryEngine, serve

    built = []
    original = server.build_server
    monkeypatch.setattr(server, "build_server",
                        lambda engine=None: built.append(engine) or original(engine))
    engine = InMemoryEngine()
    serve(engine)
    assert built == [engine]
    assert captured_run[0]["host"] == "127.0.0.1"
    assert captured_run[0]["host_origin_protection"] is True
