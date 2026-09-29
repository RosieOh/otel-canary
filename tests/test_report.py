import html
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


def test_main_breakage_links_the_commits_since_the_previous_run():
    def main_result(status, core, contrib):
        result = _result(label="main", status=status)
        result["cell"].update(otel="main", mode="force", core_ref=core, contrib_ref=contrib)
        return result

    previous = [main_result("PASS", "a" * 40, "b" * 40)]
    current = [main_result("FAIL", "c" * 40, "b" * 40)]

    [change] = report.changes(previous, current, "2026-09-29")

    assert change["kind"] == "broke"
    assert f"opentelemetry-python/compare/{'a' * 40}...{'c' * 40}" in change["body"]
    assert "contrib changes" not in change["body"]  # contrib didn't move
    assert f"--otel main --transport http --core-ref {'c' * 40}" in change["body"]


def test_a_cell_new_to_the_matrix_sets_its_baseline():
    previous = [_result(status="PASS")]
    current = [_result(status="PASS"), _result(label="main", status="FAIL")]

    [change] = report.changes(previous, current, "2026-09-29")

    assert (change["key"], change["kind"], change["from"]) == ("phoenix:http:main", "info", None)


def test_long_reasons_are_shortened_in_the_table_but_kept_in_details():
    long_reason = "Because " + "some-package>=1.0 depends on another-package " * 10 + "unsatisfiable."
    page = report.render_html([_result(status="BLOCKED", reason=long_reason)], [], "now")

    assert page.count(html.escape(long_reason)) == 1  # only inside the details
    assert "…" in page
