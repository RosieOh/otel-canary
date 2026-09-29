import json

from otel_canary import report


def _result(adapter="phoenix", transport="http", label="latest", status="PASS", reason="1 span(s) received"):
    return {
        "cell": {
            "adapter": adapter,
            "sdk": "arize-phoenix-otel==0.17.2",
            "otel": "1.45.0",
            "transport": transport,
            "label": label,
        },
        "status": status,
        "reason": reason,
        "versions": {"arize-phoenix-otel": "0.17.2", "opentelemetry-sdk": "1.45.0"},
        "logs": {"adapter": "Traceback ...\nAttributeError: boom"},
    }


def test_first_run_has_no_alerts():
    assert report.changes([], [_result(status="FAIL")], "2026-09-29") == []


def test_breakage_and_recovery_are_told_apart():
    previous = [_result(status="PASS"), _result(label="previous", status="FAIL")]
    current = [
        _result(status="FAIL", reason="AttributeError: boom"),
        _result(label="previous", status="PASS"),
    ]

    found = {change["key"]: change for change in report.changes(previous, current, "2026-09-29")}

    broke = found["phoenix:http:latest"]
    assert broke["kind"] == "broke"
    assert broke["title"] == "canary: phoenix (http) with OpenTelemetry latest"
    assert "AttributeError: boom" in broke["body"]
    assert "uv run otel-canary run --sdk arize-phoenix-otel==0.17.2" in broke["body"]
    assert found["phoenix:http:previous"]["kind"] == "recovered"


def test_other_transitions_are_informational():
    found = report.changes([_result(status="PASS")], [_result(status="BLOCKED")], "2026-09-29")
    assert [change["kind"] for change in found] == ["info"]


def test_badge_shows_the_worst_transport_on_the_latest_release():
    current = [_result(status="PASS"), _result(transport="grpc", status="FAIL"), _result(label="previous")]
    assert report.badges(current)["phoenix"] == {
        "schemaVersion": 1,
        "label": "otel 1.45.0",
        "message": "fail",
        "color": "red",
    }


def test_writes_the_site(tmp_path):
    results = tmp_path / "results"
    results.mkdir()
    (results / "phoenix-http-latest.json").write_text(json.dumps(_result(reason="<script>x</script>")))
    previous = tmp_path / "previous.json"
    previous.write_text(json.dumps([_result(status="FAIL")]))

    summary = report.write_report(results, previous, tmp_path / "site")

    assert summary["statuses"] == {"PASS": 1}
    assert summary["changes"] == [("recovered", "phoenix:http:latest")]
    page = (tmp_path / "site" / "index.html").read_text()
    assert "&lt;script&gt;" in page and "<script>x" not in page
    assert json.loads((tmp_path / "site" / "badges" / "phoenix.json").read_text())["message"] == "pass"
