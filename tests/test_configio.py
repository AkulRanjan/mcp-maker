import json

import pytest

from mcpmaker.configio import ConfigError, MissingEnvVar, load_json, render_value, write_json_atomic


def test_load_missing_or_empty_is_empty(tmp_path):
    assert load_json(tmp_path / "nope.json") == {}
    (tmp_path / "empty.json").write_text("  \n", encoding="utf-8")
    assert load_json(tmp_path / "empty.json") == {}


def test_load_malformed_reports_location(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text('{\n  "a": 1,\n  // comment\n}', encoding="utf-8")
    with pytest.raises(ConfigError, match=r"line 3, column 3"):
        load_json(p)


def test_load_rejects_non_object(tmp_path):
    p = tmp_path / "list.json"
    p.write_text("[]", encoding="utf-8")
    with pytest.raises(ConfigError, match="JSON object"):
        load_json(p)


def test_load_accepts_utf8_bom(tmp_path):
    p = tmp_path / "bom.json"
    p.write_bytes(b'\xef\xbb\xbf{"a": 1}')
    assert load_json(p) == {"a": 1}


def test_write_creates_parents_and_backs_up_previous(tmp_path):
    p = tmp_path / "deep" / "cfg.json"
    assert write_json_atomic(p, {"v": 1}) is None
    backup = write_json_atomic(p, {"v": 2})
    assert json.loads(p.read_text(encoding="utf-8")) == {"v": 2}
    assert json.loads(backup.read_text(encoding="utf-8")) == {"v": 1}
    assert backup.name == "cfg.json.bak"
    assert [f.name for f in p.parent.iterdir() if f.name.endswith(".tmp")] == []


def test_render_env_style():
    assert render_value("Bearer ${API_TOKEN}", "env") == ("Bearer ${env:API_TOKEN}", False)


def test_render_keep_style():
    assert render_value("Bearer ${API_TOKEN}", "keep") == ("Bearer ${API_TOKEN}", False)


def test_render_literal_expands(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "t0k")
    assert render_value("Bearer ${API_TOKEN}", "literal") == ("Bearer t0k", True)
    assert render_value("Bearer plain", "literal") == ("Bearer plain", False)


def test_render_literal_missing_var(monkeypatch):
    monkeypatch.delenv("NOPE_TOKEN", raising=False)
    with pytest.raises(MissingEnvVar, match="NOPE_TOKEN"):
        render_value("Bearer ${NOPE_TOKEN}", "literal")


def test_load_undecodable_bytes_raise_config_error(tmp_path):
    path = tmp_path / "mcp.json"
    path.write_bytes("{}".encode("utf-16"))
    with pytest.raises(ConfigError, match="cannot read"):
        load_json(path)
