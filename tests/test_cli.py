import json

import pytest

from otel_canary import cli


def test_parses_requirements():
    assert cli.parse_requirement("arize-phoenix-otel==0.17.1") == ("arize-phoenix-otel", "0.17.1")
    assert cli.parse_requirement("langfuse") == ("langfuse", None)
    with pytest.raises(ValueError):
        cli.parse_requirement("langfuse>=4")


def test_unknown_sdk_is_a_usage_error(capsys):
    assert cli.main(["run", "--sdk", "not-an-sdk==1.0", "--otel", "1.45.0"]) == cli.EXIT_USAGE
    assert "no adapter" in capsys.readouterr().err


def test_exit_code_follows_the_status(monkeypatch, tmp_path):
    seen = {}

    def fake_run_cell(cell, timeout):
        seen["cell"] = cell
        return {"status": "FAIL", "reason": "AttributeError: ..."}

    monkeypatch.setattr(cli, "run_cell", fake_run_cell)
    output = tmp_path / "result.json"

    code = cli.main(
        ["run", "--sdk", "arize-phoenix-otel==0.17.1", "--otel", "1.45.0", "--output", str(output)]
    )

    assert code == cli.EXIT_CODES["FAIL"]
    assert seen["cell"].adapter == "phoenix"
    assert seen["cell"].otel == "1.45.0"
    assert json.loads(output.read_text())["status"] == "FAIL"
