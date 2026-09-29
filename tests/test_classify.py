from otel_canary.adapters import AdapterSpec
from otel_canary.classify import AdapterOutcome, Status, classify
from otel_canary.install import InstallOutcome
from otel_canary.receivers import Post, ReceiverLog

SPEC = AdapterSpec(
    name="example",
    package="example-sdk",
    transports=frozenset({"http"}),
    expect_path="/v1/traces",
    expect_headers=("authorization",),
)
INSTALLED = InstallOutcome("ok")
RAN = AdapterOutcome(exit_code=0, report={"ok": True})


def _post(path="/v1/traces", status=200, spans=1, headers=("authorization",)) -> Post:
    return Post(path=path, status=status, spans=spans, headers=list(headers), at=0.1)


def _log(*posts: Post) -> ReceiverLog:
    return ReceiverLog(posts=list(posts))


def test_resolver_conflict_is_blocked():
    install = InstallOutcome("blocked", log="  × No solution found when resolving dependencies:\n  ╰─▶ ...")
    verdict = classify(install, None, None, SPEC)
    assert verdict.status is Status.BLOCKED
    assert "No solution found" in verdict.reason


def test_install_failure_is_infra():
    verdict = classify(InstallOutcome("infra", log="error: Failed to fetch"), None, None, SPEC)
    assert verdict.status is Status.INFRA


def test_adapter_timeout_is_infra():
    verdict = classify(INSTALLED, AdapterOutcome(exit_code=None, timed_out=True), _log(), SPEC)
    assert verdict.status is Status.INFRA


def test_exception_in_the_adapter_is_fail():
    report = {"ok": False, "error_type": "AttributeError", "error": "no attribute '_headers'"}
    verdict = classify(INSTALLED, AdapterOutcome(exit_code=1, report=report), _log(), SPEC)
    assert verdict.status is Status.FAIL
    assert verdict.reason == "AttributeError: no attribute '_headers'"
    assert not verdict.suspect_install


def test_missing_module_after_an_override_install_is_flagged():
    report = {"ok": False, "error_type": "ModuleNotFoundError", "error": "No module named 'urllib3'"}
    outcome = AdapterOutcome(exit_code=1, report=report)

    assert classify(INSTALLED, outcome, _log(), SPEC, used_overrides=True).suspect_install
    assert not classify(INSTALLED, outcome, _log(), SPEC, used_overrides=False).suspect_install


def test_crash_without_a_report_is_fail():
    verdict = classify(INSTALLED, AdapterOutcome(exit_code=-11), _log(), SPEC)
    assert verdict.status is Status.FAIL
    assert "-11" in verdict.reason


def test_no_spans_is_degraded():
    verdict = classify(INSTALLED, RAN, _log(), SPEC)
    assert verdict.status is Status.DEGRADED


def test_rejected_requests_do_not_count():
    verdict = classify(INSTALLED, RAN, _log(_post(status=503, spans=0)), SPEC)
    assert verdict.status is Status.DEGRADED


def test_spans_at_an_unexpected_path_are_degraded():
    verdict = classify(INSTALLED, RAN, _log(_post(path="/other")), SPEC)
    assert verdict.status is Status.DEGRADED
    assert "/v1/traces" in verdict.reason


def test_missing_header_is_degraded():
    verdict = classify(INSTALLED, RAN, _log(_post(headers=())), SPEC)
    assert verdict.status is Status.DEGRADED
    assert "authorization" in verdict.reason


def test_healthy_export_passes():
    verdict = classify(INSTALLED, RAN, _log(_post()), SPEC)
    assert verdict.status is Status.PASS
