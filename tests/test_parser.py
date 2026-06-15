"""Parser tests: YAML/JSON, $ref resolution, cycles, synthesized ids."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_curate.parser.loader import SpecError, load_spec

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLES = Path(__file__).parent.parent / "examples"


def test_loads_yaml_and_basic_fields():
    spec = load_spec(FIXTURES / "mini.yaml")
    assert spec.title == "Mini API"
    assert spec.version == "2.1.0"
    assert spec.base_url == "https://api.example.com/v2"
    assert len(spec.endpoints) == 3


def test_synthesizes_missing_operation_id():
    spec = load_spec(FIXTURES / "mini.yaml")
    post = next(e for e in spec.endpoints if e.method == "post")
    assert post.operation_id  # non-empty
    assert "widgets" in post.operation_id


def test_path_level_parameters_are_merged_into_operations():
    spec = load_spec(FIXTURES / "mini.yaml")
    list_widgets = next(e for e in spec.endpoints if e.operation_id == "listWidgets")
    names = {p.name for p in list_widgets.parameters}
    assert {"tenant", "limit"} <= names


def test_ref_resolution_with_cycle_terminates():
    spec = load_spec(FIXTURES / "mini.yaml")
    post = next(e for e in spec.endpoints if e.method == "post")
    body = post.request_body
    assert body is not None
    assert body["properties"]["name"] == {"type": "string"}
    # The self-referential `parent` is cut to an empty schema, not infinite.
    assert body["properties"]["parent"] == {}


def test_petstore_json_loads():
    spec = load_spec(EXAMPLES / "petstore.json")
    assert len(spec.endpoints) == 19


def test_rejects_non_openapi_3():
    bad = FIXTURES / "swagger2.json"
    bad.write_text('{"swagger": "2.0", "info": {}, "paths": {}}')
    try:
        with pytest.raises(SpecError):
            load_spec(bad)
    finally:
        bad.unlink()


def test_missing_file_raises():
    with pytest.raises(SpecError):
        load_spec(FIXTURES / "does-not-exist.yaml")
