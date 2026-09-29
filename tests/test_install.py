import pytest

from otel_canary.install import create_and_install, is_resolution_conflict, otel_requirements, parse_freeze

UV_CONFLICT = """\
  × No solution found when resolving dependencies:
  ╰─▶ Because opentelemetry-exporter-otlp-proto-http>=1.45.0 depends on opentelemetry-sdk>=1.45.0
      and arize-phoenix-otel==0.17.2 depends on opentelemetry-exporter-otlp-proto-http>=1.45.0, ...
"""


def test_detects_resolution_conflicts():
    assert is_resolution_conflict(UV_CONFLICT)
    assert not is_resolution_conflict("error: Failed to fetch: `https://pypi.org/simple/langfuse/`")


def test_parses_freeze_output():
    output = "arize-phoenix-otel==0.17.2\nOpenTelemetry-SDK==1.45.0\n-e file:///tmp/pkg\n"
    assert parse_freeze(output) == {"arize-phoenix-otel": "0.17.2", "opentelemetry-sdk": "1.45.0"}


def test_pins_the_otel_packages_for_the_transport():
    assert otel_requirements("1.45.0") == [
        "opentelemetry-api==1.45.0",
        "opentelemetry-sdk==1.45.0",
        "opentelemetry-exporter-otlp-proto-http==1.45.0",
    ]
    assert "opentelemetry-exporter-otlp-proto-grpc==1.45.0" in otel_requirements("1.45.0", "grpc")


@pytest.mark.integration
def test_versions_the_sdk_does_not_allow_are_blocked(tmp_path):
    # arize-phoenix-otel 0.17.2 requires opentelemetry-exporter-otlp-proto-http>=1.45.0.
    outcome = create_and_install(
        tmp_path, "3.12", ["arize-phoenix-otel==0.17.2", *otel_requirements("1.44.0")]
    )
    assert outcome.status == "blocked"
    assert "No solution found" in outcome.log


@pytest.mark.integration
def test_records_the_installed_versions(tmp_path):
    outcome = create_and_install(
        tmp_path, "3.12", ["arize-phoenix-otel==0.17.2", *otel_requirements("1.45.0")]
    )
    assert outcome.status == "ok"
    assert outcome.versions["arize-phoenix-otel"] == "0.17.2"
    assert outcome.versions["opentelemetry-sdk"] == "1.45.0"
