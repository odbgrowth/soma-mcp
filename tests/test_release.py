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


def _load_tool(name: str) -> ModuleType:
    path = ROOT / "tools" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


check_release = _load_tool("check_release")
check_floors = _load_tool("check_floors")


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
    tag = f"v{soma_mcp.__version__}"
    assert check_release.main(["--tag", tag, "--notes", str(notes)]) == 0
    assert notes.read_text(encoding="utf-8").strip() == check_release.changelog_section(
        soma_mcp.__version__)
    base = f"https://example.invalid/blob/{tag}/"
    assert check_release.main(["--tag", tag, "--notes", str(notes), "--link-base", base]) == 0
    written = notes.read_text(encoding="utf-8")
    assert f"]({base}docs/upgrading.md)" in written
    assert "](docs/" not in written


def test_link_base_without_notes_is_an_error(capsys):
    with pytest.raises(SystemExit) as exc:
        check_release.main(["--link-base", "https://example.invalid/"])
    assert exc.value.code == 2
    assert "--link-base needs --notes" in capsys.readouterr().err


def test_release_notes_links_point_at_the_tag():
    base = "https://github.com/odbgrowth/soma-mcp/blob/v0.2.0/"
    notes = ("See [upgrading](docs/upgrading.md), [runbook](./RELEASE.md#10-rollback), "
             "[spec](https://modelcontextprotocol.io), [top](#security) and [abs](/x).")
    assert check_release.absolute_links(notes, base) == (
        f"See [upgrading]({base}docs/upgrading.md), [runbook]({base}RELEASE.md#10-rollback), "
        "[spec](https://modelcontextprotocol.io), [top](#security) and [abs](/x).")
    real = check_release.absolute_links(
        check_release.changelog_section(soma_mcp.__version__), base)
    assert "](docs/" not in real and "](RELEASE.md" not in real and "](CHANGELOG.md" not in real


def test_declared_floors_are_read_from_pyproject():
    floors = check_floors.declared_floors()
    assert floors == {"cryptography": "50", "fastmcp": "4.1", "mcp": "2.3",
                      "py-key-value-aio": "0.4.4"}
    assert check_floors.release("4.1") == check_floors.release("4.1.0") == (4, 1)
    assert check_floors.release("50.0.2") != check_floors.release("50")


def _pyproject(tmp_path: Path, dependencies: str, auth: str = "") -> Path:
    path = Path(tmp_path) / "pyproject.toml"
    path.write_text(f"[project]\ndependencies = [\n{dependencies}\n]\n\n"
                    f"[project.optional-dependencies]\nauth = [\n{auth}\n]\n", encoding="utf-8")
    return path


def test_floors_are_found_in_any_specifier_order_and_comments_are_ignored(tmp_path):
    pyproject = _pyproject(
        tmp_path,
        '    "fastmcp<5,>=4.1",  # note "x>=9"\n    # "oldpkg>=1.0",\n    "mcp >= 2.3, < 3",',
        '    "py-key-value-aio[filetree]>=0.4.4,<0.5; python_version >= \'3.10\'",')
    assert check_floors.declared_floors(pyproject) == {
        "fastmcp": "4.1", "mcp": "2.3", "py-key-value-aio": "0.4.4"}


@pytest.mark.parametrize("requirement", ['"fastmcp~=4.1"', '"mcp==2.3.0"', '"cryptography"'])
def test_a_dependency_without_a_floor_fails(tmp_path, requirement, capsys):
    pyproject = _pyproject(tmp_path, f'    "mcp>=2.3,<3",\n    {requirement},')
    with pytest.raises(check_floors.FloorError, match="no >= floor"):
        check_floors.declared_floors(pyproject)
    assert check_floors.main(pyproject) == 1
    assert requirement.strip('"') in capsys.readouterr().err


def test_floor_check_fails_on_a_mismatch_or_a_missing_package(tmp_path, monkeypatch, capsys):
    pyproject = _pyproject(tmp_path, '    "fastmcp>=4.1,<5",', '    "mcp>=2.3,<3",')
    installed = {"fastmcp": "4.1.0", "mcp": "2.3"}

    def version(name):
        if name not in installed:
            raise importlib.metadata.PackageNotFoundError(name)
        return installed[name]

    monkeypatch.setattr(check_floors.importlib.metadata, "version", version)
    assert check_floors.main(pyproject) == 0  # 4.1.0 is the floor 4.1
    installed["fastmcp"] = "4.2.0"
    assert check_floors.main(pyproject) == 1
    assert "FAIL fastmcp: installed 4.2.0, floor 4.1" in capsys.readouterr().out
    installed["fastmcp"] = "4.1"
    del installed["mcp"]
    assert check_floors.main(pyproject) == 1
    assert "FAIL mcp: not installed (floor 2.3)" in capsys.readouterr().out
    assert check_floors.main(_pyproject(tmp_path, "")) == 1
    assert "no dependency floors found" in capsys.readouterr().err


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
