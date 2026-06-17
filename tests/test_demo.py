"""The `demo` command runs on the bundled spec with no external files."""

from __future__ import annotations

from importlib.resources import files

from mcp_curate.cli import main


def test_bundled_spec_is_packaged():
    resource = files("mcp_curate.data").joinpath("petstore.json")
    assert resource.is_file()


def test_demo_command_runs(capsys):
    rc = main(["demo"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Curation report" in out
    assert "curated tools: 3" in out
