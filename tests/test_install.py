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


def test_contrib_version_follows_the_core_release():
    from otel_canary.install import contrib_version

    assert contrib_version("1.45.0") == "0.66b0"
    assert contrib_version("1.42.1") == "0.63b1"


def test_force_overrides_move_core_and_contrib_together():
    from otel_canary.install import force_overrides

    pins = force_overrides("1.45.0")
    assert "opentelemetry-sdk==1.45.0" in pins
    assert "opentelemetry-exporter-otlp-proto-grpc==1.45.0" in pins
    assert "opentelemetry-semantic-conventions==0.66b0" in pins
    assert "opentelemetry-instrumentation==0.66b0" in pins


def test_main_overrides_keep_the_transport_extra():
    from otel_canary.install import main_overrides

    lines = main_overrides("abc123", "def456")
    transport = next(line for line in lines if line.startswith("opentelemetry-exporter-http-transport"))
    assert transport.startswith("opentelemetry-exporter-http-transport[urllib3] @ git+")
    assert "@abc123#subdirectory=exporter/opentelemetry-exporter-http-transport" in transport
    assert any("opentelemetry-python-contrib.git@def456" in line for line in lines)


def test_freeze_shows_git_installs_as_commits():
    output = (
        "opentelemetry-sdk @ git+https://github.com/open-telemetry/opentelemetry-python.git"
        "@0123456789abcdef0123#subdirectory=opentelemetry-sdk\n"
    )
    assert parse_freeze(output) == {"opentelemetry-sdk": "git@0123456789ab"}
